"""Pure deterministic scoring rules for A5-3 vehicle recommendations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Literal
from uuid import UUID

from src.agents.domain.budget_parsing import BUDGET_TOLERANCE, NO_BUDGET_LIMIT_VND, within_budget_band
from src.agents.domain.need_tags import canonical_need_tag
from src.agents.domain.slot_mapping import purpose_bucket
from src.agents.domain.values import PurposeBucket, SlotName, VehicleType

AssertionStatus = Literal["YES", "NO", "UNKNOWN"]
AssertionSource = Literal["FLAG", "DOCUMENT"]
SCORE_QUANTUM = Decimal("0.001")

#: Xe dưới ngưỡng tầm chạy này KHÔNG nhận lý do đi-xa nào (bug prod 2026-08-31:
#: VF 2 210 km vẫn được "Tầm hoạt động phù hợp nhu cầu đi xa", rồi
#: `claim_policy.plan_claims` đổi nó thành câu "hợp với mục đích sử dụng" trong
#: pitch — khẳng định sai). CÙNG một con số với `core.act.LONG_DISTANCE_RANGE_KM`
#: (act import lại từ đây): lọc một ngưỡng, chấm điểm một ngưỡng khác là mở lại
#: đúng khe hở vừa vá.
LONG_TRIP_MIN_RANGE_KM: Final[Decimal] = Decimal("300")

#: Trần SỐ LƯỢNG mẫu xe trả về cho một lượt tư vấn.
#:
#: Trước đây là 3 cứng (`[:MAX_RECOMMENDATIONS]`), và đó là bug khách nhìn thấy: hỏi "xe từ 200 -
#: 900 triệu" trên một catalog có VF 2 (188tr), VF 3 (278tr), VF 5 (496tr),
#: VF 6 Eco (646tr), VF 6 Plus (699tr), VF 7 (740tr), VF 8 (899tr) thì sáu mẫu
#: thoả điều kiện, nhưng chỉ ba mẫu điểm cao nhất được trả — và vì "dưới 900
#: triệu" cho ra đúng tập ứng viên đó, hai câu hỏi khác nhau trả về y hệt ba xe.
#: Bốn mẫu còn lại không bị loại vì tiêu chí nào; chúng bị cắt vì đứng thứ tư.
#:
#: [GIẢ ĐỊNH] 20 là trần AN TOÀN, không phải một con số sản phẩm: catalog VinFast
#: hiện hành chỉ có khoảng 11 biến thể ô tô và hơn 20 biến thể xe máy điện, nên
#: với ô tô nó không bao giờ chạm tới, còn với xe máy nó chặn được trường hợp một
#: câu hỏi rất rộng ("xe máy điện dưới 100 triệu") đổ nguyên danh mục ra màn hình.
#: Trần này CHỈ cắt phần đuôi của một danh sách đã xếp hạng — nó không bao giờ là
#: lý do một mẫu thoả điều kiện biến mất khi tổng số mẫu thoả còn nhỏ.
MAX_RECOMMENDATIONS: Final[int] = 20

#: Trần số ĐOẠN VĂN THUYẾT PHỤC sinh bằng LLM trong một lượt.
#:
#: Tách khỏi `MAX_RECOMMENDATIONS` vì hai con số trả lời hai câu hỏi khác nhau:
#: cái trên là "khách được thấy bao nhiêu xe", cái này là "trả tiền cho bao nhiêu
#: đoạn văn". Gộp chúng chính là chỗ hỏng: nới trần danh sách 3 → 20 để không
#: giấu xe của khách đã vô tình nới luôn chi phí lên hai mươi lần gọi LLM mỗi
#: lượt thử, tức sáu mươi lần cho một lượt chat có đủ hai lượt retry của A6-1.
#:
#: Xe ngoài top vẫn về đủ dưới dạng thẻ — tên, giá, ảnh đều đọc từ snapshot và
#: không cần LLM. Khách vẫn thấy mọi mẫu thoả điều kiện; chỉ phần thuyết phục
#: dừng ở những mẫu đứng đầu, đúng chỗ nó có tác dụng.
MAX_PITCHED_RECOMMENDATIONS: Final[int] = 3


@dataclass(frozen=True, slots=True)
class ScoringProfile:
    """Confirmed customer slots that are allowed to affect ranking."""

    vehicle_type: VehicleType
    budget_max_vnd: Decimal | None
    passenger_count: int | None
    required_range_km: int | None
    home_charging: bool | None
    purpose: str | None
    max_load_kg: int | None
    habit_need_tags: tuple[str, ...]
    #: SÀN ngân sách, chỉ có khi khách nói một khoảng hoặc một sàn. Mặc định `None`
    #: nên mọi lượt chỉ có trần được xếp hạng y như trước.
    budget_min_vnd: Decimal | None = None
    #: Mã tính năng khách xác nhận quan tâm ở lượt 2 (T7) — lượt hiện tại
    #: (`feature_mentions`) gộp lượt trước (`pending_feature_codes`), xem
    #: `nodes/synthesize.py::_feature_wording` (Sếp 2026-08-21: xe có tính
    #: năng khách vừa chọn phải được nêu làm lý do thuyết phục ở đề xuất).
    feature_mentions: tuple[str, ...] = ()
    #: Nhãn tiếng Việt của `feature_mentions` — domain/ không import được
    #: `prompts/feature_askable.FEATURE_LABELS` (biên kiến trúc), nên service
    #: layer (`recommendation.py`, được phép import prompts) giải nhãn rồi
    #: truyền xuống. Thiếu nhãn thì rơi về chính mã (Sếp 2026-08-21: claim
    #: phải nêu TÊN tính năng cụ thể, không chỉ nói chung chung).
    feature_mention_labels: Mapping[str, str] = field(default_factory=dict)
    #: Nhãn tiếng Việt của MỌI mã tính năng trong danh mục (`FEATURE_DISPLAY_LABELS`),
    #: không riêng mã khách vừa nhắc. `_feature_showcase_reasons` cần nó để kể
    #: những tính năng khách CHƯA hỏi tới. Rỗng thì showcase không sinh lý do nào —
    #: hành vi cũ giữ nguyên, không có mã trần nào lọt ra câu chữ gửi khách.
    feature_labels: Mapping[str, str] = field(default_factory=dict)
    #: Cảm quan khách vừa xin HƠN ("cốp rộng hơn", "chở nặng hơn"), đọc tất định
    #: bởi `domain/comparative_revision`.
    #:
    #: Đây là trục XẾP HẠNG, không phải bộ lọc — khác hẳn ngưỡng của
    #: `perceptual_traits`, vốn chỉ là giấy phép ĐƯỢC NÓI. Khách xin "cốp rộng
    #: hơn" thì họ muốn danh sách xếp theo dung tích cốp, chứ không muốn ta vứt
    #: bỏ mọi xe dưới 376 lít: ngưỡng ấy đo cho việc khác và dùng nó để lọc là
    #: dựng một tiêu chí chia đôi tập ứng viên mà khách chưa hề nêu.
    preferred_traits: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScoringAssertion:
    """Frozen feature assertion used by scoring; only ``FLAG`` has authority."""

    feature_code: str
    status: AssertionStatus
    source: AssertionSource
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class NeedTagLink:
    """Frozen ``feature_need_tags`` relationship and its scoring relevance."""

    need_tag: str
    feature_code: str
    relevance: Decimal

    def __post_init__(self) -> None:
        if not self.need_tag or not self.feature_code:
            raise ValueError("need-tag links require non-empty tag and feature code")
        if not Decimal("0") < self.relevance <= Decimal("1"):
            raise ValueError("need-tag relevance must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class ScoringCandidate:
    """Structured candidate facts captured in the immutable run snapshot."""

    vehicle_id: UUID
    vehicle_type: VehicleType
    price_vnd: Decimal | None
    range_km: Decimal | None
    seat_count: int | None
    max_load_kg: Decimal | None
    cargo_volume_l: Decimal | None
    energy_consumption_per_100km: Decimal | None
    home_charge_time_minutes: Decimal | None
    battery_removable: bool | None
    battery_swappable: bool | None
    over_budget_percent: Decimal | None
    assertions: tuple[ScoringAssertion, ...]
    need_tag_links: tuple[NeedTagLink, ...]


@dataclass(frozen=True, slots=True)
class ScoringReason:
    """One weighted reason with an explicit slot and optional need-tag trace."""

    slot: SlotName
    message: str
    weight: Decimal
    need_tag: str | None = None
    feature_code: str | None = None
    assertion_source: Literal["FLAG", "DOCUMENT"] | None = None
    evidence_ref: str | None = None

    def render(self) -> str:
        """Render trace metadata for the frozen public ``Recommendation`` DTO."""

        trace = [f"slot={self.slot.value}"]
        if self.need_tag is not None:
            trace.append(f"need_tag={self.need_tag}")
        if self.feature_code is not None:
            trace.append(f"feature_code={self.feature_code}")
        if self.assertion_source is not None:
            trace.append(f"source={self.assertion_source}")
        if self.evidence_ref is not None:
            trace.append(f"evidence={self.evidence_ref}")
        return f"[{'; '.join(trace)}] {self.message}"


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    """Domain result before conversion to the frozen public recommendation DTO."""

    vehicle_id: UUID
    score: Decimal
    reasons: tuple[ScoringReason, ...]
    over_budget_percent: Decimal | None


def rank_candidates(profile: ScoringProfile, candidates: Sequence[ScoringCandidate]) -> list[RankedCandidate]:
    """Trả về MỌI ứng viên đủ điều kiện, xếp theo điểm rồi theo UUID cho ổn định.

    "Mọi" chứ không còn "ba": cắt ở ba là cắt theo THỨ HẠNG, mà thứ hạng không
    phải điều kiện lọc. Khách hỏi "xe từ 200 - 900 triệu" muốn biết có những xe
    nào trong khoảng đó, và một mẫu đứng thứ tư vẫn nằm trong khoảng đó y như
    mẫu đứng thứ nhất. `MAX_RECOMMENDATIONS` chỉ còn là trần an toàn cho danh
    mục rất lớn — xem docstring của hằng số.

    Việc LOẠI ứng viên vẫn nguyên vẹn và vẫn nằm ở hai chỗ cũ: `_score_candidate`
    loại mẫu không đủ điều kiện, `_prefer_budget_band` loại mẫu nằm ngoài khoảng
    khách nêu khi vẫn còn mẫu nằm trong. Thay đổi ở đây không nới một tiêu chí nào.
    """

    _ensure_unique_candidates(candidates)
    ranked = [result for candidate in candidates if (result := _score_candidate(profile, candidate)) is not None]
    ranked.sort(key=lambda item: (-item.score, str(item.vehicle_id)))
    within_budget = _prefer_budget_band(profile, candidates, ranked)
    return _prefer_requested_traits(profile, candidates, within_budget)[:MAX_RECOMMENDATIONS]


#: Cảm quan → trường SỐ của ứng viên dùng để xếp hạng khi khách xin "… hơn".
#:
#: Chỉ hai trên bốn cảm quan có mặt, và đó là sự thật của dữ liệu chứ không phải
#: chỗ làm dở:
#:
#: - `TRAIT_STRONG_MOTOR` cần công suất, mà `ScoringCandidate` không mang cột đó;
#: - `TRAIT_SUV_STANCE` dựa vào `CAR_BODY_TYPE`, và `perceptual_traits` đã ghi rõ
#:   nó KHÔNG phân biệt được xe (10/11 mẫu ô tô là SUV) — xếp hạng theo nó là xếp
#:   hạng theo một hằng số.
#:
#: Cảm quan vắng mặt ở đây vẫn được ĐỌC bình thường; lượt chỉ không có hướng để
#: đẩy thứ tự, đúng như khi thuộc tính không quy về mã nào.
_TRAIT_RANKING_FIELDS: Final[dict[str, str]] = {
    "TRAIT_LARGE_CARGO": "cargo_volume_l",
    "TRAIT_HEAVY_CARRY": "max_load_kg",
}


def _prefer_requested_traits(
    profile: ScoringProfile,
    candidates: Sequence[ScoringCandidate],
    ranked: list[RankedCandidate],
) -> list[RankedCandidate]:
    """Xếp lại theo đúng thứ khách vừa xin HƠN, KHÔNG loại ai.

    Khách nói "cốp rộng hơn" là nói về THỨ TỰ: họ muốn chiếc cốp to nhất lên
    đầu. Lọc theo ngưỡng ở đây sẽ vứt cả những xe chỉ kém một chút, và ngưỡng
    của `perceptual_traits` vốn đo cho việc khác (được phép nói hay không).

    Xe thiếu số đứng CUỐI chứ không nhận 0: thiếu dữ liệu không phải là kém.

    Sắp xếp ỔN ĐỊNH nên điểm cũ vẫn quyết định thứ tự giữa những xe bằng nhau ở
    trục này — trục mới chồng LÊN bảng xếp hạng cũ, không thay nó.
    """

    fields = [_TRAIT_RANKING_FIELDS[trait] for trait in profile.preferred_traits if trait in _TRAIT_RANKING_FIELDS]
    if not fields or not ranked:
        return ranked
    by_id = {candidate.vehicle_id: candidate for candidate in candidates}

    def sort_key(item: RankedCandidate) -> tuple[int, Decimal]:
        candidate = by_id.get(item.vehicle_id)
        values = [
            value
            for field_name in fields
            if (value := getattr(candidate, field_name, None)) is not None and isinstance(value, Decimal)
        ]
        if not values:
            return (1, Decimal(0))
        return (0, -max(values))

    return sorted(ranked, key=sort_key)


def _prefer_budget_band(
    profile: ScoringProfile,
    candidates: Sequence[ScoringCandidate],
    ranked: list[RankedCandidate],
) -> list[RankedCandidate]:
    """Bỏ mẫu lệch hẳn khoảng ngân sách khi vẫn còn mẫu nằm trong khoảng.

    Bug đã quan sát: khách nói "từ 400 đến 600 triệu" và nhận về VF 5 (496 triệu),
    VF 3 (278 triệu), VF 2 (188 triệu). Bộ lọc Lớp 1 chỉ có TRẦN nên hai mẫu dưới
    đáy khoảng vẫn lọt vào, và điểm ngân sách thấp của chúng cũng không cứu được:
    khi cả catalog chỉ có ba xe dưới 600 triệu thì ba xe đó chính là cả danh sách.

    Xếp hạng thấp là chưa đủ — một mẫu 188 triệu KHÔNG phải câu trả lời cho câu hỏi
    "từ 400 đến 600 triệu", ở bất kỳ vị trí nào trong danh sách. Nhưng cũng không
    được bỏ trắng: hết mẫu trong biên thì trả lại đúng những gì có, kèm nhãn lệch
    ngân sách của `claim_policy.budget_fit_note`.

    Biên dùng chung với nhãn hiển thị (`budget_parsing.within_budget_band`), nên
    không bao giờ có mẫu bị loại khỏi danh sách mà lẽ ra phải mang nhãn "một chút",
    hay ngược lại. Không có SÀN thì `within_budget_band` luôn đúng và hàm này không
    đổi gì — mọi phiên chỉ nêu trần giữ nguyên hành vi cũ.
    """

    if profile.budget_min_vnd is None:
        return ranked
    price_by_id = {candidate.vehicle_id: candidate.price_vnd for candidate in candidates}

    def kept(tolerance: Decimal) -> list[RankedCandidate]:
        return [
            item
            for item in ranked
            if within_budget_band(
                price_by_id.get(item.vehicle_id),
                profile.budget_min_vnd,
                profile.budget_max_vnd,
                tolerance=tolerance,
            )
        ]

    # Ưu tiên tuyệt đối cho mẫu nằm ĐÚNG trong khoảng khách nêu, không nới biên.
    # Nới biên ngay từ bước này là cách "khoảng 900 triệu" (800–1.000) vẫn nhặt về
    # một chiếc 646 triệu cho suất thứ ba, trong khi khoảng đó đã là một biên rộng
    # ±100 triệu quanh con số khách nói — nới thêm 20% nữa là nới hai lần.
    #
    # `BUDGET_TOLERANCE` vẫn còn tác dụng, chỉ lùi xuống làm lớp thứ hai: hết mẫu
    # trong khoảng thì mẫu lệch trong biên vẫn hơn một danh sách trống, và nhãn
    # "thấp/cao hơn một chút" của `claim_policy` nói đúng chỗ lệch đó.
    return kept(Decimal(0)) or kept(BUDGET_TOLERANCE) or ranked


def _ensure_unique_candidates(candidates: Sequence[ScoringCandidate]) -> None:
    vehicle_ids = [candidate.vehicle_id for candidate in candidates]
    if len(vehicle_ids) != len(set(vehicle_ids)):
        raise ValueError("candidate vehicle_id values must be unique")


def _score_candidate(profile: ScoringProfile, candidate: ScoringCandidate) -> RankedCandidate | None:
    if candidate.vehicle_type is not profile.vehicle_type:
        return None
    if _is_unlabelled_over_budget(profile, candidate):
        return None
    reasons = [_vehicle_type_reason(profile)]
    reasons.extend(_budget_reasons(profile, candidate))
    reasons.extend(_capacity_reasons(profile, candidate))
    reasons.extend(_charging_reasons(profile, candidate))
    reasons.extend(_purpose_reasons(profile, candidate))
    # _feature_mention_reasons TRƯỚC _need_tag_reasons/_document_reasons: cùng
    # (slot, feature_code) thì `claim_policy.plan_claims` giữ claim gặp ĐẦU
    # TIÊN — tín hiệu khách chủ động chọn ở lượt 2 phải thắng suy diễn thụ động
    # từ need-tag (Sếp 2026-08-21). Thứ tự không đổi điểm (tổng trọng số không
    # phụ thuộc thứ tự cộng).
    reasons.extend(_feature_mention_reasons(profile, candidate))
    reasons.extend(_need_tag_reasons(profile, candidate))
    reasons.extend(_document_reasons(profile, candidate))
    if len(reasons) < 2:
        return None
    # SAU cổng `len(reasons) < 2` một cách có chủ ý: showcase là lý do để KỂ, không
    # phải lý do để CHỌN. Đặt trước cổng thì một mẫu chỉ khớp đúng loại xe (một lý
    # do, trước nay bị loại) sẽ lọt vào đề xuất chỉ vì nó có vài cái cờ tính năng —
    # nới điều kiện lọc mà không ai yêu cầu.
    reasons.extend(_feature_showcase_reasons(profile, candidate))
    score = sum((reason.weight for reason in reasons), start=Decimal("0"))
    return RankedCandidate(
        vehicle_id=candidate.vehicle_id,
        score=score.quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP),
        reasons=tuple(reasons),
        over_budget_percent=_effective_over_budget(profile, candidate),
    )


#: Trọng số ngân sách của một xe nằm trong khoảng khách nêu. Bằng đỉnh của
#: thang cũ (`5 + 1.0 * 20`), nên việc thêm sàn không đổi tương quan giữa slot
#: ngân sách và các slot khác.
_IN_RANGE_BUDGET_WEIGHT: Final[Decimal] = Decimal("25")


def _vehicle_type_reason(profile: ScoringProfile) -> ScoringReason:
    return ScoringReason(
        slot=SlotName.VEHICLE_TYPE,
        message=f"Đúng loại phương tiện {profile.vehicle_type.value} đã chọn",
        weight=Decimal("10"),
    )


def _is_unlabelled_over_budget(profile: ScoringProfile, candidate: ScoringCandidate) -> bool:
    return bool(
        profile.budget_max_vnd is not None
        and candidate.price_vnd is not None
        and candidate.price_vnd > profile.budget_max_vnd
        and (candidate.over_budget_percent is None or candidate.over_budget_percent <= Decimal("0"))
    )


def _effective_over_budget(profile: ScoringProfile, candidate: ScoringCandidate) -> Decimal | None:
    if (
        profile.budget_max_vnd is not None
        and candidate.price_vnd is not None
        and candidate.price_vnd > profile.budget_max_vnd
    ):
        return candidate.over_budget_percent
    return None


def _budget_reasons(profile: ScoringProfile, candidate: ScoringCandidate) -> list[ScoringReason]:
    """Bug thật 2026-08-21 (Sếp báo): công thức cũ dùng `headroom` (còn dư bao
    nhiêu so với ngân sách) — xe CÀNG RẺ càng dư nhiều, càng được cộng điểm
    cao, nên khách nói "khoảng 500 triệu" lại toàn thấy xe hẳn dưới 200 triệu
    xếp đầu. Đổi sang `closeness` (giá / ngân sách): xe giá CÀNG GẦN ngân sách
    (từ dưới lên) càng điểm cao — không loại xe rẻ hơn (khách có thể vẫn thích
    tiết kiệm), chỉ đổi thứ tự ưu tiên khi điểm những phần khác ngang nhau.
    """

    budget = profile.budget_max_vnd
    price = candidate.price_vnd
    if budget is None or budget <= 0 or price is None:
        return []
    # Khách nói RÕ là không đặt trần ("không quan tâm giá", "bao nhiêu cũng
    # được") ⇒ giá thôi làm tiêu chí xếp hạng (Sếp 2026-08-26).
    #
    # `NO_BUDGET_LIMIT_VND` là 10 tỷ — một trần giả để bộ lọc không loại xe nào.
    # Nhưng nó vẫn chảy qua công thức `closeness` bên dưới, và đo ra:
    #
    #     xe   299 triệu -> 5,60 điểm
    #     xe   899 triệu -> 6,80 điểm
    #     xe 1,491 tỷ    -> 7,98 điểm
    #
    # Tức hệ vẫn xếp theo giá, và xếp NGƯỢC: xe càng đắt càng cao điểm. Khách
    # vừa bảo đừng tính tiền thì hệ tự chọn hộ họ chiếc đắt nhất.
    #
    # Bỏ hẳn tín hiệu này chứ không đổi công thức: không có trần thì không có
    # "gần trần", và mọi con số nghĩ ra ở đây đều là chọn hộ khách một mức giá
    # họ vừa từ chối nêu. Còn lại nhu cầu, thói quen và tính năng — cộng lại tối
    # đa hơn 60 điểm, gấp hơn hai lần trọng số ngân sách.
    # `budget_min_vnd` là vế phân biệt, và nó bắt buộc: "từ 900 triệu" cũng đặt
    # trần giả 10 tỷ (không giới hạn TRÊN), nhưng ở đó khách VẪN nêu một mốc giá
    # — giá còn là tiêu chí, chỉ là tiêu chí một đầu. Thiếu vế này thì lượt đó
    # mất sạch tín hiệu giá và xe 900 triệu ngang xe 300 triệu.
    if budget >= NO_BUDGET_LIMIT_VND and not profile.budget_min_vnd:
        return []
    if price <= budget:
        floor = profile.budget_min_vnd
        if floor is not None and floor > 0 and price < floor:
            # Khách nói một KHOẢNG và xe này nằm dưới đáy khoảng đó. Vẫn giữ lại —
            # rẻ hơn dự tính là một tin tốt, và loại thẳng nó là tự quyết hộ khách —
            # nhưng phải xếp sau xe nằm trong khoảng.
            #
            # Không có nhánh này thì `headroom` bên dưới làm điều ngược hẳn: xe càng
            # rẻ càng được cộng điểm, nên "từ 300 đến 700 triệu" trả về đúng những
            # mẫu rẻ nhất catalog — mẫu duy nhất khách đã nói là không muốn.
            shortfall = min(Decimal("1"), (floor - price) / floor)
            return [
                ScoringReason(
                    slot=SlotName.BUDGET_MAX_VND,
                    message="Giá thấp hơn khoảng ngân sách đã nêu",
                    weight=max(Decimal("1"), Decimal("5") - shortfall * Decimal("4")),
                )
            ]
        if floor is None:
            # Chỉ có trần: xe giá CÀNG GẦN trần càng điểm cao (`closeness`).
            # KHÔNG quay lại `headroom` — đó chính là bug 2026-08-21: xe càng rẻ
            # càng dư nhiều nên càng điểm cao, "khoảng 500 triệu" trả về xe dưới
            # 200 triệu. Nhánh có sàn bên dưới xử lý ca khách nêu một KHOẢNG.
            closeness = min(Decimal("1"), max(Decimal("0"), price / budget))
            weight = Decimal("5") + closeness * Decimal("20")
        else:
            # Có sàn: mọi xe TRONG khoảng đều đúng ngân sách như nhau, nên không
            # thưởng thêm cho xe rẻ hơn. Thưởng theo độ rẻ ở đây sẽ luôn đẩy đáy
            # khoảng lên đầu, tức lại chọn hộ khách một mức giá họ không yêu cầu.
            weight = _IN_RANGE_BUDGET_WEIGHT
        return [
            ScoringReason(
                slot=SlotName.BUDGET_MAX_VND,
                message="Giá nằm trong ngân sách đã xác nhận",
                weight=weight,
            )
        ]
    percent = candidate.over_budget_percent
    if percent is None or percent <= 0:
        return []
    return [
        ScoringReason(
            slot=SlotName.BUDGET_MAX_VND,
            message=f"Vượt ngân sách {_format_decimal(percent)}%",
            weight=-percent,
        )
    ]


def _capacity_reasons(profile: ScoringProfile, candidate: ScoringCandidate) -> list[ScoringReason]:
    reasons: list[ScoringReason] = []
    if profile.required_range_km and candidate.range_km is not None and candidate.range_km >= profile.required_range_km:
        ratio = min(candidate.range_km / Decimal(profile.required_range_km), Decimal("2"))
        reasons.append(
            ScoringReason(
                slot=SlotName.REQUIRED_RANGE_KM,
                message="Tầm hoạt động đáp ứng quãng đường đã nêu",
                weight=ratio * Decimal("15"),
            )
        )
    if profile.passenger_count and candidate.seat_count is not None and candidate.seat_count >= profile.passenger_count:
        ratio = min(Decimal(candidate.seat_count) / Decimal(profile.passenger_count), Decimal("1.5"))
        reasons.append(
            ScoringReason(
                slot=SlotName.PASSENGER_COUNT,
                message="Số chỗ phù hợp số người đã xác nhận",
                weight=ratio * Decimal("10"),
            )
        )
    if profile.max_load_kg and candidate.max_load_kg is not None and candidate.max_load_kg >= profile.max_load_kg:
        ratio = min(candidate.max_load_kg / Decimal(profile.max_load_kg), Decimal("1.5"))
        reasons.append(
            ScoringReason(
                slot=SlotName.MAX_LOAD_KG,
                message="Tải trọng đáp ứng nhu cầu đã xác nhận",
                weight=ratio * Decimal("10"),
            )
        )
    return reasons


def _purpose_reasons(profile: ScoringProfile, candidate: ScoringCandidate) -> list[ScoringReason]:
    # Nhóm mục đích, KHÔNG so chuỗi thô (Sếp 2026-08-25).
    #
    # Bản cũ so `purpose` với đúng bốn token `gia_dinh`/`di_lam`/`kinh_doanh`/
    # `giao_hang`. Nhưng prompt trích xuất chỉ dặn LLM ghi "mục đích khách nêu",
    # tức CHỮ TỰ DO — nên "về quê", "đưa đón con", "chở gia đình đi xa" đều không
    # khớp token nào và KHÔNG góp một điểm nào vào việc chọn xe.
    #
    # Lỗ đó im lặng hoàn toàn: không log, không lỗi, chỉ là gợi ý kém đi. Chính
    # lượt Sếp thử ("nhà 4 người về quê") đã rơi vào đó.
    #
    # `purpose_bucket` vốn đã xử lý chữ tự do — nó đang được dùng để chọn
    # allowlist tính năng lượt 2. Dùng lại đúng hàm ấy ở đây thì hai nơi hiểu
    # mục đích theo cùng một cách, thay vì hai cách lệch nhau.
    bucket = purpose_bucket(profile.purpose)
    if (
        bucket is PurposeBucket.PERSONAL
        and candidate.vehicle_type is VehicleType.CAR
        and candidate.energy_consumption_per_100km is not None
        and candidate.energy_consumption_per_100km > 0
    ):
        return [
            ScoringReason(
                slot=SlotName.PURPOSE,
                message="Mức tiêu thụ điện phù hợp nhu cầu đi lại trong đô thị",
                weight=min(Decimal("100") / candidate.energy_consumption_per_100km, Decimal("10")),
                feature_code="ENERGY_CONSUMPTION_KWH_PER_100KM",
                assertion_source="DOCUMENT",
                evidence_ref="cars.energy_consumption_kwh_per_100km",
            )
        ]
    if bucket is PurposeBucket.FAMILY and candidate.cargo_volume_l is not None:
        seat_weight = Decimal(candidate.seat_count or 0)
        cargo_weight = min(candidate.cargo_volume_l / Decimal("100"), Decimal("10"))
        return [
            ScoringReason(
                slot=SlotName.PURPOSE,
                message="Khoang hành lý hỗ trợ nhu cầu gia đình",
                weight=seat_weight + cargo_weight,
            )
        ]
    if bucket is PurposeBucket.SERVICE and candidate.energy_consumption_per_100km:
        range_weight = min((candidate.range_km or Decimal("0")) / Decimal("100"), Decimal("10"))
        efficiency_weight = min(Decimal("100") / candidate.energy_consumption_per_100km, Decimal("10"))
        return [
            ScoringReason(
                slot=SlotName.PURPOSE,
                message="Mức tiêu thụ điện phù hợp ưu tiên vận hành kinh doanh",
                weight=range_weight + efficiency_weight,
            )
        ]
    if bucket is PurposeBucket.LONG_TRIP and candidate.range_km is not None:
        # Đi tỉnh / về quê: TẦM CHẠY là thứ quyết định, và mỗi ki-lô-mét đáng giá
        # hơn hẳn so với đi làm — chia 15 thay vì 20, nên một xe phải đi được ít
        # km hơn mới chạm trần. Xe đi trong phố sạc lại mỗi tối; xe về quê thì
        # phải tới nơi.
        if candidate.range_km < LONG_TRIP_MIN_RANGE_KM:
            # Xe không tới nơi thì không có lý do đi-xa nào cả — kể cả một lý do
            # "yếu": chuỗi lý do này chính là giấy phép để pitch nói "hợp với
            # mục đích", nên cho điểm thấp vẫn là cho phép nói sai.
            return []
        return [
            ScoringReason(
                slot=SlotName.PURPOSE,
                message="Tầm hoạt động phù hợp nhu cầu đi xa",
                weight=min(candidate.range_km / Decimal("15"), Decimal("10")),
            )
        ]
    if bucket is PurposeBucket.WORK and candidate.range_km is not None:
        return [
            ScoringReason(
                slot=SlotName.PURPOSE,
                message="Tầm hoạt động phù hợp nhu cầu đi làm",
                weight=min(candidate.range_km / Decimal("20"), Decimal("10")),
            )
        ]
    if bucket is PurposeBucket.DELIVERY and (
        candidate.battery_removable is True or candidate.battery_swappable is True
    ):
        return [
            ScoringReason(
                slot=SlotName.PURPOSE,
                message="Pin tháo rời hỗ trợ nhu cầu giao hàng",
                weight=Decimal("10"),
            )
        ]
    return []


def _charging_reasons(profile: ScoringProfile, candidate: ScoringCandidate) -> list[ScoringReason]:
    if profile.home_charging is True and candidate.home_charge_time_minutes:
        weight = min(Decimal("600") / candidate.home_charge_time_minutes, Decimal("10"))
        return [
            ScoringReason(
                slot=SlotName.HOME_CHARGING,
                message="Có thông số sạc tại nhà phù hợp nhu cầu đã xác nhận",
                weight=weight,
            )
        ]
    if profile.home_charging is False and candidate.battery_removable is True:
        return [
            ScoringReason(
                slot=SlotName.HOME_CHARGING,
                message="Pin tháo rời hỗ trợ khi không thể sạc tại nhà",
                weight=Decimal("10"),
            )
        ]
    return []


def _need_tag_reasons(profile: ScoringProfile, candidate: ScoringCandidate) -> list[ScoringReason]:
    confirmed_tags = {canonical_need_tag(tag) for tag in profile.habit_need_tags}
    flag_evidence = {
        assertion.feature_code: assertion.evidence_ref
        for assertion in candidate.assertions
        if assertion.source == "FLAG" and assertion.status == "YES"
    }
    return [
        ScoringReason(
            slot=SlotName.HABIT_NEED_TAGS,
            message=f"Tính năng {link.feature_code} phù hợp nhu cầu {link.need_tag}",
            weight=link.relevance * Decimal("20"),
            need_tag=link.need_tag,
            feature_code=link.feature_code,
            assertion_source="FLAG",
            evidence_ref=flag_evidence[link.feature_code],
        )
        for link in candidate.need_tag_links
        if canonical_need_tag(link.need_tag) in confirmed_tags and link.feature_code in flag_evidence
    ]


#: Khách CHỦ ĐỘNG xác nhận quan tâm (trả lời câu hỏi lượt 2) là tín hiệu mạnh
#: hơn need-tag suy ra từ slot khác (relevance tối đa chỉ cho điểm 20) — khách
#: tự nói ra, không phải hệ thống đoán.
FEATURE_MENTION_REASON_WEIGHT: Final[Decimal] = Decimal("25")


def _feature_mention_reasons(profile: ScoringProfile, candidate: ScoringCandidate) -> list[ScoringReason]:
    """Xe THẬT SỰ có tính năng khách vừa chọn ở lượt 2 → thêm lý do (Sếp
    2026-08-21). Chỉ nhận `FLAG` đã duyệt `YES` — cùng chuẩn `_need_tag_reasons`,
    không suy diễn từ tài liệu (căn cứ yếu hơn) hay assertion chưa duyệt."""

    if not profile.feature_mentions:
        return []
    asked = set(profile.feature_mentions)
    return [
        ScoringReason(
            slot=SlotName.HABIT_NEED_TAGS,
            message=(
                f"Có tính năng "
                f"{profile.feature_mention_labels.get(assertion.feature_code, assertion.feature_code)}"
                " mà khách vừa xác nhận quan tâm"
            ),
            weight=FEATURE_MENTION_REASON_WEIGHT,
            feature_code=assertion.feature_code,
            assertion_source="FLAG",
            evidence_ref=assertion.evidence_ref,
        )
        for assertion in candidate.assertions
        if assertion.feature_code in asked and assertion.source == "FLAG" and assertion.status == "YES"
    ]


#: Trọng số BẰNG KHÔNG, cố ý: showcase không được đổi một thứ hạng nào. Nó chỉ
#: mở đường cho `claim_policy.plan_claims` sinh claim, tức cho pitch được PHÉP
#: nhắc tới tính năng đó. Xếp hạng vẫn do các lý do có trọng số quyết định y như cũ.
FEATURE_SHOWCASE_REASON_WEIGHT: Final[Decimal] = Decimal("0")


def _feature_showcase_reasons(profile: ScoringProfile, candidate: ScoringCandidate) -> list[ScoringReason]:
    """Kể MỌI tính năng đã duyệt của xe, kể cả tính năng khách chưa hỏi tới.

    Sếp 2026-08-25: "tính năng đề xuất quá ít nên khó thuyết phục khách". Nguyên
    nhân không phải thiếu dữ liệu mà là pitch LỌC: `reasons` trước đây chỉ chứa
    thứ đã dùng để CHẤM ĐIỂM, nên xe có ADAS mà khách không hỏi ADAS thì im. Cờ
    tính năng đã duyệt nằm sẵn trong snapshot; hàm này đưa chúng ra.

    Cùng chuẩn bằng chứng với `_need_tag_reasons`/`_feature_mention_reasons`: chỉ
    nhận `FLAG` đã duyệt `YES`, không suy diễn từ tài liệu.

    BỎ QUA mã không có nhãn tiếng Việt. Đây là ràng buộc an toàn chứ không phải
    phòng thủ thừa: rơi về chính mã (`ADAS_SUITE`) thì câu claim mang dấu gạch
    dưới, `synthesis.RAW_STRUCTURED_PATTERN` chặn, guardrail retry hai lần rồi
    đẩy khách sang tư vấn viên. Thà không kể còn hơn làm vỡ cả pitch.
    """

    if not profile.feature_labels:
        return []
    return [
        ScoringReason(
            slot=SlotName.HABIT_NEED_TAGS,
            message=f"Xe được trang bị {profile.feature_labels[assertion.feature_code]} theo dữ liệu đã duyệt",
            weight=FEATURE_SHOWCASE_REASON_WEIGHT,
            feature_code=assertion.feature_code,
            assertion_source="FLAG",
            evidence_ref=assertion.evidence_ref,
        )
        for assertion in candidate.assertions
        if assertion.source == "FLAG" and assertion.status == "YES" and assertion.feature_code in profile.feature_labels
    ]


#: Lý do dựa trên tài liệu nhẹ hơn hẳn lý do dựa trên flag (hệ số 20). Tài liệu
#: được đọc là mô tả có căn cứ, còn flag mới là dữ liệu đã kiểm chứng — giữ khoảng
#: cách này thì `FLAG` vẫn là thứ quyết định thứ hạng.
DOCUMENT_REASON_WEIGHT: Final[Decimal] = Decimal("8")


def _document_reasons(profile: ScoringProfile, candidate: ScoringCandidate) -> list[ScoringReason]:
    """Tài liệu khẳng định được tính năng thì cũng được góp một lý do.

    Chỉ nhận assertion `DOCUMENT` đã kết luận `YES`; đoạn chỉ dùng để trích dẫn
    (`status="UNKNOWN"`) không cộng điểm, vì nó không khẳng định điều gì.
    """

    confirmed_tags = {canonical_need_tag(tag) for tag in profile.habit_need_tags}
    document_evidence = {
        assertion.feature_code: assertion.evidence_ref
        for assertion in candidate.assertions
        if assertion.source == "DOCUMENT" and assertion.status == "YES"
    }
    return [
        ScoringReason(
            slot=SlotName.HABIT_NEED_TAGS,
            message=f"Tài liệu mô tả {link.feature_code} phù hợp nhu cầu {link.need_tag}",
            weight=link.relevance * DOCUMENT_REASON_WEIGHT,
            need_tag=link.need_tag,
            feature_code=link.feature_code,
            assertion_source="DOCUMENT",
            evidence_ref=document_evidence[link.feature_code],
        )
        for link in candidate.need_tag_links
        if canonical_need_tag(link.need_tag) in confirmed_tags and link.feature_code in document_evidence
    ]


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")
