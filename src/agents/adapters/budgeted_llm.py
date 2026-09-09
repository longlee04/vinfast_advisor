"""Bọc ngân sách quanh biên gọi provider THẬT.

Bọc ở đây chứ không bọc quanh node hay service: một service fan-out ra ba xe là
ba lần chạm provider, đếm ở tầng trên sẽ đếm thành một.

Loại việc (`REQUIRED` / `OPTIONAL`) được chốt ở CHỖ TIÊM, không suy từ tên
method. Ba nơi khác nhau — synthesis, câu dẫn tìm địa điểm, tóm tắt bảng so sánh
— đều gọi đúng một `synthesize(prompt=...)`, nên nhìn vào method là không phân
biệt được cái nào bắt buộc. `composition` biết nó đang lắp cho ai, nên nó là chỗ
duy nhất nói được điều đó.

Hai kiểu từ chối, theo đúng quy ước sẵn có của từng nơi gọi:

- `OPTIONAL` cạn hạn mức → trả chuỗi RỖNG. Cả ba nơi gọi đều đã coi rỗng là tín
  hiệu rơi về bản tất định (`text or _fallback_...`), nên không cần sửa chúng.
- `REQUIRED` cạn hạn mức → ném `CallBudgetExhaustedError`. Lỗi có kiểu để đường
  trên rẽ sang tư vấn viên chứ không thành 500.

Không có ngân sách nào đang gắn (script, eval offline, test cũ) thì lớp này chỉ
chuyển tiếp — xem `current_call_budget`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.agents.domain.bottleneck_signal import (
    BottleneckDetectionStatus,
    BottleneckUnavailable,
)
from src.agents.services.call_budget import CallKind, current_call_budget

if TYPE_CHECKING:
    from src.agents.contracts import LLMExtractionPayload
    from src.agents.domain.conversation_memory import WorkingMemoryProjection
    from src.agents.domain.values import VehicleType


def _record() -> None:
    """Ghi nhận một lần chạm provider. KHÔNG tiêu quota.

    Quota là chính sách và được tiêu ở tầng ĐIỀU PHỐI, nơi biết đâu là ranh giới
    một thao tác. Wrapper ở đây chỉ đứng đúng chỗ để ĐẾM: nó là điểm duy nhất
    thấy được số lần chạm provider thật, kể cả khi một thao tác fan-out.
    """

    budget = current_call_budget()
    if budget is not None:
        budget.record_provider_call()


@dataclass(frozen=True, slots=True)
class MeteredWriter:
    """Bọc một `synthesize(prompt=...)` bất kỳ để ĐẾM lần chạm provider.

    Không tiêu quota: quota là chính sách và thuộc tầng điều phối, nơi biết ranh
    giới một thao tác. Wrapper này chỉ đứng đúng chỗ để đo.
    """

    inner: Any

    async def synthesize(self, *, prompt: str) -> str:
        _record()
        return await self.inner.synthesize(prompt=prompt)


@dataclass(frozen=True, slots=True)
class MeteredLLM:
    """Bọc cả `LLMPort` để đếm mọi lần chạm provider. Không tiêu quota."""

    inner: Any

    @property
    def model_name(self) -> str:
        return str(getattr(self.inner, "model_name", "unspecified"))

    async def extract_slots(
        self,
        *,
        vehicle_type: VehicleType | None,
        feature_vocabulary: Sequence[str],
        conversation_history: str | WorkingMemoryProjection,
        user_message: str,
    ) -> LLMExtractionPayload:
        _record()
        return await self.inner.extract_slots(
            vehicle_type=vehicle_type,
            feature_vocabulary=feature_vocabulary,
            conversation_history=conversation_history,
            user_message=user_message,
        )

    async def synthesize(self, *, prompt: str) -> str:
        _record()
        return await self.inner.synthesize(prompt=prompt)

    async def synthesize_policy(self, *, query: str, chunks: list[dict], application: bool = False) -> str:
        _record()
        return await self.inner.synthesize_policy(query=query, chunks=chunks, application=application)


@dataclass(frozen=True, slots=True)
class BudgetedBottleneckDetector:
    """Phát hiện nút thắt là việc TUỲ CHỌN — nó tự dựng client OpenAI riêng.

    Chính vì né `LLMPort` mà nó là chỗ dễ đếm sót nhất; bọc riêng ở đây để nó
    không bao giờ nằm ngoài sổ.
    """

    inner: Any

    async def detect(self, current_server_quote: str) -> Any:
        budget = current_call_budget()
        if budget is not None and not budget.take(CallKind.OPTIONAL):
            # Phát hiện nút thắt là một THAO TÁC tuỳ chọn trọn vẹn, không có
            # tầng điều phối nào khác đứng trước nó — nên nó tự xin slot ở đây.
            # Hết ngân sách thì trả "không xác định được", cùng kết quả với ca
            # thiếu API key, tuyệt đối không đoán bừa một nhãn nút thắt.
            return BottleneckUnavailable(BottleneckDetectionStatus.UNAVAILABLE)
        _record()
        return await self.inner.detect(current_server_quote)


__all__ = [
    "BudgetedBottleneckDetector",
    "MeteredLLM",
    "MeteredWriter",
]
