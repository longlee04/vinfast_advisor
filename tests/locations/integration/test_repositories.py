"""Truy vấn thật trên Postgres cho module Locations."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.locations.domain.values import BoundingBox, Coordinate
from src.locations.infrastructure.models import LocationRow
from src.locations.infrastructure.repositories import SqlAlchemyLocationStore

NOW = datetime(2026, 8, 8, 12, tzinfo=UTC)

HANOI = (21.028511, 105.804817)
HCMC = (10.762622, 106.660172)


def make_row(
    identifier: str,
    *,
    latitude: float,
    longitude: float,
    location_type: str = "test_charging_station",
    city: str = "Hà Nội",
    district: str | None = "Quận Ba Đình",
    name: str = "Trạm sạc mẫu",
    address: str = "1 Đường Mẫu, Quận Ba Đình, Hà Nội",
) -> LocationRow:
    return LocationRow(
        location_id=identifier,
        external_id=f"EXT-{identifier}",
        location_type=location_type,
        category_name="Trạm sạc mẫu",
        name=name,
        address=address,
        city=city,
        district=district,
        province_id="01",
        district_id="001",
        latitude=latitude,
        longitude=longitude,
        hotline="19002338",
        directions_url=None,
        open_time="07:00",
        close_time="22:00",
        status="ACTIVE",
        source_url=None,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_bounds_include_points_exactly_on_the_edge(locations_session_factory) -> None:
    async with locations_session_factory() as session:
        session.add(make_row("edge", latitude=21.0, longitude=105.0, location_type="test_edge"))
        session.add(make_row("outside", latitude=22.5, longitude=105.0, location_type="test_edge"))
        await session.commit()

        store = SqlAlchemyLocationStore(locations_session_factory)
        page = await store.list_in_bounds(
            bounds=BoundingBox.parse(south=21.0, north=22.0, west=104.0, east=106.0),
            types=("test_edge",),
            city=None,
            district=None,
            query=None,
            limit=500,
        )

    assert page.total == 1
    assert page.items[0].external_id == "EXT-edge"


@pytest.mark.asyncio
async def test_truncated_flag_turns_on_when_matches_exceed_limit(
    locations_session_factory,
) -> None:
    async with locations_session_factory() as session:
        for index in range(5):
            session.add(
                make_row(
                    f"row-{index}",
                    latitude=21.0 + index / 1000,
                    longitude=105.0,
                    location_type="test_trunc",
                )
            )
        await session.commit()

        store = SqlAlchemyLocationStore(locations_session_factory)
        page = await store.list_in_bounds(
            bounds=None, types=("test_trunc",), city=None, district=None, query=None, limit=2
        )

    assert page.total == 5
    assert len(page.items) == 2
    assert page.truncated is True


@pytest.mark.asyncio
async def test_wildcard_in_query_does_not_match_everything(
    locations_session_factory,
) -> None:
    async with locations_session_factory() as session:
        session.add(make_row("plain", latitude=21.0, longitude=105.0, name="Trạm A", location_type="test_wild"))
        session.add(make_row("other", latitude=21.1, longitude=105.1, name="Trạm B", location_type="test_wild"))
        await session.commit()

        store = SqlAlchemyLocationStore(locations_session_factory)
        page = await store.list_in_bounds(
            bounds=None, types=("test_wild",), city=None, district=None, query="%", limit=500
        )

    assert page.total == 0


@pytest.mark.asyncio
async def test_nearby_sorts_by_distance_and_drops_points_outside_the_radius(
    locations_session_factory,
) -> None:
    async with locations_session_factory() as session:
        session.add(make_row("near", latitude=21.030, longitude=105.806, location_type="test_near"))
        session.add(make_row("far", latitude=21.100, longitude=105.900, location_type="test_near"))
        session.add(make_row("saigon", latitude=HCMC[0], longitude=HCMC[1], location_type="test_near"))
        await session.commit()

        store = SqlAlchemyLocationStore(locations_session_factory)
        page = await store.list_nearby(
            origin=Coordinate.parse(latitude=HANOI[0], longitude=HANOI[1]),
            radius_km=Decimal("20"),
            types=("test_near",),
            limit=50,
        )

    assert [item.external_id for item in page.items] == ["EXT-near", "EXT-far"]
    assert page.items[0].distance_km < page.items[1].distance_km


@pytest.mark.asyncio
async def test_category_counts_match_the_stored_rows(locations_session_factory) -> None:
    async with locations_session_factory() as session:
        session.add(make_row("a", latitude=21.0, longitude=105.0, location_type="test_cat_a"))
        session.add(make_row("b", latitude=21.1, longitude=105.1, location_type="test_cat_a"))
        session.add(make_row("c", latitude=21.2, longitude=105.2, location_type="test_cat_b"))
        await session.commit()

        store = SqlAlchemyLocationStore(locations_session_factory)
        counts = {entry.location_type: entry.count for entry in await store.count_by_category()}

    assert counts.get("test_cat_a") == 2
    assert counts.get("test_cat_b") == 1


@pytest.mark.asyncio
async def test_regions_group_districts_under_their_city(locations_session_factory) -> None:
    """ĐỔI KỲ VỌNG 2026-08-31: danh mục tỉnh/quận CHỈ đọc từ SHOWROOM.

    Prod có ~60k hàng trạm sạc/tủ pin crawl với cột city BẨN (13.487 giá trị
    khác nhau: địa chỉ, tên người, cả KINH ĐỘ) — đổ hết vào dropdown thì khách
    "không chọn được tên tỉnh thành" (Sếp báo). Showroom seed chuẩn đúng 36
    tỉnh/thành nên làm nguồn danh mục; các loại khác không góp tên vùng nữa.
    """

    async with locations_session_factory() as session:
        session.add(
            make_row(
                "a",
                latitude=21.0,
                longitude=105.0,
                city="Thành Phố Mẫu",
                district="Quận Mẫu A",
                location_type="showroom_car",
            )
        )
        session.add(
            make_row(
                "b",
                latitude=21.1,
                longitude=105.1,
                city="Thành Phố Mẫu",
                district="Quận Mẫu B",
                location_type="showroom_escooter",
            )
        )
        session.add(
            make_row(
                "rac",
                latitude=21.2,
                longitude=105.2,
                city="105.27655792236328",
                district="Phạm Văn Thoả + Nguyễn Thị Huệ",
                location_type="battery_swap_station",
            )
        )
        await session.commit()

        store = SqlAlchemyLocationStore(locations_session_factory)
        regions = {entry.city: entry.districts for entry in await store.list_regions()}

    assert regions["Thành Phố Mẫu"] == ("Quận Mẫu A", "Quận Mẫu B")
    assert "105.27655792236328" not in regions
