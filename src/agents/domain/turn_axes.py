"""Bốn trục hiểu một lượt, tách rời nhau, cộng phép chiếu về nhãn cũ.

Bốn trục:

- **hành vi hội thoại** (`DialogueAct`) — khách đang LÀM gì: hỏi, phàn nàn, đáp slot.
- **nhiệm vụ** (`IntentType`) — khách MUỐN gì: tìm xe, hỏi thông số, so sánh, hỏi giá…
- **chủ đề** (`Topic`) — câu ĐANG NÓI về cái gì, một chính và tối đa ba phụ.
- **mức khẩn** (`Severity`) — hệ thống PHẢI làm gì gấp đến đâu.

Vì sao tách: gộp lại thì câu *"Đắt quá, VF 8 giá bao nhiêu?"* buộc phải chọn một
— hoặc là phàn nàn, hoặc là hỏi giá. Chọn kiểu nào cũng mất một nửa. Tách ra thì
hành vi là *phàn nàn* mà nhiệm vụ vẫn là *hỏi giá*, và cả hai cùng được đáp.

`IntentType` vốn đã có trong `values.py` nhưng chưa ai dùng. Tái dùng nó làm trục
nhiệm vụ thay vì đẻ enum thứ hai — hai bảng phân loại song song là mầm bug.

Phép chiếu `project_legacy_intents` là đường MỘT CHIỀU sang `Intent` cũ để routing
hiện hữu chạy tiếp. Nó chỉ ĐỌC bốn trục và không bao giờ là nguồn sự thật thứ hai.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from src.agents.domain.values import (
    DialogueAct,
    Intent,
    IntentType,
    Severity,
    Topic,
)

#: Trần chủ đề phụ. Quá ba thì câu đã mơ hồ tới mức nhãn không còn dùng được để
#: định tuyến, và giữ thêm chỉ làm prompt dài ra.
MAX_SECONDARY_TOPICS: Final[int] = 3


@dataclass(frozen=True, slots=True)
class TurnAxes:
    """Bốn trục của đúng một lượt. Bất biến."""

    dialogue_act: DialogueAct
    task: IntentType
    primary_topic: Topic
    secondary_topics: tuple[Topic, ...] = ()
    severity: Severity = Severity.NORMAL
    #: Mô hình đọc được ý muốn gặp người. HỢP với tín hiệu keyword ở
    #: `domain/escalation`, không thay thế nó.
    human_requested: bool = False

    def __post_init__(self) -> None:
        cleaned: list[Topic] = []
        for topic in self.secondary_topics:
            if topic is self.primary_topic or topic in cleaned:
                continue
            cleaned.append(topic)
        object.__setattr__(self, "secondary_topics", tuple(cleaned[:MAX_SECONDARY_TOPICS]))


def coerce_topic(value: object) -> Topic:
    """Chuỗi bất kỳ → `Topic`; không đọc được thì `OTHER`.

    Rơi về `OTHER` chứ không raise: mô hình trả một nhãn lạ là chuyện thường, và
    làm chết cả lượt vì một nhãn phụ là phản ứng quá tay.
    """

    if isinstance(value, Topic):
        return value
    if isinstance(value, str):
        try:
            return Topic(value.strip().upper())
        except ValueError:
            return Topic.OTHER
    return Topic.OTHER


def coerce_topics(values: object) -> tuple[Topic, ...]:
    """Danh sách chủ đề phụ, giữ nguyên thứ tự, bỏ mục không đọc được."""

    if not isinstance(values, Sequence) or isinstance(values, str | bytes):
        return ()
    return tuple(coerce_topic(item) for item in values)


#: Nhiệm vụ KHÔNG có thẩm quyền lái routing cũ. Chúng có đường đi riêng —
#: chính sách và giao dịch chưa nối, còn xin gặp người thì chốt tất định đã bắt
#: từ trước graph. Chiếu chúng sang `ADVISORY` sẽ khiến một câu hỏi bảo hành
#: chạy cả pipeline tư vấn rồi trả về danh sách xe.
_NO_LEGACY_AUTHORITY: Final[frozenset[IntentType]] = frozenset(
    {
        IntentType.POLICY_QUERY,
        IntentType.TRANSACTION_REQUEST,
        IntentType.HUMAN_REQUEST,
        #: Chê suông không phải một yêu cầu tra cứu. Lượt VỪA chê VỪA hỏi thì
        #: nhiệm vụ đã mang giá trị khác `COMPLAINT`, nên nhánh này không chạm tới.
        IntentType.COMPLAINT,
        IntentType.OTHER,
    }
)


def project_legacy_intents(task: IntentType, *, vehicle_mentions: Sequence[str] = ()) -> list[Intent]:
    """Chiếu trục NHIỆM VỤ sang nhãn `Intent` cũ cho routing hiện hữu.

    Một chiều và chỉ đọc. Danh sách rỗng nghĩa là *"nhiệm vụ này không lái được
    routing cũ"* — người gọi phải tự có đường xử lý, không được coi rỗng là
    `ADVISORY`.
    """

    if task in _NO_LEGACY_AUTHORITY:
        return []
    if task is IntentType.VEHICLE_DISCOVERY:
        return [Intent.ADVISORY]
    if task is IntentType.COMPARISON:
        return [Intent.COMPARE_VEHICLES]
    if task is IntentType.VEHICLE_INFO:
        # Có tên mẫu thì tra cứu đúng mẫu đó; chỉ nêu LOẠI xe thì là xem danh mục.
        return [Intent.CATALOG_LOOKUP if vehicle_mentions else Intent.CATALOG_BROWSE]
    if task is IntentType.PRICE_TCO_QUERY:
        # Hỏi giá một mẫu cụ thể là tra cứu; hỏi giá chung chung vẫn là tư vấn,
        # vì chưa biết xe nào thì câu trả lời phải đi qua bước thu hẹp nhu cầu.
        return [Intent.CATALOG_LOOKUP if vehicle_mentions else Intent.ADVISORY]
    return []


__all__ = [
    "MAX_SECONDARY_TOPICS",
    "TurnAxes",
    "coerce_topic",
    "coerce_topics",
    "project_legacy_intents",
]
