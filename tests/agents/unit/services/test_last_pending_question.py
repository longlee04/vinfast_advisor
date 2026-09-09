"""`last_pending_question` phải hỏi về lượt TRƯỚC, không phải lượt đang chạy.

**Bug thật 2026-08-26**, Sếp báo: khách đáp "không cần" cho câu hỏi tính năng thì
nhận lại lời từ chối *"chuyện này ngoài hiểu biết của em"*. Vệt quyết định chỉ
đúng nguyên nhân:

    customer_declined:   true    ← nhận đúng khách từ chối
    bot_asked_last_turn: false   ← SAI, bot vừa hỏi ngay lượt trước

`nodes/classify_scope` đòi CẢ HAI mới mở cửa phạm vi, nên bypass không chạy và
`OUT_OF_SCOPE` thắng.

Gốc: `chain.run_turn` gọi `memory.start_turn` từ rất sớm, nên hàng của lượt đang
chạy đã nằm trong `conversation_turn_outcomes` (status `IN_PROGRESS`, chưa có
`pending_question`) trước mọi lần đọc sau đó. `outcomes.latest()` vì thế trả về
CHÍNH lượt hiện tại.

Đo trên prod: `bot_asked_last_turn` là `false` ở **188/188** lượt — cờ chết hoàn
toàn, và ba cờ "đây là câu trả lời" (`customer_declined`,
`customer_delegates_choice`, `customer_answered_vaguely`) chưa bao giờ mở được
cửa. Cả một bản vá nằm im mà không ai thấy.

Test cũ chỉ khoá NODE (`test_classify_scope_size_gate`) — nó nhận cờ như một đầu
vào dựng sẵn nên vẫn xanh. Bộ này khoá ĐƯỜNG ĐỌC.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

SESSION_ID = UUID("c200c853-ab50-43cd-afa2-7d3191300a8f")
CUSTOMER_ID = "khach-1"


@dataclass
class _Outcome:
    pending_question: str | None


class _RecordingOutcomes:
    """Ghi lại tham số `latest` nhận được, trả về lượt do test dựng."""

    def __init__(self, outcome: _Outcome | None) -> None:
        self.outcome = outcome
        self.calls: list[UUID | None] = []

    async def latest(
        self,
        conversation_id: UUID,
        customer_id: str,
        *,
        exclude_client_turn_id: UUID | None = None,
    ) -> _Outcome | None:
        self.calls.append(exclude_client_turn_id)
        return self.outcome


class _Transaction:
    def __init__(self, outcomes: _RecordingOutcomes) -> None:
        self.outcomes = outcomes


class _UnitOfWork:
    def __init__(self, outcomes: _RecordingOutcomes) -> None:
        self._outcomes = outcomes

    @asynccontextmanager
    async def transaction(self):
        yield _Transaction(self._outcomes)


def _service(outcome: _Outcome | None) -> tuple[object, _RecordingOutcomes]:
    from src.agents.services.conversation import ConversationServiceImpl

    outcomes = _RecordingOutcomes(outcome)
    service = ConversationServiceImpl.__new__(ConversationServiceImpl)
    object.__setattr__(service, "_unit_of_work", _UnitOfWork(outcomes))
    return service, outcomes


@pytest.mark.asyncio
async def test_luot_dang_chay_bi_loai_khoi_phep_doc() -> None:
    """Không loại thì "lượt trước" chính là lượt hiện tại, và hàm luôn trả False."""

    service, outcomes = _service(_Outcome(pending_question="Anh/chị cần tính năng nào ạ?"))
    client_turn_id = uuid4()

    await service.last_pending_question(str(SESSION_ID), CUSTOMER_ID, client_turn_id)

    assert outcomes.calls == [client_turn_id]


@pytest.mark.asyncio
async def test_luot_truoc_co_cau_hoi_thi_bat_co() -> None:
    service, _ = _service(_Outcome(pending_question="Anh/chị cần tính năng nào ạ?"))

    assert await service.last_pending_question(str(SESSION_ID), CUSTOMER_ID, uuid4()) is not None


@pytest.mark.asyncio
async def test_luot_truoc_khong_hoi_gi_thi_khong_bat() -> None:
    """Không có câu hỏi nào đang chờ thì một lời "từ chối" là vô nghĩa — đó chính
    là lỗ rò "tư vấn giúp tôi cách nấu phở" mà cờ này sinh ra để bịt."""

    service, _ = _service(_Outcome(pending_question=None))

    assert await service.last_pending_question(str(SESSION_ID), CUSTOMER_ID, uuid4()) is None


@pytest.mark.asyncio
async def test_tin_nhan_dau_phien_khong_bat_co() -> None:
    service, _ = _service(None)

    assert await service.last_pending_question(str(SESSION_ID), CUSTOMER_ID, uuid4()) is None


@pytest.mark.asyncio
async def test_doc_hong_thi_coi_nhu_co_hoi() -> None:
    """Chiều an toàn: chặn nhầm làm khách mất câu trả lời, cho qua chỉ mất một
    lần chặn phạm vi."""

    class _Broken:
        @asynccontextmanager
        async def transaction(self):
            raise RuntimeError("mat ket noi")
            yield  # pragma: no cover

    from src.agents.domain.feature_selection import UNKNOWN_QUESTION
    from src.agents.services.conversation import ConversationServiceImpl

    service = ConversationServiceImpl.__new__(ConversationServiceImpl)
    object.__setattr__(service, "_unit_of_work", _Broken())

    # Trả một chuỗi rỗng-nghĩa chứ không phải câu hỏi thật: người gọi biết "coi
    # như có hỏi", còn suy mã tính năng từ nó thì ra tập RỖNG — không gán bừa.
    assert await service.last_pending_question(str(SESSION_ID), CUSTOMER_ID, uuid4()) == UNKNOWN_QUESTION
