"""Pure rules for safe, bounded conversation working memory."""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, TypeAlias
from uuid import UUID

from src.agents.domain.values import SlotValue

if TYPE_CHECKING:
    from src.agents.contracts import TurnResult

ConversationRole = Literal["USER", "ASSISTANT", "ADVISOR"]


class ConversationState(StrEnum):
    """Customer-facing lifecycle state independent from advisory run status."""

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class TurnOutcomeStatus(StrEnum):
    """Durable state of one idempotent customer turn."""

    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    WAITING_REVIEW = "WAITING_REVIEW"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class Conversation:
    """One owned conversation exposed through the public Conversation API."""

    conversation_id: UUID
    customer_id: str
    state: ConversationState
    created_at: datetime
    last_activity_at: datetime
    archived_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.customer_id.strip():
            raise ValueError("conversation customer_id must not be empty")
        if self.state is ConversationState.ARCHIVED and self.archived_at is None:
            raise ValueError("archived conversation requires archived_at")


@dataclass(frozen=True, slots=True)
class ConversationCursor:
    """Stable list cursor using the same keys as conversation ordering."""

    last_activity_at: datetime
    conversation_id: UUID


@dataclass(frozen=True, slots=True)
class MessageCursor:
    """Stable transcript cursor using server order and message identity."""

    turn_index: int
    message_id: UUID

    def __post_init__(self) -> None:
        if self.turn_index < 1:
            raise ValueError("message cursor turn_index must be positive")


@dataclass(frozen=True, slots=True)
class ConversationPage:
    """One stable page of owned conversations."""

    items: tuple[Conversation, ...]
    limit: int
    next_cursor: ConversationCursor | None = None

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("page limit must be positive")


@dataclass(frozen=True, slots=True)
class MessagePage:
    """One chronological page of visible messages."""

    items: tuple[ConversationMessage, ...]
    limit: int
    next_cursor: MessageCursor | None = None

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("page limit must be positive")


def encode_conversation_cursor(cursor: ConversationCursor) -> str:
    """Encode a conversation cursor as URL-safe opaque text."""

    return _encode_cursor({"at": cursor.last_activity_at.isoformat(), "id": str(cursor.conversation_id)})


def decode_conversation_cursor(value: str) -> ConversationCursor:
    """Decode and validate a conversation list cursor."""

    payload = _decode_cursor(value)
    try:
        timestamp = datetime.fromisoformat(str(payload["at"]))
        identifier = UUID(str(payload["id"]))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid conversation cursor") from error
    if timestamp.tzinfo is None:
        raise ValueError("invalid conversation cursor")
    return ConversationCursor(timestamp, identifier)


def encode_message_cursor(cursor: MessageCursor) -> str:
    """Encode a message cursor as URL-safe opaque text."""

    return _encode_cursor({"turn": cursor.turn_index, "id": str(cursor.message_id)})


def decode_message_cursor(value: str) -> MessageCursor:
    """Decode and validate a chronological message cursor."""

    payload = _decode_cursor(value)
    try:
        return MessageCursor(int(payload["turn"]), UUID(str(payload["id"])))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid message cursor") from error


def _encode_cursor(payload: Mapping[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str) -> Mapping[str, object]:
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode((value + padding).encode())
        payload = json.loads(decoded)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid pagination cursor") from error
    if not isinstance(payload, dict):
        raise ValueError("invalid pagination cursor")
    return payload


@dataclass(frozen=True, slots=True)
class MemoryMessage:
    """Transport-neutral role message projected for an LLM adapter."""

    role: ConversationRole | str
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"USER", "ASSISTANT", "ADVISOR"}:
            raise ValueError("memory message role must be USER, ASSISTANT, or ADVISOR")
        if not self.content.strip():
            raise ValueError("memory message content must not be empty")


@dataclass(frozen=True, slots=True)
class WorkingMemoryProjection:
    """Bounded, role-preserving context for exactly one owned conversation."""

    slots: Mapping[str, SlotValue]
    summary: str | None
    recent_messages: tuple[MemoryMessage, ...]
    pending_features: tuple[str, ...]
    current_user_message: str
    instruction_context: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.current_user_message.strip():
            raise ValueError("current user message must not be empty")


