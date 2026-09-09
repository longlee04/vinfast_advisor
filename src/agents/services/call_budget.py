"""Ngân sách gọi provider của MỘT lượt, tách theo request bằng `ContextVar`.

Đặt ở `services/` chứ không ở `adapters/`: đây là chính sách của lượt, còn
adapter chỉ là nơi hỏi xin phép. Đếm ở đây là đếm **lần gọi provider thật**,
không phải lần gọi service hay node — một service fan-out ra ba xe là ba lần.

Hai hạn mức TÁCH RỜI (quyết định B, Sếp chốt 2026-08-24):

- `REQUIRED` — 4 slot: 1 trích slot + 1 synthesis + 2 lượt retry của A6-1.
- `OPTIONAL` — 1 slot RIÊNG, nằm ngoài 4 slot trên.

Vì sao tách chứ không dùng một trần chung: `detect_bottleneck` nằm ngay trên
đường đi tới `synthesize`, nên một lượt hoàn toàn có thể cần
`trích slot + nút thắt + ba lượt synthesis`. Với một trần chung là 4 thì hoặc
phải chặn phát hiện nút thắt, hoặc phải cắt lượt retry thứ hai của A6-1 — cả
hai đều là mất mát thật. Tách hạn mức làm điều khoản "việc tuỳ chọn không bao
giờ cướp slot bắt buộc" thành **bất biến của cấu trúc dữ liệu**, chứ không phải
một con số phải chỉnh lại mỗi khi thêm một việc tuỳ chọn.

Việc tuỳ chọn cạn hạn mức thì `take` trả `False` và nơi gọi PHẢI rơi về bản tất
định. Việc bắt buộc cạn thì `claim` ném lỗi CÓ KIỂU để đường trên rẽ sang tư vấn
viên — không bao giờ để thành 500.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from enum import StrEnum
from typing import Final

#: Slot cho việc BẮT BUỘC. Đổi số này là đổi hợp đồng A6-1 — phải qua quyết định.
REQUIRED_CALLS_PER_TURN: Final[int] = 4

#: Slot cho việc TUỲ CHỌN. Một lượt chỉ được một việc tuỳ chọn dùng LLM; việc
#: thứ hai rơi về bản tất định. Giữ ở 1 để chi phí mỗi lượt còn dự đoán được.
OPTIONAL_CALLS_PER_TURN: Final[int] = 1


class CallKind(StrEnum):
    """Lần gọi này có phải thứ lượt KHÔNG THỂ thiếu hay không.

    `REQUIRED` — thiếu nó thì lượt không có câu trả lời: trích slot, synthesis
    và các lượt retry của synthesis.

    `OPTIONAL` — thiếu nó lượt vẫn trả lời được bằng bản tất định: diễn đạt lại
    câu hỏi, câu dẫn tìm địa điểm, tóm tắt bảng so sánh, phát hiện nút thắt.
    """

    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"


class CallBudgetExhaustedError(RuntimeError):
    """Việc bắt buộc xin thêm một lần gọi khi hạn mức đã cạn.

    Cố ý KHÔNG mang theo prompt hay bản nháp: lỗi này đi vào log và lên tới biên
    HTTP, mà cả hai chỗ đó đều không được chứa chữ của khách hay của mô hình.
    """

    def __init__(self, kind: CallKind) -> None:
        super().__init__(f"llm call budget exhausted for {kind.value} work")
        self.kind = kind


class TurnCallBudget:
    """Bộ đếm của đúng một lượt. KHÔNG dùng chung giữa các lượt."""

    __slots__ = ("_provider_calls", "_remaining")

    def __init__(
        self,
        *,
        required: int = REQUIRED_CALLS_PER_TURN,
        optional: int = OPTIONAL_CALLS_PER_TURN,
    ) -> None:
        self._remaining: dict[CallKind, int] = {
            CallKind.REQUIRED: required,
            CallKind.OPTIONAL: optional,
        }
        self._provider_calls = 0

    @property
    def provider_calls(self) -> int:
        """Số lần CHẠM provider thật trong lượt — chỉ để quan sát, không chặn.

        Tách khỏi quota vì hai con số trả lời hai câu hỏi: quota hỏi "được làm
        thêm một THAO TÁC nữa không", metric hỏi "thao tác đó tốn bao nhiêu lần
        gọi". Một lượt thử synthesis tiêu đúng một slot nhưng chạm provider
        `pitched_count` lần — không có metric thì con số sau vô hình.
        """

        return self._provider_calls

    def record_provider_call(self) -> None:
        """Ghi nhận một lần chạm provider. KHÔNG đụng tới quota."""

        self._provider_calls += 1

    def remaining(self, kind: CallKind) -> int:
        """Số lần gọi còn lại của một loại."""

        return self._remaining[kind]

    def take(self, kind: CallKind) -> bool:
        """Xin một lần gọi. `False` nghĩa là hết — nơi gọi tự lo đường lui.

        Dùng cho việc TUỲ CHỌN. Việc bắt buộc nên dùng `claim`.
        """

        if self._remaining[kind] <= 0:
            return False
        self._remaining[kind] -= 1
        return True

    def claim(self, kind: CallKind) -> None:
        """Như `take` nhưng cạn thì ném lỗi có kiểu. Dùng cho việc BẮT BUỘC."""

        if not self.take(kind):
            raise CallBudgetExhaustedError(kind)


_CURRENT: ContextVar[TurnCallBudget | None] = ContextVar("agent_turn_call_budget", default=None)


def current_call_budget() -> TurnCallBudget | None:
    """Ngân sách của lượt đang chạy, hoặc `None` khi đang ở ngoài một lượt.

    `None` nghĩa là KHÔNG áp trần — đúng cho script, cho eval offline và cho các
    test cũ chưa biết tới ngân sách. Mặc định phải là "không chặn": một bộ đếm
    tự bật ở nơi không ai dựng nó sẽ chặn nhầm những đường đang chạy tốt.
    """

    return _CURRENT.get()


@contextmanager
def use_call_budget(budget: TurnCallBudget) -> Iterator[TurnCallBudget]:
    """Gắn ngân sách vào lượt hiện tại rồi trả lại nguyên trạng khi xong.

    Dùng `Token` để khôi phục thay vì gán `None`: lượt lồng trong lượt (test,
    replay) phải trả về đúng ngân sách bên ngoài, không phải xoá trắng.
    """

    token: Token[TurnCallBudget | None] = _CURRENT.set(budget)
    try:
        yield budget
    finally:
        _CURRENT.reset(token)


__all__ = [
    "OPTIONAL_CALLS_PER_TURN",
    "REQUIRED_CALLS_PER_TURN",
    "CallBudgetExhaustedError",
    "CallKind",
    "TurnCallBudget",
    "current_call_budget",
    "use_call_budget",
]
