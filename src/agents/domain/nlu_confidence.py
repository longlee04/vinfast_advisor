"""[Lớp 3 + Lớp 4] Phân loại ý định có căn cứ, rồi định tuyến theo confidence.

**Lớp 3 — có căn cứ nghĩa là gì.** Bộ phân loại này không đọc câu chữ tự do: nó
chỉ cộng điểm từ những entity mà Lớp 2 đã trích được, và mỗi kết luận đều mang
theo danh sách entity đã dẫn tới nó (`evidence`). Nhờ vậy một nhãn sai luôn truy
được về đúng entity gây ra nó, thay vì phải đoán mô hình đã "nghĩ" gì.

`intent_hint` là GỢI Ý, không phải nhãn cuối cùng. Nguồn sự thật duy nhất của
`state["intents"]` vẫn là `domain/intent_reconciliation.reconcile_intents`, chạy
sau `extract_slots`. Hai bộ cùng ghi một field là cách chắc chắn nhất để chúng
lệch nhau âm thầm ở các câu lai (A4-6) mà không test nào bắt được.

**Ưu tiên slot đang chờ (tương thích ngược A7-10).** Khi phiên đang chờ khách trả
lời một slot, mọi câu ngắn phải được đọc như câu trả lời cho slot đó TRƯỚC. Ở đây
điều đó được thực hiện bằng cách trả confidence tuyệt đối và tier `AUTO` — tức
Lớp 4 không được phép chen một câu hỏi xác nhận nào vào giữa. Cơ chế A7-10 ở
`services/pending_slot.py` giữ nguyên quyền quyết định.

**Lớp 4 — định tuyến.** Ba mức, và ranh giới giữa chúng đọc được từ config chứ
không nằm trong logic.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from src.agents.domain.entity_catalog import EntityCategory
from src.agents.domain.fuzzy_match import EntityMatch, accepted_only, all_of, best_of
from src.agents.domain.values import Intent, SlotName, SlotValue, is_declined
from src.agents.domain.vehicle_comparison import (
    MIN_COMPARISON_VEHICLES,
    has_comparison_cue,
)

# ── Trọng số tính điểm ý định ─────────────────────────────────────────────────
#
# [GIẢ ĐỊNH] Toàn bộ trọng số dưới đây là phỏng đoán khởi đầu, cùng tinh thần với
# `domain/quote_risk.py`: phải tinh chỉnh bằng log hội thoại thật. Chúng nằm
# thành hằng số có tên để đọc log xong là biết chỉnh số nào.

#: Có TÊN MẪU xe là bằng chứng mạnh nhất cho `CATALOG_LOOKUP` — đó đúng là định
#: nghĩa của intent này ở `domain/values.Intent`.
WEIGHT_VEHICLE: Final[float] = 0.60
#: Hỏi một thuộc tính cụ thể củng cố thêm, nhưng một mình nó không đủ: "màu gì"
#: mà không có tên xe thì chưa biết hỏi màu của xe nào.
WEIGHT_ATTRIBUTE: Final[float] = 0.25
#: Từ khoá intent — tín hiệu trực tiếp nhưng dễ trùng lặp giữa các nhánh.
WEIGHT_INTENT_KEYWORD: Final[float] = 0.40

#: [COMPARE_VEHICLES] Hai tên mẫu xe TRONG CÙNG một câu là bằng chứng riêng của
#: ý so sánh, và nó mạnh hơn bằng chứng của tra cứu: một câu nêu hai xe mà chỉ
#: trả bảng của một xe là bỏ mất nửa câu hỏi. Chỉ cộng khi ĐỦ
#: `MIN_COMPARISON_VEHICLES` xe — từ khoá "so sánh" đứng một mình chưa nói được
#: so sánh cái gì với cái gì.
WEIGHT_COMPARE_MULTI_VEHICLE: Final[float] = 0.55
#: Câu đã đủ căn cứ so sánh thì `CATALOG_LOOKUP` phải nhường: hai nhãn cùng đứng
#: đầu bảng điểm sẽ để `intent_hint` lật qua lật lại theo sai số điểm khớp.
LOOKUP_PENALTY_WITH_COMPARISON: Final[float] = 0.50

#: [A4-7] Tên MẪU xe cụ thể hơn tên LOẠI xe. "VF 5 với các ô tô khác thì sao"
#: phải ra bảng của VF 5. Trừ điểm `CATALOG_BROWSE` khi câu có tên mẫu, giữ đúng
#: thứ tự ưu tiên mà `nodes/route_intent` đang áp dụng.
BROWSE_PENALTY_WITH_VEHICLE: Final[float] = 0.50

# ── Trọng số tính confidence tổng ─────────────────────────────────────────────
#: Chất lượng khớp của entity mạnh nhất.
WEIGHT_EVIDENCE: Final[float] = 0.50
#: Mức được nhiều entity cùng chứng thực.
WEIGHT_SUPPORT: Final[float] = 0.20
#: Độ tin cậy của Lớp 1 — câu không cần sửa thì bằng 1.0.
WEIGHT_TRUST: Final[float] = 0.30
#: Số entity đủ để coi là "được chứng thực đầy đủ".
FULL_SUPPORT_COUNT: Final[int] = 2
#: Phạt khi MỌI bằng chứng chỉ xuất hiện sau khi rewrite — lúc đó cả kết luận
#: đang đứng trên một suy đoán của mô hình, không phải trên chữ khách đã viết.
REWRITE_ONLY_PENALTY: Final[float] = 0.90
#: Không có ý định nào đủ căn cứ thì confidence phải rơi hẳn, không lửng lơ.
NO_INTENT_CONFIDENCE_FACTOR: Final[float] = 0.20


class NluTier(StrEnum):
    """Ba mức xử lý của Lớp 4."""

    #: Đủ tin cậy → đi thẳng vào multi-slot extraction như trước.
    AUTO = "AUTO"
    #: Hiểu được nhưng chưa chắc → hỏi lại khách một câu xác nhận có nút bấm.
    CONFIRM = "CONFIRM"
    #: Không đủ căn cứ → hỏi làm rõ, kèm gợi ý mẫu xe phổ biến.
    CLARIFY = "CLARIFY"


#: [GIẢ ĐỊNH] 0.85 / 0.60 là số khởi điểm theo yêu cầu nghiệp vụ, chưa hiệu
#: chuẩn bằng dữ liệu thật.
#:
#: Khai báo thành hằng số MODULE chứ không chỉ làm default của dataclass: lớp
#: dưới dùng `slots=True`, và với slots thì `ConfidenceThresholds.auto` truy cập
#: ở mức CLASS trả về một `member_descriptor` chứ không phải `0.85`. Đọc default
#: qua class như vậy không lỗi ngay lúc import mà lỗi lúc so sánh số — đúng kiểu
#: bug chỉ lộ ra khi đọc config lúc khởi động.
DEFAULT_AUTO_THRESHOLD: Final[float] = 0.85
DEFAULT_CONFIRM_THRESHOLD: Final[float] = 0.60


@dataclass(frozen=True, slots=True)
class ConfidenceThresholds:
    """Ranh giới giữa ba mức. Đọc từ biến môi trường ở `services/nlu_pipeline.py`."""

    auto: float = DEFAULT_AUTO_THRESHOLD
    confirm: float = DEFAULT_CONFIRM_THRESHOLD

    def tier_for(self, confidence: float) -> NluTier:
        if confidence >= self.auto:
            return NluTier.AUTO
        if confidence >= self.confirm:
            return NluTier.CONFIRM
        return NluTier.CLARIFY


@dataclass(frozen=True, slots=True)
class IntentCandidate:
    """Một ứng viên ý định kèm điểm thô — để log và để hỏi lại khách cho đúng."""

    intent: str
    score: float


@dataclass(frozen=True, slots=True)
class NluClassification:
    """Kết luận Lớp 3: ý định + confidence + bằng chứng đã dẫn tới nó."""

    intent_hint: str | None
    confidence: float
    candidates: tuple[IntentCandidate, ...] = ()
    evidence: tuple[EntityMatch, ...] = ()
    #: `True` khi lượt này được đọc theo slot đang chờ (A7-10) thay vì phân loại lại.
    resolved_via_pending_slot: bool = False
    pending_slot: str | None = None

    @property
    def vehicle_names(self) -> tuple[str, ...]:
        """Tên xe đã nhận ra, theo thứ tự điểm giảm dần."""

        return tuple(match.canonical for match in self.evidence if match.category is EntityCategory.VEHICLE)

    @property
    def attributes(self) -> tuple[str, ...]:
        """Thuộc tính khách hỏi (`VehicleAttribute`), theo thứ tự điểm giảm dần."""

        return tuple(match.canonical for match in self.evidence if match.category is EntityCategory.ATTRIBUTE)


@dataclass(frozen=True, slots=True)
class QuickReplyOption:
    """Một nút bấm trả về cho client.

    [GIẢ ĐỊNH] Backend chỉ trả dữ liệu có cấu trúc; việc vẽ nút là của frontend.
    Chưa có tài liệu hợp đồng API nào cho quick-reply nên hình dạng tối thiểu
    `{label, value}` được chọn: `value` là chuỗi sẽ được gửi lại như một tin nhắn
    bình thường, nên client cũ chưa hỗ trợ nút vẫn dùng được câu chữ trong `label`.
    """

    label: str
    value: str


def classify_intent(
    *,
    entities: Sequence[EntityMatch],
    rewrite_trust: float = 1.0,
    pending_slot: str | None = None,
    pending_intent: str | None = None,
    user_message: str = "",
) -> NluClassification:
    """Suy ra ý định từ entity đã trích, kèm confidence có thể giải thích được.

    `pending_slot` khác `None` chiếm quyền tuyệt đối: lượt đang trả lời một câu
    hỏi slot thì không được phân loại lại như một tin nhắn mới — đó chính là con
    bug mà A7-10 sinh ra để sửa, chỉ khác chỗ phát sinh.
    """

    if pending_slot is not None:
        return NluClassification(
            intent_hint=pending_intent,
            confidence=1.0,
            candidates=(),
            evidence=tuple(entities),
            resolved_via_pending_slot=True,
            pending_slot=pending_slot,
        )

    accepted = accepted_only(entities)
    if not accepted:
        return NluClassification(intent_hint=None, confidence=0.0, evidence=tuple(entities))

    scores = _intent_scores(accepted, user_message)
    candidates = tuple(
        IntentCandidate(intent=name, score=round(score, 4))
        for name, score in sorted(scores.items(), key=lambda item: -item[1])
        if score > 0.0
    )
    if not candidates:
        best_score = max(match.score for match in accepted) / 100.0
        return NluClassification(
            intent_hint=None,
            confidence=round(NO_INTENT_CONFIDENCE_FACTOR * best_score, 4),
            evidence=tuple(accepted),
        )

    confidence = _confidence(accepted, rewrite_trust)
    return NluClassification(
        intent_hint=candidates[0].intent,
        confidence=confidence,
        candidates=candidates,
        evidence=tuple(accepted),
    )


def _intent_scores(accepted: Sequence[EntityMatch], user_message: str = "") -> dict[str, float]:
    """Cộng điểm cho từng ý định từ entity đã được chấp nhận.

    `user_message` chỉ dùng cho MỘT việc: hỏi `has_comparison_cue` xem câu có ý
    so sánh không. Bảng từ khoá intent ở `entity_catalog` đã phủ phần lớn cue,
    nhưng nó khớp MỜ nên "nên mua vf3 hay vf5" (không có chữ "so sánh") chỉ ra
    được `ADVISORY`. Gọi thẳng hàm cue dùng chung là cách để Lớp 3 và bộ hoà giải
    nhãn không bao giờ bất đồng về việc câu nào là câu so sánh.
    """

    scores: dict[str, float] = {}
    vehicle = best_of(accepted, EntityCategory.VEHICLE)
    attribute = best_of(accepted, EntityCategory.ATTRIBUTE)
    vehicles = all_of(accepted, EntityCategory.VEHICLE)

    if vehicle is not None:
        scores[Intent.CATALOG_LOOKUP.value] = WEIGHT_VEHICLE * (vehicle.score / 100.0)
    if attribute is not None and vehicle is not None:
        # Thuộc tính chỉ cộng cho `CATALOG_LOOKUP` khi đã biết hỏi về xe nào.
        scores[Intent.CATALOG_LOOKUP.value] = scores.get(Intent.CATALOG_LOOKUP.value, 0.0) + WEIGHT_ATTRIBUTE * (
            attribute.score / 100.0
        )

    for match in accepted:
        if match.category is not EntityCategory.INTENT_KEYWORD:
            continue
        scores[match.canonical] = scores.get(match.canonical, 0.0) + (WEIGHT_INTENT_KEYWORD * (match.score / 100.0))

    browse = scores.get(Intent.CATALOG_BROWSE.value)
    if browse is not None and vehicle is not None:
        scores[Intent.CATALOG_BROWSE.value] = browse * (1.0 - BROWSE_PENALTY_WITH_VEHICLE)

    if len(vehicles) >= MIN_COMPARISON_VEHICLES and has_comparison_cue(user_message):
        weakest = min(match.score for match in vehicles) / 100.0
        # Lấy điểm khớp YẾU NHẤT chứ không phải mạnh nhất: một bảng so sánh chỉ
        # đáng tin bằng cột kém chắc chắn nhất trong nó.
        scores[Intent.COMPARE_VEHICLES.value] = (
            scores.get(Intent.COMPARE_VEHICLES.value, 0.0) + WEIGHT_COMPARE_MULTI_VEHICLE * weakest
        )
        lookup = scores.get(Intent.CATALOG_LOOKUP.value)
        if lookup is not None:
            scores[Intent.CATALOG_LOOKUP.value] = lookup * (1.0 - LOOKUP_PENALTY_WITH_COMPARISON)
    else:
        # Từ khoá "so sánh"/"khác gì" khớp được nhưng chưa đủ hai xe: giữ nhãn
        # này ở bảng điểm sẽ dựng một `intent_hint` mà nhánh compare chắc chắn
        # từ chối phục vụ, và Lớp 4 lại hỏi xác nhận cho đúng nhãn đó.
        scores.pop(Intent.COMPARE_VEHICLES.value, None)
    return scores


def _confidence(accepted: Sequence[EntityMatch], rewrite_trust: float) -> float:
    """Confidence tổng: chất lượng khớp × mức chứng thực × độ tin của Lớp 1."""

    evidence_component = max(match.score for match in accepted) / 100.0
    support_component = min(len(accepted), FULL_SUPPORT_COUNT) / FULL_SUPPORT_COUNT
    raw = (
        WEIGHT_EVIDENCE * evidence_component
        + WEIGHT_SUPPORT * support_component
        + WEIGHT_TRUST * max(0.0, min(1.0, rewrite_trust))
    )
    if all(match.matched_on == "rewritten" for match in accepted):
        raw *= REWRITE_ONLY_PENALTY
    return round(max(0.0, min(1.0, raw)), 4)


#: Slot cho thấy phiên đang ở giữa một cuộc tư vấn chọn xe. Cùng tập với
#: `intent_reconciliation._has_active_advisory_context` — hai chỗ hỏi cùng một
#: câu hỏi ("phiên này đã bắt đầu tư vấn chưa"), nên phải cùng một câu trả lời.
ADVISORY_SLOTS: Final[frozenset[SlotName]] = frozenset(
    {
        SlotName.BUDGET_MAX_VND,
        SlotName.PASSENGER_COUNT,
        SlotName.REQUIRED_RANGE_KM,
        SlotName.HOME_CHARGING,
        SlotName.PURPOSE,
        SlotName.MAX_LOAD_KG,
        SlotName.HABIT_NEED_TAGS,
    }
)


def advisory_flow_active(known_slots: Mapping[str, SlotValue] | None) -> bool:
    """Phiên có đang ở giữa một cuộc tư vấn chọn xe không.

    Đây là guard quan trọng nhất của Lớp 4, và nó bảo vệ một ca rất dễ vỡ: bot
    hỏi "ngân sách khoảng bao nhiêu ạ?", khách đáp "700 triệu". Câu đó KHÔNG khớp
    entity nào trong ba danh mục — không có tên xe, không có thuộc tính, không có
    từ khoá intent — nên confidence rơi về 0 và nhánh hỏi làm rõ sẽ cướp lượt,
    trả lại đúng câu "em chưa nắm rõ ý anh/chị" cho một câu trả lời hoàn toàn rõ
    ràng. Đó là bug A7-10 tái sinh dưới hình hài mới.

    Chỉ tính slot có giá trị THẬT: `DECLINED_SLOT_VALUE` nghĩa là khách đã từ
    chối trả lời, nó đánh dấu một ô đã đóng chứ không phải một thông tin đã thu
    được — cùng cách `intent_reconciliation._slot_names` đang lọc.
    """

    if not known_slots:
        return False
    for name, value in known_slots.items():
        if value is None or is_declined(value):
            continue
        try:
            slot = SlotName(name)
        except ValueError:
            continue
        if slot in ADVISORY_SLOTS:
            return True
    return False


def route_confidence(
    classification: NluClassification,
    thresholds: ConfidenceThresholds,
    *,
    handoff_active: bool = False,
    slot_flow_active: bool = False,
    input_looks_noisy: bool = True,
) -> NluTier:
    """[Lớp 4] Chọn mức xử lý, có bốn lối tắt bắt buộc đi thẳng.

    `input_looks_noisy=False` — câu KHÔNG có dấu hiệu gõ hỏng nào. Đây là lối
    tắt quan trọng nhất về mặt tương thích ngược, và lý do của nó là phạm vi:
    bốn lớp này sinh ra để cứu input BỊ NHIỄU. Một câu sạch không khớp entity
    nào không phải câu bị gõ hỏng — nó chỉ là câu mà bảng từ khoá tĩnh ở đây
    không phủ ("chào em", "tôi muốn mua xe", "cho tôi hỏi chút"). Những câu đó
    đã có `classify_scope` (A6-2, có nhãn `SOCIAL`) và `extract_slots` xử lý
    bằng LLM, tốt hơn nhiều so với một bảng keyword.

    Bỏ lối tắt này thì câu chào đầu tiên của mọi cuộc hội thoại nhận về "em chưa
    nắm rõ ý anh/chị" — một hồi quy nặng hơn hẳn vấn đề đang đi sửa.

    `handoff_active` — phiên đang chờ NGƯỜI xử lý (`PENDING_HANDOFF` theo cách
    gọi nghiệp vụ; trong code hôm nay là lượt đã vào hàng đợi tư vấn viên hoặc đã
    chuyển hẳn cho tư vấn viên). Khi đó tuyệt đối không chen câu hỏi của bot:
    khách vừa được báo "đã chuyển tư vấn viên" mà lại nhận "ý anh/chị là gì ạ?"
    thì hai câu đó phủ định nhau, và câu sau xoá mất câu trước. Lượt vẫn chạy
    tiếp như cũ để luồng HITL giữ nguyên quyền quyết định.

    `slot_flow_active` — xem `advisory_flow_active`.

    `resolved_via_pending_slot` — xem docstring module.
    """

    if handoff_active or classification.resolved_via_pending_slot:
        return NluTier.AUTO
    if classification.intent_hint is None:
        # KHÔNG hiểu được ý định nào. Hai ca rất khác nhau cùng rơi vào đây:
        #
        # - câu SẠCH mà bảng từ khoá tĩnh không phủ ("chào em", "700 triệu") —
        #   `classify_scope`/`extract_slots` đọc bằng LLM tốt hơn hẳn, nên nhường;
        # - câu NHIỄU đọc không ra chữ gì — đó đúng là lúc phải hỏi lại.
        return NluTier.CLARIFY if input_looks_noisy and not slot_flow_active else NluTier.AUTO
    # ĐÃ hiểu ra một ý định, chỉ chưa chắc chắn. Đây mới là chỗ ngưỡng làm việc,
    # và trước 2026-08-25 nó không bao giờ chạy: hai lối tắt `not
    # input_looks_noisy` / `slot_flow_active` đứng ở trên và nuốt gần hết lưu
    # lượng — câu gõ SẠCH (tức phần lớn câu thật) luôn đi thẳng, nên `0.85/0.60`
    # chỉ còn áp cho câu gõ hỏng. Hai lối tắt đó nay chỉ còn tác dụng ở nhánh
    # "không hiểu gì" phía trên, đúng phạm vi mà docstring của chúng mô tả.
    return thresholds.tier_for(classification.confidence)


__all__ = [
    "ADVISORY_SLOTS",
    "BROWSE_PENALTY_WITH_VEHICLE",
    "LOOKUP_PENALTY_WITH_COMPARISON",
    "FULL_SUPPORT_COUNT",
    "NO_INTENT_CONFIDENCE_FACTOR",
    "REWRITE_ONLY_PENALTY",
    "WEIGHT_ATTRIBUTE",
    "WEIGHT_COMPARE_MULTI_VEHICLE",
    "WEIGHT_EVIDENCE",
    "WEIGHT_INTENT_KEYWORD",
    "WEIGHT_SUPPORT",
    "WEIGHT_TRUST",
    "WEIGHT_VEHICLE",
    "ConfidenceThresholds",
    "IntentCandidate",
    "NluClassification",
    "NluTier",
    "QuickReplyOption",
    "advisory_flow_active",
    "classify_intent",
    "route_confidence",
]
