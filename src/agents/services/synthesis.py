"""Safe placeholder-only natural-language synthesis for A5-6."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final, Protocol
from uuid import UUID

from src.agents.contracts import Citation, Recommendation, TcoResult, VehiclePitch
from src.agents.domain.claim_policy import (
    EQUIPMENT_CLAIM_PREFIXES,
    PlannedClaim,
    approved_feature_codes,
    budget_fit_note,
    feature_codes_backed_by_facts,
    plan_claims,
    reject_unbacked_feature_claims,
    reject_unstructured_claims,
)
from src.agents.domain.need_evidence import evidence_claims
from src.agents.domain.perceptual_traits import (
    TRAIT_PHRASING,
    reject_unbacked_trait_claims,
    traits_from_values,
)
from src.agents.domain.scoring import MAX_PITCHED_RECOMMENDATIONS
from src.agents.domain.standout_facts import standout_claims
from src.agents.domain.text_normalization import RAW_STRUCTURED_PATTERN
from src.agents.logging import get_agent_logger
from src.agents.prompts.feature_askable import FEATURE_LABELS
from src.agents.prompts.synthesis_prompts import build_synthesis_prompt
from src.agents.services.call_budget import CallKind, current_call_budget

# BUG THẬT phát hiện 2026-08-23 (Sếp yêu cầu điều tra "case không trả kết
# quả"): `logging.getLogger(__name__)` không gắn FileHandler của app, nên
# logger.error("bỏ pitch của xe...") bên dưới ÂM THẦM KHÔNG vào logs/app.log
# suốt từ khi module này được viết — mọi lần synthesize thất bại toàn phần,
# log không để lại dấu vết gì, buộc điều tra guardrail phải đoán mù nhiều
# vòng. Đổi sang `get_agent_logger` (cùng chuẩn mọi module agent khác) để
# log ERROR thật sự ghi ra file.
logger = get_agent_logger(__name__)

#: Mọi con số pitch được phép nêu, kèm đơn vị code tự ghép (guardrail A6-1 chỉ
#: đối chiếu SỐ với snapshot, không đối chiếu đơn vị — nên đơn vị KHÔNG giao cho LLM).
#:
#: Mở rộng 2026-08-25 (Sếp: "tính năng đề xuất quá ít, khó thuyết phục khách"):
#: `cars.csv`/`motorbikes.csv` có 28 và 27 cột thông số THẬT nhưng pitch chỉ dùng
#: sáu và năm. Công suất, mô-men, tăng tốc, dung lượng pin, công suất trụ sạc,
#: cốp gập tối đa, tải kéo là những con số tư vấn viên thật dùng để chốt khách —
#: chúng nằm sẵn trong snapshot nên guardrail verify được từng chữ số, không phải
#: dữ liệu mới cần duyệt lại.
PLACEHOLDER_UNITS: Final[dict[str, str]] = {
    "CAR_RANGE_KM": "km",
    "CAR_SEAT_COUNT": "chỗ ngồi",
    "CARGO_VOLUME_STANDARD_L": "lít",
    "CARGO_VOLUME_MAXIMUM_L": "lít",
    "FAST_CHARGE_TIME_MINUTES": "phút",
    "HOME_CHARGE_TIME_MINUTES": "phút",
    "CAR_BATTERY_CAPACITY_KWH": "kWh",
    "CAR_MOTOR_POWER_KW": "kW",
    "CAR_TORQUE_NM": "Nm",
    "CAR_MAX_SPEED_KMH": "km/h",
    "CAR_ACCELERATION_0_100_SECONDS": "giây",
    "CAR_FAST_CHARGE_POWER_KW": "kW",
    "CAR_TOWING_CAPACITY_KG": "kg",
    "MOTORBIKE_RANGE_MAX_KM": "km",
    "MOTORBIKE_MAX_LOAD_KG": "kg",
    "MOTORBIKE_MOTOR_POWER_W": "W",
    "MOTORBIKE_MAX_POWER_W": "W",
    "MOTORBIKE_TORQUE_NM": "Nm",
    "MOTORBIKE_MAX_SPEED_KMH": "km/h",
    "MOTORBIKE_BATTERY_CAPACITY_KWH": "kWh",
    "MOTORBIKE_CHARGING_TIME_MINUTES": "phút",
    "MOTORBIKE_SEAT_HEIGHT_MM": "mm",
    "STARTING_PRICE_VND": "VND",
    "TCO_TOTAL_VND": "VND",
    "BATTERY_RENT_VND_PER_MONTH": "VND/tháng",
}
#: Sắp theo độ dài giảm dần để dedupe unit dài ("VND/tháng") trước unit ngắn ("VND").
PLACEHOLDER_UNITS_BY_LENGTH: Final[tuple[str, ...]] = tuple(
    sorted(set(PLACEHOLDER_UNITS.values()), key=len, reverse=True)
)
#: Đơn vị lặp lại NGAY SAU con số khi nhãn in đậm đã kết thúc bằng chính đơn vị đó:
#: "**Số chỗ ngồi**: 5 chỗ ngồi" → "**Số chỗ ngồi**: 5".
#:
#: Chỉ khớp khi nhãn kết thúc đúng bằng đơn vị, nên "**Quãng đường mỗi lần sạc**:
#: 326 km" không bị chạm — ở đó "km" là thông tin, không phải tiếng vọng. Đây là
#: bản GỬI KHÁCH; bản đối chiếu guardrail giữ nguyên đơn vị.
_LABEL_UNIT_ECHO: Final[re.Pattern[str]] = re.compile(
    r"(\*\*[^*]*?(?:"
    + "|".join(re.escape(unit) for unit in PLACEHOLDER_UNITS_BY_LENGTH)
    + r")\*\*: )([\d.,]+) (?:"
    + "|".join(re.escape(unit) for unit in PLACEHOLDER_UNITS_BY_LENGTH)
    + r")(?![\w/])"
)
PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")
QUOTE_PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{(QUOTE_\d+)\}")
#: Phần thập phân toàn số không của một số ĐỘC LẬP: "326.00" → "326".
#:
#: `value_text` đến từ cột `NUMERIC` nên mang nguyên phần thập phân của schema, và
#: `_render_all` chèn nó VERBATIM vì guardrail A6-1 so từng ký tự với snapshot. Chỗ
#: gọn lại là bản gửi khách, không phải bản đối chiếu.
#:
#: Hai lookaround chặn việc cắt vào một số có dấu phân nhóm: trong "1.200.000.000"
#: mọi cụm ".000" đều có chữ số hoặc dấu ngay sát trước/sau, nên không cụm nào khớp.
_TRAILING_ZERO_DECIMAL: Final[re.Pattern[str]] = re.compile(r"(?<![\d.,])(\d+)\.0+(?![\d.,])")
FOOTNOTE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\s*\[\d+\]")
DIGIT_PATTERN: Final[re.Pattern[str]] = re.compile(r"\d")
MAX_SYNTHESIS_ATTEMPTS: Final[int] = 3
MAX_REQUIRED_CLAIMS: Final[int] = 3


@dataclass(frozen=True, slots=True)
class SynthesisFact:
    """One allowlisted numeric snapshot value with a source evidence trace."""

    vehicle_id: UUID
    fact_code: str
    value_text: str
    unit: str
    evidence_id: UUID
    source_record: str

    def __post_init__(self) -> None:
        if self.fact_code not in PLACEHOLDER_UNITS:
            raise ValueError(f"fact code is outside synthesis allowlist: {self.fact_code}")
        if self.unit != PLACEHOLDER_UNITS[self.fact_code]:
            raise ValueError(f"unit does not match synthesis allowlist: {self.fact_code}")
        if not self.source_record:
            raise ValueError("synthesis fact requires a source record")
        try:
            Decimal(self.value_text)
        except InvalidOperation as error:
            raise ValueError("synthesis fact value must be numeric") from error


@dataclass(frozen=True, slots=True)
class SynthesisQuote:
    """One exact brochure excerpt tied to immutable run evidence."""

    text: str
    evidence_id: UUID
    vehicle_id: UUID
    #: Đối xứng với `SynthesisFact.source_record`; thiếu nó thì citation sinh từ
    #: quote không điền được `Citation.source_record`.
    source_record: str = ""

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("synthesis quote must not be empty")


class SynthesisLlmPort(Protocol):
    """Narrow LLM capability used by this service."""

    async def synthesize(self, *, prompt: str) -> str: ...


class SynthesisDataSource(Protocol):
    """Load allowlisted facts from the immutable run snapshot and evidence rows."""

    async def load_vehicle_name(self, *, run_id: UUID, vehicle_id: UUID) -> str | None: ...

    async def load_facts(self, *, run_id: UUID, vehicle_ids: tuple[UUID, ...]) -> Sequence[SynthesisFact]: ...

    async def load_quotes(self, *, run_id: UUID, vehicle_ids: tuple[UUID, ...]) -> Sequence[SynthesisQuote]: ...


class DefaultSynthesisService:
    """Let the LLM write prose only, then render every number in deterministic code."""

    def __init__(
        self,
        *,
        llm: SynthesisLlmPort,
        source: SynthesisDataSource,
        fallback_llm: SynthesisLlmPort | None = None,
    ) -> None:
        self._llm = llm
        self._source = source
        self._fallback_llm = fallback_llm

    async def synthesize_policy(self, *, query: str, chunks: list[dict], application: bool = False) -> str:
        """Forward policy synthesis to llm adapter if supported."""
        method = getattr(self._llm, "synthesize_policy", None)
        if method is not None:
            return await method(query=query, chunks=chunks, application=application)
        return ""

    async def synthesize(
        self,
        *,
        run_id: UUID,
        recommendations: Sequence[Recommendation],
        tco: TcoResult | None,
        customer_wording: Sequence[str] = (),
        budget_min_vnd: float | None = None,
        budget_max_vnd: float | None = None,
        feature_mention_codes: Sequence[str] = (),
    ) -> Sequence[VehiclePitch]:
        """Mỗi xe một đoạn riêng: mỗi call LLM chỉ thấy facts và quotes của xe đó.

        Ngân sách đi vào đây chỉ để gắn NHÃN lệch ngân sách lên từng thẻ xe. Nó
        không lọc và không xếp hạng lại gì — việc đó đã xong ở Lớp 1 và ở scoring.
        """

        # MỘT slot cho cả LƯỢT THỬ, không phải mỗi xe một slot (quyết định A,
        # Sếp chốt 2026-08-24). Fan-out theo xe là chủ ý: mỗi call chỉ thấy facts
        # và quotes của ĐÚNG xe đó nên mô hình không gán nhầm thông số giữa các
        # xe, và một xe hỏng không kéo sập cụm. Đếm theo lần chạm provider sẽ ép
        # phải gộp lô, tức đánh đổi đúng hai tính chất ấy lấy tiền. Thứ cần chặn
        # là số LƯỢT THỬ; số xe đã bị Lớp 1 chặn từ trước.
        budget = current_call_budget()
        if budget is not None:
            budget.claim(CallKind.REQUIRED)

        ordered = _ordered_recommendations(recommendations)
        vehicle_ids = tuple(dict.fromkeys(item.vehicle_id for item in ordered))
        # Nạp MỘT lần cho cả cụm rồi chia trong bộ nhớ: gọi theo từng xe biến bốn
        # truy vấn thành mười hai, và guardrail cho retry ≤ 2 nên xấu nhất là ba sáu.
        facts = tuple(await self._source.load_facts(run_id=run_id, vehicle_ids=vehicle_ids))
        quotes = tuple(await self._source.load_quotes(run_id=run_id, vehicle_ids=vehicle_ids))
        facts_by_vehicle = _group_by_vehicle(facts)
        quotes_by_vehicle = _group_by_vehicle(quotes)
        # LIỆT KÊ và THUYẾT PHỤC là hai việc khác nhau, và chỉ việc thứ hai tốn
        # tiền. Mọi xe thoả điều kiện đều về đủ dưới dạng thẻ; chỉ những xe đứng
        # đầu mới được sinh đoạn văn. Không tách thì chi phí đi theo số xe thoả
        # — một câu hỏi rộng về xe máy điện chạm trần 20 sẽ thành sáu mươi lần
        # gọi LLM cho một lượt chat.
        pitched = ordered[:MAX_PITCHED_RECOMMENDATIONS]
        listed_only = ordered[MAX_PITCHED_RECOMMENDATIONS:]
        # Điểm mỗi xe HƠN HẲN mấy xe đứng cạnh nó trong CHÍNH lượt này.
        #
        # Tính ở đây chứ không trong `_pitch_for` vì đây là chỗ duy nhất nhìn
        # thấy cả nhóm — một câu so sánh nhất không dựng được từ dữ liệu một xe.
        # Giới hạn trong `pitched`: nhóm để so là nhóm khách ĐỌC ĐƯỢC, không phải
        # toàn bộ tập thoả điều kiện.
        standouts = standout_claims(
            {
                recommendation.vehicle_id: facts_by_vehicle.get(recommendation.vehicle_id, ())
                for recommendation in pitched
            }
        )
        results = await asyncio.gather(
            *(
                self._pitch_for(
                    recommendation=recommendation,
                    facts=facts_by_vehicle.get(recommendation.vehicle_id, ()),
                    quotes=quotes_by_vehicle.get(recommendation.vehicle_id, ()),
                    tco=tco,
                    customer_wording=customer_wording,
                    budget_min_vnd=budget_min_vnd,
                    budget_max_vnd=budget_max_vnd,
                    feature_mention_codes=feature_mention_codes,
                    standout=standouts.get(recommendation.vehicle_id),
                )
                for recommendation in pitched
            ),
            # BẮT BUỘC: thiếu cờ này thì một xe raise sẽ kéo sập cả cụm, đúng
            # hành vi mà việc tách pitch theo xe đang muốn bỏ.
            return_exceptions=True,
        )
        # Lỗi bị nuốt để các xe khác vẫn về, nhưng không được nuốt trong im lặng:
        # thiếu dòng log này thì một lỗi code (TypeError/AttributeError/...) làm
        # RỚT hết pitch mà không để lại dấu vết nào trong log.
        for recommendation, result in zip(pitched, results, strict=True):
            if isinstance(result, BaseException):
                logger.error(
                    "synthesis: bỏ pitch của xe %s do lỗi %s: %s",
                    recommendation.vehicle_id,
                    type(result).__name__,
                    result,
                    exc_info=result,
                )
        cards = tuple(
            _card_only_pitch(
                recommendation=recommendation,
                facts=facts_by_vehicle.get(recommendation.vehicle_id, ()),
            )
            for recommendation in listed_only
        )
        return tuple(item for item in results if isinstance(item, VehiclePitch)) + cards

    async def _pitch_for(
        self,
        *,
        recommendation: Recommendation,
        facts: tuple[SynthesisFact, ...],
        quotes: tuple[SynthesisQuote, ...],
        tco: TcoResult | None,
        customer_wording: Sequence[str],
        budget_min_vnd: float | None = None,
        budget_max_vnd: float | None = None,
        feature_mention_codes: Sequence[str] = (),
        standout: PlannedClaim | None = None,
    ) -> VehiclePitch:
        vehicle_id = recommendation.vehicle_id
        # TCO tính cho đúng một xe; với xe khác nó không phải dữ liệu của xe này.
        vehicle_tco = tco if tco is not None and tco.vehicle_id == vehicle_id else None
        fact_by_code = _validate_facts(facts, vehicle_id, vehicle_tco)
        quote_by_key = {f"QUOTE_{index}": quote for index, quote in enumerate(quotes, start=1)}
        vehicle_name = recommendation.display_name or "mẫu xe này"
        claims = plan_claims(recommendation.reasons)
        claim_by_key = {claim.placeholder: claim for claim in claims}
        # Nới claim plan bằng chính snapshot của lượt.
        #
        # Đo trên prod 24h (2026-08-28): 36/106 lượt rơi bản dựng tay, và **36/36
        # lần** là `suitability statement must use an approved claim
        # placeholder`. `plan_claims` chỉ đọc lý do chấm điểm, mà lý do không phủ
        # hết những gì xe THẬT SỰ có — nên mô hình với tay tìm claim chưa duyệt.
        #
        # `setdefault` chứ không ghi đè: claim sinh từ lý do chấm điểm mang đúng
        # ngữ cảnh của lượt (vượt/dưới ngân sách, khách vừa xác nhận tính năng),
        # còn claim mở thêm ở đây chỉ là câu chung. Ai có trước thì giữ.
        for extra in evidence_claims(fact_by_code):
            claim_by_key.setdefault(extra.placeholder, extra)
        # Câu "hơn hẳn phần còn lại" là claim BÌNH THƯỜNG, không phải đường tắt:
        # nó vào cùng một bảng, nên vẫn qua `_validate_draft`, vẫn được render
        # tất định, và bản dựng tay dự phòng cũng dùng được nó.
        if standout is not None:
            claim_by_key[standout.placeholder] = standout
        if not claim_by_key:
            return _card_only_pitch(recommendation=recommendation, facts=facts)
        mandatory_feature_claims = tuple(
            f"CLAIM_{code.upper()}" for code in feature_mention_codes if f"CLAIM_{code.upper()}" in claim_by_key
        )[:MAX_REQUIRED_CLAIMS]
        required_claims = tuple(
            dict.fromkeys(((standout.placeholder,) if standout is not None else ()) + mandatory_feature_claims)
        )[:MAX_REQUIRED_CLAIMS]
        # Bug thật 2026-08-21 (Sếp báo): chỉ đưa nhãn tính năng vào ngữ cảnh
        # LLM nếu xe NÀY thật sự có claim tương ứng — không thì LLM cố nhắc
        # tới một tính năng không có căn cứ, bị chặn bởi
        # `reject_unstructured_claims` liên tục, hết retry thì handoff.
        backed_feature_wording = [
            FEATURE_LABELS[code]
            for code in feature_mention_codes
            if code in FEATURE_LABELS and f"CLAIM_{code.upper()}" in claim_by_key
        ]
        full_customer_wording = tuple(dict.fromkeys((*customer_wording, *backed_feature_wording)))
        prompt = build_synthesis_prompt(
            vehicle_name=vehicle_name,
            available_claims=tuple((claim.placeholder, claim.text) for claim in claim_by_key.values()),
            available_placeholders=tuple(sorted(fact_by_code)),
            available_quotes=tuple((key, quote_by_key[key].text) for key in sorted(quote_by_key)),
            customer_wording=full_customer_wording,
            available_traits=tuple(
                TRAIT_PHRASING[trait]
                for trait in sorted(traits_from_values({code: fact.value_text for code, fact in fact_by_code.items()}))
                if trait in TRAIT_PHRASING
            ),
            required_claims=required_claims,
            equipment_claims=tuple(
                placeholder
                for placeholder, claim in claim_by_key.items()
                if claim.text.startswith(EQUIPMENT_CLAIM_PREFIXES)
            ),
        )
        # Tên xe là dữ liệu catalog, KHÔNG phải số LLM bịa: "VF 8" phải đi vào
        # prompt nguyên vẹn. Kiểm chữ số trên phần còn lại.
        #
        # BUG THẬT phát hiện 2026-08-23 (Sếp yêu cầu điều tra "case không trả
        # kết quả"): `available_quotes` chèn NGUYÊN VĂN nội dung DOC_EXCERPT
        # (kèm số thật, vd "dài 3.190 mm") vào prompt để LLM biết trích dẫn đó
        # nói gì — số đó không nằm trong `{placeholder}` nên bị chính check
        # này coi là "số lạ" và raise ngay LẬP TỨC, trước khi gọi LLM. Xảy ra
        # với MỌI xe có DOC_EXCERPT (rất phổ biến, không liên quan mục đích
        # khách) → cả 3 pitch cùng vỡ → draft_answer rỗng → guardrail báo
        # GUARDRAIL_CONFIGURATION_ERROR, khách nhận "chuyển tư vấn viên" giả.
        # Che nguyên văn từng quote (như đã che vehicle_name) trước khi kiểm —
        # số trong quote là bằng chứng THẬT cho LLM tham khảo, không phải số
        # LLM có thể tự viết ra.
        digit_check_text = prompt.replace(vehicle_name, "")
        for quote in quote_by_key.values():
            digit_check_text = digit_check_text.replace(quote.text, "")
        _reject_digits_outside_placeholders(digit_check_text)
        if self._fallback_llm is None:
            # BUG THẬT trên prod 2026-08-26: nhánh này KHÔNG có lưới đỡ, khác
            # hẳn nhánh có `_fallback_llm` ngay dưới. LLM viết "sạc nhanh" cho
            # một xe không có căn cứ FAST_CHARGING → `_validate_draft` raise →
            # `_pitch_for` ném lên `asyncio.gather(return_exceptions=True)` →
            # xe BIẾN MẤT. Lượt chỉ có một xe thoả ngân sách thì `draft_answer`
            # rỗng và guardrail báo GUARDRAIL_CONFIGURATION_ERROR, khách nhận
            # câu "đã chuyển tư vấn viên" GIẢ. Đo trên 8 giờ log prod: 7 lượt
            # có đúng 1 xe thì 3 lượt chết theo đường này (43%); lượt nhiều xe
            # thì xe rơi trong im lặng, tệ theo kiểu khó thấy hơn.
            #
            # Bản dựng tay không cần LLM và luôn qua được `_validate_draft` (nó
            # chỉ ghép placeholder từ chính snapshot), nên xe mất chỗ thuyết
            # phục chứ không mất khỏi câu trả lời.
            outcome = "llm"
            try:
                draft = await _synthesize_with_retry(
                    self._llm,
                    prompt=prompt,
                    vehicle_id=vehicle_id,
                    vehicle_name=vehicle_name,
                    fact_by_code=fact_by_code,
                    claim_by_key=claim_by_key,
                    quote_by_key=quote_by_key,
                    required_claims=required_claims,
                )
            except Exception as error:  # noqa: BLE001
                outcome = "fallback"
                # `Exception` chứ không `ValueError`.
                #
                # Bản trước cố ý thả lỗi transport (timeout, lỗi nhà cung cấp)
                # lên `asyncio.gather(return_exceptions=True)` "để lỗi hạ tầng
                # lan nhanh". Thứ lan nhanh thật ra là một chiếc xe rơi khỏi bản
                # đề xuất TRONG IM LẶNG — mà bản dựng tay ngay dưới không cần
                # LLM và luôn hợp lệ. Không có lý do gì để một cú timeout xoá
                # một chiếc xe khách đủ điều kiện mua.
                #
                # Lưới này KHÔNG che được lỗi dữ liệu: `_validate_draft` chạy
                # trên chính bản dựng tay ngay sau đây, và nó ném ra ngoài.
                logger.warning(
                    "synthesis: LLM khong viet duoc ban hop le cho xe %s (%s), dung ban dung tay: %s",
                    vehicle_id,
                    type(error).__name__,
                    error,
                )
                draft = _deterministic_fallback_draft(
                    vehicle_name=vehicle_name,
                    fact_by_code=fact_by_code,
                    claim_by_key=claim_by_key,
                    quote_by_key=quote_by_key,
                )
                if not draft.strip():
                    # Không claim nào dựng được câu → trả thẻ số liệu thay vì bản
                    # nháp rỗng; nháp rỗng làm guardrail báo
                    # GUARDRAIL_CONFIGURATION_ERROR và đẩy tư vấn viên (prod
                    # 2026-08-26..28: 5 lần, đều sau "Ô tô điện").
                    return _card_only_pitch(recommendation=recommendation, facts=facts)
                _validate_draft(draft, fact_by_code, claim_by_key, vehicle_name, required_claims)
                _validate_quotes(draft, quote_by_key)
        else:
            # `Exception` chứ không `ValueError` — cùng lý do với nhánh trên.
            # Thêm một lẽ nữa ở đây: bộ viết THỨ NHẤT timeout thì bộ thứ hai vẫn
            # đáng thử, mà `except ValueError` để lỗi đó thoát ngay khỏi vòng lặp
            # và bộ dự phòng không bao giờ được gọi.
            outcome = "llm"
            last_error: Exception | None = None
            for writer in (self._llm, self._fallback_llm):
                try:
                    draft = await _synthesize_with_retry(
                        writer,
                        prompt=prompt,
                        vehicle_id=vehicle_id,
                        vehicle_name=vehicle_name,
                        fact_by_code=fact_by_code,
                        claim_by_key=claim_by_key,
                        quote_by_key=quote_by_key,
                        required_claims=required_claims,
                        max_attempts=1,
                    )
                    break
                except Exception as error:  # noqa: BLE001
                    last_error = error
            else:
                outcome = "fallback"
                assert last_error is not None
                # Nhánh này từng NUỐT lỗi suốt từ đầu — đo trên prod 2026-08-27:
                # log đếm được 0 lần "khong viet duoc ban hop le", trong khi thẻ
                # xe khách vừa nhận có đúng bố cục bản dự phòng cũ dạng bảng spec.
                #
                # Tức là bản viết thật hỏng, khách nhận về một bảng thông số, và
                # KHÔNG AI biết vì sao. Site kia (dòng ~430) đã log; site này thì
                # không — cùng một sự cố, một nửa nhìn thấy được.
                logger.warning(
                    "synthesis: CA HAI bo viet deu hong cho xe %s (%s), dung ban dung tay: %s",
                    vehicle_id,
                    type(last_error).__name__,
                    last_error,
                )
                draft = _deterministic_fallback_draft(
                    vehicle_name=vehicle_name,
                    fact_by_code=fact_by_code,
                    claim_by_key=claim_by_key,
                    quote_by_key=quote_by_key,
                )
                if not draft.strip():
                    # Không claim nào dựng được câu → trả thẻ số liệu thay vì bản
                    # nháp rỗng; nháp rỗng làm guardrail báo
                    # GUARDRAIL_CONFIGURATION_ERROR và đẩy tư vấn viên (prod
                    # 2026-08-26..28: 5 lần, đều sau "Ô tô điện").
                    return _card_only_pitch(recommendation=recommendation, facts=facts)
                _validate_draft(draft, fact_by_code, claim_by_key, vehicle_name, required_claims)
                _validate_quotes(draft, quote_by_key)
        # MỘT dòng cho MỖI xe, ở điểm thoát duy nhất. Đây là mẫu số — thiếu nó
        # thì mọi tỉ lệ về sau đều là đoán, kể cả tỉ lệ dùng làm ngưỡng phát hành.
        logger.info(
            "%s vehicle=%s outcome=%s claims=%d required=%d quotes=%d",
            SYNTHESIS_OUTCOME_EVENT,
            vehicle_id,
            outcome,
            len(claim_by_key),
            len(required_claims),
            len(quote_by_key),
        )
        pitch, citations = _render_all(
            draft,
            fact_by_code,
            quote_by_key,
            claim_by_key,
        )
        price = fact_by_code.get("STARTING_PRICE_VND")
        # Nhãn lệch ngân sách gắn SAU khi render, và đó là điều kiện an toàn: nó
        # không đi qua `_validate_draft` (nên không cần là placeholder) và nó không
        # chứa chữ số (nên guardrail A6-1 vẫn đối chiếu được từng số như trước).
        note = budget_fit_note(
            price_vnd=_as_decimal(price.value_text if price is not None else None),
            budget_min_vnd=_as_decimal(budget_min_vnd),
            budget_max_vnd=_as_decimal(budget_max_vnd),
        )
        return VehiclePitch(
            vehicle_id=vehicle_id,
            rank=recommendation.rank,
            display_name=recommendation.display_name,
            # Nhãn ngân sách là một KHỐI riêng, không dính vào câu mở đầu: nó là
            # cảnh báo về tiền, và dính nó vào giữa một câu giới thiệu là chỗ dễ
            # đọc lướt qua nhất.
            # Chú thích lệch ngân sách đứng SAU câu chào xe, không đứng một mình
            # trên đầu như một dòng lạc (đo 2026-08-28: khách đọc thấy "(thấp hơn
            # ngân sách một chút, tiết kiệm hơn)" rồi mới tới tên xe).
            pitch=f"{pitch} {note}" if note else pitch,
            citations=citations,
            starting_price_vnd=price.value_text if price is not None else None,
        )


def _card_only_pitch(*, recommendation: Recommendation, facts: Sequence[SynthesisFact]) -> VehiclePitch:
    """Thẻ xe KHÔNG có đoạn thuyết phục — dựng thuần từ snapshot, 0 lần gọi LLM.

    `citations` cố ý để rỗng: không gọi mô hình thì không có câu nào cần dẫn
    chứng, và gắn dẫn chứng vào một thẻ không có chữ nào là dẫn chứng cho hư không.
    """

    price = next((item for item in facts if item.fact_code == "STARTING_PRICE_VND"), None)
    return VehiclePitch(
        vehicle_id=recommendation.vehicle_id,
        rank=recommendation.rank,
        display_name=recommendation.display_name,
        pitch="",
        citations=(),
        starting_price_vnd=price.value_text if price is not None else None,
    )


def _as_decimal(value: object) -> Decimal | None:
    """`Decimal` khi đọc được, `None` khi không — số tiền hỏng không làm chết lượt."""

    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _ordered_recommendations(
    recommendations: Sequence[Recommendation],
) -> tuple[Recommendation, ...]:
    if not recommendations:
        raise ValueError("synthesis requires at least one recommendation")
    ranks = [item.rank for item in recommendations]
    if len(ranks) != len(set(ranks)):
        raise ValueError("recommendation ranks must be unique")
    return tuple(sorted(recommendations, key=lambda item: item.rank))


def _group_by_vehicle(items):
    """Chia facts/quotes đã nạp một lần về từng xe, giữ nguyên thứ tự nạp."""

    grouped: dict[UUID, list] = {}
    for item in items:
        grouped.setdefault(item.vehicle_id, []).append(item)
    return {vehicle_id: tuple(values) for vehicle_id, values in grouped.items()}


def _validate_facts(
    facts: tuple[SynthesisFact, ...], vehicle_id: UUID, tco: TcoResult | None
) -> dict[str, SynthesisFact]:
    if any(fact.vehicle_id != vehicle_id for fact in facts):
        raise ValueError("synthesis fact is outside the top recommendation")
    by_code = {fact.fact_code: fact for fact in facts}
    if len(by_code) != len(facts):
        raise ValueError("synthesis facts must have unique fact codes")
    if tco is not None and tco.total_vnd is not None:
        fact = by_code.get("TCO_TOTAL_VND")
        if tco.vehicle_id != vehicle_id or fact is None or Decimal(fact.value_text) != tco.total_vnd:
            raise ValueError("TCO_TOTAL_VND does not match the supplied TCO result")
    else:
        by_code.pop("TCO_TOTAL_VND", None)
    return by_code


#: Trần số claim trong một bản dựng tay.
#:
#: Bản cũ cắt cứng ở 2. Xe có 9 tính năng đã xác minh vẫn chỉ được nói hai điều —
#: đo trên prod 2026-08-28, khách nhận một câu không có con số nào.
#:
#: Nhưng KHÔNG mở vô hạn: bốn claim cùng một chiều lợi ích thì đọc như đọc
#: catalog, không như một lời tư vấn. Bốn là chỗ dừng — đủ để nói ngân sách, hai
#: lợi ích khớp nhu cầu, và một thông số.
MAX_FALLBACK_CLAIMS: Final[int] = 4

#: Nhãn dòng log KẾT CỤC — một dòng mỗi xe, ghi ở mức `INFO`.
#:
#: Đây là MẪU SỐ của mọi tỉ lệ về sau. Trước bản này `synthesis` chỉ ghi log khi
#: có vấn đề, nên đếm được số lần hỏng mà không đếm được tổng — và bản đo
#: 2026-08-28 đã chia 36 cho 106 dòng CẢNH BÁO rồi gọi đó là 34%. Sai mẫu số.
SYNTHESIS_OUTCOME_EVENT: Final[str] = "synthesis_outcome"


def select_fallback_claims(claim_by_key: Mapping[str, PlannedClaim]) -> tuple[str, ...]:
    """Chọn tối đa `MAX_FALLBACK_CLAIMS` claim, mỗi CHIỀU LỢI ÍCH đúng một lần.

    Khử trùng theo `PlannedClaim.slot`, không theo placeholder: hai claim khác
    tên nhưng cùng `slot` là hai cách nói một điều, và nói hai lần không thuyết
    phục hơn — chỉ dài hơn.

    `CLAIM_STANDOUT` luôn đứng đầu khi có: nó là điều đáng nói nhất của chiếc xe,
    rơi khỏi danh sách là mất đúng câu mở hay nhất.

    Trả rỗng khi không có claim nào — bịa ra một câu không có căn cứ còn tệ hơn
    im lặng.
    """

    ordered = sorted(claim_by_key, key=lambda key: key != "CLAIM_STANDOUT")
    chosen: list[str] = []
    seen_slots: set[str] = set()
    for key in ordered:
        slot = claim_by_key[key].slot
        if slot in seen_slots:
            continue
        seen_slots.add(slot)
        chosen.append(key)
        if len(chosen) == MAX_FALLBACK_CLAIMS:
            break
    return tuple(chosen)


def _tidy_number(value_text: str) -> str:
    """ "82.00" → "82", "310.50" → "310.5".

    Số trong snapshot lưu dạng Decimal chuỗi, in nguyên ra khách đọc thành
    "82.00 km" (đo 2026-08-28). Chỉ cắt số 0 thừa sau dấu chấm — không đổi giá
    trị, guardrail đối chiếu số vẫn khớp.
    """

    text = str(value_text).strip()
    if re.fullmatch(r"-?\d+\.\d+", text):
        text = text.rstrip("0").rstrip(".")
    return text


def _deterministic_fallback_draft(
    *,
    vehicle_name: str,
    fact_by_code: dict[str, SynthesisFact],
    claim_by_key: dict[str, PlannedClaim],
    quote_by_key: dict[str, SynthesisQuote],
) -> str:
    """Build safe prose solely from claims approved for this recommendation."""

    del fact_by_code
    selected_claims = list(select_fallback_claims(claim_by_key))
    if not selected_claims:
        return ""
    # Claim "thuộc đúng dòng xe" chỉ là nhiễu khi đã có lý do thật — bỏ khi còn
    # claim khác. Và KHÔNG xâu chuỗi "và … và … và": câu đầu một lý do mạnh, các
    # lý do còn lại gom vào câu thứ hai (đo 2026-08-28: mọi xe cùng một câu bốn
    # vế "và").
    if len(selected_claims) > 1:
        selected_claims = [key for key in selected_claims if key != "CLAIM_VEHICLE_TYPE"] or selected_claims
    head, *rest = [f"{{{key}}}" for key in selected_claims[:3]]
    sentences = [f"{vehicle_name} {head}."]
    if rest:
        tail = rest[0] if len(rest) == 1 else f"{', '.join(rest[:-1])} và {rest[-1]}"
        sentences.append(f"Mẫu này còn {tail}.")
    quote_key = next(iter(quote_by_key), None)
    if quote_key is not None:
        sentences.append(f"Tài liệu mô tả: {{{quote_key}}}.")
    return " ".join(sentences)


def _validate_draft(
    draft: str,
    fact_by_code: dict[str, SynthesisFact],
    claim_by_key: dict[str, PlannedClaim],
    vehicle_name: str,
    required_claims: tuple[str, ...] = (),
) -> tuple[str, ...]:
    if not draft.strip():
        raise ValueError("LLM synthesis output must not be empty")
    _reject_digits_outside_placeholders(_mask_vehicle_name(draft, vehicle_name))
    placeholders = tuple(PLACEHOLDER_PATTERN.findall(draft))
    draft_without_placeholders = PLACEHOLDER_PATTERN.sub("", draft)
    if "{" in draft_without_placeholders or "}" in draft_without_placeholders:
        raise ValueError("invalid placeholder syntax")
    fact_placeholders = tuple(code for code in placeholders if not code.startswith(("QUOTE_", "CLAIM_")))
    claim_placeholders = tuple(code for code in placeholders if code.startswith("CLAIM_"))
    unknown = set(fact_placeholders) - set(PLACEHOLDER_UNITS)
    if unknown:
        raise ValueError("placeholder is outside synthesis allowlist")
    unavailable = set(fact_placeholders) - set(fact_by_code)
    if unavailable:
        raise ValueError("placeholder is absent from the run snapshot")
    unavailable_claims = set(claim_placeholders) - set(claim_by_key)
    if unavailable_claims:
        raise ValueError("claim placeholder is absent from the approved claim plan")
    if RAW_STRUCTURED_PATTERN.search(draft_without_placeholders):
        raise ValueError("structured token is forbidden in synthesis output")
    reject_unstructured_claims(draft_without_placeholders)
    # Tính năng khẳng định trong VĂN XUÔI mà xe không có căn cứ (Sếp 2026-08-26:
    # pitch nói VF 8 "thiết kế nhỏ gọn" trong khi cờ COMPACT_SIZE chỉ gắn VF 2/VF 3).
    #
    # Mã đã duyệt có HAI nguồn, không phải một:
    #
    # 1. claim plan — tính năng khách nhắc, đã qua luật chấm điểm;
    # 2. snapshot — tính năng mà chính thông số của lượt chứng minh.
    #
    # Thiếu nguồn 2 là bug prod 2026-08-26: 32/32 pitch bị vứt vì câu "sạc nhanh
    # trong {FAST_CHARGE_TIME_MINUTES} phút" — số thật, xe thật, nhưng khách
    # không nhắc sạc nhanh nên claim plan rỗng chỗ đó. Xem
    # `claim_policy._FACT_BACKED_FEATURE_CODES`.
    reject_unbacked_feature_claims(
        draft_without_placeholders,
        approved_feature_codes=(approved_feature_codes(claim_by_key) | feature_codes_backed_by_facts(fact_by_code)),
    )
    # Cảm quan ("mạnh mẽ", "cốp rộng", "chở khoẻ") — cùng bài toán, khác căn cứ:
    # tính năng dựa vào CỜ, cảm quan dựa vào SỐ. Sếp 2026-08-26: chặn thẳng những
    # cụm này là thô, nó giết cả câu đúng — VF 9 công suất 300 kW thì "vận hành
    # mạnh mẽ" là sự thật. Thông số đã nằm sẵn trong snapshot của lượt này nên
    # không phải nới luồng dữ liệu, chỉ đọc lại cái đã có.
    reject_unbacked_trait_claims(
        draft_without_placeholders,
        approved_traits=traits_from_values({code: fact.value_text for code, fact in fact_by_code.items()}),
    )
    # Câu phân biệt xe này với mấy xe bên cạnh: BỎ QUA là bản nháp hỏng.
    #
    # Cùng cơ chế với `_validate_quotes` — trích dẫn bắt buộc phải được dùng.
    # Không có luật này thì lời dặn trong prompt chỉ là lời khuyên, và đo trên
    # prod cho thấy mô hình nhặt mấy câu chung rồi thôi: hai thẻ xe cạnh nhau ra
    # đúng một đoạn văn như nhau.
    missing_claims = set(required_claims) - set(placeholders)
    if missing_claims:
        raise ValueError(f"draft must use mandatory claims: {sorted(missing_claims)}")
    return placeholders


def _reject_digits_outside_placeholders(text: str) -> None:
    # QUOTE_1 carries an allowed placeholder index, not user-visible numeric content.
    without_placeholders = PLACEHOLDER_PATTERN.sub("", text)
    if DIGIT_PATTERN.search(without_placeholders):
        raise ValueError("digit is forbidden outside synthesis placeholders")


def _mask_vehicle_name(text: str, vehicle_name: str) -> str:
    """Xoá nguyên cụm tên xe (VF 3, VF 8...) trước khi kiểm chữ số.

    Chỉ xoá khi cả cụm xuất hiện (token nối bằng khoảng trắng linh hoạt), không
    xoá token rời: tên "VF 8" phải che đúng "VF 8", không che số bịa "8 người".
    """

    tokens = re.findall(r"\S+", vehicle_name)
    if not tokens or not any(re.search(r"\d", token) for token in tokens):
        return text
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    return re.sub(rf"(?<!\w){pattern}(?!\w)", "", text)


def _validate_quotes(draft: str, quote_by_key: dict[str, SynthesisQuote]) -> None:
    """Reject quote placeholders that are not backed by this run's evidence."""

    matches = tuple(QUOTE_PLACEHOLDER_PATTERN.finditer(draft))
    if quote_by_key and not matches:
        raise ValueError("draft must use at least one evidence quote placeholder")
    for match in matches:
        if match.group(1) not in quote_by_key:
            raise ValueError(f"draft cites an unknown quote placeholder: {match.group(1)}")