@dataclass(frozen=True, slots=True)
class TurnOutcome:
    """Immutable customer-safe payload used for exact idempotent replay."""

    conversation_id: UUID
    client_turn_id: UUID
    turn_number: int
    status: TurnOutcomeStatus
    answer: str | None = None
    pending_question: str | None = None
    terminal_reason: str | None = None
    lookup_facts: tuple[Mapping[str, object], ...] = ()
    recommendations: tuple[Mapping[str, object], ...] = ()
    error_category: str | None = None
    review_id: UUID | None = None
    message_id: UUID | None = None
    # Versioned customer-visible replay payload. Kept last for positional-call compatibility.
    result_payload: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.turn_number < 1:
            raise ValueError("turn_number must be positive")
        visible = bool(self.answer or self.pending_question or self.terminal_reason or self.lookup_facts)
        if self.status is TurnOutcomeStatus.COMPLETED and not visible:
            raise ValueError("completed turn outcome requires a customer result")
        if self.status in {TurnOutcomeStatus.IN_PROGRESS, TurnOutcomeStatus.FAILED} and visible:
            raise ValueError("non-completed turn outcome cannot contain a visible success")


@dataclass(frozen=True, slots=True)
class TurnClaim:
    """Result of claiming a client turn key under the conversation lock."""

    outcome: TurnOutcome
    claimed: bool


@dataclass(frozen=True, slots=True)
class CoreTurnLease:
    """Lease xác nhận MỘT worker là owner đang chạy lượt của một phiên.

    Khác `TurnClaim` (result wrapper cũ): lease mang token xác thực để re-check
    trước side-effect và trước commit, kèm `turn_number` ấn định một lần.
    """

    session_id: UUID
    client_turn_id: UUID
    turn_number: int
    claim_token: UUID
    claimed_at: datetime
    lease_expires_at: datetime

    def __post_init__(self) -> None:
        if self.turn_number < 1:
            raise ValueError("turn_number must be positive")
        if self.claimed_at > self.lease_expires_at:
            raise ValueError("lease claimed_at must not be after lease_expires_at")


@dataclass(frozen=True, slots=True)
class LeaseAcquired:
    """`begin_core_turn` cấp được lease mới cho worker này."""

    lease: CoreTurnLease


@dataclass(frozen=True, slots=True)
class TerminalReplay:
    """Lượt đã chấm dứt (terminal-visible) — trả đúng kết quả đã persist."""

    result: TurnResult


@dataclass(frozen=True, slots=True)
class TurnBusy:
    """Session đang có một lượt khác chạy; caller nên retry sau `retry_after_seconds`."""

    retry_after_seconds: int
    recovery_url: str


@dataclass(frozen=True, slots=True)
class LeaseBusy:
    """Repository trả khi còn lease ACTIVE; application wait loop đổi thành `TurnBusy`."""

    retry_after_seconds: int


CoreTurnStart: TypeAlias = "LeaseAcquired | TerminalReplay | TurnBusy"


