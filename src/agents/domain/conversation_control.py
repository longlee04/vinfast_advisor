"""Deterministic control language for cancelling, declining, and switching focus."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final

from src.agents.domain.canonical_text import CanonicalText, build_canonical_text
from src.agents.domain.turn_understanding import is_restart_task_request


class ConversationControlAction(StrEnum):
    """A customer instruction that changes how persisted conversation focus is used."""

    CONTINUE = "CONTINUE"
    CANCEL = "CANCEL"
    DECLINE_SLOT = "DECLINE_SLOT"
    REVISE_TASK = "REVISE_TASK"
    SWITCH_TASK = "SWITCH_TASK"


_SWITCH_TASK_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:tu\s+van|so\s+sanh|chon\s+xe|tim\s+xe|showroom|dai\s+ly|tram\s+sac|"
    r"bao\s+hanh|thong\s+so|gia\s+niem\s+yet|mau\s+gi|nhung\s+mau)\b|"
    r"\bvf\s*\d+\b.*\b(?:mau|thong\s+so|bao\s+hanh|gia|phien\s+ban)\b",
    re.IGNORECASE,
)
_DECLINE_SLOT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:khong\s+muon\s+(?:cung\s+cap|noi|tra\s+loi|chia\s+se)|"
    r"xin\s+phep\s+khong\s+tra\s+loi|"
    r"bo\s+qua\s+(?:cau|thong\s+tin|muc|phan)\s+(?:nay|do)|"
    r"khong\s+tra\s+loi\s+(?:cau|thong\s+tin|muc|phan)\s+(?:nay|do))\b",
    re.IGNORECASE,
)
_CANCEL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:huy\s+(?:yeu\s+cau|viec|task|phan|cai)|"
    r"thoi\s+bo\s+(?:yeu\s+cau|viec|task|cai\s+nay)|"
    r"khong\s+can\s+(?:lam|tiep\s+tuc|tinh|tra\s+cuu).*\bnua)\b|"
    r"^thoi\s+bo(?:\s+di)?[.!]?$",
    re.IGNORECASE,
)
_REVISE_TASK_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:xe|mau|phuong\s+an|lua\s+chon)\s+khac\b|"
    r"\b(?:con|co)\s+(?:xe|mau|phuong\s+an)\s+nao\s+khac\b",
    re.IGNORECASE,
)


def classify_conversation_control(
    user_message: str, canonical: CanonicalText | None = None
) -> ConversationControlAction:
    """Classify only explicit focus-control language; ordinary turns remain untouched.

    So khớp trên `canonical.folded` sinh tại chain (ENG REVIEW AMENDMENT 2) —
    gate không tự normalize. Vắng mặt thì tự dựng từ `user_message` (đường
    tương thích cho test double).
    """

    canonical = canonical or build_canonical_text(user_message)
    text = canonical.folded
    if not text:
        return ConversationControlAction.CONTINUE
    # "tư vấn xe khác" revises the current advisory result set. Clearing focus
    # here would erase the exact recommendation IDs that must be excluded.
    if _REVISE_TASK_PATTERN.search(text):
        return ConversationControlAction.REVISE_TASK
    # A message that both closes the old request and names a new one must reach
    # the normal router in this same turn, not end at a cancellation receipt.
    if _SWITCH_TASK_PATTERN.search(text) or is_restart_task_request(user_message, canonical):
        return ConversationControlAction.SWITCH_TASK
    if _DECLINE_SLOT_PATTERN.search(text):
        return ConversationControlAction.DECLINE_SLOT
    if _CANCEL_PATTERN.search(text):
        return ConversationControlAction.CANCEL
    return ConversationControlAction.CONTINUE


def declined_slot_reply(slot_name: str) -> str:
    """Explain the consequence of declining a required operational field."""

    if slot_name == "province":
        return (
            "Không sao ạ. Không có tỉnh/thành đăng ký thì em không thể tính chính xác "
            "giá lăn bánh, nên em đã dừng yêu cầu này. Anh/chị vẫn có thể hỏi giá niêm "
            "yết hoặc nội dung khác về xe."
        )
    return (
        "Không sao ạ, em đã bỏ qua thông tin này và dừng yêu cầu đang chờ. "
        "Anh/chị có thể chuyển sang nội dung khác bất cứ lúc nào."
    )


__all__ = [
    "ConversationControlAction",
    "classify_conversation_control",
    "declined_slot_reply",
]