def _render_all(
    draft: str,
    fact_by_code: dict[str, SynthesisFact],
    quote_by_key: dict[str, SynthesisQuote],
    claim_by_key: dict[str, PlannedClaim] | None = None,
) -> tuple[str, tuple[Citation, ...]]:
    """Thay mọi placeholder trong MỘT lượt, đánh số dẫn chứng theo thứ tự xuất hiện.

    Một lượt chứ không phải hai: fact và quote dùng chung bộ đếm, hai bộ đếm độc
    lập sẽ đẻ ra hai cái `[1]` trong cùng một đoạn văn.

    Text giữ footnote `[n]` làm marker: guardrail A6-1 rewrite nó thành
    `[evidence_id:UUID]` để đối chiếu từng số với snapshot. Bản gửi khách được
    làm sạch ở `client_pitch_text`, không phải ở đây.

    Đơn vị do code ghép, không giao cho LLM: guardrail chỉ đối chiếu SỐ nên nó
    không bắt được khi LLM quên hoặc viết sai đơn vị.
    """

    citations: list[Citation] = []
    index_by_evidence: dict[UUID, int] = {}
    claims = claim_by_key or {}

    def number_of(evidence_id: UUID, source_record: str) -> int:
        existing = index_by_evidence.get(evidence_id)
        if existing is not None:
            return existing
        index = len(index_by_evidence) + 1
        index_by_evidence[evidence_id] = index
        citations.append(Citation(index=index, evidence_id=evidence_id, source_record=source_record))
        return index

    def replace(match: re.Match[str]) -> str:
        code = match.group(1)
        claim = claims.get(code)
        if claim is not None:
            return claim.text
        quote = quote_by_key.get(code)
        if quote is not None:
            return f'"{quote.text}" [{number_of(quote.evidence_id, quote.source_record)}]'
        fact = fact_by_code[code]
        index = number_of(fact.evidence_id, fact.source_record)
        return f"{_tidy_number(fact.value_text)} {fact.unit} [{index}]"

    return PLACEHOLDER_PATTERN.sub(replace, draft), tuple(citations)


