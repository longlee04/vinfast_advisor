"""Lớp bọc ĐO lần chạm provider — kể cả chỗ né `LLMPort`.

Hợp đồng đã đổi (plan cập nhật 2026-08-24): wrapper **quan sát**, không **tiêu**
quota. Quota là chính sách và thuộc tầng điều phối, nơi biết ranh giới một thao
tác; wrapper chỉ là điểm duy nhất thấy được số lần chạm provider thật.

Ngoại lệ có chủ ý: `BudgetedBottleneckDetector`. Phát hiện nút thắt là một thao
tác tuỳ chọn TRỌN VẸN, không có tầng điều phối nào khác đứng trước nó, nên nó tự
xin slot.
"""

from __future__ import annotations

import pytest

from src.agents.adapters.budgeted_llm import (
    BudgetedBottleneckDetector,
    MeteredLLM,
    MeteredWriter,
)
from src.agents.domain.bottleneck_signal import BottleneckDetectionStatus
from src.agents.services.call_budget import (
    CallKind,
    TurnCallBudget,
    use_call_budget,
)


class _Writer:
    """Đếm số lần THẬT SỰ chạm provider."""

    def __init__(self) -> None:
        self.calls = 0

    async def synthesize(self, *, prompt: str) -> str:
        self.calls += 1
        return "van ban that"


class _Detector:
    def __init__(self) -> None:
        self.calls = 0

    async def detect(self, current_server_quote: str) -> str:
        self.calls += 1
        return "da phan loai"


@pytest.mark.asyncio
async def test_without_a_budget_the_wrapper_only_forwards() -> None:
    """Script, eval offline và test cũ không được bị chặn."""

    writer = _Writer()
    wrapped = MeteredWriter(writer)
    for _ in range(5):
        assert await wrapped.synthesize(prompt="x") == "van ban that"
    assert writer.calls == 5


@pytest.mark.asyncio
async def test_a_writer_records_a_metric_and_never_spends_quota() -> None:
    """CHUYỂN ĐỔI từ hợp đồng cũ "gọi lần hai trả rỗng".

    Wrapper không còn quyền từ chối: một thao tác tuỳ chọn có thể fan-out nhiều
    lần chạm provider, và cắt giữa chừng sẽ trả về nửa kết quả.
    """

    writer = _Writer()
    wrapped = MeteredWriter(writer)
    with use_call_budget(TurnCallBudget()) as budget:
        for _ in range(3):
            assert await wrapped.synthesize(prompt="x") == "van ban that"
        assert budget.remaining(CallKind.OPTIONAL) == 1, "khong duoc tieu quota"
        assert budget.provider_calls == 3, "nhung phai dem du ba lan cham"
    assert writer.calls == 3


@pytest.mark.asyncio
async def test_an_exhausted_quota_never_silently_truncates_an_operation() -> None:
    """CHUYỂN ĐỔI từ "bị từ chối thì không chạm provider".

    Chặn phải xảy ra ở tầng điều phối TRƯỚC khi thao tác bắt đầu. Chặn giữa
    chừng là tệ hơn không chặn: khách nhận một câu trả lời cụt.
    """

    writer = _Writer()
    wrapped = MeteredWriter(writer)
    with use_call_budget(TurnCallBudget(required=0, optional=0)):
        assert await wrapped.synthesize(prompt="x") == "van ban that"
    assert writer.calls == 1


@pytest.mark.asyncio
async def test_every_llm_port_method_is_metered() -> None:
    """CHUYỂN ĐỔI từ "mọi method tính là REQUIRED"."""

    class _Llm:
        def __init__(self) -> None:
            self.calls = 0

        async def synthesize(self, *, prompt: str) -> str:
            self.calls += 1
            return "x"

    inner = _Llm()
    with use_call_budget(TurnCallBudget()) as budget:
        wrapped = MeteredLLM(inner)
        await wrapped.synthesize(prompt="a")
        await wrapped.synthesize(prompt="b")
        assert budget.provider_calls == 2
        assert budget.remaining(CallKind.REQUIRED) == 4, "do khong phai tieu"
    assert inner.calls == 2


@pytest.mark.asyncio
async def test_metering_a_writer_leaves_the_required_pool_untouched() -> None:
    """CHUYỂN ĐỔI từ "tuỳ chọn không rút cạn pool bắt buộc"."""

    with use_call_budget(TurnCallBudget()) as budget:
        await MeteredWriter(_Writer()).synthesize(prompt="x")
        assert budget.remaining(CallKind.REQUIRED) == 4
        assert budget.remaining(CallKind.OPTIONAL) == 1


@pytest.mark.asyncio
async def test_the_bottleneck_detector_is_inside_the_ledger_despite_its_own_client() -> None:
    """Nó tự dựng client OpenAI nên là chỗ dễ đếm sót nhất."""

    detector = _Detector()
    wrapped = BudgetedBottleneckDetector(detector)
    with use_call_budget(TurnCallBudget(optional=0)):
        result = await wrapped.detect("gia hoi cao")
    assert detector.calls == 0
    assert result.status is BottleneckDetectionStatus.UNAVAILABLE


@pytest.mark.asyncio
async def test_a_refused_detector_reports_unavailable_not_a_made_up_label() -> None:
    """Hết ngân sách phải nói "không biết", tuyệt đối không đoán một nút thắt."""

    with use_call_budget(TurnCallBudget(optional=0)):
        result = await BudgetedBottleneckDetector(_Detector()).detect("dat qua")
    assert result.status is BottleneckDetectionStatus.UNAVAILABLE


@pytest.mark.asyncio
async def test_the_detector_spends_its_own_slot_because_it_is_a_whole_operation() -> None:
    detector = _Detector()
    with use_call_budget(TurnCallBudget()) as budget:
        await BudgetedBottleneckDetector(detector).detect("dat qua")
        assert budget.remaining(CallKind.OPTIONAL) == 0
        assert budget.provider_calls == 1
    assert detector.calls == 1
