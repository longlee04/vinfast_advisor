from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.task_state import ActiveTask, TaskStatus, TaskType
from src.agents.services.task_context import ActiveTaskService

NOW = datetime(2026, 8, 16, 10, 0, tzinfo=UTC)


def _payload(*, updated_at: datetime = NOW) -> dict[str, object]:
    return ActiveTask(
        task_type=TaskType.ON_ROAD_PRICE_LOOKUP,
        status=TaskStatus.COMPLETED,
        form={
            "vehicle_id": "50000000-0000-0000-0000-000000000005",
            "vehicle_name": "VinFast VF 5 All New",
            "province": "HN",
        },
        revision=1,
        updated_at=updated_at,
    ).to_payload()


def test_province_correction_becomes_a_structured_delta() -> None:
    resolution = ActiveTaskService(clock=lambda: NOW).resolve(
        payload=_payload(), user_message="À tôi nhầm, đăng ký ở Nghệ An.", canonical=build_canonical_text("À tôi nhầm, đăng ký ở Nghệ An.")
    )

    assert resolution.handled is True
    assert resolution.filled_form is not None
    assert resolution.filled_form["province"] == "NA"
    assert resolution.delta is not None
    assert resolution.delta.changes[0].field == "province"
    assert resolution.delta.changes[0].old_value == "HN"
    assert resolution.delta.changes[0].new_value == "NA"


def test_unrelated_location_request_does_not_reuse_the_price_task() -> None:
    resolution = ActiveTaskService(clock=lambda: NOW).resolve(
        payload=_payload(), user_message="Showroom ở Nghệ An nằm ở đâu?", canonical=build_canonical_text("Showroom ở Nghệ An nằm ở đâu?")
    )

    assert resolution.handled is False
    assert resolution.clear_task is False


def test_expired_task_is_cleared_instead_of_reused() -> None:
    resolution = ActiveTaskService(clock=lambda: NOW).resolve(
        payload=_payload(updated_at=NOW - timedelta(minutes=31)),
        user_message="À tôi nhầm, ở Nghệ An.", canonical=build_canonical_text("À tôi nhầm, ở Nghệ An."),
    )

    assert resolution.handled is False
    assert resolution.clear_task is True


def test_correction_without_a_supported_province_asks_for_the_field_again() -> None:
    resolution = ActiveTaskService(clock=lambda: NOW).resolve(
        payload=_payload(), user_message="À tôi nhầm tỉnh đăng ký rồi.", canonical=build_canonical_text("À tôi nhầm tỉnh đăng ký rồi.")
    )

    assert resolution.handled is True
    assert resolution.reply is not None
    assert resolution.pending is not None
    assert resolution.pending.missing_slot == "province"


def test_completed_advisory_task_accumulates_seen_recommendations() -> None:
    service = ActiveTaskService(clock=lambda: NOW)
    first = service.completed_advisory_task(
        recommendation_ids=[
            "10000000-0000-0000-0000-000000000001",
            "10000000-0000-0000-0000-000000000002",
        ]
    )

    second = service.completed_advisory_task(
        recommendation_ids=[
            "10000000-0000-0000-0000-000000000003",
            "10000000-0000-0000-0000-000000000001",
        ],
        previous=first,
    )

    assert second.task_type is TaskType.ADVISORY
    assert second.form["seen_recommendation_ids"] == [
        "10000000-0000-0000-0000-000000000001",
        "10000000-0000-0000-0000-000000000002",
        "10000000-0000-0000-0000-000000000003",
    ]
