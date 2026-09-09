from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.agents.domain.task_state import (
    ActiveTask,
    DeltaOperation,
    StateChange,
    StateDelta,
    TaskStatus,
    TaskType,
)

NOW = datetime(2026, 8, 16, 10, 0, tzinfo=UTC)


def _task() -> ActiveTask:
    return ActiveTask(
        task_type=TaskType.ON_ROAD_PRICE_LOOKUP,
        status=TaskStatus.COMPLETED,
        form={"vehicle_id": "vf5", "vehicle_name": "VF 5", "province": "HN"},
        revision=1,
        updated_at=NOW,
    )


def test_state_delta_replaces_only_the_changed_field() -> None:
    task = _task()
    delta = StateDelta(
        changes=(
            StateChange(
                operation=DeltaOperation.REPLACE,
                field="province",
                old_value="HN",
                new_value="NA",
            ),
        )
    )

    updated = task.apply(delta, now=NOW + timedelta(minutes=1))

    assert updated.form == {
        "vehicle_id": "vf5",
        "vehicle_name": "VF 5",
        "province": "NA",
    }
    assert updated.revision == 2
    assert updated.status is TaskStatus.READY


def test_invalid_old_value_does_not_mutate_the_task() -> None:
    task = _task()
    delta = StateDelta(
        changes=(
            StateChange(
                operation=DeltaOperation.REPLACE,
                field="province",
                old_value="HCM",
                new_value="NA",
            ),
        )
    )

    assert task.apply(delta, now=NOW + timedelta(minutes=1)) == task


def test_payload_round_trip_and_expiry_are_deterministic() -> None:
    task = _task()

    restored = ActiveTask.from_payload(task.to_payload())

    assert restored == task
    assert restored is not None
    assert restored.is_expired(NOW + timedelta(minutes=29)) is False
    assert restored.is_expired(NOW + timedelta(minutes=31)) is True


def test_corrupt_payload_is_ignored() -> None:
    assert ActiveTask.from_payload(None) is None
    assert ActiveTask.from_payload({"task_type": "UNKNOWN"}) is None
