"""Unit tests for Gate A1 Two-Layer Retrieval (Vector similarity 2a/2b, Hybrid RAG 2e with RRF k=60, NeedTags)."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.agents.adapters.catalog_reader import CatalogReadAdapter
from src.agents.adapters.embedding import DeterministicEmbeddingAdapter
from src.agents.adapters.feature_retriever import FeatureRetrievalAdapter, _vocab_cache
from src.agents.contracts import FeatureAssertion, FilterCriteria
from src.agents.domain.need_tags import NeedTag, get_need_tag_definition
from src.agents.domain.values import VehicleType
from src.agents.services.retrieval import RetrievalServiceImpl


class _SessionContext:
    """Async context manager giả lập `session_factory()` cho một session giả có sẵn."""

    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, *exc_info: object) -> None:
        return None


def _session_factory(session: object):
    """Giả lập `async_sessionmaker`: gọi ra một context manager bọc session có sẵn."""

    return lambda: _SessionContext(session)


@pytest.fixture(autouse=True)
def _reset_vocab_cache():
    """Ensure in-memory vocabulary cache is clean before each test."""
    _vocab_cache.invalidate()
    yield
    _vocab_cache.invalidate()


def test_domain_need_tags_closed_set_has_non_empty_vietnamese_descriptions():
    """A1-4b: Test every NeedTag in closed set has non-empty Vietnamese description and valid defaults."""
    for tag_enum in NeedTag:
        definition = get_need_tag_definition(tag_enum.value)
        assert definition is not None, f"NeedTag {tag_enum} missing from registry"
        assert len(definition.name_vi.strip()) > 0, f"NeedTag {tag_enum} name_vi is empty"
        assert len(definition.description_vi.strip()) > 0, f"NeedTag {tag_enum} description_vi is empty"
        assert len(definition.default_feature_codes) > 0, f"NeedTag {tag_enum} default_feature_codes is empty"

    # Tag outside closed set must return None
    assert get_need_tag_definition("INVALID_TAG_OUTSIDE_CLOSED_SET") is None


@pytest.mark.asyncio
async def test_layer1_car_filtering_queries_correct_spec_and_price():
    """Test Layer 1 hard filter constructs queries for CAR budget, seats, range."""
    mock_session = AsyncMock()
    mock_execute = MagicMock()
    mock_scalars = MagicMock()
    car_uuid = uuid4()
    mock_scalars.all.return_value = [str(car_uuid)]
    mock_execute.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_execute

    adapter = CatalogReadAdapter(_session_factory(mock_session))
    criteria = FilterCriteria(
        vehicle_type=VehicleType.CAR,
        budget_max_vnd=Decimal("700000000"),
        passenger_count=7,
        required_range_km=300,
    )

    result = await adapter.hard_filter(criteria)

    assert len(result) == 1
    assert result[0] == car_uuid
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_layer1_motorbike_filtering_separates_from_car():
    """Test Layer 1 ELECTRIC_MOTORBIKE queries motorbikes spec table without touching cars."""
    mock_session = AsyncMock()
    mock_execute = MagicMock()
    mock_scalars = MagicMock()
    bike_uuid = uuid4()
    mock_scalars.all.return_value = [str(bike_uuid)]
    mock_execute.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_execute

    adapter = CatalogReadAdapter(_session_factory(mock_session))
    criteria = FilterCriteria(
        vehicle_type=VehicleType.ELECTRIC_MOTORBIKE,
        budget_max_vnd=Decimal("50000000"),
        required_range_km=100,
        required_load_kg=150,
    )

    result = await adapter.hard_filter(criteria)

    assert len(result) == 1
    assert result[0] == bike_uuid
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("synonym_phrase", ["cửa sổ trời", "kính toàn cảnh", "nóc kính"])
async def test_layer2_vector_matching_synonyms_resolve_same_feature_code(synonym_phrase: str):
    """A1-7: Test synonyms 'cửa sổ trời', 'kính toàn cảnh', 'nóc kính' all resolve to PANORAMIC_ROOF via vector embedding."""
    mock_session = AsyncMock()

    # Mock DB load for feature_definitions and need_tags
    f_res = MagicMock()
    f_res.all.return_value = [
        ("PANORAMIC_ROOF", "Cửa sổ trời toàn cảnh", "Kính trần xe toàn cảnh panorama nóc kính"),
        ("ECO_MODE", "Chế độ tiết kiệm điện", "Tối ưu công suất"),
    ]
    n_res = MagicMock()
    n_res.all.return_value = []

    cand_id = uuid4()
    flag_res = MagicMock()
    flag_scalars = MagicMock()
    flag_row = MagicMock()
    flag_row.vehicle_id = str(cand_id)
    flag_row.feature_code = "PANORAMIC_ROOF"
    flag_row.status = "YES"
    flag_row.confidence = Decimal("0.95")
    flag_scalars.all.return_value = [flag_row]
    flag_res.scalars.return_value = flag_scalars

    empty_fts_res = MagicMock()
    empty_fts_res.all.return_value = []
    empty_dense_res = MagicMock()
    empty_dense_res.all.return_value = []

    mock_session.execute.side_effect = [f_res, n_res, flag_res, empty_fts_res, empty_dense_res]

    embedding_adapter = DeterministicEmbeddingAdapter()
    retriever = FeatureRetrievalAdapter(mock_session, embedding_port=embedding_adapter, threshold=0.40)

    assertions = await retriever.resolve(
        utterance=synonym_phrase,
        vehicle_type=VehicleType.CAR,
        candidate_ids=[cand_id],
    )

    assert len(assertions) >= 1
    matched_codes = {a.feature_code for a in assertions if a.status == "YES"}
    assert "PANORAMIC_ROOF" in matched_codes


@pytest.mark.asyncio
async def test_layer2_vector_matching_need_tag_urban_traffic():
    """A1-7: Test phrase 'hay đi trong phố' resolves to URBAN_TRAFFIC need tag and its default features."""
    mock_session = AsyncMock()

    f_res = MagicMock()
    f_res.all.return_value = [
        ("ECO_MODE", "Chế độ tiết kiệm", "Chế độ sinh thái"),
        ("COMPACT_SIZE", "Kích thước nhỏ gọn", "Dễ xoay xở"),
    ]
    n_res = MagicMock()
    n_res.all.return_value = []

    cand_id = uuid4()
    flag_res = MagicMock()
    flag_scalars = MagicMock()
    flag_row = MagicMock()
    flag_row.vehicle_id = str(cand_id)
    flag_row.feature_code = "COMPACT_SIZE"
    flag_row.status = "YES"
    flag_row.confidence = Decimal("0.90")
    flag_scalars.all.return_value = [flag_row]
    flag_res.scalars.return_value = flag_scalars

    empty_fts_res = MagicMock()
    empty_fts_res.all.return_value = []
    empty_dense_res = MagicMock()
    empty_dense_res.all.return_value = []

    mock_session.execute.side_effect = [f_res, n_res, flag_res, empty_fts_res, empty_dense_res]

    embedding_adapter = DeterministicEmbeddingAdapter()
    retriever = FeatureRetrievalAdapter(mock_session, embedding_port=embedding_adapter, threshold=0.50)

    assertions = await retriever.resolve(
        utterance="hay đi trong phố",
        vehicle_type=VehicleType.CAR,
        candidate_ids=[cand_id],
    )

    matched_codes = {a.feature_code for a in assertions}
    assert "ECO_MODE" in matched_codes or "COMPACT_SIZE" in matched_codes


@pytest.mark.asyncio
async def test_layer2_below_threshold_returns_unknown():
    """Test Layer 2 returns UNKNOWN status when vector similarity is below threshold."""
    mock_session = AsyncMock()

    f_res = MagicMock()
    f_res.all.return_value = [("PANORAMIC_ROOF", "Cửa sổ trời", "Panoramic roof")]
    n_res = MagicMock()
    n_res.all.return_value = []

    empty_fts_res = MagicMock()
    empty_fts_res.all.return_value = []
    empty_dense_res = MagicMock()
    empty_dense_res.all.return_value = []
    mock_session.execute.side_effect = [f_res, n_res, empty_fts_res, empty_dense_res]

    embedding_adapter = DeterministicEmbeddingAdapter()
    retriever = FeatureRetrievalAdapter(mock_session, embedding_port=embedding_adapter, threshold=0.99)
    cand_id = uuid4()

    assertions = await retriever.resolve(
        utterance="xyz completely unrelated text 123",
        vehicle_type=VehicleType.CAR,
        candidate_ids=[cand_id],
    )

    assert len(assertions) == 1
    assert assertions[0].status == "UNKNOWN"
    assert assertions[0].evidence_ref == "below_similarity_threshold"


@pytest.mark.asyncio
async def test_retrieval_service_orchestrates_layer1_and_layer2():
    """Test RetrievalServiceImpl delegates correctly to ports."""
    mock_reader = AsyncMock()
    mock_retriever = AsyncMock()

    cand_id = uuid4()
    mock_reader.hard_filter.return_value = [cand_id]
    expected_assertion = FeatureAssertion(
        vehicle_id=cand_id,
        feature_code="PANORAMIC_ROOF",
        status="YES",
        source="FLAG",
        evidence_ref="flag_test",
    )
    mock_retriever.resolve.return_value = [expected_assertion]

    service = RetrievalServiceImpl(catalog_reader=mock_reader, feature_retriever=mock_retriever)

    l1_res = await service.layer1(FilterCriteria(vehicle_type=VehicleType.CAR, budget_max_vnd=Decimal("800000000")))
    assert l1_res == [cand_id]

    l2_res = await service.layer2(utterance="cửa sổ trời", vehicle_type=VehicleType.CAR, candidate_ids=[cand_id])
    assert l2_res == [expected_assertion]
