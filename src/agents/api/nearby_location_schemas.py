"""[FIND_NEARBY_LOCATION] Hợp đồng HTTP của danh sách địa điểm.

File RIÊNG chứ không nhét vào `api/routes.py`: cùng bộ schema này được dùng ở ba
bề mặt — trường `nearby_locations` của `POST /agent/turn`, endpoint mới
`POST /locations/nearest`, và endpoint cũ `POST /charging-stations/nearest`. Khai
ba lần là dựng ba hợp đồng cho cùng một payload, và chúng sẽ lệch nhau ngay lần
thêm trường đầu tiên.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.agents.contracts import NearbyLocationListView, QuickReplyView
from src.agents.domain.nearby_location import CHARGING_KINDS, LocationKind

#: Nhãn hành động gửi client. Client rẽ nhánh render theo đúng chuỗi này, nên nó
#: là một phần của hợp đồng, không phải một chi tiết nội bộ.
NEARBY_LOCATION_LIST_ACTION = "NEARBY_LOCATION_LIST"

#: [KHÁC BIỆT] Nhãn CŨ, chỉ trả ở endpoint cũ `/charging-stations/nearest`. Giữ
#: nguyên để client đã dựng theo nó không phải sửa cùng lúc với backend — xem
#: docstring `api/nearby_location_routes.py`.
CHARGING_STATION_LIST_ACTION = "CHARGING_STATION_LIST"


class NearbyLocationResponse(BaseModel):
    """Một địa điểm, đủ dữ liệu để client dựng card và nút "Chỉ đường".

    `maps_url` là deep link Google Maps đã kèm sẵn `origin` (toạ độ khách) và
    `destination` (toạ độ địa điểm) — client chỉ việc mở nó ở tab mới, không phải
    ghép chuỗi và không cần quyền vị trí lần thứ hai.

    `charger_type` là `None` với showroom và tủ đổi pin: hai loại đó không có
    khái niệm cổng sạc nào để nói.
    """

    id: str
    name: str
    address: str
    latitude: float
    longitude: float
    distance_km: float | None = None
    location_type: str
    category_label: str
    maps_url: str
    charger_type: str | None = None
    hotline: str | None = None
    open_time: str | None = None
    close_time: str | None = None
    status: str | None = None


class NearbyLocationListResponse(BaseModel):
    """Danh sách địa điểm đã sắp tăng dần theo `distance_km`.

    `searched_radius_km` là bán kính THẬT SỰ đã quét. Nó có ý nghĩa nhất đúng lúc
    `results` rỗng: "không tìm thấy" mà không kèm con số này thì khách không biết
    nên gõ lại một khu vực rộng hơn hay kết luận là quanh đó chưa có.
    """

    results: list[NearbyLocationResponse] = []
    #: Các loại đã tra trong lượt này. Nhiều hơn một là bình thường — "trạm sạc"
    #: trần xác định về nhóm nhưng chưa xác định về phương tiện.
    location_types: list[str] = []
    origin_latitude: float | None = None
    origin_longitude: float | None = None
    origin_label: str | None = None
    searched_radius_km: float | None = None
    #: `True` khi backend chưa biết khách tìm LOẠI nào — client hiện năm nút bấm
    #: (`quick_replies` của cùng lượt mang nhãn của chúng).
    needs_location_kind: bool = False
    #: `True` khi backend chưa biết khách ở đâu — client hiện UI xin vị trí.
    #: Client KHÔNG suy ra được điều này từ `results` rỗng: rỗng cũng đúng cho ca
    #: "đã biết vị trí nhưng quanh đó không có gì", và hai ca đó cần hai màn khác
    #: hẳn nhau.
    needs_location: bool = False
    action_type: str = NEARBY_LOCATION_LIST_ACTION


class NearestLocationRequest(BaseModel):
    """`location_type` + (`{latitude, longitude}` HOẶC `{location_text}`).

    Không ép "đúng một trong hai nguồn vị trí" bằng validator: gửi cả hai là hợp
    lệ và có ích — toạ độ được ưu tiên, `location_text` đi kèm chỉ để hiển thị.
    Gửi cả hai đều rỗng thì route trả 422 với mã máy đọc được, chứ không đoán một
    vị trí.

    `session_id` là TUỲ CHỌN nhưng nên gửi: có nó thì toạ độ vừa dùng được ghi
    vào bộ nhớ phiên, và câu hỏi địa điểm kế tiếp trong khung chat không phải xin
    quyền vị trí lần nữa. Thiếu nó, endpoint vẫn trả lời đúng — chỉ là phiên
    không học được gì.
    """

    location_type: list[LocationKind] = Field(min_length=1)
    latitude: float | None = None
    longitude: float | None = None
    location_text: str | None = None
    session_id: str | None = None


class NearestLocationResponse(BaseModel):
    """Response của `POST /locations/nearest`.

    `reply_text` do LLM viết từ CHÍNH `results` ở dưới, để giọng văn đồng bộ với
    các intent khác. Chưa nối LLM hoặc lời gọi hỏng thì nó là một câu
    deterministic — danh sách vẫn gửi được, chỉ thiếu phần văn xuôi.

    `action_type` luôn là `NEARBY_LOCATION_LIST` kể cả khi `results` rỗng: client
    vẫn phải render đúng khối đó để hiện câu "chưa thấy … trong bán kính N km",
    thay vì rơi về nhánh text thuần.
    """

    reply_text: str
    action_type: str = NEARBY_LOCATION_LIST_ACTION
    results: list[NearbyLocationResponse] = []
    location_types: list[str] = []
    origin_latitude: float | None = None
    origin_longitude: float | None = None
    origin_label: str | None = None
    searched_radius_km: float | None = None
    needs_location_kind: bool = False
    needs_location: bool = False
    quick_replies: list[QuickReplyView] = []


# ── Bề mặt CŨ, giữ nguyên hình dạng ──────────────────────────────────────────


class ChargingStationResponse(BaseModel):
    """[Tương thích ngược] Một trạm sạc theo đúng hình dạng trước khi tổng quát hoá.

    Khác `NearbyLocationResponse` ở hai điểm, và cả hai đều cố ý: không có
    `location_type`, và `charger_type` là `str` chứ không `str | None` — client cũ
    đọc thẳng trường đó để dựng nhãn.
    """

    id: str
    name: str
    address: str
    latitude: float
    longitude: float
    distance_km: float | None = None
    charger_type: str
    category_label: str
    maps_url: str
    hotline: str | None = None
    open_time: str | None = None
    close_time: str | None = None
    status: str | None = None


class NearestChargingStationRequest(BaseModel):
    """[Tương thích ngược] `{latitude, longitude}` HOẶC `{location_text}`.

    KHÔNG có `location_type`: endpoint này mặc định tra hai loại trạm sạc, đúng
    như nó vẫn làm trước khi có năm loại.
    """

    latitude: float | None = None
    longitude: float | None = None
    location_text: str | None = None
    session_id: str | None = None


class NearestChargingStationResponse(BaseModel):
    """[Tương thích ngược] Response của `POST /charging-stations/nearest`."""

    reply_text: str
    action_type: str = CHARGING_STATION_LIST_ACTION
    results: list[ChargingStationResponse] = []
    origin_latitude: float | None = None
    origin_longitude: float | None = None
    origin_label: str | None = None
    searched_radius_km: float | None = None
    needs_location: bool = False


def _location(item) -> NearbyLocationResponse:
    return NearbyLocationResponse(
        id=item.id,
        name=item.name,
        address=item.address,
        latitude=item.latitude,
        longitude=item.longitude,
        distance_km=item.distance_km,
        location_type=item.location_type,
        category_label=item.category_label,
        maps_url=item.maps_url,
        charger_type=item.charger_type,
        hotline=item.hotline,
        open_time=item.open_time,
        close_time=item.close_time,
        status=item.status,
    )


def nearby_location_payload(
    view: NearbyLocationListView | None,
) -> NearbyLocationListResponse | None:
    """View domain → hợp đồng HTTP. `None` đi qua nguyên vẹn."""

    if view is None:
        return None
    return NearbyLocationListResponse(
        results=[_location(item) for item in view.locations],
        location_types=list(view.location_types),
        origin_latitude=view.origin_latitude,
        origin_longitude=view.origin_longitude,
        origin_label=view.origin_label,
        searched_radius_km=view.searched_radius_km,
        needs_location_kind=view.needs_location_kind,
        needs_location=view.needs_location,
    )


def nearest_response(
    *, reply_text: str, view: NearbyLocationListView | None, quick_replies: list[QuickReplyView] | None = None
) -> NearestLocationResponse:
    """Response đầy đủ của endpoint trực tiếp."""

    payload = nearby_location_payload(view)
    if payload is None:
        return NearestLocationResponse(reply_text=reply_text)
    return NearestLocationResponse(
        reply_text=reply_text,
        results=payload.results,
        location_types=payload.location_types,
        origin_latitude=payload.origin_latitude,
        origin_longitude=payload.origin_longitude,
        origin_label=payload.origin_label,
        searched_radius_km=payload.searched_radius_km,
        needs_location_kind=payload.needs_location_kind,
        needs_location=payload.needs_location,
        quick_replies=quick_replies or [],
    )


def legacy_charging_response(*, reply_text: str, view: NearbyLocationListView | None) -> NearestChargingStationResponse:
    """Response theo hình dạng CŨ, dựng từ cùng một view.

    `charger_type` không bao giờ `None` ở đây: endpoint cũ chỉ tra hai loại trạm
    sạc, và cả hai đều có nhãn. Chuỗi rỗng chỉ xuất hiện nếu ai đó gọi hàm này
    với một view chứa showroom — không nhánh nào làm vậy, và để rỗng vẫn tốt hơn
    là ném `ValidationError` vào giữa một lượt chat.
    """

    payload = nearby_location_payload(view)
    if payload is None:
        return NearestChargingStationResponse(reply_text=reply_text)
    return NearestChargingStationResponse(
        reply_text=reply_text,
        results=[
            ChargingStationResponse(
                **{
                    **item.model_dump(exclude={"location_type", "charger_type"}),
                    "charger_type": item.charger_type or "",
                }
            )
            for item in payload.results
        ],
        origin_latitude=payload.origin_latitude,
        origin_longitude=payload.origin_longitude,
        origin_label=payload.origin_label,
        searched_radius_km=payload.searched_radius_km,
        needs_location=payload.needs_location,
    )


def charging_station_kinds() -> tuple[LocationKind, ...]:
    """Hai loại trạm sạc — mặc định của bề mặt cũ."""

    return CHARGING_KINDS


__all__ = [
    "CHARGING_STATION_LIST_ACTION",
    "NEARBY_LOCATION_LIST_ACTION",
    "ChargingStationResponse",
    "NearbyLocationListResponse",
    "NearbyLocationResponse",
    "NearestChargingStationRequest",
    "NearestChargingStationResponse",
    "NearestLocationRequest",
    "NearestLocationResponse",
    "charging_station_kinds",
    "legacy_charging_response",
    "nearby_location_payload",
    "nearest_response",
]