def client_pitch_text(text: str) -> str:
    """Bản pitch gửi khách: bỏ footnote `[n]` và gộp đơn vị lặp liền kề.

    `_render_all` giữ `[n]` cho guardrail A6-1; bản khách thấy phải sạch marker
    đó. LLM đôi khi lặp đơn vị sau placeholder ("{CAR_SEAT_COUNT} chỗ ngồi" →
    "5 chỗ ngồi [1] chỗ ngồi"); sau khi bỏ marker, dedupe liền kề trả "5 chỗ ngồi".

    Cũng gọn phần thập phân rỗng: "326.00 km" là cách cột `NUMERIC` lưu, không phải
    cách một tư vấn viên nói. Xem `_TRAILING_ZERO_DECIMAL`.
    """

    cleaned = FOOTNOTE_PATTERN.sub("", text)
    for unit in PLACEHOLDER_UNITS_BY_LENGTH:
        cleaned = cleaned.replace(f"{unit} {unit}", unit)
    cleaned = _LABEL_UNIT_ECHO.sub(r"\1\2", cleaned)
    return _TRAILING_ZERO_DECIMAL.sub(r"\1", cleaned)


async def _synthesize_with_retry(
    llm: SynthesisLlmPort,
    *,
    prompt: str,
    vehicle_id: UUID,
    vehicle_name: str,
    fact_by_code: dict[str, SynthesisFact],
    claim_by_key: dict[str, PlannedClaim],
    quote_by_key: dict[str, SynthesisQuote],
    required_claims: tuple[str, ...] = (),
    max_attempts: int = MAX_SYNTHESIS_ATTEMPTS,
) -> str:
    """Retry khi LLM vi phạm ràng buộc prompt (chữ số/structured token).

    LLM đôi khi viết chữ số ngoài placeholder dù prompt cấm; nếu rớt hết pitch
    thì draft rỗng và guardrail báo cấu hình sai → handoff. Retry cùng prompt
    cho LLM cơ hội tuân thủ. Không retry lỗi transport (timeout/...) để lỗi hạ
    tầng lan nhanh qua `return_exceptions` của caller.
    """

    for attempt in range(1, max_attempts + 1):
        draft = await llm.synthesize(prompt=prompt)
        try:
            _validate_draft(draft, fact_by_code, claim_by_key, vehicle_name, required_claims)
            _validate_quotes(draft, quote_by_key)
            return draft
        except ValueError:
            if attempt == max_attempts:
                # Log BẢN BỊ LOẠI ở lần cuối, không chỉ ở các lần giữa. Thiếu vế
                # này thì lượt rơi xuống bản dự phòng mà không ai biết mô hình đã
                # viết gì — chỉ biết "có lỗi". Sếp bắt trên prod 2026-08-27: thẻ
                # VF 5 ra một bảng thông số thay vì lời tư vấn, và log không đủ
                # để nói vì sao.
                logger.warning(
                    "synthesis: ban bi loai o lan cuoi, xe %s: %r",
                    vehicle_id,
                    # `str(...)` chứ không cắt thẳng: bộ viết trong test là một
                    # double, và cắt lát một object không hỗ trợ `__getitem__` ném
                    # `TypeError` — lỗi đó THOÁT khỏi `except ValueError` và làm
                    # rớt pitch theo một đường hoàn toàn khác. Một dòng log không
                    # được phép đổi luồng lỗi.
                    str(draft)[:400],
                )
                raise
            logger.warning(
                "synthesis: LLM vi phạm ràng buộc prompt, thử lại xe %s (lần %s): %r",
                vehicle_id,
                attempt,
                draft[:300],
            )
    raise AssertionError("unreachable")
