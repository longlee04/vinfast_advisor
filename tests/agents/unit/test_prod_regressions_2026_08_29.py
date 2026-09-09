"""Lỗi bắt trên prod ngay sau deploy 2026-08-29 (Sếp test tay 17:23–17:27 UTC).

Mỗi test ghi đúng dấu vết trong log/DB prod. Đỏ = lỗi cũ quay lại.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from src.agents.contracts import LLMExtractionPayload
from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.task_state import ActiveTask, TaskStatus, TaskType
from src.agents.domain.turn_understanding import reconcile_task_action
from src.agents.domain.values import Intent, TaskAction
from src.agents.domain.vehicle_overview import EngineSpecs, EngineVariantSpecs
from src.agents.services.vehicle_overview import _performance_details
from src.agents.services.verification import _same_number


class TestVerificationComparesNumbersByValue:
    """`verify tu choi draft: draft='457' evidence='457.00'` → guardrail loại → đẩy TVV."""

    def test_trailing_zero_decimal_is_same_number(self) -> None:
        assert _same_number("457", "457.00")
        assert _same_number("310.5", "310.50")
        assert _same_number("1348000000", "1348000000")

    def test_different_values_still_rejected(self) -> None:
        assert not _same_number("457", "458.00")
        assert not _same_number("457", None)
        assert not _same_number("abc", "457")


class TestLlmPayloadDropsOnlyUnknownEnumValues:
    """`Payload LLM sai kiểu, đã loại` ×146 trên prod: một nhãn lạ làm mất cả ngân sách khách vừa nói."""

    def test_unknown_task_and_action_keep_the_rest(self) -> None:
        payload = LLMExtractionPayload.model_validate(
            {
                "task": "RECOMMEND",
                "task_action": "ASK",
                "purpose_bucket": "city",
                "scope": "SOMETHING",
                "vehicle_type": "CAR",
                "intents": ["ADVISORY", "POLICY_QA"],
                "budget_max_vnd": "700 triệu",
            }
        )
        assert payload.task is None
        assert payload.task_action is TaskAction.NONE
        assert payload.purpose_bucket is None
        assert payload.scope is None
        assert payload.vehicle_type is not None and payload.vehicle_type.value == "CAR"
        assert [intent.value for intent in payload.intents] == ["ADVISORY"]
        assert payload.budget_max_vnd == "700 triệu"

    def test_valid_values_untouched(self) -> None:
        payload = LLMExtractionPayload.model_validate({"task": "POLICY_QUERY", "task_action": "CLARIFY_TASK"})
        assert payload.task is not None and payload.task.value == "POLICY_QUERY"
        assert payload.task_action is TaskAction.CLARIFY_TASK


class TestOverviewUsesCatalogPerformanceSpecs:
    """VF 5 chưa có tài liệu RAG → trước chỉ in công suất/mô-men; pin, tầm chạy, tốc độ nằm sẵn ở bảng `cars`."""

    def test_performance_line_from_catalog(self) -> None:
        variant = EngineVariantSpecs(
            variant_name="VF 5 All New",
            motor_power_kw=Decimal("100.000"),
            torque_nm=Decimal("135.000"),
            battery_capacity_kwh=Decimal("37.230"),
            range_km=Decimal("326.00"),
            range_cycle="NEDC",
            max_speed_kmh=Decimal("130.00"),
            fast_charge_time_minutes=30,
            fast_charge_from_percent=10,
            fast_charge_to_percent=70,
        )
        text = ", ".join(_performance_details(variant))
        assert "dung lượng pin 37.23 kWh" in text
        assert "quãng đường mỗi lần sạc 326 km (NEDC)" in text
        assert "tốc độ tối đa 130 km/h" in text
        assert "sạc nhanh 30 phút (10–70%)" in text

    def test_missing_specs_render_nothing(self) -> None:
        assert _performance_details(EngineVariantSpecs(variant_name="x")) == []
        assert EngineSpecs(variants=[]).variants == []


class TestCostRequestAfterPitchIsNotClarifyTask:
    """ "tính giá lăn bánh" sau đề xuất bị LLM gán ADVISORY → CLARIFY_TASK → "xem lại danh sách hay đổi tiêu chí?"."""

    def _completed(self) -> dict:
        task = ActiveTask(
            task_type=TaskType.ADVISORY, status=TaskStatus.COMPLETED, form={}, revision=1, updated_at=datetime.now(UTC)
        )
        return dict(task.to_payload())

    def test_cost_request_is_not_clarify(self) -> None:
        action, _ = reconcile_task_action(
            user_message="tính giá lăn bánh",
            raw_action=TaskAction.NONE,
            intents=[Intent.ADVISORY],
            active_task_payload=self._completed(),
            current_slots={},
            known_slots={"budget_max_vnd": 500_000_000},
            vehicle_mentions=[],
            canonical=build_canonical_text("tính giá lăn bánh"),
        )
        assert action is not TaskAction.CLARIFY_TASK

    def test_plain_advice_request_still_clarifies(self) -> None:
        action, _ = reconcile_task_action(
            user_message="anh muốn tư vấn",
            raw_action=TaskAction.NONE,
            intents=[Intent.ADVISORY],
            active_task_payload=self._completed(),
            current_slots={},
            known_slots={"budget_max_vnd": 500_000_000},
            vehicle_mentions=[],
            canonical=build_canonical_text("anh muốn tư vấn"),
        )
        assert action is TaskAction.CLARIFY_TASK


class TestInterestVehicleAndFeatureHighlights:
    """Sếp 2026-08-29: nhớ xe khách vừa xem; đề xuất/giới thiệu kể thêm tính năng đã duyệt."""

    def test_overview_feature_names_prefer_labels(self) -> None:
        from types import SimpleNamespace

        from src.agents.services.vehicle_overview import _approved_feature_names

        facts = [SimpleNamespace(features={"GPS": "GPS", "LEATHER_SEATS": "Ghế bọc da"})]
        assert _approved_feature_names(facts) == ("định vị GPS", "ghế bọc da")

    def test_restart_slots_keep_interest_vehicle(self) -> None:
        from src.agents.domain.advisory_restart import RESTART_SLOTS
        from src.agents.domain.values import SlotName

        assert SlotName.INTEREST_VEHICLE.value not in RESTART_SLOTS
        assert SlotName.BUDGET_MAX_VND.value in RESTART_SLOTS


class TestCostAssumptionRevisionStaysInCostBranch:
    """LP35 (2026-08-29): sau bảng chi phí, "Hà Nội" là sửa tỉnh đăng ký, không phải "hết băn khoăn"."""

    def test_province_or_distance_after_decision_is_cost(self) -> None:
        from src.agents.domain.post_pitch import PostPitchStage
        from src.agents.domain.post_pitch_branch import PostPitchBranch, branch_from_readers

        for message in ("Hà Nội", "anh đăng ký ở Đà Nẵng", "ngày anh đi 80km"):
            assert branch_from_readers(PostPitchStage.AWAITING_DECISION, message) is PostPitchBranch.WANTS_COST, message
            assert branch_from_readers(PostPitchStage.AWAITING_COST_CONSENT, message) is PostPitchBranch.WANTS_COST, (
                message
            )

    def test_plain_agreement_unchanged(self) -> None:
        from src.agents.domain.post_pitch import PostPitchStage
        from src.agents.domain.post_pitch_branch import PostPitchBranch, branch_from_readers

        assert branch_from_readers(PostPitchStage.AWAITING_DECISION, "tính giá lăn bánh") is PostPitchBranch.WANTS_COST
        assert (
            branch_from_readers(PostPitchStage.AWAITING_DECISION, "anh muốn lái thử")
            is PostPitchBranch.WANTS_TEST_DRIVE
        )