_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:password|passwd|pwd|token|api[_-]?key)\s*[:=]\s*[^\s,;]+"),
    re.compile(
        r"(?i)\b(?:cookie|session(?:id)?|refresh[_-]?token|access[_-]?token)"
        r"\s*[:=]\s*[^\s,;]+"
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^\s]+"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"),
)
_NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_VEHICLE_MODEL_PATTERN = re.compile(r"\bVF\s*-?\s*(E?\d+)\b", re.IGNORECASE)
_ELIMINATE_MODEL_PATTERN = re.compile(
    r"\b(?:loại|loai|bỏ|bo)\s+(?:mẫu\s+|mau\s+|xe\s+)?VF\s*-?\s*(E?\d+)\b",
    re.IGNORECASE,
)
_CANONICAL_ELIMINATED_PATTERN = re.compile(r"Đã loại:\s*([^;.]+)", re.IGNORECASE)
_CANONICAL_ACTIVE_PATTERN = re.compile(r"Đang xem:\s*([^;.]+)", re.IGNORECASE)
_CANONICAL_STATE_LINE = re.compile(r"\s*Trạng thái xe\s+—[^\n]*(?:\n|$)", re.IGNORECASE)
_REOPEN_ELIMINATED_PATTERN = re.compile(
    r"\b(?:đổi\s+ý|doi\s+y)\b.*\b(?:mẫu|mau)\b.*\b(?:vừa|vua)\b.*"
    r"\b(?:loại|loai|bỏ|bo)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    """One customer-visible transcript item in stable turn order."""

    role: ConversationRole | str
    content: str
    turn_index: int
    message_id: UUID | None = None
    conversation_id: UUID | None = None
    client_turn_id: UUID | None = None
    review_id: UUID | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.role not in {"USER", "ASSISTANT", "ADVISOR"}:
            raise ValueError("conversation message role must be USER, ASSISTANT, or ADVISOR")
        if not self.content.strip():
            raise ValueError("conversation message content must not be empty")
        if self.turn_index < 1:
            raise ValueError("conversation message turn_index must be positive")


@dataclass(frozen=True, slots=True)
class ConversationSummary:
    """Incremental summary through one persisted transcript turn."""

    content: str
    summarized_through_turn: int
    prompt_version: str = "conversation-summary-v1"
    model_name: str = "unspecified"

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("conversation summary content must not be empty")
        if self.summarized_through_turn < 0:
            raise ValueError("summarized_through_turn must not be negative")
        if not self.prompt_version.strip() or not self.model_name.strip():
            raise ValueError("summary prompt_version and model_name must not be empty")


def redact_sensitive(text: str) -> str:
    """Remove credential-shaped values before persistence or an LLM prompt."""

    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def sanitize_summary(candidate: str, *, source_text: str, max_chars: int = 2_000) -> str:
    """Redact and reject summary sentences that introduce unseen numeric facts.

    This guard does not try to prove every natural-language claim. It blocks the
    dangerous class for this Agent: invented prices, ranges, or specifications.
    Structured slots remain authoritative and are rendered separately.
    """

    safe_source = redact_sensitive(source_text)
    allowed_numbers = set(_NUMBER_PATTERN.findall(safe_source))
    safe_candidate = redact_sensitive(candidate).strip()
    kept: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(safe_candidate):
        numbers = set(_NUMBER_PATTERN.findall(sentence))
        if numbers <= allowed_numbers:
            kept.append(sentence.strip())
    return " ".join(part for part in kept if part)[:max_chars].strip()


def stabilize_vehicle_summary(*, candidate: str, previous_summary: str, user_message: str) -> str:
    """Preserve explicit eliminated/active vehicle state despite LLM paraphrasing."""

    eliminated = _models_in_group(_CANONICAL_ELIMINATED_PATTERN, previous_summary)
    active = _models_in_group(_CANONICAL_ACTIVE_PATTERN, previous_summary)
    explicit_eliminated = [f"VF {value.upper()}" for value in _ELIMINATE_MODEL_PATTERN.findall(user_message)]
    current_models = _ordered_vehicle_models(user_message)
    if explicit_eliminated:
        eliminated = _dedupe([*eliminated, *explicit_eliminated])
        remaining = [model for model in current_models if model not in set(explicit_eliminated)]
        if not remaining:
            remaining = [model for model in _ordered_vehicle_models(candidate) if model not in set(explicit_eliminated)]
        if remaining:
            active = [remaining[-1]]
    elif _REOPEN_ELIMINATED_PATTERN.search(user_message) and eliminated:
        reopened = eliminated[-1]
        eliminated = [model for model in eliminated if model != reopened]
        active = [reopened]

    base = _CANONICAL_STATE_LINE.sub("", candidate).strip()
    if not eliminated and not active:
        return base
    eliminated_text = ", ".join(eliminated) if eliminated else "không có"
    active_text = ", ".join(active) if active else "chưa chốt"
    state = f"Trạng thái xe — Đã loại: {eliminated_text}; Đang xem: {active_text}."
    return f"{base}\n{state}" if base else state


def _models_in_group(pattern: re.Pattern[str], text: str) -> list[str]:
    match = pattern.search(text)
    return _ordered_vehicle_models(match.group(1)) if match else []


def _ordered_vehicle_models(text: str) -> list[str]:
    return _dedupe([f"VF {value.upper()}" for value in _VEHICLE_MODEL_PATTERN.findall(text)])


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def build_working_memory(
    *,
    slots: dict[str, SlotValue],
    summary: ConversationSummary | None,
    recent_messages: tuple[ConversationMessage, ...],
    current_user_message: str,
    max_chars: int = 4_000,
) -> str:
    """Project Slot + Summary + recent transcript into a bounded prompt context.

    Slots and the current utterance are mandatory. When the budget is tight,
    older transcript items are removed first, followed by summary truncation.
    """

    if not current_user_message.strip():
        raise ValueError("current user message must not be empty")
    safe_slots = redact_sensitive(json.dumps(slots, ensure_ascii=False, sort_keys=True))
    required = (
        "SLOT ĐÃ XÁC NHẬN (nguồn sự thật):\n"
        f"{safe_slots}\n\n"
        "LƯỢT HIỆN TẠI:\n"
        f"{redact_sensitive(current_user_message.strip())}"
    )
    summary_header = ""
    if summary is not None:
        safe_summary = redact_sensitive(summary.content)
        available = max(0, max_chars - len(required) - len("\n\nTÓM TẮT:\n"))
        if available:
            summary_header = f"\n\nTÓM TẮT:\n{safe_summary[:available]}"

    transcript_header = "\n\nTIN NHẮN GẦN ĐÂY:"
    selected: list[str] = []
    # Work backwards so the newest customer-visible messages survive first.
    for message in reversed(recent_messages):
        rendered = f"\n{message.role}: {redact_sensitive(message.content.strip())}"
        projected_length = len(required) + len(summary_header) + len(transcript_header)
        projected_length += sum(len(item) for item in selected) + len(rendered)
        if projected_length <= max_chars:
            selected.append(rendered)
    selected.reverse()

    # Summary must appear before transcript. If it consumed the transcript budget,
    # shrink it to make room for the newest message.
    if recent_messages and not selected:
        newest = f"\n{recent_messages[-1].role}: {redact_sensitive(recent_messages[-1].content.strip())}"
        allowed_summary = max(
            0,
            max_chars - len(required) - len(transcript_header) - len(newest) - len("\n\nTÓM TẮT:\n"),
        )
        if summary is not None and allowed_summary:
            summary_header = f"\n\nTÓM TẮT:\n{redact_sensitive(summary.content)[:allowed_summary]}"
        else:
            summary_header = ""
        selected = [newest]

    transcript = transcript_header + "".join(selected) if selected else ""
    return f"{required}{summary_header}{transcript}"


def build_working_memory_projection(
    *,
    slots: Mapping[str, SlotValue],
    summary: ConversationSummary | None,
    recent_messages: tuple[ConversationMessage, ...],
    pending_features: tuple[str, ...],
    current_user_message: str,
    max_chars: int = 4_000,
) -> WorkingMemoryProjection:
    """Build a bounded neutral projection without flattening transcript roles."""

    if not current_user_message.strip():
        raise ValueError("current user message must not be empty")
    safe_slots = {
        key: redact_sensitive(json.dumps(value, ensure_ascii=False)).strip('"') if isinstance(value, str) else value
        for key, value in slots.items()
    }
    safe_pending = tuple(redact_sensitive(item.strip()) for item in pending_features if item.strip())
    required_size = len(json.dumps(safe_slots, ensure_ascii=False))
    required_size += len(current_user_message) + sum(len(item) for item in safe_pending)
    remaining = max(0, max_chars - required_size)
    safe_summary = redact_sensitive(summary.content) if summary is not None else None
    if safe_summary is not None:
        summary_budget = min(len(safe_summary), remaining // 2)
        safe_summary = safe_summary[:summary_budget] or None
        remaining -= summary_budget

    groups = _message_groups(recent_messages)
    selected_groups: list[tuple[ConversationMessage, ...]] = []
    for group in reversed(groups):
        group_size = sum(len(message.content) + len(str(message.role)) + 2 for message in group)
        if group_size <= remaining:
            selected_groups.append(group)
            remaining -= group_size
    selected_groups.reverse()
    selected = tuple(
        MemoryMessage(message.role, redact_sensitive(message.content.strip()))
        for group in selected_groups
        for message in group
    )
    return WorkingMemoryProjection(
        slots=safe_slots,
        summary=safe_summary,
        recent_messages=selected,
        pending_features=safe_pending,
        current_user_message=redact_sensitive(current_user_message.strip()),
    )


def render_working_memory_projection(projection: WorkingMemoryProjection) -> str:
    """Render neutral memory only for deterministic rules and legacy consumers."""

    parts = [
        "SLOT ĐÃ XÁC NHẬN (nguồn sự thật):\n" + json.dumps(projection.slots, ensure_ascii=False, sort_keys=True),
    ]
    if projection.summary:
        parts.append(f"TÓM TẮT:\n{projection.summary}")
    if projection.pending_features:
        parts.append("TÍNH NĂNG ĐANG CHỜ:\n" + ", ".join(projection.pending_features))
    if projection.instruction_context:
        parts.append("NGỮ CẢNH TRÍCH XUẤT:\n" + "\n".join(projection.instruction_context))
    if projection.recent_messages:
        parts.append(
            "TIN NHẮN GẦN ĐÂY:\n"
            + "\n".join(f"{message.role}: {message.content}" for message in projection.recent_messages)
        )
    parts.append(f"LƯỢT HIỆN TẠI:\n{projection.current_user_message}")
    return "\n\n".join(parts)


def _message_groups(
    messages: tuple[ConversationMessage, ...],
) -> list[tuple[ConversationMessage, ...]]:
    groups: list[tuple[ConversationMessage, ...]] = []
    index = 0
    while index < len(messages):
        current = messages[index]
        if current.role == "USER" and index + 1 < len(messages) and messages[index + 1].role == "ASSISTANT":
            groups.append((current, messages[index + 1]))
            index += 2
        else:
            groups.append((current,))
            index += 1
    return groups
