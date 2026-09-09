"""Bó `ConversationTransaction` phải phủ ĐỦ repository mà service của nó chạm.

Bug thật bắt được trên prod 2026-08-26: `turn_traces` được thêm vào
`SqlAlchemyAgentTransaction` (bó Khối 4) nhưng KHÔNG thêm vào
`ConversationTransaction` (bó Khối 2) — mà `ConversationServiceImpl` chạy trên
bó Khối 2. Kết quả: `transaction.turn_traces` ném `AttributeError` mỗi lượt, hook
nuốt lỗi đúng như thiết kế, và **bảng vệt rỗng suốt** trong im lặng.

Cùng bẫy dính lại lần hai (2026-08-29) với `core_state`: `ConversationMemoryService
.commit_core_turn` và `ConversationServiceImpl.core_state_exists`/`load_core_state`
(lõi v2, spec mục 4/8) đều gọi `transaction.core_state`, nhưng trường này vắng mặt
ở `ConversationTransaction` cho tới khi `tests/agents/integration/test_core_run_turn.py`
bắt được — `core/flag.py:use_core_v2` nuốt `AttributeError` rồi luôn rơi về lõi cũ,
không log gì khách thấy được.

Docstring của chính `ConversationTransaction` đã cảnh báo trước: bó này bị `cast`
sang `UnitOfWorkPort` nên **trình kiểm kiểu không bắt được thiếu sót, chỉ runtime
mới nổ**. Test này thay chỗ cho trình kiểm kiểu.

Cùng họ với bẫy 3.2 (`luong-tu-van-da-sua.md`): một thứ phải khai ở HAI bó, và
quên một bó thì hỏng âm thầm.
"""

from __future__ import annotations

from src.agents.composition import ConversationTransaction

#: Repository mà `ConversationServiceImpl` và `ConversationMemoryService` gọi tới.
#: Thêm lời gọi `transaction.<gì đó>` mới trong hai service ấy thì thêm tên vào đây.
REQUIRED_REPOSITORIES = (
    "sessions",
    "pending_mentions",
    "memory",
    "conversations",
    "outcomes",
    "runs",
    "messages",
    "review_queue",
    "bottleneck_signals",
    "session_offers",
    "turn_traces",
    "core_state",
)


def test_the_conversation_bundle_declares_every_repository_its_services_use() -> None:
    missing = [name for name in REQUIRED_REPOSITORIES if name not in ConversationTransaction.__annotations__]

    assert missing == [], f"Bó Khối 2 thiếu repository: {missing}"
