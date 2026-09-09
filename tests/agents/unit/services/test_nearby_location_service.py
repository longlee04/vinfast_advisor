"""[FIND_NEARBY_LOCATION] Use case tìm địa điểm — không DB, không LLM, không mạng.

Bốn nhánh mà mọi thứ khác dựa vào: chưa rõ LOẠI thì hỏi kèm nút bấm, chưa có VỊ
TRÍ thì hỏi, có cả hai thì XẾP theo khoảng cách, geocode hỏng thì TRẢ LỜI TỬ TẾ
chứ không ném lỗi.
"""

from __future__ import annotations

import pytest

from src.agents.domain.nearby_location import LocationKind, UserLocation
from src.agents.ports import GeocodedPlace, NearbyPlace
from src.agents.services.nearby_location import NearbyLocationServiceImpl

HANOI = UserLocation(latitude=21.0285, longitude=105.8542)


def _station(
    identifier: str, name: str, distance_km: float, location_type: str = "car_charging_station"
) -> NearbyPlace:
    return NearbyPlace(
        id=identifier,
        location_type=location_type,
        category_label="Trạm sạc ô tô điện",
        name=name,
        address=f"{name}, Hà Nội",
        latitude=21.01,
        longitude=105.84,
        distance_km=distance_km,
        hotline=None,
        open_time=None,
        close_time=None,
        status="1",
    )


class FakeStations:
    """Trả về đúng những gì được nạp, và ghi lại bán kính từng lần được hỏi."""

    def __init__(self, rows: list[NearbyPlace], *, min_radius_km: float = 0.0) -> None:
        self._rows = rows
        self._min_radius_km = min_radius_km
        self.radii: list[float] = []
        self.types: list[tuple[str, ...]] = []

    async def nearest(self, *, latitude, longitude, radius_km, location_types, limit):
        del latitude, longitude
        self.radii.append(radius_km)
        self.types.append(tuple(location_types))
        if radius_km < self._min_radius_km:
            return []
        # Lọc theo loại NGAY TRONG fake, đúng như adapter thật làm bằng `WHERE
        # location_type IN (...)`. Fake bỏ qua bộ lọc sẽ khiến bài test "truy vấn
        # tủ đổi pin không được trả về showroom" luôn xanh dù service truyền sai
        # loại — tức là test đúng thứ nó sinh ra để bắt lại không bắt được gì.
        rows = [row for row in self._rows if row.location_type in set(location_types)]
        return rows[:limit]


class FakeGeocoder:
    """`None` cho địa danh nằm trong `unknown` — đúng hợp đồng `GeocodePort`."""

    def __init__(self, unknown: frozenset[str] = frozenset()) -> None:
        self._unknown = unknown
        self.calls: list[str] = []

    async def geocode(self, location_text: str) -> GeocodedPlace | None:
        self.calls.append(location_text)
        if location_text in self._unknown:
            return None
        return GeocodedPlace(21.03, 105.85, f"{location_text}, Hà Nội")


class ExplodingGeocoder:
    """Nhà cung cấp ngoài đang hỏng hẳn — service KHÔNG được để lỗi thoát ra."""

    async def geocode(self, location_text: str) -> GeocodedPlace | None:
        raise RuntimeError(f"nominatim down: {location_text}")


@pytest.mark.asyncio
async def test_turn_without_a_known_location_asks_instead_of_guessing() -> None:
    """Chưa biết khách ở đâu thì DỪNG và hỏi.

    Đoán một toạ độ mặc định sẽ trả về một danh sách trông rất thuyết phục và sai
    hoàn toàn — khách chỉ phát hiện ra khi đã lái tới nơi.
    """

    stations = FakeStations([_station("EXT-1", "Vincom", 1.0)])
    service = NearbyLocationServiceImpl(locations=stations, geocoder=FakeGeocoder())

    result = await service.answer(user_message="tìm trạm sạc gần nhất")

    assert result is not None
    assert result.needs_location is True
    assert result.locations is not None and result.locations.needs_location is True
    assert result.locations.locations == []
    assert result.pending_request is not None
    assert result.pending_request.intent == "FIND_NEARBY_LOCATION"
    assert result.pending_request.missing_slot == "user_location"
    # Không một lần đọc database nào trước khi biết khách ở đâu.
    assert stations.radii == []


