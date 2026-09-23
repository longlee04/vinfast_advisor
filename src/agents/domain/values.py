"""Domain value object thuần của module `agent` (mục 6.0/§2.1 team_split).

THUẦN Python — không import FastAPI/SQLAlchemy/LangGraph/LLM SDK (mục 6.5b).
Đóng băng ở Ngày 0: đổi chữ ký (thêm/bớt/đổi kiểu) là một PR riêng, cả 4 người
duyệt (§2.2 docs/team_split.md). Đổi thân hàm (không áp dụng ở đây, toàn value
object) là tự do.

Không tái dùng `src.products.domain.values.VehicleType` dù trùng nghĩa: mỗi
module giữ domain value riêng, chỉ giao tiếp qua port/adapter (modular
monolith, `docs/backend-module-standard.md`) — cùng quy ước auth/document/product
đang áp dụng (không module nào import domain của module khác).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Final


class VehicleType(StrEnum):
    """Khớp `ck_vehicles_vehicle_type` (`docs/vehicle-catalog-schema.md` §4.1)."""

    CAR = "CAR"
    ELECTRIC_MOTORBIKE = "ELECTRIC_MOTORBIKE"


class Intent(StrEnum):
    """A4-1/A4-6: một lượt có thể mang nhiều intent (câu lai, mục 6.10).

    Ba intent gốc khác nhau ở thứ khách ĐƯA VÀO — xem docstring các thành viên
    bên dưới. `MORE_FEATURES` KHÔNG cùng nhóm: nó không mô tả thứ khách đưa
    vào mà là một yêu cầu MỞ RỘNG câu hỏi lượt 2 đang chờ ("còn tính năng nào
    khác không") — cờ độc lập, không loại trừ các intent khác trong cùng lượt.

    - `ADVISORY` — khách đưa TIÊU CHÍ CÁ NHÂN (ngân sách, số người, quãng đường)
      và cần chọn hộ.
    - `CATALOG_LOOKUP` — khách đưa TÊN MỘT MẪU XE và cần số liệu của đúng xe đó.
    - `CATALOG_BROWSE` — khách đưa TÊN MỘT LOẠI XE và cần biết loại đó gồm những
      xe nào. Không có tên mẫu để tra, cũng không có tiêu chí để lọc, nên cả hai
      nhánh trên đều không trả lời được: đưa "xe máy điện" vào `CATALOG_LOOKUP`
      là đi tìm một mẫu xe tên "xe máy điện" và tất nhiên không thấy.
    - `COMPARE_VEHICLES` — khách đưa TỪ HAI TÊN MẪU XE trở lên và cần biết chúng
      khác nhau ở đâu. Khác `CATALOG_LOOKUP` ở thứ khách cần nhận: tra cứu trả
      bảng thông số của từng xe nối đuôi nhau, còn so sánh phải đặt chúng cạnh
      nhau theo cùng một bộ tiêu chí thì mới trả lời được câu "chọn cái nào".

    Thêm `COMPARE_VEHICLES` là THÊM một thành viên enum, không đổi chữ ký nào
    đang có — bộ trích slot vẫn không bao giờ phát nhãn này (prompt LLM không
    nhắc tới nó), `domain/intent_reconciliation.reconcile_intents` gắn nó một
    cách tất định. Nhờ vậy lượt so sánh không tốn thêm lần gọi LLM nào ở bước
    hiểu ý (A4-2).

    - `MORE_FEATURES` — khách đang ở lượt 2 (đã được hỏi tính năng quan tâm) và
      xin xem thêm lựa chọn khác ngoài các tính năng vừa gợi ý, KHÔNG nêu tiêu
      chí cá nhân mới.
    """

    ADVISORY = "ADVISORY"
    CATALOG_LOOKUP = "CATALOG_LOOKUP"
    CATALOG_BROWSE = "CATALOG_BROWSE"
    COMPARE_VEHICLES = "COMPARE_VEHICLES"
    FIND_NEARBY_LOCATION = "FIND_NEARBY_LOCATION"
    FIND_CHARGING_STATION = "FIND_CHARGING_STATION"
    MORE_FEATURES = "MORE_FEATURES"


class IntentType(StrEnum):
    """Primary intent taxonomy used by the Agentic RAG router."""

    VEHICLE_DISCOVERY = "VEHICLE_DISCOVERY"
    VEHICLE_INFO = "VEHICLE_INFO"
    COMPARISON = "COMPARISON"
    PRICE_TCO_QUERY = "PRICE_TCO_QUERY"
    POLICY_QUERY = "POLICY_QUERY"
    TRANSACTION_REQUEST = "TRANSACTION_REQUEST"
    HUMAN_REQUEST = "HUMAN_REQUEST"
    COMPLAINT = "COMPLAINT"
    OTHER = "OTHER"


class EmotionLevel(StrEnum):
    """Customer emotion classification used for response tone and escalation."""

    NORMAL = "NORMAL"
    FRUSTRATED = "FRUSTRATED"
    ANGRY = "ANGRY"
    ABUSIVE_OR_THREAT = "ABUSIVE_OR_THREAT"


class Topic(StrEnum):
    """Câu của khách đang NÓI VỀ cái gì — trục thứ ba của việc hiểu lượt.

    Tách khỏi `IntentType` (khách MUỐN gì) vì một nhiệm vụ chạy trên nhiều chủ đề
    và ngược lại: "VF 8 bảo hành mấy năm" là nhiệm vụ hỏi-chính-sách trên chủ đề
    `POLICY`, còn "VF 8 giá bao nhiêu" cùng dạng câu nhưng chủ đề `PRICE_TCO`.
    Gộp hai trục thì bảng nhãn nở theo tích số.
    """

    VEHICLE = "VEHICLE"
    PRICE_TCO = "PRICE_TCO"
    POLICY = "POLICY"
    LOCATION = "LOCATION"
    CHARGING = "CHARGING"
    TRANSACTION = "TRANSACTION"
    CUSTOMER_EXPERIENCE = "CUSTOMER_EXPERIENCE"
    OTHER = "OTHER"


class Severity(StrEnum):
    """Mức khẩn vận hành của lượt, tách khỏi `EmotionLevel`.

    `EmotionLevel` nói khách đang CẢM THẤY gì; `Severity` nói hệ thống PHẢI làm
    gì. Một khách bình tĩnh báo xe bốc khói là `NORMAL` về cảm xúc nhưng
    `CRITICAL` về xử lý — gộp hai thang lại thì mất đúng ca đó.
    """

    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    CRITICAL = "CRITICAL"


class HitlReason(StrEnum):
    """Reasons that require advisor review or direct human intervention."""

    CUSTOMER_REQUESTED_HUMAN = "CUSTOMER_REQUESTED_HUMAN"
    PURCHASE_INTENT = "PURCHASE_INTENT"
    TRANSACTION_REQUEST = "TRANSACTION_REQUEST"
    POLICY_APPLICATION = "POLICY_APPLICATION"
    CREDIT_ASSESSMENT = "CREDIT_ASSESSMENT"
    PROMOTION_APPLICATION = "PROMOTION_APPLICATION"
    USED_CAR_VALUATION = "USED_CAR_VALUATION"
    BUYBACK_ASSESSMENT = "BUYBACK_ASSESSMENT"
    WARRANTY_ASSESSMENT = "WARRANTY_ASSESSMENT"
    ROADSIDE_ASSISTANCE = "ROADSIDE_ASSISTANCE"
    CONTRACT_ACTION = "CONTRACT_ACTION"
    COMPLAINT = "COMPLAINT"
    HIGH_FRUSTRATION = "HIGH_FRUSTRATION"
    ABUSIVE_LANGUAGE = "ABUSIVE_LANGUAGE"
    THREAT = "THREAT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class PurposeBucket(StrEnum):
    """Nhóm mục đích suy từ `purpose` — khoá cho allowlist feature (T7).

    Sống ở đây (không phải `slot_mapping.py`, nơi định nghĩa gốc) vì
    `contracts.py` cần import kiểu này cho `LLMExtractionPayload`, còn
    `slot_mapping.py` lại import ngược từ `contracts.py` (`FilterCriteria`) —
    để `PurposeBucket` ở `slot_mapping.py` sẽ tạo vòng lặp import.
    """

    FAMILY = "family"
    WORK = "work"
    SERVICE = "service"
    DELIVERY = "delivery"
    #: Đi tỉnh, về quê, chạy đường dài (Sếp 2026-08-25).
    #:
    #: Trước đây "về quê" rơi về `PERSONAL`, mà nhóm đó KHÔNG có nhánh chấm điểm
    #: nào — khách nói mục đích rõ ràng mà không đổi được thứ hạng xe nào. Nhóm
    #: riêng vì tiêu chí của nó khác hẳn bốn nhóm kia: thứ quyết định là TẦM CHẠY
    #: và sạc nhanh, không phải cốp xe hay tải trọng.
    LONG_TRIP = "long_trip"
    PERSONAL = "personal"
    UNKNOWN = "unknown"


class RunState(StrEnum):
    """8 state của `agent_runs` (mục 5, `agent_0003`), CAPTURING là state đầu."""

    CAPTURING = "CAPTURING"
    SNAPSHOT_READY = "SNAPSHOT_READY"
    PACKAGE_READY = "PACKAGE_READY"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class ScopeLabel(StrEnum):
    """A6-2: nhãn phân loại ngoài phạm vi, ghi vào `out_of_scope_log`.

    `SOCIAL` tách chào hỏi/cảm ơn khỏi `OUT_OF_SCOPE`: hai nhãn này dẫn tới hai
    hành vi trái ngược — một bên đi tiếp cuộc tư vấn, một bên dừng lượt — nên gộp
    chúng làm khách chào một câu là hội thoại chết.

    ``MISSING_DATA`` được giữ để đọc dữ liệu/audit cũ. Production scope không còn
    phát nhãn này: đủ entity/slot hay đủ dữ liệu nguồn là quyết định của router,
    slot planner và retrieval sau khi intent đã được hiểu.
    """

    IN_SCOPE = "IN_SCOPE"
    SOCIAL = "SOCIAL"
    MISSING_DATA = "MISSING_DATA"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class DialogueAct(StrEnum):
    """What the customer is doing in the current turn, independent of topic."""

    REQUEST = "REQUEST"
    SLOT_ANSWER = "SLOT_ANSWER"
    ACKNOWLEDGMENT = "ACKNOWLEDGMENT"
    #: Khách chê hoặc lo ngại. Là HÀNH VI, không phải nhiệm vụ: một lượt vừa chê
    #: vừa hỏi thông tin vẫn giữ `COMPLAIN` ở trục này còn nhiệm vụ đi theo câu
    #: hỏi chính. Không có nhãn này thì "Đắt quá, VF 8 giá bao nhiêu?" buộc phải
    #: chọn một nửa để vứt đi.
    COMPLAIN = "COMPLAIN"
    CORRECTION = "CORRECTION"
    REJECTION = "REJECTION"
    SOCIAL = "SOCIAL"
    UNKNOWN = "UNKNOWN"


class TaskAction(StrEnum):
    """How the current request relates to the focused cross-turn task."""

    NONE = "NONE"
    START_NEW_TASK = "START_NEW_TASK"
    CONTINUE_TASK = "CONTINUE_TASK"
    CLARIFY_TASK = "CLARIFY_TASK"
    INTERRUPT_WITH_LOOKUP = "INTERRUPT_WITH_LOOKUP"
    REVISE_RESULTS = "REVISE_RESULTS"
    RESTART_TASK = "RESTART_TASK"
    RESUME_TASK = "RESUME_TASK"
    CANCEL_TASK = "CANCEL_TASK"


class SlotName(StrEnum):
    """Cây slot A3-1 (mục 7.0 `docs/vehicle-catalog-schema.md`).

    `PASSENGER_COUNT` chỉ nhánh CAR; `MAX_LOAD_KG` chỉ nhánh giao hàng của
    ELECTRIC_MOTORBIKE. `HABIT_NEED_TAGS` là slot mở cuối cây, nạp nhánh 2b (A1-7).
    `BUDGET_MIN_VND` không nằm trong thứ tự hỏi — xem chú thích tại chỗ khai báo.

    `PURPOSE_BUCKET` không nằm trong luồng hỏi (`SLOT_ORDER`) — chỉ là kết quả
    LLM đóng gói của `purpose`, dùng để chọn allowlist tính năng lượt 2, không
    bao giờ được hỏi trực tiếp.
    """

    VEHICLE_TYPE = "vehicle_type"
    PASSENGER_COUNT = "passenger_count"
    REQUIRED_RANGE_KM = "required_range_km"
    HOME_CHARGING = "home_charging"
    BUDGET_MAX_VND = "budget_max_vnd"
    #: SÀN ngân sách. Không bao giờ được HỎI riêng — nó luôn đi kèm câu trả lời
    #: cho `BUDGET_MAX_VND` ("từ 300 đến 700 triệu" là một câu, không phải hai), nên
    #: nó nằm ngoài `slot_tree.SLOT_ORDER`. Thiếu sàn là chuyện bình thường: phần
    #: lớn khách chỉ nói trần.
    BUDGET_MIN_VND = "budget_min_vnd"
    #: Con số ngân sách khách NÓI RA, giữ nguyên văn, không nới biên.
    #:
    #: Không bao giờ được hỏi (như `PURPOSE_BUCKET`) và không tham gia lọc. Nó
    #: chỉ tồn tại để nhắc lại cho khách đúng lời họ vừa nói: "khoảng 500 triệu"
    #: nới thành dải 400–600 để không bỏ sót xe, nhưng đáp "ngân sách khoảng 600
    #: triệu" là nói lại một con số họ không hề nói (Sếp 2026-08-25).
    #:
    #: `None` khi khách nêu một KHOẢNG hoặc một biên ("từ 400 đến 600", "dưới
    #: 500") — lúc đó chính hai biên đã là lời khách, không cần con số thứ ba.
    BUDGET_STATED_VND = "budget_stated_vnd"
    PURPOSE = "purpose"
    PURPOSE_BUCKET = "purpose_bucket"
    MAX_LOAD_KG = "max_load_kg"
    HABIT_NEED_TAGS = "habit_need_tags"
    #: Tỉnh/thành khách sẽ ĐĂNG KÝ xe — mã tỉnh của `pricing_intent.PROVINCES`.
    #:
    #: **Không phải nơi khách đang đứng.** Vị trí trình duyệt (`user_location`)
    #: trả lời câu "showroom nào gần khách nhất"; slot này trả lời câu "lệ phí
    #: biển số bao nhiêu". Người ở Hà Nội đăng ký xe ở quê là chuyện thường, nên
    #: gộp hai thứ vào một trường là để khách đổi tỉnh đăng ký rồi thấy showroom
    #: lái thử nhảy sang tỉnh khác (Sếp 2026-08-26).
    #:
    #: Không bao giờ HỎI trong bước thu thập: suy từ vị trí trình duyệt trước,
    #: và khách sửa được ngay dưới bảng chi phí. Chỉ hỏi khi sắp đặt lái thử mà
    #: không có vị trí nào — lúc đó không có nó thì không tìm nổi showroom.
    REGISTRATION_PROVINCE = "registration_province"
    #: Mẫu xe khách VỪA XEM/HỎI riêng ("chi tiết VF 5", "Tôi chọn VF 5") — không phải
    #: tiêu chí lọc (không nằm trong ADVISORY_CRITERION_SLOTS), chỉ là bối cảnh: lái
    #: thử / lăn bánh không hỏi lại "mẫu nào", và bản đề xuất nhắc tới nó (Sếp 2026-08-29).
    INTEREST_VEHICLE = "interest_vehicle"


# Giá trị một slot có thể mang — nguyên thuỷ hoặc list (HABIT_NEED_TAGS là nhiều tag).
SlotValue = str | int | float | bool | list[str] | None

# Text sentinel: persists in the existing text column and makes a declined slot
# count as answered without requiring a database migration.
DECLINED_SLOT_VALUE: Final[str] = "__declined__"


#: Hai nhãn cùng chỉ nhánh "tìm địa điểm gần nhất"
NEARBY_LOCATION_INTENTS: Final[frozenset[str]] = frozenset(
    {Intent.FIND_NEARBY_LOCATION.value, Intent.FIND_CHARGING_STATION.value}
)


def is_declined(value: SlotValue) -> bool:
    """Return whether a slot records that the customer could not answer it."""

    return value == DECLINED_SLOT_VALUE


@dataclass(frozen=True, slots=True)
class Money:
    """VND — luôn nguyên đồng. `Decimal` + half-up ở biên component (mục 4.11 schema)."""

    amount_vnd: Decimal

    def __post_init__(self) -> None:
        if self.amount_vnd != self.amount_vnd.to_integral_value():
            raise ValueError(f"Money.amount_vnd phải là số nguyên đồng, nhận {self.amount_vnd!r}")
