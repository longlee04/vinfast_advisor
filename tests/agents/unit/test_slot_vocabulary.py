"""[A2-4] Enum feature dựng tại runtime từ DB — thêm feature là INSERT, không sửa prompt."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.agents.domain.values import (
    DialogueAct,
    Intent,
    IntentType,
    ScopeLabel,
    Severity,
    TaskAction,
    Topic,
    VehicleType,
)
from src.agents.prompts import slot_extraction_prompts
from src.agents.prompts.slot_extraction_prompts import SYSTEM_PROMPT, build_tool_schema


class FakeFeatureVocabulary:
    """Fake port A1-4 — 12 feature theo mục A1-4 của plan."""

    def __init__(self, rows: dict[VehicleType, list[tuple[str, str]]]) -> None:
        self.rows = rows

    async def list_active_features(self, vehicle_type: VehicleType) -> list[tuple[str, str]]:
        return self.rows[vehicle_type]


_CAR_FEATURES = [
    ("POWER_ADJUST_SEAT", "Ghế chỉnh điện"),
    ("PANORAMIC_ROOF", "Cửa sổ trời toàn cảnh"),
]


def _feature_enum(schema: dict) -> list[str]:
    return schema["parameters"]["properties"]["feature_mentions"]["items"]["enum"]


def test_tool_schema_enum_comes_from_the_supplied_rows() -> None:
    schema = build_tool_schema(VehicleType.CAR, _CAR_FEATURES)

    assert _feature_enum(schema) == ["POWER_ADJUST_SEAT", "PANORAMIC_ROOF"]


def test_a_newly_inserted_feature_appears_without_editing_any_prompt_file() -> None:
    before = build_tool_schema(VehicleType.CAR, _CAR_FEATURES)
    after = build_tool_schema(VehicleType.CAR, [*_CAR_FEATURES, ("HEAT_PUMP", "Bơm nhiệt")])

    assert "HEAT_PUMP" not in _feature_enum(before)
    assert "HEAT_PUMP" in _feature_enum(after)


def test_prompt_source_file_contains_no_hardcoded_feature_code() -> None:
    source = Path(slot_extraction_prompts.__file__).read_text(encoding="utf-8")
    hardcoded = re.findall(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+){1,}\b", source)

    # Tên thành viên `VehicleType` không phải feature code — lấy từ chính enum để
    # allowlist không phải sửa tay khi loại phương tiện thay đổi.
    allowed = {"SYSTEM_PROMPT", "TOOL_NAME"} | {
        member.name
        # Bốn trục hiểu lượt (Todo 6) cũng là enum, không phải feature code —
        # lấy từ chính enum để allowlist không phải sửa tay khi enum đổi.
        for enum_type in (
            VehicleType,
            Intent,
            ScopeLabel,
            DialogueAct,
            TaskAction,
            IntentType,
            Topic,
            Severity,
        )
        for member in enum_type
    }

    assert [token for token in hardcoded if token not in allowed] == []


def test_system_prompt_string_contains_no_feature_code_list() -> None:
    assert "PANORAMIC_ROOF" not in SYSTEM_PROMPT
    assert "POWER_ADJUST_SEAT" not in SYSTEM_PROMPT


def test_motorbike_schema_never_offers_a_car_only_feature() -> None:
    schema = build_tool_schema(VehicleType.ELECTRIC_MOTORBIKE, [("BATTERY_REMOVABLE", "Pin tháo rời")])

    assert "PANORAMIC_ROOF" not in _feature_enum(schema)


def test_empty_vocabulary_yields_an_empty_enum_not_a_missing_field() -> None:
    schema = build_tool_schema(VehicleType.CAR, [])

    assert _feature_enum(schema) == []


def test_unknown_vehicle_type_schema_still_declares_the_vehicle_type_field() -> None:
    schema = build_tool_schema(None, [])

    assert "vehicle_type" in schema["parameters"]["properties"]


@pytest.mark.asyncio
async def test_service_passes_db_built_vocabulary_to_the_llm_port() -> None:
    from src.agents.contracts import LLMExtractionPayload
    from src.agents.services.slot_extraction import SlotExtractionServiceImpl
    from tests.agents.unit.test_slot_extraction import Pending, Uow

    seen: dict[str, object] = {}

    class RecordingLLM:
        async def extract_slots(self, **kwargs: object) -> LLMExtractionPayload:
            seen.update(kwargs)
            return LLMExtractionPayload()

        async def synthesize(self, *, prompt: str) -> str:
            return prompt

    service = SlotExtractionServiceImpl(
        RecordingLLM(),
        Uow(Pending([])),
        FakeFeatureVocabulary({VehicleType.CAR: _CAR_FEATURES}),
    )

    await service.extract(session_id="s", customer_id="c", vehicle_type=VehicleType.CAR, user_message="x")

    assert list(seen["feature_vocabulary"]) == ["POWER_ADJUST_SEAT", "PANORAMIC_ROOF"]


def _properties(schema: dict) -> dict:
    return schema["parameters"]["properties"]


def test_motorbike_schema_asks_for_load_and_never_for_passenger_count() -> None:
    schema = build_tool_schema(VehicleType.ELECTRIC_MOTORBIKE, _CAR_FEATURES)

    assert "max_load_kg" in _properties(schema)
    assert "passenger_count" not in _properties(schema)


def test_car_schema_asks_for_passenger_count_and_never_for_load() -> None:
    schema = build_tool_schema(VehicleType.CAR, _CAR_FEATURES)

    assert "passenger_count" in _properties(schema)
    assert "max_load_kg" not in _properties(schema)


def test_unknown_vehicle_type_accepts_both_branch_specific_slots_for_same_turn_inference() -> None:
    schema = build_tool_schema(None, _CAR_FEATURES)

    assert "passenger_count" in _properties(schema)
    assert "max_load_kg" in _properties(schema)


# ── `habit_need_tags` phải là TẬP ĐÓNG, không phải chữ tự do ──────────────────


def _habit_field(schema: dict) -> dict:
    return _properties(schema)["habit_need_tags"]


def test_habit_need_tags_la_enum_cua_tap_dong_sau_nhan() -> None:
    """Lượt thật 2026-08-26: prompt dặn "giữ nguyên lời khách" nên LLM lưu
    `"nhỏ gọn"`, mà `canonical_need_tag("nhỏ gọn")` ra chuỗi rác `NH_G_N` —
    KHÔNG cộng một điểm nào. Đúng bẫy mục 3.4. Nới regex chỉ mua thêm vài chữ
    rồi lại thủng; bắt LLM chọn trong tập đóng mới là cách dứt điểm."""

    from src.agents.domain.need_tags import NeedTag

    field = _habit_field(build_tool_schema(VehicleType.CAR, _CAR_FEATURES))

    assert field["items"]["enum"] == [tag.value for tag in NeedTag]


def test_mo_ta_habit_need_tags_giai_thich_tung_nhan_bang_tieng_viet() -> None:
    """Mã trần không dạy mô hình được gì — đúng cùng một lỗi với `feature_mentions`."""

    from src.agents.domain.need_tags import NEED_TAG_REGISTRY, NeedTag

    description = _habit_field(build_tool_schema(VehicleType.CAR, _CAR_FEATURES))["description"]

    for tag in NeedTag:
        definition = NEED_TAG_REGISTRY[tag]
        assert definition.name_vi in description
        assert definition.description_vi in description
