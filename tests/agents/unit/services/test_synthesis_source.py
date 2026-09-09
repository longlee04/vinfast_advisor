"""Synthesis source maps run evidence into numeric facts and exact quotes."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.agents.adapters.synthesis_source import SqlAlchemySynthesisDataSource
from src.agents.services.synthesis import PLACEHOLDER_UNITS

RUN_ID = uuid4()
VEHICLE_1 = uuid4()
VEHICLE_2 = uuid4()
DOC_1 = uuid4()
DOC_2 = uuid4()


class _Result:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def scalars(self) -> list[SimpleNamespace]:
        return self._rows

    def all(self) -> list[SimpleNamespace]:
        # Session giả dùng trong các test cũ không phân biệt được truy vấn
        # `vehicle_documents`/`vehicle_prices` với truy vấn `run_evidence`
        # chính, nên trả rỗng an toàn — các test đó không phụ thuộc bảng chủ
        # sở hữu, chúng khớp xe qua nhánh fallback của `_owner_vehicle`.
        return []

    def scalar_one_or_none(self) -> SimpleNamespace | None:
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(
        self,
        rows: list[SimpleNamespace],
        document_rows: list[SimpleNamespace] | None = None,
    ) -> None:
        self.rows = rows
        self.document_rows = document_rows
        self.execute_count = 0

    async def execute(self, statement: object) -> _Result:
        self.execute_count += 1
        if self.execute_count == 2 and self.document_rows is not None:
            return _Result(self.document_rows)
        return _Result(self.rows)

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


@pytest.mark.asyncio
async def test_load_facts_maps_allowlisted_numeric_evidence() -> None:
    vehicle_id = uuid4()
    evidence_id = uuid4()
    row = SimpleNamespace(
        fact_code="CAR_RANGE_KM",
        value_text="399",
        evidence_id=evidence_id,
        source_table="vehicle_specs",
        source_id=vehicle_id,
    )

    facts = await SqlAlchemySynthesisDataSource(lambda: _Session([row])).load_facts(
        run_id=uuid4(), vehicle_ids=(vehicle_id,)
    )

    assert len(facts) == 1
    assert facts[0].vehicle_id == vehicle_id
    assert facts[0].unit == PLACEHOLDER_UNITS["CAR_RANGE_KM"]
    assert facts[0].source_record == f"vehicle_specs:{vehicle_id}"
    assert facts[0].evidence_id == evidence_id


@pytest.mark.asyncio
async def test_load_vehicle_name_reads_top_vehicle_from_immutable_snapshot() -> None:
    vehicle_id = uuid4()
    captured_at = datetime(2026, 8, 18, tzinfo=UTC)
    snapshot_row = SimpleNamespace(
        captured_at=captured_at,
        payload={
            "schema_version": "agent_snapshot_v1",
            "candidates": [
                {
                    "vehicle_id": str(vehicle_id),
                    "model_name": "VinFast VF 5",
                    "facts": [],
                }
            ],
            "assertions": [],
        },
    )

    name = await SqlAlchemySynthesisDataSource(lambda: _Session([snapshot_row])).load_vehicle_name(
        run_id=uuid4(), vehicle_id=vehicle_id
    )

    assert name == "VinFast VF 5"


@pytest.mark.asyncio
async def test_load_facts_skips_unknown_and_non_numeric_evidence() -> None:
    rows = [
        SimpleNamespace(
            fact_code="UNKNOWN",
            value_text="1",
            evidence_id=uuid4(),
            source_table="x",
            source_id=None,
        ),
        SimpleNamespace(
            fact_code="CAR_RANGE_KM",
            value_text="not-a-number",
            evidence_id=uuid4(),
            source_table="x",
            source_id=None,
        ),
    ]

    facts = await SqlAlchemySynthesisDataSource(lambda: _Session(rows)).load_facts(
        run_id=uuid4(), vehicle_ids=(uuid4(),)
    )

    assert list(facts) == []


@pytest.mark.asyncio
async def test_load_quotes_returns_non_empty_doc_excerpts() -> None:
    vehicle_id = uuid4()
    evidence_id = uuid4()
    row = SimpleNamespace(
        fact_code="DOC_EXCERPT",
        value_text="Cửa sổ trời toàn cảnh chống tia UV",
        evidence_id=evidence_id,
        source_table="vehicle_specs",
        source_id=vehicle_id,
    )

    quotes = await SqlAlchemySynthesisDataSource(lambda: _Session([row])).load_quotes(
        run_id=uuid4(), vehicle_ids=(vehicle_id,)
    )

    assert len(quotes) == 1
    assert quotes[0].text == row.value_text
    assert quotes[0].evidence_id == evidence_id


class _VehicleGroupResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def scalars(self) -> list:
        return self._rows

    def all(self) -> list:
        return self._rows


class _VehicleGroupSession:
    """Session giả trả lời đúng hai hình dạng truy vấn của adapter, có lọc thật.

    Khác `_Session` ở trên (luôn trả nguyên một danh sách bất kể câu lệnh gì),
    session này soi bảng đích và tham số bind thật của từng `select(...)` để
    mô phỏng đúng hành vi lọc theo xe — cần thiết vì hai test dưới đây kiểm
    tra chính hành vi lọc đó.
    """

    def __init__(self, run_evidence_rows: list, vehicle_document_rows: list) -> None:
        self._run_evidence_rows = run_evidence_rows
        self._vehicle_document_rows = vehicle_document_rows

    async def execute(self, statement: object) -> _VehicleGroupResult:
        table_name = statement.get_final_froms()[0].name
        params = statement.compile().params
        if table_name == "run_evidence":
            rows = self._run_evidence_rows
            fact_code = params.get("fact_code_1")
            if fact_code is not None:
                rows = [row for row in rows if row.fact_code == fact_code]
            return _VehicleGroupResult(rows)
        if table_name == "vehicle_documents":
            allowed = set(params.get("vehicle_id_1", ()))
            pairs = [
                (row.document_id, row.vehicle_id)
                for row in self._vehicle_document_rows
                if str(row.vehicle_id) in allowed
            ]
            return _VehicleGroupResult(pairs)
        raise AssertionError(f"unexpected table queried in fake session: {table_name}")

    async def __aenter__(self) -> _VehicleGroupSession:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


@pytest.fixture
def session_factory():
    """Một run, hai xe, mỗi xe một tài liệu và một fact — dùng chung cho cả
    test lọc quote lẫn test gán vehicle_id cho fact."""

    run_evidence_rows = [
        SimpleNamespace(
            fact_code="DOC_EXCERPT",
            value_text="Trích dẫn của xe một",
            evidence_id=uuid4(),
            source_table="vehicle_documents",
            source_id=DOC_1,
        ),
        SimpleNamespace(
            fact_code="DOC_EXCERPT",
            value_text="Trích dẫn của xe hai",
            evidence_id=uuid4(),
            source_table="vehicle_documents",
            source_id=DOC_2,
        ),
        SimpleNamespace(
            fact_code="CAR_RANGE_KM",
            value_text="399",
            evidence_id=uuid4(),
            source_table="vehicles",
            source_id=VEHICLE_1,
        ),
        SimpleNamespace(
            fact_code="CAR_RANGE_KM",
            value_text="450",
            evidence_id=uuid4(),
            source_table="vehicles",
            source_id=VEHICLE_2,
        ),
    ]
    vehicle_document_rows = [
        SimpleNamespace(document_id=DOC_1, vehicle_id=VEHICLE_1),
        SimpleNamespace(document_id=DOC_2, vehicle_id=VEHICLE_2),
    ]
    session = _VehicleGroupSession(run_evidence_rows, vehicle_document_rows)
    return lambda: session


@pytest.mark.asyncio
async def test_load_quotes_excludes_other_vehicles_in_same_run(session_factory) -> None:
    """Hai xe cùng run, mỗi xe một tài liệu: hỏi xe 1 không được trả quote xe 2."""

    source = SqlAlchemySynthesisDataSource(session_factory)

    quotes = await source.load_quotes(run_id=RUN_ID, vehicle_ids=(VEHICLE_1,))

    assert [quote.text for quote in quotes] == ["Trích dẫn của xe một"]
    assert {quote.vehicle_id for quote in quotes} == {VEHICLE_1}
    assert all(quote.source_record.startswith("vehicle_documents:") for quote in quotes)


@pytest.mark.asyncio
async def test_load_facts_tags_each_row_with_its_own_vehicle(session_factory) -> None:
    """Hai xe cùng run: mỗi fact phải mang đúng xe của hàng, không phải vehicle_ids[0]."""

    source = SqlAlchemySynthesisDataSource(session_factory)

    facts = await source.load_facts(run_id=RUN_ID, vehicle_ids=(VEHICLE_1, VEHICLE_2))

    by_vehicle = {(fact.vehicle_id, fact.fact_code) for fact in facts}
    assert (VEHICLE_1, "CAR_RANGE_KM") in by_vehicle
    assert (VEHICLE_2, "CAR_RANGE_KM") in by_vehicle