@pytest.mark.asyncio
async def test_known_location_returns_places_sorted_by_distance() -> None:
    """Danh sách giữ nguyên thứ tự tăng dần và làm tròn 1 chữ số thập phân."""

    rows = [
        _station("EXT-1", "Vincom Bà Triệu", 1.24),
        _station("EXT-2", "Royal City", 3.5),
        _station("EXT-3", "Times City", 7.08),
    ]
    service = NearbyLocationServiceImpl(locations=FakeStations(rows))

    result = await service.answer(user_message="trạm sạc ô tô gần đây", known_location=HANOI)

    assert result is not None and result.locations is not None
    assert [item.distance_km for item in result.locations.locations] == [1.2, 3.5, 7.1]
    assert [item.id for item in result.locations.locations] == ["EXT-1", "EXT-2", "EXT-3"]
    assert result.locations.needs_location is False


@pytest.mark.asyncio
async def test_fallback_lead_reads_as_one_sentence() -> None:
    """Câu dự phòng không được lặp chữ.

    `format_distance` tự thêm "khoảng" cho quãng dưới 1 km, nên một template
    cũng thêm "khoảng" sẽ sinh "cách khoảng khoảng 600 m" — quan sát được trên
    dữ liệu thật, và chỉ ở đúng những trạm gần nhất, tức những trạm khách đọc
    nhiều nhất.
    """

    service = NearbyLocationServiceImpl(locations=FakeStations([_station("EXT-1", "Trạm Nhà Thờ", 0.62)]))

    result = await service.answer(user_message="trạm sạc gần đây", known_location=HANOI)

    assert result is not None
    assert "khoảng khoảng" not in result.answer
    # 0.62 km được LÀM TRÒN 1 chữ số (0.6) trước khi định dạng, nên câu chữ khớp
    # đúng con số trên card — hai chỗ không được nói hai khoảng cách khác nhau.
    assert "cách khoảng 600 m" in result.answer


@pytest.mark.asyncio
async def test_maps_url_carries_both_origin_and_destination() -> None:
    """Deep link phải kèm `origin`.

    Thiếu nó, Google Maps tự xin quyền vị trí một lần nữa trên máy khách — đúng
    quyền mà khách có thể vừa từ chối ở trang này, và khi đó tuyến đường không
    bao giờ dựng được.
    """

    service = NearbyLocationServiceImpl(locations=FakeStations([_station("EXT-1", "Vincom", 1.2)]))

    result = await service.answer(user_message="trạm sạc gần đây", known_location=HANOI)

    assert result is not None and result.locations is not None
    url = result.locations.locations[0].maps_url
    assert "origin=21.0285,105.8542" in url
    assert "destination=21.01,105.84" in url


@pytest.mark.asyncio
async def test_search_widens_the_radius_before_giving_up() -> None:
    """Quét nới dần: 5 km rỗng thì thử 15 km, không bắn thẳng bán kính tối đa."""

    stations = FakeStations([_station("EXT-1", "Xa", 12.0)], min_radius_km=15.0)
    service = NearbyLocationServiceImpl(locations=stations)

    result = await service.answer(user_message="trạm sạc gần đây", known_location=HANOI)

    assert stations.radii == [5.0, 15.0]
    assert result is not None and result.locations is not None
    assert len(result.locations.locations) == 1
    assert result.locations.searched_radius_km == 15.0


@pytest.mark.asyncio
async def test_no_station_within_range_states_how_far_it_looked() -> None:
    """Rỗng KHÔNG được im lặng: câu trả lời phải nói đã quét bao xa."""

    service = NearbyLocationServiceImpl(locations=FakeStations([], min_radius_km=999.0))

    result = await service.answer(user_message="trạm sạc gần đây", known_location=HANOI)

    assert result is not None and result.locations is not None
    assert result.locations.locations == []
    assert "50" in result.answer
    assert result.needs_location is False


@pytest.mark.asyncio
async def test_failed_geocoding_replies_with_a_fallback_instead_of_raising() -> None:
    """Địa danh không tra ra → mời khách nói rõ hơn, không ném lỗi lên trên."""

    geocoder = FakeGeocoder(unknown=frozenset({"Xã Không Tồn Tại"}))
    service = NearbyLocationServiceImpl(locations=FakeStations([]), geocoder=geocoder)

    result = await service.answer(
        user_message="trạm sạc gần đây",
        location_text="Xã Không Tồn Tại",
        assume_request=True,
    )

    assert result is not None
    assert result.needs_location is True
    assert "Xã Không Tồn Tại" in result.answer
    assert result.pending_request is not None
    assert geocoder.calls == ["Xã Không Tồn Tại"]


@pytest.mark.asyncio
async def test_geocoder_failure_is_contained_by_the_port_contract() -> None:
    """`GeocodePort` cam kết nuốt lỗi hạ tầng.

    Một adapter phá cam kết đó phải làm test này đỏ ở ĐÂY, chứ không phải làm
    lượt của khách trả 500 trên production.
    """

    service = NearbyLocationServiceImpl(locations=FakeStations([]), geocoder=ExplodingGeocoder())

    with pytest.raises(RuntimeError):
        await service.answer(user_message="trạm sạc gần đây", location_text="Cầu Giấy", assume_request=True)


