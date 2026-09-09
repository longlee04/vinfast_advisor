"""[FIND_NEARBY_LOCATION] Endpoint trực tiếp cho nút bấm của giao diện.

Hai router trong cùng một file, và đó là chủ ý:

- `router` — `POST /locations/nearest`, bề mặt HIỆN HÀNH. Nhận `location_type`
  bắt buộc, trả `action_type: NEARBY_LOCATION_LIST`.
- `legacy_router` — `POST /charging-stations/nearest`, bề mặt CŨ, giữ nguyên
  hình dạng request/response từ trước khi tổng quát hoá. Nó mặc định tra hai loại
  trạm sạc. Giữ lại vì client đã dựng theo nó, và một endpoint biến mất là một
  màn hình trắng chứ không phải một lỗi biên dịch.

Cả hai đứng cạnh `POST /agent/turn` chứ không thay nó. Hai bề mặt cho hai người
dùng khác nhau:

- `/agent/turn` là đường của cuộc hội thoại: khách hỏi bằng tiếng Việt, agent
  nhận diện ý định rồi trả `nearby_locations` kèm câu dẫn.
- `/locations/nearest` là đường của GIAO DIỆN: nút "Chia sẻ vị trí" gửi thẳng
  toạ độ trình duyệt vừa lấy được, không cần diễn đạt lại thành một câu tiếng
  Việt để hệ thống phân loại lại từ đầu. Bắt frontend đi vòng qua `/agent/turn`
  cho một cú bấm nút là tốn một lần gọi LLM phân loại cho một ý định đã biết chắc.

[KHÁC BIỆT] Prefix `/locations` DÙNG CHUNG với router chỉ-đọc của module
Locations (`GET /locations`, `/locations/nearby`, `/locations/categories`,
`/locations/regions`). Không có đường dẫn nào trùng nhau. Route này nằm ở module
`agents` chứ không ở `locations` vì `reply_text` do LLM viết, và LLM chỉ được nối
trong composition của `agents` — đặt nó bên kia sẽ kéo cả một `LLMPort` sang một
module không có lý do gì để biết tới LLM.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from src.agents.api.dependencies import AgentDependency, CustomerDependency
from src.agents.api.nearby_location_schemas import (
    NearestChargingStationRequest,
    NearestChargingStationResponse,
    NearestLocationRequest,
    NearestLocationResponse,
    charging_station_kinds,
    legacy_charging_response,
    nearest_response,
)
from src.agents.domain.nearby_location import LocationKind, UserLocation
from src.agents.domain.pending_slot import PendingSlotRequest
from src.agents.domain.values import VehicleType
from src.agents.services.slot_codec import coerce_vehicle_type
from src.agents.services.test_drive import TEST_DRIVE_PENDING_MARKER, TEST_DRIVE_VEHICLE_TYPE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/locations", tags=["nearby-locations"])
legacy_router = APIRouter(prefix="/charging-stations", tags=["nearby-locations"])


def _service(agent: object):
    services = getattr(agent, "services", None)
    return getattr(services, "nearby_location", None)


def _require(agent: object, customer_id: str | None):
    """Xác thực + service sẵn sàng, hoặc ném đúng mã lỗi.

    Yêu cầu xác thực như mọi route agent khác: danh sách địa điểm là dữ liệu công
    khai, nhưng toạ độ khách gửi lên thì không, và một endpoint mở nhận toạ độ là
    một endpoint mở ghi log toạ độ của người lạ.
    """

    if customer_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    service = _service(agent)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "NEARBY_LOCATION_UNAVAILABLE"},
        )
    return service


def _known_location(latitude: float | None, longitude: float | None, label: str | None) -> UserLocation | None:
    """Toạ độ trình duyệt gửi lên, hoặc `None` khi request chỉ mang địa danh.

    Toạ độ ngoài mặt cầu Trái Đất bị bỏ qua thay vì trả 422: nó chỉ có thể đến từ
    một client hỏng, và nhánh `location_text`/hỏi lại phía sau vẫn là một câu trả
    lời tử tế hơn một mã lỗi.
    """

    if latitude is None or longitude is None:
        return None
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return None
    return UserLocation(
        latitude=latitude,
        longitude=longitude,
        source="browser",
        label=(label or "").strip() or None,
    )


async def _remember(agent: object, session_id: str | None, location) -> None:
    """Ghi toạ độ vừa dùng vào bộ nhớ phiên, nếu client có gửi `session_id`.

    Đây là mảnh nối giữa hai bề mặt: khách bấm "Chia sẻ vị trí" (đi đường REST)
    rồi hỏi tiếp bằng lời trong khung chat (đi đường `/agent/turn`). Không ghi thì
    lượt chat kế tiếp lại xin quyền vị trí lần nữa — đúng thứ mà bộ nhớ phiên
    sinh ra để tránh.

    Nuốt mọi lỗi: một sự cố ghi bộ nhớ tiện lợi không được biến một câu trả lời
    đã dựng xong thành HTTP 500.
    """

    if not session_id or location is None:
        return
    conversation = getattr(getattr(agent, "services", None), "conversation", None)
    saver = getattr(conversation, "save_user_location", None)
    if saver is None:
        return
    try:
        await saver(session_id, location.to_payload())
    except Exception:
        logger.warning("khong ghi duoc vi tri vao phien %s", session_id, exc_info=True)


async def _answer(agent, service, *, message: str, kinds, latitude, longitude, text, session_id, customer_id: str = ""):
    """Gọi use case rồi ghi lại vị trí — phần chung của cả hai endpoint."""

    known = _known_location(latitude, longitude, text)
    cleaned = (text or "").strip()
    if known is None and not cleaned:
        # Không đoán một vị trí mặc định: một danh sách tính từ toạ độ sai trông y
        # hệt một danh sách đúng, và khách chỉ phát hiện ra khi đã tới nơi.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "LOCATION_REQUIRED"},
        )
    result = await service.answer(
        user_message=cleaned or message,
        known_location=known,
        location_text=cleaned or None,
        location_kinds=kinds,
        # Bấm nút là một ý định đã biết chắc — không bắt nó phải mang từ khoá.
        assume_request=True,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "NEARBY_LOCATION_UNAVAILABLE"},
        )
    await _remember(agent, session_id, result.resolved_location)
    quick_replies = []
    if session_id and result.resolved_location is not None:
        conversation = getattr(getattr(agent, "services", None), "conversation", None)
        loader = getattr(conversation, "load_pending_slot", None)
        saver = getattr(conversation, "save_pending_slot", None)
        pending = PendingSlotRequest.from_payload(await loader(session_id)) if callable(loader) else None
        vehicle_name = str(pending.partial_form.get(TEST_DRIVE_PENDING_MARKER) or "") if pending else ""
        if vehicle_name:
            service = getattr(getattr(agent, "services", None), "test_drive", None)
            vehicle_type = coerce_vehicle_type(pending.partial_form.get(TEST_DRIVE_VEHICLE_TYPE)) or VehicleType.CAR
            if service is not None:
                test_drive = await service.answer(
                    user_message=message,
                    vehicle_name=vehicle_name,
                    vehicle_type=vehicle_type,
                    known_location=result.resolved_location,
                    session_id=session_id,
                    customer_id=customer_id,
                )
                result = result.__class__(answer=test_drive.answer, resolved_location=result.resolved_location)
                quick_replies = [
                    {
                        "label": option.label,
                        "value": option.value,
                    }
                    for option in test_drive.slot_options
                ]
                if callable(saver):
                    await saver(session_id, None)
    return result, quick_replies


@router.post("/nearest", response_model=NearestLocationResponse)
async def nearest_location(
    request: NearestLocationRequest,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> NearestLocationResponse:
    """Địa điểm gần nhất theo LOẠI, quanh một toạ độ hoặc một địa danh."""

    service = _require(agent, customer_id)
    kinds = tuple(LocationKind(value) for value in request.location_type)
    result, quick_replies = await _answer(
        agent,
        service,
        message="tìm địa điểm gần nhất",
        kinds=kinds,
        latitude=request.latitude,
        longitude=request.longitude,
        text=request.location_text,
        session_id=request.session_id,
        customer_id=customer_id or "",
    )
    return nearest_response(reply_text=result.answer, view=result.locations, quick_replies=quick_replies)


@legacy_router.post("/nearest", response_model=NearestChargingStationResponse)
async def nearest_charging_station(
    request: NearestChargingStationRequest,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> NearestChargingStationResponse:
    """[Tương thích ngược] Trạm sạc gần nhất — hình dạng cũ, hai loại trạm sạc."""

    service = _require(agent, customer_id)
    result, quick_replies = await _answer(
        agent,
        service,
        message="tìm trạm sạc gần nhất",
        kinds=charging_station_kinds(),
        latitude=request.latitude,
        longitude=request.longitude,
        text=request.location_text,
        session_id=request.session_id,
        customer_id=customer_id or "",
    )
    return legacy_charging_response(reply_text=result.answer, view=result.locations)


__all__ = ["legacy_router", "router"]
