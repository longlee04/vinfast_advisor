"""Resolve safe follow-ups against a persisted structured conversation task."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

from src.agents.domain.canonical_text import CanonicalText
from src.agents.domain.pending_slot import PendingSlotRequest
from src.agents.domain.pricing_intent import (
    PricingIntent,
    classify_pricing_intent,
    detect_province,
)
from src.agents.domain.task_state import (
    ActiveTask,
    DeltaOperation,
    StateChange,
    StateDelta,
    TaskStatus,
    TaskType,
)
from src.agents.prompts.pricing_reply import MISSING_PROVINCE_QUESTION
from src.agents.services.pending_slot import pending_for_province

_CORRECTION_CUE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:nhầm|nham|đổi|doi|thay|sửa|sua|tính\s+lại|tinh\s+lai|"
    r"đăng\s+ký|dang\s+ky|ra\s+biển|ra\s+bien|"
    # "còn ở Hồ Chí Minh" / "ở Đà Nẵng thì sao" ngay sau một bảng lăn bánh —
    # đo 2026-08-28: rơi OUT_OF_SCOPE vì không cụm nào ở đây khớp.
    r"còn\s+(?:ở|tại)|con\s+(?:o|tai)|thì\s+sao|thi\s+sao)\b",
    re.IGNORECASE,
)
_PROVINCE_CONTEXT: Final[re.Pattern[str]] = re.compile(
    r"\b(?:tỉnh|tinh|thành\s+phố|thanh\s+pho|địa\s+phương|dia\s+phuong|"
    r"đăng\s+ký|dang\s+ky|ra\s+biển|ra\s+bien)\b",
    re.IGNORECASE,
)
_UNRELATED_LOCATION_CUE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:showroom|đại\s+lý|dai\s+ly|trạm\s+sạc|tram\s+sac|xưởng|xuong|"
    r"bảo\s+hành|bao\s+hanh)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class TaskFollowupResolution:
    """Result of interpreting one turn against the focused operational task."""

    handled: bool = False
    clear_task: bool = False
    task: ActiveTask | None = None
    delta: StateDelta | None = None
    filled_form: Mapping[str, Any] | None = None
    reply: str | None = None
    pending: PendingSlotRequest | None = None


@dataclass(slots=True)
class ActiveTaskService:
    """Build, validate and transition follow-up-eligible task state.

    The state/delta machinery is task-neutral.  Each task family owns a small
    resolver because its form and safe follow-up signals are domain-specific.
    """

    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))

    def resolve(
        self, *, payload: Mapping[str, Any] | None, user_message: str, canonical: CanonicalText
    ) -> TaskFollowupResolution:
        """Resolve a correction, or leave an unrelated turn to the normal graph."""

        task = ActiveTask.from_payload(payload)
        if task is None:
            return TaskFollowupResolution(clear_task=bool(payload))
        now = self.clock()
        if task.is_expired(now):
            return TaskFollowupResolution(clear_task=True)
        if task.task_type is TaskType.ON_ROAD_PRICE_LOOKUP:
            return self._resolve_on_road(task, user_message, canonical, now)
        return TaskFollowupResolution()

    def completed_on_road_task(
        self,
        *,
        vehicle_id: UUID | str,
        vehicle_name: str,
        province: str,
        previous: ActiveTask | None = None,
    ) -> ActiveTask:
        """Build the durable form used by one successful deterministic calculation."""

        now = self.clock()
        revision = previous.revision + 1 if previous is not None else 1
        return ActiveTask(
            task_type=TaskType.ON_ROAD_PRICE_LOOKUP,
            status=TaskStatus.COMPLETED,
            form={
                "vehicle_id": str(vehicle_id),
                "vehicle_name": vehicle_name.strip(),
                "province": province,
            },
            revision=revision,
            updated_at=now,
        )

    def completed_advisory_task(
        self,
        *,
        recommendation_ids: list[UUID | str],
        previous: ActiveTask | None = None,
    ) -> ActiveTask:
        """Remember every recommendation already shown in the current advisory branch."""

        now = self.clock()
        previous_ids: list[str] = []
        if previous is not None and previous.task_type is TaskType.ADVISORY:
            raw_previous = previous.form.get("seen_recommendation_ids")
            if isinstance(raw_previous, list):
                previous_ids = [str(value) for value in raw_previous if value]
        seen = list(dict.fromkeys([*previous_ids, *(str(value) for value in recommendation_ids)]))
        revision = previous.revision + 1 if previous is not None else 1
        return ActiveTask(
            task_type=TaskType.ADVISORY,
            status=TaskStatus.COMPLETED,
            form={"seen_recommendation_ids": seen},
            revision=revision,
            updated_at=now,
        )

    def _resolve_on_road(
        self, task: ActiveTask, user_message: str, canonical: CanonicalText, now: datetime
    ) -> TaskFollowupResolution:
        text = " ".join((user_message or "").split())
        if not text or _UNRELATED_LOCATION_CUE.search(text):
            return TaskFollowupResolution()
        province = detect_province(text, canonical)
        explicit_pricing = classify_pricing_intent(text, canonical) is PricingIntent.ON_ROAD_PRICE_LOOKUP
        is_correction = _CORRECTION_CUE.search(text) is not None
        province_only = province is not None and self._is_short_location_reply(text)
        if province is not None and (explicit_pricing or is_correction or province_only):
            old = task.form.get("province")
            operation = DeltaOperation.REPLACE if old is not None else DeltaOperation.SET
            delta = StateDelta(
                changes=(
                    StateChange(
                        operation=operation,
                        field="province",
                        old_value=old,
                        new_value=province,
                    ),
                )
            )
            updated = task.apply(delta, now=now)
            if updated is task and old == province:
                updated = task.with_status(TaskStatus.READY, now=now)
            return TaskFollowupResolution(
                handled=True,
                task=updated,
                delta=delta,
                filled_form=dict(updated.form),
            )
        if is_correction and _PROVINCE_CONTEXT.search(text):
            vehicle_id = task.form.get("vehicle_id")
            vehicle_name = task.form.get("vehicle_name")
            if vehicle_id and isinstance(vehicle_name, str) and vehicle_name.strip():
                pending = pending_for_province(vehicle_id, vehicle_name, now)
                return TaskFollowupResolution(
                    handled=True,
                    task=task.with_status(TaskStatus.COLLECTING, now=now),
                    reply=MISSING_PROVINCE_QUESTION,
                    pending=pending,
                )
        return TaskFollowupResolution()

    @staticmethod
    def _is_short_location_reply(user_message: str) -> bool:
        normalized = user_message.casefold().strip(" .,!?:;ạá")
        words = normalized.split()
        return len(words) <= 4


__all__ = ["ActiveTaskService", "TaskFollowupResolution"]
