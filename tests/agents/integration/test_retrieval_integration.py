"""Integration tests for Gate A1 Retrieval with PostgreSQL database."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.agents.adapters.catalog_reader import CatalogReadAdapter
from src.agents.adapters.feature_retriever import reverse_write_pending_flag
from src.agents.contracts import FilterCriteria
from src.agents.domain.values import VehicleType
from src.products.infrastructure.models import (
    CarSpecRow,
    FeatureDefinitionRow,
    VehicleFeatureFlagRow,
    VehiclePriceRow,
    VehicleRow,
)


@pytest_asyncio.fixture
async def session(migrated_engine: AsyncEngine):
    """Provide a transactional AsyncSession for integration tests."""
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def session_factory(migrated_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Nguồn session độc lập cùng engine, cho CatalogReadAdapter tự mở/đóng session."""
    return async_sessionmaker(migrated_engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_layer1_hard_filter_db_integration(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
):
    """Integration test for Layer 1 SQL hard filter querying real database tables."""
    now_utc = datetime.now(UTC)
    v_id_1 = str(uuid.uuid4())
    v_id_2 = str(uuid.uuid4())

    # Vehicle 1: Active car under 700m, 7 seats, range 400km
    car1 = VehicleRow(
        vehicle_id=v_id_1,
        vehicle_type="CAR",
        brand="VinFast",
        model_name="VF 7",
        variant_name="Plus",
        status="ACTIVE",
        slug="vf-7-plus-test",
        created_at=now_utc,
        updated_at=now_utc,
    )
    price1 = VehiclePriceRow(
        price_id=str(uuid.uuid4()),
        vehicle_id=v_id_1,
        price_type="STARTING_PRICE",
        amount_vnd=650000000,
        status="ACTIVE",
        valid_from=now_utc,
        created_at=now_utc,
        updated_at=now_utc,
    )
    spec1 = CarSpecRow(
        vehicle_id=v_id_1,
        seat_count=7,
        range_km=Decimal("400"),
        created_at=now_utc,
        updated_at=now_utc,
    )

    # Vehicle 2: Active car over 700m (850m) - should be filtered out
    car2 = VehicleRow(
        vehicle_id=v_id_2,
        vehicle_type="CAR",
        brand="VinFast",
        model_name="VF 8",
        variant_name="Eco",
        status="ACTIVE",
        slug="vf-8-eco-test",
        created_at=now_utc,
        updated_at=now_utc,
    )
    price2 = VehiclePriceRow(
        price_id=str(uuid.uuid4()),
        vehicle_id=v_id_2,
        price_type="STARTING_PRICE",
        amount_vnd=850000000,
        status="ACTIVE",
        valid_from=now_utc,
        created_at=now_utc,
        updated_at=now_utc,
    )
    spec2 = CarSpecRow(
        vehicle_id=v_id_2,
        seat_count=5,
        range_km=Decimal("450"),
        created_at=now_utc,
        updated_at=now_utc,
    )

    session.add_all([car1, price1, spec1, car2, price2, spec2])
    await session.commit()

    adapter = CatalogReadAdapter(session_factory)
    criteria = FilterCriteria(
        vehicle_type=VehicleType.CAR,
        budget_max_vnd=Decimal("700000000"),
        passenger_count=7,
        required_range_km=350,
    )

    candidate_ids = await adapter.hard_filter(criteria)

    assert len(candidate_ids) == 1
    assert str(candidate_ids[0]) == v_id_1


@pytest.mark.asyncio
async def test_layer2_reverse_write_pending_flag_db_integration(session: AsyncSession):
    """Test reverse write creates PENDING feature flag when evidence is found."""
    v_id = str(uuid.uuid4())
    f_code = "PANORAMIC_ROOF"
    now_utc = datetime.now(UTC)

    # Create vehicle row first to satisfy FK constraint
    vehicle = VehicleRow(
        vehicle_id=v_id,
        vehicle_type="CAR",
        brand="VinFast",
        model_name="VF 6",
        status="ACTIVE",
        slug=f"vf-6-{v_id}",
        created_at=now_utc,
        updated_at=now_utc,
    )
    # Create feature definition
    fdef = FeatureDefinitionRow(
        feature_code=f_code,
        name="Cửa sổ trời toàn cảnh",
        category="COMFORT",
        status="ACTIVE",
        created_at=now_utc,
        updated_at=now_utc,
    )
    session.add_all([vehicle, fdef])
    await session.commit()

    await reverse_write_pending_flag(
        session=session,
        vehicle_id=v_id,
        feature_code=f_code,
        status="YES",
        confidence=0.88,
    )

    # Verify in DB
    row = (
        await session.execute(
            VehicleFeatureFlagRow.__table__.select().where(
                VehicleFeatureFlagRow.vehicle_id == v_id,
                VehicleFeatureFlagRow.feature_code == f_code,
            )
        )
    ).first()

    assert row is not None
    assert row.verification_status == "PENDING"
    assert row.status == "YES"


@pytest.mark.asyncio
async def test_vehicle_name_resolution_ignores_spacing(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
):
    """[A4-1] "vf3" phải ra đúng mẫu catalog ghi là "VF 3".

    Khách gõ liền là cách gõ phổ biến nhất, còn catalog luôn ghi có dấu cách. So
    khớp nguyên văn khiến câu hỏi giá thường gặp nhất trả về "chưa tìm thấy trong
    danh mục" — tức đọc đúng dữ liệu nhưng vẫn không phục vụ được ai.

    Vẫn là khớp CHÍNH XÁC: tiền tố "vf" không được ra xe nào, vì đoán danh tính
    xe là điều A4-1 cấm.
    """

    now_utc = datetime.now(UTC)
    vehicle_id = str(uuid.uuid4())
    session.add(
        VehicleRow(
            vehicle_id=vehicle_id,
            vehicle_type="CAR",
            brand="VinFast",
            model_name="VF 3",
            variant_name="All New",
            status="ACTIVE",
            slug=f"vf-3-all-new-{vehicle_id[:8]}",
            created_at=now_utc,
            updated_at=now_utc,
        )
    )
    await session.commit()
    adapter = CatalogReadAdapter(session_factory)

    for mention in ("vf3", "VF 3", "vf  3", "VinFast VF 3 All New"):
        matches = await adapter.resolve_vehicle_names([mention])
        assert [m.display_name for m in matches] == ["VinFast VF 3 All New"], mention

    assert await adapter.resolve_vehicle_names(["vf"]) == []


@pytest.mark.asyncio
async def test_active_feature_codes_returns_active_rows_for_vehicle_type(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
):
    """`active_feature_codes` chỉ lấy ACTIVE, khớp `vehicle_type` hoặc dùng chung.

    DB tích hợp dùng chung một database cho cả session pytest và bảng
    `feature_definitions` không bị truncate giữa các test (khác các bảng
    trong `clean_agent_database`) — test khác trong file này (vd
    `test_layer2_reverse_write_pending_flag_db_integration`) có thể để lại
    hàng. Vì vậy chỉ kiểm tra bao hàm/loại trừ đúng logic lọc, không so khớp
    tuyệt đối cả tập kết quả.
    """
    now_utc = datetime.now(UTC)

    def _fdef(feature_code: str, vehicle_type: str | None, status: str) -> FeatureDefinitionRow:
        return FeatureDefinitionRow(
            feature_code=feature_code,
            name=feature_code,
            category="SAFETY",
            vehicle_type=vehicle_type,
            status=status,
            created_at=now_utc,
            updated_at=now_utc,
        )

    session.add_all(
        [
            _fdef("HIGH_PAYLOAD", "CAR", "ACTIVE"),
            _fdef("SHARED_FEATURE", None, "ACTIVE"),
            _fdef("BIKE_ONLY_FEATURE", "ELECTRIC_MOTORBIKE", "ACTIVE"),
            _fdef("ARCHIVED_CAR_FEATURE", "CAR", "ARCHIVED"),
        ]
    )
    await session.commit()

    adapter = CatalogReadAdapter(session_factory)
    codes = await adapter.active_feature_codes(VehicleType.CAR)

    assert isinstance(codes, frozenset)
    assert {"HIGH_PAYLOAD", "SHARED_FEATURE"} <= codes
    assert "BIKE_ONLY_FEATURE" not in codes
    assert "ARCHIVED_CAR_FEATURE" not in codes
