"""[FIND_NEARBY_LOCATION] Khoảng cách Haversine, đo trên Postgres thật.

[KHÁC BIỆT] Đặc tả tính năng mô tả Haversine như một hàm Python trong service, và
một unit test thuần cho nó. Trong repo này phép tính KHÔNG nằm ở Python: nó là
một biểu thức SQL (`src/locations/infrastructure/repositories._haversine_km`),
chạy trong cùng câu lệnh với bộ lọc bounding box để 60 nghìn điểm không phải rời
database. Viết lại công thức bằng Python chỉ để có một test chạy không cần hạ
tầng là test một BẢN SAO — bản sao đó vẫn xanh nguyên vẹn trong khi biểu thức
SQL thật bị sửa sai.

Vì vậy test này cần Postgres và tự SKIP khi thiếu DSN, cùng khuôn với các test
tích hợp khác trong thư mục này. `tests/agents/unit/services/` giữ phần logic
chạy được không cần hạ tầng (lọc theo loại, xếp thứ tự, nới bán kính, làm tròn,
geocode hỏng).
"""

from decimal import Decimal

import pytest

from src.agents.adapters.nearby_location_source import LocationsNearbySource
from src.locations.domain.values import Coordinate
from src.locations.infrastructure.repositories import SqlAlchemyLocationStore
from tests.locations.integration.test_repositories import make_row

#: Hai điểm có khoảng cách đường chim bay đã biết trước.
#:
#: Hồ Hoàn Kiếm (21.028511, 105.852260) → Sân bay Nội Bài (21.221200, 105.807200):
#: 21,9 km theo công thức Haversine trên bán kính Trái Đất 6371 km. Chọn một cặp
#: TRONG bán kính tối đa 50 km để cùng số liệu dùng được cho cả `list_nearby`.
HOAN_KIEM = (21.028511, 105.852260)
NOI_BAI = (21.221200, 105.807200)
EXPECTED_KM = 21.9

#: Sai số cho phép: 1% như đặc tả yêu cầu.
TOLERANCE = EXPECTED_KM * 0.01

#: `location_type` RIÊNG cho test, không phải `car_charging_station` thật.
#: Database phát triển đang giữ 22.898 trạm sạc ô tô thật quanh Hà Nội, nên lọc
#: theo loại thật sẽ trộn chúng vào kết quả và bài test thứ tự đo một tập dữ
#: liệu khác nhau ở mỗi máy. Loại trạm chỉ là một tham số của truy vấn, nên
#: dùng một giá trị cô lập không làm giảm thứ đang được kiểm: `ORDER BY` trên
#: khoảng cách.
TEST_STATION_TYPE = "test_charging_nearest"


@pytest.mark.asyncio
async def test_haversine_matches_a_known_distance_within_one_percent(
    locations_session_factory,
) -> None:
    """Khoảng cách giữa hai toạ độ đã biết, sai số < 1%."""

    async with locations_session_factory() as session:
        session.add(
            make_row(
                "noibai",
                latitude=NOI_BAI[0],
                longitude=NOI_BAI[1],
                location_type="test_haversine",
                name="Trạm sạc Nội Bài",
            )
        )
        await session.commit()

    store = SqlAlchemyLocationStore(locations_session_factory)
    page = await store.list_nearby(
        origin=Coordinate.parse(latitude=HOAN_KIEM[0], longitude=HOAN_KIEM[1]),
        radius_km=Decimal("50"),
        types=("test_haversine",),
        limit=10,
    )

    assert len(page.items) == 1
    measured = float(page.items[0].distance_km)
    assert abs(measured - EXPECTED_KM) < TOLERANCE, (
        f"Haversine trả {measured} km, chờ {EXPECTED_KM} km (±{TOLERANCE:.3f})"
    )


@pytest.mark.asyncio
async def test_adapter_returns_places_sorted_by_real_distance(
    locations_session_factory,
) -> None:
    """Thứ tự tăng dần do `ORDER BY` trong SQL quyết định, không do Python sắp lại.

    Ba hàng được CHÈN theo thứ tự xa → gần, nên một adapter chỉ chép lại thứ tự
    đọc được từ bảng sẽ làm test này đỏ.
    """

    async with locations_session_factory() as session:
        session.add(
            make_row(
                "far",
                latitude=21.221200,
                longitude=105.807200,
                location_type=TEST_STATION_TYPE,
                name="Trạm xa",
            )
        )
        session.add(
            make_row(
                "mid",
                latitude=21.100000,
                longitude=105.840000,
                location_type=TEST_STATION_TYPE,
                name="Trạm giữa",
            )
        )
        session.add(
            make_row(
                "near",
                latitude=21.030000,
                longitude=105.853000,
                location_type=TEST_STATION_TYPE,
                name="Trạm gần",
            )
        )
        await session.commit()

    source = LocationsNearbySource(locations_session_factory)
    rows = await source.nearest(
        latitude=HOAN_KIEM[0],
        longitude=HOAN_KIEM[1],
        radius_km=50.0,
        location_types=(TEST_STATION_TYPE,),
        limit=5,
    )

    names = [row.name for row in rows]
    assert names == ["Trạm gần", "Trạm giữa", "Trạm xa"]
    distances = [row.distance_km for row in rows]
    assert distances == sorted(distances)
    # Trạm gần nhất cách chưa tới nửa cây số — nếu hoán vị lat/lon thì con số này
    # nhảy lên hàng nghìn km, và đó là kiểu lỗi im lặng duy nhất mà bài test thứ
    # tự ở trên không bắt được.
    assert distances[0] < 0.5
