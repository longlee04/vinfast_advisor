"""Kiểu trạng thái của lõi v2 và cạnh chặng hợp lệ (spec mục 4).

Mọi thứ ở đây bất biến và thuần: không I/O, không import chain/nodes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from src.agents.domain.values import SlotName, SlotValue


class Stage(StrEnum):
    GREETING = "GREETING"
    COLLECTING = "COLLECTING"
    RECOMMENDED = "RECOMMENDED"
    CHOSEN = "CHOSEN"
    COSTING = "COSTING"
    SCHEDULING = "SCHEDULING"
    OFFER_REVIEW = "OFFER_REVIEW"
    HANDED_OFF = "HANDED_OFF"


class Intent(StrEnum):
    ADVISORY = "ADVISORY"
    CATALOG_LOOKUP = "CATALOG_LOOKUP"
    CATALOG_BROWSE = "CATALOG_BROWSE"
    COMPARE = "COMPARE"
    NEARBY = "NEARBY"
    POLICY_QA = "POLICY_QA"
    VEHICLE_QA = "VEHICLE_QA"
    COST = "COST"
    ON_ROAD_PRICE = "ON_ROAD_PRICE"
    TEST_DRIVE = "TEST_DRIVE"
    OFFER = "OFFER"
    #: Khách XIN gặp người thật (tư vấn viên/nhân viên). Bot dừng ngay, không hỏi thêm.
    HANDOFF = "HANDOFF"
    NONE = "NONE"


class DialogueAct(StrEnum):
    SLOT_ANSWER = "SLOT_ANSWER"
    REQUEST = "REQUEST"
    CHOICE = "CHOICE"
    CONFIRM = "CONFIRM"
    REJECT = "REJECT"
    INTERRUPT = "INTERRUPT"
    SOCIAL = "SOCIAL"
    RESTART = "RESTART"
    UNCLEAR = "UNCLEAR"


class PendingKind(StrEnum):
    SLOT = "SLOT"
    CHOICE = "CHOICE"
    CONFIRM = "CONFIRM"


#: Cạnh chặng hợp lệ ngoài (a) ở nguyên chặng, (b) mọi chặng → HANDED_OFF,
#: (c) mọi chặng → COLLECTING khi RESTART. Spec mục 4.
_EDGES: frozenset[tuple[Stage, Stage]] = frozenset(
    {
        (Stage.GREETING, Stage.COLLECTING),
        #: khách nhắn một câu đủ slot ngay lúc chào → đề xuất luôn.
        (Stage.GREETING, Stage.RECOMMENDED),
        (Stage.COLLECTING, Stage.RECOMMENDED),
        (Stage.RECOMMENDED, Stage.CHOSEN),
        (Stage.CHOSEN, Stage.RECOMMENDED),
        (Stage.CHOSEN, Stage.COSTING),
        (Stage.CHOSEN, Stage.SCHEDULING),
        (Stage.CHOSEN, Stage.OFFER_REVIEW),
        (Stage.COSTING, Stage.CHOSEN),
        # Xem chi phí xong đi đặt lịch (và ngược lại) là hành trình thường —
        # thiếu cạnh này thì lượt lái thử sau thẻ chi phí bị kéo stage sai
        # (probe Đà Nẵng 2026-08-31, luật 5a' trượt).
        (Stage.COSTING, Stage.SCHEDULING),
        (Stage.SCHEDULING, Stage.COSTING),
        (Stage.COSTING, Stage.OFFER_REVIEW),
        (Stage.SCHEDULING, Stage.OFFER_REVIEW),
        (Stage.SCHEDULING, Stage.CHOSEN),
        (Stage.OFFER_REVIEW, Stage.CHOSEN),
        (Stage.HANDED_OFF, Stage.CHOSEN),
    }
)


def can_transition(src: Stage, dst: Stage) -> bool:
    if src is dst or dst is Stage.HANDED_OFF or dst is Stage.COLLECTING:
        return True
    return (src, dst) in _EDGES


def _frozen(mapping: Mapping[Any, Any] | None) -> Mapping[Any, Any]:
    return MappingProxyType(dict(mapping or {}))


@dataclass(frozen=True, slots=True)
class Pending:
    """Bot vừa hỏi gì — để lượt sau hiểu "đi làm thôi" là câu trả lời."""

    kind: PendingKind
    key: str
    #: Giá trị máy (id xe / mã tính năng).
    options: tuple[str, ...] = ()
    #: Nhãn khách đọc được, song song `options` — lưu kèm để lượt sau nối lại
    #: câu hỏi mà không phải tra lại tên xe.
    labels: tuple[str, ...] = ()
    asked_at_turn: int = 0
    #: Tên VIỆC của câu hỏi treo ("đặt lái thử") — để câu NỐI LẠI sau lượt chen
    #: ngang vẫn đúng khung (prod 2026-08-31: "Quay lại câu lúc nãy" đọc lại câu
    #: luồng thông số dù việc treo là lái thử). Rỗng = câu không gắn việc.
    job: str = ""


@dataclass(frozen=True, slots=True)
class CoreState:
    session_id: str
    stage: Stage = Stage.GREETING
    intent: Intent = Intent.NONE
    slots: Mapping[SlotName, SlotValue] = field(default_factory=lambda: _frozen({}))
    pending: Pending | None = None
    chosen_vehicle_id: str | None = None
    recommended_ids: tuple[str, ...] = ()
    ask_counts: Mapping[str, int] = field(default_factory=lambda: _frozen({}))
    turn_count: int = 0
    #: Id lịch lái thử ĐÃ ĐẶT THÀNH CÔNG trong phiên (`act._book`). Lượt sau cần
    #: hiểu khác đi vì nó: câu kết không mời "đặt lái thử" nữa mà hỏi "cần gì
    #: thêm trước ngày lái thử", và panel bước kế đổi thành "Xem lịch của tôi".
    #: Đúng luật "state chỉ tồn tại khi lượt SAU cần hiểu khác đi vì nó".
    booking_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "slots", _frozen(self.slots))
        object.__setattr__(self, "ask_counts", _frozen(self.ask_counts))
        object.__setattr__(self, "recommended_ids", tuple(self.recommended_ids))

    def with_(self, **changes: Any) -> CoreState:
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class Understanding:
    """Kết quả một cửa LLM sau khi `validate` (spec mục 5)."""

    dialogue_act: DialogueAct
    intent: Intent
    slots: Mapping[SlotName, SlotValue] = field(default_factory=lambda: _frozen({}))
    vehicle_ids: tuple[str, ...] = ()
    choice_ref: str | None = None
    confidence: float = 1.0
    features_all: bool = False
    question: str = ""
    #: Lượt này có hỏi ĐỘ PHÙ HỢP không ("có hợp với nhu cầu của tôi không",
    #: "được không", "ổn không"). Đọc TẤT ĐỊNH ở `understand`: LLM gắn act
    #: CHOICE cho nguyên câu đó và câu hỏi bị nuốt mất (prod vòng 9).
    fit_asked: bool = False
    #: Lượt này có hỏi CÁCH ĐI TIẾP không ("làm sao để tôi chốt vf3", "thủ tục
    #: đặt cọc thế nào"). Cũng đọc tất định ở `understand`: LLM gán ADVISORY
    #: cho câu đó và lõi đề xuất lại đúng chiếc khách vừa nói là muốn chốt.
    next_steps_asked: bool = False
    #: Lượt này có hỏi thứ NGOÀI phạm vi tư vấn xe không ("VF3 thì nên đi du
    #: lịch ở Việt Nam, ở đâu"). Không có cờ này thì câu đó rơi vào đường xin
    #: CHỈNH đề xuất và khách nhận "em chưa có mẫu nào khác hợp hơn" (prod vòng 9).
    off_topic_asked: bool = False
    #: Lượt này có phải lời DỪNG không ("thôi không tư vấn nữa", "khỏi", "để
    #: sau"). Đọc TẤT ĐỊNH ở `understand`, KHÔNG tin `dialogue_act=REJECT` một
    #: mình: đo trên máy 2026-09-23, LLM gắn REJECT cho cả "rẻ hơn đi" — một
    #: lời XIN CHỈNH — và lượt đó bị đọc thành khách bỏ cuộc.
    stop_asked: bool = False
    #: Trang bị khách hỏi CÓ/KHÔNG ("có trợ lý ảo không"), hoặc rỗng. Đọc TẤT
    #: ĐỊNH ở `understand` (`domain/feature_question`). Đo trên máy 2026-09-23:
    #: câu này khi CHƯA nêu xe nào bị đẩy sang hỏi ngân sách — khách hỏi một
    #: trang bị mà bot hỏi tiền là trả lời sai ý định.
    feature_asked: str = ""
    #: Chủ đề LO NGẠI của lượt ("pin chai bán ai mua", "hầm chung cư chưa có trụ
    #: sạc") — đọc TẤT ĐỊNH ở `understand`. Rỗng = không phải câu lo ngại. Log
    #: prod 2026-08-31: các câu này bị LLM gắn act lửng lơ và rơi vào câu mặc
    #: định "muốn xem kỹ mẫu nào ạ?" — nỗi lo của khách bị nuốt trong im lặng.
    concern_topic: str = ""
    #: Mã thời điểm định mua (`domain.purchase_timeframe`) khi lượt này TRẢ LỜI câu
    #: hỏi 4G của lượt ngay trước — `run_turn` chỉ gắn đúng lượt đó. Rỗng = không phải.
    purchase_timeframe: str = ""
    #: KHÍA CẠNH khách hỏi về một mẫu ở lượt tra cứu — hiện chỉ có "price" (xem
    #: `actions.ASPECT_PRICE`). Đọc tất định ở `understand`: "giá con vf8 mới"
    #: về `CATALOG_LOOKUP` và `act` trả NGUYÊN bảng thông số (động cơ, ADAS…)
    #: cho một câu hỏi tiền (prod benchmark2 2026-08-30). Rỗng = không rõ khía
    #: cạnh, trả bảng tổng quan như cũ.
    aspect: str = ""
    #: Tên xe khách VỪA NÊU mà danh bạ không giải được ("VF 10", "Evo") — chỉ
    #: khi `vehicle_ids` rỗng. Đọc tất định ở `understand`. Không có nó thì
    #: policy hỏi "mẫu nào?" ngay sau khi khách nói tên (prod benchmark2).
    unresolved_mention: str = ""
    #: Nhãn của LỚP HỘI THOẠI (`domain.conversational.ConversationalIntent`):
    #: khen/chê/phân vân/đồng ý/cảm ơn/tạm biệt/tán gẫu/chào — đọc TẤT ĐỊNH ở
    #: `understand` có ngữ cảnh lượt trước. Rỗng = câu không thuộc lớp này.
    conversational: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "slots", _frozen(self.slots))


UNCLEAR_UNDERSTANDING = Understanding(dialogue_act=DialogueAct.UNCLEAR, intent=Intent.NONE, confidence=0.0)
