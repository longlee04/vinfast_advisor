"""Structured state for a conversation task that can continue across turns.

Transcript memory explains what was said.  An ``ActiveTask`` records what the
application was doing with that conversation so a later correction can be
applied without reclassifying the whole request from free text.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Final

from src.agents.domain.focus_policy import DEFAULT_CONVERSATION_FOCUS_POLICY

ACTIVE_TASK_TTL: Final[timedelta] = DEFAULT_CONVERSATION_FOCUS_POLICY.resumable_task_ttl


class TaskType(StrEnum):
    """Supported operational task families."""

    ADVISORY = "ADVISORY"
    ON_ROAD_PRICE_LOOKUP = "ON_ROAD_PRICE_LOOKUP"
    #: Chặng SAU khi đã đề xuất xe (Sếp 2026-08-26): khách chọn mẫu → xem thông
    #: tin → tính chi phí → hết lăn tăn thì mời lái thử, còn lăn tăn thì qua tư
    #: vấn viên rồi quay lại.
    #:
    #: Dùng `ActiveTask` chứ không dựng chỗ lưu mới: chặng này có tới năm điểm
    #: dừng, mà `pending_question` chỉ nói được "đang chờ trả lời" — không nói
    #: đang chờ trả lời CÁI GÌ. `ActiveTask` sẵn có TTL, revision và
    #: compare-before-write, tức đúng ba thứ một máy trạng thái nhiều lượt cần.
    POST_PITCH = "POST_PITCH"


class TaskStatus(StrEnum):
    """Lifecycle state of the focused conversation task."""

    COLLECTING = "COLLECTING"
    READY = "READY"
    COMPLETED = "COMPLETED"
    SUPERSEDED = "SUPERSEDED"


class DeltaOperation(StrEnum):
    """A typed mutation requested by one customer turn."""

    SET = "SET"
    REPLACE = "REPLACE"
    REMOVE = "REMOVE"
    KEEP = "KEEP"


@dataclass(frozen=True, slots=True)
class StateChange:
    """One field-level mutation with optional compare-before-write protection."""

    operation: DeltaOperation
    field: str
    old_value: Any = None
    new_value: Any = None

    def __post_init__(self) -> None:
        if not self.field.strip():
            raise ValueError("state change field must not be empty")


@dataclass(frozen=True, slots=True)
class StateDelta:
    """All structured changes inferred from exactly one customer turn."""

    changes: tuple[StateChange, ...] = ()

    def __post_init__(self) -> None:
        fields = [change.field for change in self.changes]
        if len(fields) != len(set(fields)):
            raise ValueError("state delta cannot mutate one field twice")


@dataclass(frozen=True, slots=True)
class ActiveTask:
    """The latest follow-up-eligible operation for one conversation session."""

    task_type: TaskType
    status: TaskStatus
    form: Mapping[str, Any] = field(default_factory=dict)
    revision: int = 1
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.revision < 1:
            raise ValueError("active task revision must be positive")
        if self.updated_at is None:
            raise ValueError("active task updated_at is required")

    def is_expired(self, now: datetime, ttl: timedelta = ACTIVE_TASK_TTL) -> bool:
        """Return whether this task is too old to capture an implicit follow-up."""

        if self.status is TaskStatus.SUPERSEDED:
            return True
        assert self.updated_at is not None
        updated = self.updated_at if self.updated_at.tzinfo is not None else self.updated_at.replace(tzinfo=UTC)
        moment = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
        return moment - updated > ttl

    def apply(self, delta: StateDelta, *, now: datetime) -> ActiveTask:
        """Apply a validated compare-before-write delta, or keep the task unchanged."""

        form = dict(self.form)
        for change in delta.changes:
            current = form.get(change.field)
            if change.operation is DeltaOperation.KEEP:
                if change.old_value is not None and current != change.old_value:
                    return self
                continue
            if change.operation is DeltaOperation.REPLACE:
                if change.field not in form or current != change.old_value:
                    return self
                form[change.field] = change.new_value
                continue
            if change.operation is DeltaOperation.SET:
                if change.field in form and current != change.new_value:
                    return self
                form[change.field] = change.new_value
                continue
            if change.operation is DeltaOperation.REMOVE:
                if change.old_value is not None and current != change.old_value:
                    return self
                form.pop(change.field, None)
        if form == dict(self.form):
            return self
        return replace(
            self,
            form=form,
            status=TaskStatus.READY,
            revision=self.revision + 1,
            updated_at=now,
        )

    def with_status(self, status: TaskStatus, *, now: datetime) -> ActiveTask:
        """Advance lifecycle status without changing the validated input form."""

        if status is self.status and now == self.updated_at:
            return self
        return replace(
            self,
            status=status,
            revision=self.revision + 1,
            updated_at=now,
        )

    def to_payload(self) -> dict[str, Any]:
        """Return the versioned JSON representation stored by infrastructure."""

        assert self.updated_at is not None
        return {
            "schema_version": 1,
            "task_type": self.task_type.value,
            "status": self.status.value,
            "form": dict(self.form),
            "revision": self.revision,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> ActiveTask | None:
        """Parse persisted JSON defensively; corrupt legacy state is treated as absent."""

        if not payload:
            return None
        try:
            task_type = TaskType(str(payload["task_type"]))
            status = TaskStatus(str(payload["status"]))
            revision = int(payload["revision"])
            raw_updated_at = payload["updated_at"]
            if not isinstance(raw_updated_at, str):
                return None
            updated_at = datetime.fromisoformat(raw_updated_at)
            raw_form = payload.get("form")
            if not isinstance(raw_form, Mapping):
                return None
            return cls(
                task_type=task_type,
                status=status,
                form=dict(raw_form),
                revision=revision,
                updated_at=updated_at,
            )
        except (KeyError, TypeError, ValueError):
            return None


__all__ = [
    "ACTIVE_TASK_TTL",
    "ActiveTask",
    "DeltaOperation",
    "StateChange",
    "StateDelta",
    "TaskStatus",
    "TaskType",
]
