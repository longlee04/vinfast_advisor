"""DTO vào/ra giữa node/service/adapter + hợp đồng trích slot (mục 6.7).

`ports.py`, `contracts.py`, `errors.py` nằm ở gốc vì cả node, service lẫn
adapter đều trỏ vào (mục 6.2). Đóng băng ở Ngày 0 (§2.1 docs/team_split.md):
đổi chữ ký là một PR riêng, cả 4 người duyệt; đổi thân hàm (không áp dụng ở
đây, toàn dataclass) tự do.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from src.agents.domain.bottleneck_signal import BottleneckDetectionResult
from src.agents.domain.next_step import NextStepPanel
from src.agents.domain.pending_slot import PendingSlotRequest
from src.agents.domain.values import (
    DialogueAct,
    Intent,
    IntentType,
    PurposeBucket,
    ScopeLabel,
    Severity,
    SlotValue,
    TaskAction,
    Topic,
    VehicleType,
)

FeatureAssertionSource = Literal["FLAG", "DOCUMENT"]
FeatureAssertionStatus = Literal["YES", "NO", "UNKNOWN"]


class LLMExtractionPayload(BaseModel):
    """Raw structured understanding payload parsed from exactly one LLM call."""

    model_config = ConfigDict(frozen=True)

    # LLM thỉnh thoảng trả một nhãn không có trong enum ("task": "RECOMMEND",
    # "task_action": "ASK"). Trước đây một field sai là VỨT CẢ payload — mất luôn
    # ngân sách, loại xe khách vừa nói (prod: 146 lần trong 3 ngày). Nay chỉ bỏ
    # đúng giá trị lạ; các field còn lại vẫn được dùng.
    @field_validator(
        "scope",
        "dialogue_act",
        "task_action",
        "vehicle_type",
        "purpose_bucket",
        "task",
        "primary_topic",
        "severity",
        mode="before",
    )
    @classmethod
    def _drop_unknown_enum(cls, value: object, info: ValidationInfo) -> object:
        if value is None or not isinstance(value, str):
            return value
        allowed = {
            "scope": ScopeLabel,
            "dialogue_act": DialogueAct,
            "task_action": TaskAction,
            "vehicle_type": VehicleType,
            "purpose_bucket": PurposeBucket,
            "task": IntentType,
            "primary_topic": Topic,
            "severity": Severity,
        }[info.field_name]
        try:
            allowed(value)
        except ValueError:
            return (
                None
                if info.field_name not in {"dialogue_act", "task_action"}
                else cls.model_fields[info.field_name].default
            )
        return value

    @field_validator("intents", mode="before")
    @classmethod
    def _drop_unknown_intents(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        kept = []
        for item in value:
            try:
                Intent(item)
            except ValueError:
                continue
            kept.append(item)
        return kept

    scope: ScopeLabel | None = None
    dialogue_act: DialogueAct = DialogueAct.UNKNOWN
    task_action: TaskAction = TaskAction.NONE
    vehicle_type: VehicleType | None = None
    budget_max_vnd: str | int | float | None = None
    passenger_count: int | None = None
    required_range_km: int | float | None = None
    range_period: str | None = None
    home_charging: bool | None = None
    max_load_kg: int | float | None = None
    purpose: str | None = None
    purpose_bucket: PurposeBucket | None = None
    habit_need_tags: list[str] = Field(default_factory=list)
    intents: list[Intent] = Field(default_factory=list)
    feature_mentions: list[str] = Field(default_factory=list)
    vehicle_name_mentions: list[str] = Field(default_factory=list)
    rejected_vehicle_mention: str | None = None
    rejection_reason: str | None = None

    # ── Bốn trục hiểu lượt (Todo 6) ──────────────────────────────────────────
    #
    # Mọi field dưới đây đều CÓ MẶC ĐỊNH an toàn: mô hình chưa biết trả chúng,
    # hoặc trả rác, thì lượt vẫn chạy đúng như trước. Đó là điều kiện để chuyển
    # đổi dần thay vì phải sửa mọi consumer trong một PR.
    #
    # `dialogue_act` đã có ở trên — nó chính là trục thứ nhất.
    #: Trục NHIỆM VỤ: khách muốn gì. `None` nghĩa là mô hình chưa nói, và người
    #: đọc phải rơi về `intents` cũ chứ không được đoán.
    task: IntentType | None = None
    #: Trục CHỦ ĐỀ: câu đang nói về cái gì.
    primary_topic: Topic | None = None
    secondary_topics: list[str] = Field(default_factory=list)
    #: Trục MỨC KHẨN. Đây là tín hiệu MỀM — `domain/escalation` giữ một sàn tất
    #: định và luôn thắng nếu nó cao hơn.
    severity: Severity | None = None
    #: Mô hình đọc được ý muốn gặp người. HỢP với keyword, không thay thế.
    human_requested: bool = False


@dataclass(frozen=True, slots=True)
class FeatureAssertion:
    """Đầu ra thống nhất của Lớp 2, mọi nhánh 2a-2e (mục 7.2 schema, A1-3)."""

    vehicle_id: UUID
    feature_code: str
    status: FeatureAssertionStatus
    source: FeatureAssertionSource
    evidence_ref: str
    confidence: float | None = None
    excerpt: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceInput:
    """Một số liệu phẳng để guardrail đối chiếu (PRD 8.4)."""

    fact_code: str
    value_text: str
    source_table: str
    source_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CandidateInput:
    """Một ứng viên và tầng truy xuất xa nhất nó đi tới (PRD 5.2/5.3)."""

    vehicle_id: UUID
    layer_reached: str


@dataclass(frozen=True, slots=True)
class ScoreInput:
    """Điểm và lý do của một ứng viên, chuẩn bị ghi `scoring_result` (PRD 5.3)."""

    vehicle_id: UUID
    score: Decimal
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VehicleMatch:
    """A4-1: kết quả resolve tên xe khách nêu về danh tính trong `vehicles`."""

    vehicle_id: UUID
    display_name: str
    vehicle_type: VehicleType
    #: Tên dòng xe không kèm phiên bản ("VF 6"), để biết hai kết quả có phải hai
    #: PHIÊN BẢN của cùng một dòng hay hai dòng khác nhau — hai ca đó cần hai
    #: cách xử lý trái ngược (chọn bản mặc định / hỏi lại khách).
    model_name: str = ""


@dataclass(frozen=True, slots=True)
class VehicleFacts:
    """A4-1: số liệu đọc thẳng theo `vehicle_id` — giá `STARTING_PRICE` đang hiệu lực + specs."""

    vehicle_id: UUID
    display_name: str
    vehicle_type: VehicleType
    starting_price_vnd: Decimal | None
    specs: dict[str, str | int | None]
    #: Tính năng đã duyệt của xe: `feature_code` → tên hiển thị. Chỉ gồm tính
    #: năng `status='YES'` và `verification_status='APPROVED'` — bảng thông số
    #: gửi khách không được nhắc tới thứ chưa ai xác minh.
    #:
    #: Khoá là MÃ chứ không phải `category`: `feature_definitions.category` gom
    #: theo mục đích nội bộ (SMART_FEATURE chứa lẫn GPS với Anti Theft), không
    #: khớp các nhóm của bảng thông số gửi khách. Phân nhóm hiển thị là việc của
    #: `domain/catalog_reply.py`, và nó cần mã để làm chính xác.
    features: dict[str, str] = field(default_factory=dict)
    #: `feature_code` → `feature_definitions.category` (SAFETY/COMFORT/SMART_FEATURE/UTILITY)
    #: cho bảng chi tiết xe nhóm trang bị theo mục (Sếp 2026-08-29). Rỗng khi nguồn không đọc.
    feature_categories: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FilterCriteria:
    """Tham số Lớp 1 (mục 7.1 schema) — dựng từ slot đã xác nhận, LLM không viết SQL."""

    vehicle_type: VehicleType | str
    budget_max_vnd: Decimal | None = None
    budget_min_vnd: Decimal | None = None
    passenger_count: int | None = None
    passenger_count_min: int | None = None
    passenger_count_max: int | None = None
    required_range_km: int | None = None
    required_load_kg: int | None = None


@dataclass(frozen=True, slots=True)
class ExtractedSlots:
    """Validated result of one structured turn-understanding call."""

    slots: dict[str, SlotValue] = field(default_factory=dict)
    intents: list[Intent] = field(default_factory=list)
    vehicle_name_mentions: list[str] = field(default_factory=list)
    scope: ScopeLabel = ScopeLabel.IN_SCOPE
    dialogue_act: DialogueAct = DialogueAct.UNKNOWN
    task_action: TaskAction = TaskAction.NONE
    excluded_vehicle_ids: tuple[str, ...] = ()
    #: Mã tính năng khách nhắc trong lượt NÀY (vd câu trả lời cho câu hỏi lượt 2).
    #: Bảng `pending_feature_mentions` chỉ tiêu thụ được ở lượt sau, mà lượt đề
    #: xuất chính là lượt chứa câu trả lời — nên phải trả kèm ở đây.
    feature_mentions: list[str] = field(default_factory=list)
    #: Cảm quan khách vừa xin HƠN ("cốp rộng hơn"), đọc tất định bởi
    #: `domain/comparative_revision`. Là trục XẾP HẠNG, không phải bộ lọc.
    trait_mentions: list[str] = field(default_factory=list)
    #: T2 Lớp 3: lý do `normalize_range_km` từ chối quãng đường. Khác `None`
    #: nghĩa là lượt này phải phát câu xác nhận đơn vị thay vì hỏi slot kế tiếp.
    range_clarify_reason: str | None = None
    #: T4: tên xe LLM đóng gói là khách vừa loại khi đang so sánh 2 mẫu — hint
    #: cho `question_for_turn`, còn phải validate khớp `vehicle_name_mentions`
    #: của CHÍNH lượt này trước khi tin (chống bịa tên, xem `slot_planning.py`).
    rejected_vehicle_mention: str | None = None
    #: Lý do khách nêu khi loại xe ở `rejected_vehicle_mention`, giữ nguyên lời khách.
    rejection_reason: str | None = None
    # ── Bốn trục, đã chuẩn hoá (Todo 6) ──────────────────────────────────────
    #: `None` nghĩa là mô hình chưa nói — người đọc rơi về `intents` cũ.
    task: IntentType | None = None
    primary_topic: Topic = Topic.OTHER
    secondary_topics: tuple[Topic, ...] = ()
    severity: Severity = Severity.NORMAL
    human_requested: bool = False


@dataclass(frozen=True, slots=True)
class Recommendation:
    """Một mẫu đề xuất (A5-3), mỗi cái ≥ 2 `reasons` trỏ về slot.

    Số lượng không còn cố định ở 3: trần nằm ở `domain/scoring.MAX_RECOMMENDATIONS`
    và chỉ là trần an toàn cho danh mục lớn — mọi mẫu thoả điều kiện đều được trả.
    """

    vehicle_id: UUID
    rank: int
    reasons: list[str]
    #: Tên hiển thị lấy từ snapshot của chính run này, không đọc lại catalog:
    #: tên phải khớp bản bất biến của lượt, không lệch nếu catalog đổi giữa chừng.
    display_name: str = ""
    over_budget_percent: float | None = None


@dataclass(frozen=True, slots=True)
class TcoResult:
    """Kết quả `vinfast_tco_v1` (A5-5) — `unavailable_reason` khác `None` thì bỏ qua các field số."""

    vehicle_id: UUID
    total_vnd: Decimal | None
    components_vnd: dict[str, Decimal]
    assumptions_id: UUID | None
    computed_at: datetime
    unavailable_reason: str | None = None


@dataclass(frozen=True, slots=True)
class QuoteGateDecision:
    """[A7-4] Kết luận của cổng rủi ro báo giá cho MỘT lượt.

    `evaluation` giữ dạng `Mapping` thô chứ không phải `QuoteEvaluation`: DTO này
    đi vào `nodes/`, mà node bị cấm chạm `domain/` (mục 6.5b). Bản dựng có kiểu
    nằm trong `domain/quote_risk.py`, service phẳng hoá nó ở biên.

    `legacy_requires_hitl` là kết quả của luồng CŨ trên cùng lượt đó — chỉ để so
    sánh shadow-mode, KHÔNG ảnh hưởng tới câu trả lời gửi khách.
    """

    tier: str
    delivery_action: str
    requires_hitl: bool
    legacy_requires_hitl: bool
    evaluation: Mapping[str, Any] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    escalation_note: str | None = None
    #: A7-5: `new_request` | `acknowledgment`.
    turn_type: str = "new_request"
    #: Câu trả thẳng cho khách, kết thúc lượt tại cổng (chỉ nhánh acknowledgment).
    #: `None` nghĩa là lượt đi tiếp như thường.
    reply: str | None = None
    #: Đánh giá vừa dựng MỚI ở lượt này, cần ghi vào bộ nhớ phiên. `None` ở nhánh
    #: acknowledgment — và đó chính là cách A7-5 bảo đảm không xoá nhầm bộ nhớ cũ.
    evaluation_to_remember: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class QuoteAuditRecord:
    """[A7-4] Một dòng audit bất đồng bộ cho hàng đợi review định kỳ.

    Ghi cho MỌI lượt đi qua cổng, kể cả lượt được auto-approve: bỏ giám sát các
    case tự động là bỏ đúng thứ cần bằng chứng nhất khi nới HITL.
    """

    session_id: str
    tier: str
    requires_hitl: bool
    legacy_requires_hitl: bool
    user_message: str
    output_content: str
    evaluation: Mapping[str, Any] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    run_id: UUID | None = None
    sampled_for_review: bool = False
    near_threshold: bool = False
    shadow_mode: bool = False


@dataclass(frozen=True, slots=True)
class Citation:
    """Một dẫn chứng đánh số trong pitch — footnote `[index]` trỏ về evidence."""

    index: int
    evidence_id: UUID
    source_record: str


@dataclass(frozen=True, slots=True)
class VehiclePitch:
    """Đoạn văn thuyết phục của ĐÚNG một xe, kèm dẫn chứng của chính xe đó."""

    vehicle_id: UUID
    rank: int
    display_name: str
    pitch: str
    citations: tuple[Citation, ...] = ()
    starting_price_vnd: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogBrowseResult:
    """Verified catalog listing plus card-ready vehicle data."""

    answer: str
    pitches: tuple[VehiclePitch, ...]


@dataclass(frozen=True, slots=True)
class ComparisonSpecField:
    """Một dòng tiêu chí của bảng so sánh: mã cột catalog + nhãn gửi khách."""

    code: str
    label: str


@dataclass(frozen=True, slots=True)
class ComparedVehicleView:
    """Một cột của bảng so sánh, đã sẵn sàng serialize cho client.

    `found=False` là một trạng thái HỢP LỆ, không phải lỗi: khách nêu một mẫu
    không còn trong danh mục thì cột đó nói đúng như vậy, các cột kia vẫn hiện.
    """

    vehicle_id: str
    found: bool
    display_name: str = ""
    vehicle_type: str = ""
    image_url: str | None = None
    starting_price_vnd: str | None = None
    specs: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VehicleComparisonView:
    """Bảng so sánh gửi client + đoạn tóm tắt đặt ngay dưới phần ảnh.

    Đi ĐƯỜNG RIÊNG, không dùng lại `recommendations`: hai thứ đó có nghĩa khác
    nhau (`recommendations` là kết quả xếp hạng của luồng tư vấn, bị strip
    pitch/citation khi lượt chưa qua HITL ở `chain.run_turn`) và một bảng so sánh
    tra cứu công khai không được thừa hưởng ràng buộc đó.

    Cũng KHÔNG chèn vào `VehicleInquiryForm`/luồng slot tư vấn cá nhân hoá: đây
    là payload chỉ-đọc của một lượt, không phải hồ sơ nhu cầu của khách.
    """

    vehicles: list[ComparedVehicleView] = field(default_factory=list)
    spec_fields: list[ComparisonSpecField] = field(default_factory=list)
    #: Đoạn tóm tắt do LLM viết từ chính `specs` ở trên. Rỗng khi chưa nối LLM
    #: hoặc lời gọi thất bại — client vẫn dựng được bảng, chỉ thiếu phần văn xuôi.
    summary: str = ""
    #: Tên xe khách nêu mà catalog không có. Để client nói rõ thiếu mẫu nào.
    missing_vehicle_names: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CompareVehiclesResult:
    """Kết quả một lượt so sánh: câu chữ + (có thể) bảng.

    `comparison=None` với `answer` khác rỗng là các nhánh KHÔNG gọi tool — trùng
    xe, quá ba xe. Chúng vẫn là câu trả lời hoàn chỉnh của lượt.
    """

    answer: str
    comparison: VehicleComparisonView | None = None
    #: Câu mời khách nêu thêm xe, dùng ở nhánh mới nắm được MỘT xe. Nhánh đó rơi
    #: về intent cũ (tra cứu), nên chuỗi này được nối vào cuối câu trả lời của
    #: nhánh cũ thay vì thay thế nó.
    follow_up: str | None = None
    #: Bản ghi trạng thái "đang chờ khách nêu xe để so sánh"
    #: (`domain/vehicle_comparison.COMPARE_TARGETS_SLOT`), hoặc `None`.
    #:
    #: DỰNG SẴN ở service chứ không để node tự dựng: `nodes/` bị cấm import
    #: `domain/` (mục 6.5b, `test_graph_boundary` cưỡng chế), nên node không có
    #: cách nào tạo một `PendingSlotRequest`. Node chỉ chuyển tiếp nó vào state,
    #: và `chain._remember_pending_slot` là chỗ DUY NHẤT ghi xuống database —
    #: cùng quy ước với `pending_slot_request` của luồng giá lăn bánh (A7-10).
    #:
    #: Thiếu bản ghi này thì câu trả lời kế tiếp ("VF3 và VF5") lại bị đọc như
    #: một tin nhắn rời và `classify_scope` gắn OUT_OF_SCOPE — đúng con bug A7-10
    #: sinh ra để sửa, chỉ khác chỗ phát sinh.
    pending_request: PendingSlotRequest | None = None


@dataclass(frozen=True, slots=True)
class RecommendedVehicleView:
    """Một phần tử `recommendations` gửi ra client: pitch + dữ liệu dựng card.

    `image_url` KHÔNG nằm trong run snapshot: ảnh không phải khẳng định sự thật
    như giá hay tầm hoạt động, nên đọc thẳng từ catalog lúc serialize.
    """

    vehicle_id: UUID
    rank: int
    display_name: str
    image_url: str | None
    starting_price_vnd: str | None
    pitch: str
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class QuickReplyView:
    """Một nút bấm gợi ý gửi ra client (Lớp 4 nhận diện ý định).

    `value` là chuỗi client gửi lại như một tin nhắn bình thường — không phải mã
    lệnh riêng. Nhờ vậy client CHƯA hỗ trợ nút bấm vẫn dùng được: khách đọc câu
    hỏi trong `answer` rồi tự gõ "đúng" thì luồng chạy y hệt như bấm nút.
    """

    label: str
    value: str


@dataclass(frozen=True, slots=True)
class NearbyLocationView:
    """Một địa điểm gửi client, đã sẵn sàng dựng card."""

    id: str
    name: str
    address: str
    latitude: float
    longitude: float
    distance_km: float | None
    location_type: str
    category_label: str
    maps_url: str
    charger_type: str | None = None
    hotline: str | None = None
    open_time: str | None = None
    close_time: str | None = None
    status: str | None = None


@dataclass(frozen=True, slots=True)
class NearbyLocationListView:
    """Payload `NEARBY_LOCATION_LIST` gửi client cho một lượt tìm địa điểm."""

    locations: list[NearbyLocationView] = field(default_factory=list)
    location_types: list[str] = field(default_factory=list)
    origin_latitude: float | None = None
    origin_longitude: float | None = None
    origin_label: str | None = None
    searched_radius_km: float | None = None
    needs_location_kind: bool = False
    needs_location: bool = False


@dataclass(frozen=True, slots=True)
class FindNearbyLocationResult:
    """Kết quả một lượt tìm địa điểm: câu chữ + (có thể) danh sách."""

    answer: str
    locations: NearbyLocationListView | None = None
    needs_location: bool = False
    needs_location_kind: bool = False
    quick_replies: list[QuickReplyView] = field(default_factory=list)
    pending_request: PendingSlotRequest | None = None
    resolved_location: object | None = None


@dataclass(frozen=True, slots=True)
class TestDriveSlotOption:
    """Một khung giờ trống ở một showroom, đủ để đặt lịch mà không phải hỏi lại."""

    showroom: str
    scheduled_at: datetime
    label: str
    #: Giấy phép đã ký cho đúng khung này. Sinh ở service vì chỉ tầng đó biết
    #: khoá — chỗ gọi KHÔNG được tự ghép chuỗi, đó là cách lỗ hổng cũ sống sót.
    value: str = ""


@dataclass(frozen=True, slots=True)
class TestDriveShowroomView:
    """Một showroom trong thẻ chọn lịch lái thử."""

    showroom_id: str
    name: str
    address: str
    distance_label: str
    #: Toạ độ + khoảng cách số (đợt 9): để client vẽ bản đồ (`navigate.kind=map`).
    #: `None` khi nguồn không có toạ độ — thẻ vẫn nguyên, chỉ không có ghim.
    lat: float | None = None
    lng: float | None = None
    distance_km: float | None = None


@dataclass(frozen=True, slots=True)
class TestDriveTimeView:
    """Một ô giờ trong cột giờ dùng chung."""

    scheduled_at: datetime
    label: str


@dataclass(frozen=True, slots=True)
class TestDriveDayView:
    """Một ngày và các ô giờ của nó — HỢP của mọi showroom trong thẻ.

    Cột giờ dùng chung là chủ ý của Sếp 2026-08-28: đổi showroom thì cột giờ giữ
    nguyên, chỉ những ô showroom đó hết chỗ mới mờ đi. Dựng cột riêng cho từng
    showroom sẽ làm lưới nhảy mỗi lần bấm, và khách mất mốc so sánh.
    """

    date: str
    label: str
    times: tuple[TestDriveTimeView, ...] = ()


@dataclass(frozen=True, slots=True)
class TestDriveOptionView:
    """Một ô CÒN CHỖ: cặp (showroom, giờ) kèm mã nút đã sinh sẵn.

    Chỉ ô còn chỗ mới có mặt ở đây — client suy ra "mờ" bằng phép vắng mặt, nên
    không có chỗ nào cho hai nguồn sự thật lệch nhau.

    `value` là mã có cấu trúc do chính hệ sinh (`domain/test_drive_booking`):
    bước chốt lịch không được đoán giờ, sai một tiếng là khách tới lúc không ai đợi.
    """

    showroom_id: str
    scheduled_at: datetime
    value: str


@dataclass(frozen=True, slots=True)
class TestDriveCardView:
    """Thẻ chọn showroom + khung giờ, thay cho việc bắt khách gõ vào khung chat.

    Sếp 2026-08-28: *"hiện ra các thao tác chọn chứ không phải yêu cầu người dùng
    nhập chat"*. Ba showroom gần nhất một cột, cột giờ bên cạnh dùng chung.
    """

    vehicle_name: str
    showrooms: tuple[TestDriveShowroomView, ...] = ()
    days: tuple[TestDriveDayView, ...] = ()
    options: tuple[TestDriveOptionView, ...] = ()
    default_showroom_id: str = ""
    default_date: str = ""
    #: Id xe (uuid chuỗi) để client gọi `POST /agent/test-drive/options` khi
    #: khách chọn vị trí NGAY TRÊN thẻ (đợt 8, contract mục 1). Mặc định rỗng
    #: vì `build_test_drive_card` không biết id — tầng act/route điền vào.
    vehicle_id: str = ""
    #: Chưa biết vị trí khách: thẻ trống (không showroom/ngày/ô giờ) bày nút
    #: "Dùng vị trí của tôi" + ô gõ quận/huyện. MỘT thẻ cho cả hai bước, không
    #: có lượt chat thứ hai chỉ để hỏi tỉnh.
    needs_location: bool = False


@dataclass(frozen=True, slots=True)
class NavigateShowroomView:
    """Một ghim showroom trên bản đồ (`NavigateView.kind == "map"`)."""

    showroom_id: str
    name: str
    address: str
    lat: float | None = None
    lng: float | None = None
    distance_km: float | None = None


@dataclass(frozen=True, slots=True)
class NavigateCenter:
    lat: float
    lng: float


@dataclass(frozen=True, slots=True)
class NavigateView:
    """Lệnh "dẫn khách đi xem" — đợt 9 "tour guide", contract mục 1.

    Lõi v2 CHỈ phát khi khách VỪA QUYẾT ĐỊNH: chốt một mẫu (`kind="vehicle"`,
    client mở trang `/vehicles/<slug>`) hoặc xin lái thử/showroom gần
    (`kind="map"`, client vẽ bản đồ). Đang so sánh/đề xuất thì KHÔNG phát —
    mở trang lúc khách còn cân nhắc là giật họ khỏi cuộc tư vấn.
    """

    kind: str
    vehicle_id: str = ""
    #: Slug trang chi tiết trên chính web này (cùng nguồn với link "Xem thêm"
    #: của `catalog_browse`). Rỗng = mẫu chưa có trang, client không mở gì.
    slug: str = ""
    #: Đường dẫn trang thật trên web ("/vehicles/vf-5" | "/motorbikes/vero-x").
    #: Rỗng = chưa có trang; client giữ bản tóm tắt. Ô tô suy được từ `slug`,
    #: xe máy BẮT BUỘC đọc trường này (trang nằm dưới /motorbikes).
    path: str = ""
    name: str = ""
    center: NavigateCenter | None = None
    showrooms: tuple[NavigateShowroomView, ...] = ()
    needs_location: bool = False


@dataclass(frozen=True, slots=True)
class SpecGroup:
    """Một nhóm thông số. Nhóm không có dòng nào thì KHÔNG được dựng."""

    title: str
    rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class VehicleDetailsView:
    """Dữ liệu TRÌNH BÀY cho thẻ chi tiết — không phải một chặng, không có TTL."""

    vehicle_name: str
    #: Chỉ nhóm thông số đọc từ DANH MỤC. Ba trường cũ (`highlights`/`features`/
    #: `safety`) đã bị gỡ ở vòng rà soát #4: chúng chở trích đoạn RAG thô, lọc
    #: duy nhất bằng `VehicleDocumentRow.status == "ACTIVE"` — trạng thái của
    #: tài liệu, không phải dấu duyệt cho từng câu khẳng định.
    spec_groups: tuple[SpecGroup, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class TestDriveResult:
    """Kết quả một lượt đặt lịch lái thử.

    Khi chưa biết vị trí khách, `answer` là câu hỏi vị trí và `pending_request`
    mở trạng thái chờ (tái dùng cơ chế `pending_for_user_location`). Khi đã biết,
    `answer` chứa sẵn danh sách showroom gần kèm khung giờ trống.
    """

    answer: str
    needs_location: bool = False
    pending_request: PendingSlotRequest | None = None
    #: Từng khung giờ trống, dạng CẤU TRÚC để dựng nút bấm (Sếp 2026-08-26).
    #:
    #: `answer` là chữ cho người đọc; nút thì cần đúng showroom và đúng mốc thời
    #: gian. Bắt khách gõ lại "chiều mai lúc 3h" rồi parse tiếng Việt tự do là mở
    #: một cửa đoán sai mới ngay ở bước chốt lịch — nơi sai một giờ là khách tới
    #: showroom vào lúc không ai đợi.
    slot_options: tuple[TestDriveSlotOption, ...] = ()
    #: Thẻ chọn có cấu trúc. `None` ở lượt hỏi vị trí và lượt không còn khung nào.
    card: TestDriveCardView | None = None


@dataclass(frozen=True, slots=True)
class TcoComponentView:
    """Một khoản trong bảng chi phí, kèm nhãn tiếng Việt sẵn cho client."""

    code: str
    label: str
    amount_vnd: str
    #: Nhóm hiển thị trên thẻ (Sếp 2026-08-31: "giá lăn bánh với TCO là MỘT"):
    #: "rolling" = tiền bỏ ra để xe LĂN BÁNH (giá xe + lệ phí ban đầu),
    #: "operating" = chi phí VẬN HÀNH 5 năm. Chuỗi rỗng cho chỗ dựng cũ chưa
    #: gán nhóm — client phải chịu được cả hai (fallback: bảng phẳng như cũ).
    group: str = ""


#: Nhóm của từng mã khoản trong `components_vnd` — MỘT nguồn cho cả thẻ trong
#: chat (`core/act.build_tco_card`) lẫn API tính lại (`api/routes`): hai bảng
#: nhóm là hai chỗ để lệch, mà khách nhìn thấy cả hai trên cùng một thẻ.
TCO_COMPONENT_GROUPS: Final[Mapping[str, str]] = {
    "promoted_purchase_price_vnd": "rolling",
    "rolling_fees_vnd": "rolling",
    "energy_vnd": "operating",
    "battery_vnd": "operating",
    "scheduled_maintenance_vnd": "operating",
}


@dataclass(frozen=True, slots=True)
class ProvinceOptionView:
    """Một tỉnh khách chọn được ngay trên thẻ chi phí."""

    code: str
    name: str
    region_code: str


@dataclass(frozen=True, slots=True)
class TcoRatesView:
    """Hệ số để CLIENT tính lại tổng ngay tại chỗ khi khách kéo số km.

    Sếp 2026-08-29: mỗi lần khách đổi km mà phải chờ một lượt chat là thẻ chi
    phí mất hết tác dụng "chỉnh được ngay trên giao diện". Gửi kèm hệ số thì
    thanh trượt chạy tức thì, và lượt chat chỉ cần cho lần tính đầu.

    Hợp đồng client dùng (đúng thứ tự máy chủ cộng, `products/domain/tco.py`):

        total = fixed
              + energy_vnd_per_km × km_ngày × days_per_year × years
              + insurance_vnd_per_year × years
              + ceil(km_ngày × days_per_year × years / maintenance_interval_km)
                × maintenance_vnd_per_service
              + battery_vnd_per_month × 12 × years

    Hai chỗ dễ lệch, cố ý ghi rõ ở đây:

    - `days_per_year` là **360**, không phải 365: máy chủ tính theo 30 ngày/tháng
      × 60 tháng (`tools/tco.DAYS_PER_MONTH`). Dùng 365 thì tiền điện lệch 1,4%
      — trên một tổng năm năm là vài triệu đồng, đủ để khách thấy hai con số
      khác nhau giữa thẻ và câu trả lời.
    - Số lần bảo dưỡng làm tròn LÊN (`ceil`): đi quá mốc một kilômét vẫn phải
      vào xưởng.

    Tiền là CHUỖI như `TcoCardView`. `energy_vnd_per_km` là chuỗi thập phân —
    số duy nhất không làm tròn về đồng, vì sai một đồng trên mỗi km là sai vài
    chục nghìn trên tổng.
    """

    fixed_vnd: str
    energy_vnd_per_km: str
    insurance_vnd_per_year: str
    maintenance_vnd_per_service: str
    maintenance_interval_km: str
    battery_vnd_per_month: str
    years: int = 5
    days_per_year: int = 360
    formula_note: str = ""


@dataclass(frozen=True, slots=True)
class TcoCardView:
    """Thẻ chi phí 5 năm mà khách CHỈNH ĐƯỢC ngay trên giao diện.

    Sếp 2026-08-27: khách phải kéo được số km và chọn được tỉnh ngay tại thẻ,
    không phải gõ vào khung chat rồi chờ tính lại.

    Mang theo `vehicle_id` và hai giả định hiện hành để client dựng ô chỉnh với
    đúng giá trị đang tính — không có chúng thì thanh trượt phải đoán, và lần
    chỉnh đầu tiên của khách sẽ nhảy số vô cớ.

    Tiền là CHUỖI, không phải float: `Decimal` đi qua JSON float mất chính xác
    âm thầm, và đây là con số khách đem đi so với đại lý.
    """

    vehicle_id: UUID
    vehicle_name: str
    total_vnd: str | None
    components: tuple[TcoComponentView, ...] = ()
    daily_distance_km: float = 0.0
    #: `False` khi khách CHƯA nói quãng đường và hệ đang dùng mốc mặc định —
    #: client nên nói ra điều đó ngay cạnh ô nhập.
    daily_distance_known: bool = False
    province_code: str | None = None
    region_code: str = ""
    assumption_note: str = ""
    #: Danh sách tỉnh cho ô chọn, GỬI KÈM luôn thay vì bắt client gọi thêm.
    #:
    #: BUG THẬT Sếp báo 2026-08-27: *"khung chọn khu vực không hiển thị cho người
    #: dùng thấy để chọn"*. Client gọi `/agent/tco/provinces` riêng; lần gọi đó
    #: hỏng là danh sách rỗng, ô chọn bị khoá, và lỗi bị nuốt im lặng — khách thấy
    #: một ô xám không bấm được.
    #:
    #: Danh sách này TĨNH và nhỏ (37 mục). Gửi kèm thì bỏ hẳn được một lần gọi
    #: mạng VÀ cả một đường hỏng: thẻ hiện ra là đã có đủ thứ để chọn.
    province_options: tuple[ProvinceOptionView, ...] = ()
    #: Hệ số để client tính lại tổng tại chỗ. `None` cho mọi chỗ gọi cũ (lõi v1
    #: không dựng nó) — thêm field có mặc định nên không hợp đồng nào vỡ.
    rates: TcoRatesView | None = None


#: `terminal_reason` của một lượt mà phiên đang chờ NGƯỜI xử lý (ownership
#: `PENDING_HANDOFF`): bot im lặng, không trả lời chồng lên bản đang chờ duyệt.
#:
#: Ở `contracts` chứ không ở `chain.py` vì CẢ HAI lõi đều trả mã này, mà lõi v2
#: (`core/run_turn.py`) không được import `chain` (spec mục 6.5b). Hai lõi lệch
#: mã ở đây thì `agent_turn_outcomes` có hai nhãn cho cùng một tình huống và bộ
#: đo bước 4 đọc ra hai nhóm — đúng bài học của `CONTENT_BLOCKED_REASON`.
#:
#: Mã NỘI BỘ: `project_public_result` làm mờ nó thành `UNAVAILABLE` ở biên công
#: khai (nó không nằm trong `_PUBLIC_TERMINAL_REASONS`), y như với lõi cũ.
PENDING_HANDOFF_REASON: Final[str] = "PENDING_HANDOFF"


@dataclass(frozen=True, slots=True)
class TurnResult:
    """DTO câu trả lời — điểm ra duy nhất của `chain.run_turn` cho `api/` (mục 6.5)."""

    session_id: str
    answer: str | None
    pending_question: str | None
    terminal_reason: str | None = None
    lookup_facts: list[VehicleFacts] = field(default_factory=list)
    conversation_state: str | None = None
    options: list[dict[str, str]] | None = None
    vehicle_type: str | None = None
    # A7-4: lượt này đã vào hàng đợi duyệt hay chưa.
    awaiting_review: bool = False
    review_id: UUID | None = None
    turn_status: str = "COMPLETED"
    #: Bản có cấu trúc của cùng nội dung `answer`, cho client muốn dựng card.
    #: Default rỗng nên client cũ không vỡ.
    recommendations: list[RecommendedVehicleView] = field(default_factory=list)
    #: Thẻ chọn lịch lái thử. `None` ở mọi lượt khác.
    test_drive_card: TestDriveCardView | None = None
    #: Thẻ chi tiết xe khách vừa chốt — dữ liệu CÓ CẤU TRÚC.
    #:
    #: `answer` vẫn chở toàn văn như cũ, đúng quy ước `tco_card`/`comparison`:
    #: client chưa render thẻ thì không mất nội dung nào. Field TUỲ CHỌN, nhận
    #: `None` — lệch phiên bản lúc triển khai là chuyện bình thường.
    vehicle_details: VehicleDetailsView | None = None
    #: Panel "Bước tiếp theo" — DỮ LIỆU TRÌNH BÀY, không phải một chặng.
    next_step_panel: NextStepPanel | None = None
    #: Lệnh dẫn khách đi xem (trang xe / bản đồ) — đợt 9. `None` ở mọi lượt khác.
    navigate: NavigateView | None = None
    #: Nút bấm gợi ý cho lượt hỏi xác nhận / hỏi làm rõ. Rỗng ở mọi lượt khác.
    quick_replies: list[QuickReplyView] = field(default_factory=list)
    #: Bảng so sánh của lượt `COMPARE_VEHICLES`. `None` ở mọi lượt khác, nên
    #: client cũ không đổi gì vẫn chạy đúng như trước.
    comparison: VehicleComparisonView | None = None
    #: Danh sách địa điểm của lượt `FIND_NEARBY_LOCATION`.
    nearby_locations: NearbyLocationListView | None = None
    #: Thẻ chi phí 5 năm CÓ CẤU TRÚC của mẫu khách vừa chốt. `None` ở mọi lượt
    #: khác. `answer` vẫn chở khối chữ như cũ — client chưa cập nhật không vỡ.
    tco_card: TcoCardView | None = None
    bottleneck_detection: BottleneckDetectionResult | None = None
    bottleneck_anchor_client_turn_id: UUID | None = None
