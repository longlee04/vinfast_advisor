"""[A2-4] Vocabulary adapter đọc `feature_definitions` — thêm feature là INSERT, không sửa prompt."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.agents.adapters.feature_vocabulary import SqlAlchemyFeatureVocabularyAdapter
from src.agents.domain.values import VehicleType
from src.agents.prompts.slot_extraction_prompts import build_tool_schema


class _FakeSession:
    """Ghi lại câu lệnh đã chạy và trả về đúng các hàng được dựng sẵn."""

    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self.rows = rows
        self.statements: list[object] = []

    async def execute(self, statement: object) -> MagicMock:
        self.statements.append(statement)
        result = MagicMock()
        result.all.return_value = self.rows
        return result

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


@pytest.mark.asyncio
async def test_rows_become_code_label_pairs_in_display_order() -> None:
    session = _FakeSession([("PANORAMIC_ROOF", "Cửa sổ trời"), ("GPS", "Định vị GPS")])
    adapter = SqlAlchemyFeatureVocabularyAdapter(lambda: session)  # type: ignore[arg-type]

    features = await adapter.list_active_features(VehicleType.CAR)

    assert features == [("PANORAMIC_ROOF", "Cửa sổ trời"), ("GPS", "Định vị GPS")]


@pytest.mark.asyncio
async def test_query_keeps_only_active_rows_of_this_type_or_shared_ones() -> None:
    session = _FakeSession([])
    adapter = SqlAlchemyFeatureVocabularyAdapter(lambda: session)  # type: ignore[arg-type]

    await adapter.list_active_features(VehicleType.ELECTRIC_MOTORBIKE)

    compiled = str(session.statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "status = 'ACTIVE'" in compiled
    assert "ELECTRIC_MOTORBIKE" in compiled
    assert "IS NULL" in compiled


@pytest.mark.asyncio
async def test_a_newly_inserted_row_reaches_the_tool_schema_without_touching_prompts() -> None:
    session = _FakeSession([("HEAT_PUMP", "Bơm nhiệt")])
    adapter = SqlAlchemyFeatureVocabularyAdapter(lambda: session)  # type: ignore[arg-type]

    features = await adapter.list_active_features(VehicleType.CAR)
    schema = build_tool_schema(VehicleType.CAR, features)

    assert schema["parameters"]["properties"]["feature_mentions"]["items"]["enum"] == ["HEAT_PUMP"]