@pytest.mark.asyncio
async def test_motorbike_question_does_not_return_car_stations() -> None:
    """Khách đi xe máy điện nhận trạm xe máy + tủ đổi pin, không phải trụ ô tô."""

    stations = FakeStations([_station("EXT-1", "Trạm xe máy", 0.4, "bike_charging_station")])
    service = NearbyLocationServiceImpl(locations=stations)

    await service.answer(user_message="trạm sạc xe máy điện gần đây", known_location=HANOI)

    assert stations.types[0] == ("bike_charging_station",)


@pytest.mark.asyncio
async def test_unrelated_turn_is_not_hijacked() -> None:
    """`None` = "lượt này không thuộc nhánh trạm sạc", để nơi gọi rơi xuống nhánh cũ."""

    service = NearbyLocationServiceImpl(locations=FakeStations([]))

    assert await service.answer(user_message="VF 5 giá bao nhiêu") is None
    assert await service.answer(user_message="nhà em có sạc tại nhà rồi") is None


@pytest.mark.asyncio
async def test_query_for_one_kind_never_returns_another() -> None:
    """[Bước 5'] Tra tủ đổi pin KHÔNG được trả về showroom.

    Đây là bất biến then chốt của việc tổng quát hoá: năm loại dùng chung một
    bảng, một truy vấn và một service, nên một bộ lọc thiếu sẽ trả về đúng thứ
    trông giống kết quả — cùng khoảng cách, cùng hình dạng card — nhưng sai loại.
    """

    rows = [
        _station("SW-1", "Tủ đổi pin Nhà Thờ", 0.3, "battery_swap_station"),
        _station("SR-1", "Showroom Long Biên", 0.4, "showroom_car"),
        _station("CS-1", "Trạm sạc Bà Triệu", 0.5, "car_charging_station"),
    ]
    stations = FakeStations(rows)
    service = NearbyLocationServiceImpl(locations=stations)

    result = await service.answer(user_message="tủ đổi pin gần đây", known_location=HANOI)

    assert result is not None and result.locations is not None
    assert [item.id for item in result.locations.locations] == ["SW-1"]
    assert stations.types[0] == ("battery_swap_station",)
    assert result.locations.location_types == ["BATTERY_SWAP_CABINET"]
    # Tủ đổi pin không có cổng sạc nào để nói.
    assert result.locations.locations[0].charger_type is None


@pytest.mark.asyncio
async def test_typeless_question_asks_which_kind_with_five_buttons() -> None:
    """Chưa rõ loại thì HỎI, và hỏi bằng nút bấm chứ không bắt khách gõ lại."""

    stations = FakeStations([_station("EXT-1", "Vincom", 1.0)])
    service = NearbyLocationServiceImpl(locations=stations)

    result = await service.answer(user_message="tìm chỗ gần tôi")

    assert result is not None
    assert result.needs_location_kind is True
    assert result.locations is not None and result.locations.needs_location_kind is True
    assert [item.label for item in result.quick_replies] == [
        "Showroom Ô tô",
        "Showroom Xe máy điện",
        "Trạm sạc Ô tô điện",
        "Trạm sạc Xe máy điện",
        "Tủ đổi pin",
    ]
    assert result.pending_request is not None
    assert result.pending_request.missing_slot == "location_kind"
    # Chưa hỏi loại xong thì KHÔNG chạm database — và cũng chưa xin vị trí.
    assert stations.radii == []
    assert result.needs_location is False


@pytest.mark.asyncio
async def test_explicit_kinds_win_over_whatever_the_sentence_says() -> None:
    """Loại đã chốt ở lượt trước phải thắng bộ dò của lượt này.

    Lượt trả lời vị trí ("Cầu Giấy") không mang từ khoá loại nào; nếu bộ dò được
    chạy lại trên câu đó thì loại vừa chốt biến mất và service quay về hỏi lại từ
    đầu — một vòng lặp mà khách không có cách nào thoát.
    """

    stations = FakeStations([_station("SR-1", "Showroom", 0.4, "showroom_escooter")])
    service = NearbyLocationServiceImpl(locations=stations)

    result = await service.answer(
        user_message="Cầu Giấy",
        known_location=HANOI,
        location_kinds=(LocationKind.SHOWROOM_MOTORBIKE,),
        assume_request=True,
    )

    assert result is not None and result.locations is not None
    assert stations.types[0] == ("showroom_escooter",)
    assert result.locations.location_types == ["SHOWROOM_MOTORBIKE"]
