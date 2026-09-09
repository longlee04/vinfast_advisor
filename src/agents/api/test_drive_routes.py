"""HTTP cho việc chọn vị trí NGAY TRÊN thẻ lái thử (đợt 8, contract mục 2).

Vì sao có endpoint này: lượt chat khi chưa biết vị trí khách trước đây hỏi tỉnh
bằng CHỮ, khách gõ, lượt sau mới có thẻ — hai lượt cho một việc. Nay lượt chat
trả thẻ `needs_location=True`; khách bấm "Dùng vị trí của tôi" hoặc gõ quận/huyện
trong thẻ, client gọi vào đây, và thẻ đầy đủ về ngay, không qua cửa hiểu ý.

Ba việc phải giống HỆT lượt chat, nếu không nút giờ bấm xong sẽ lạc đường:
- vị trí LƯU vào đúng kho `act._known_location` đọc (`save_user_location`);
- thẻ dựng bằng cùng `TestDriveServiceImpl.answer` (cùng mã nút đã ký);
- `conversation_core_state` ghi qua `policy.schedule_for` — cùng khoá treo
  `showroom_slot`, cùng cạnh chặng — để lượt chat kế đọc ra một phiên đang chọn giờ.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from src.agents.api.dependencies import AgentDependency, CustomerDependency
from src.agents.api.routes import (
    NavigateResponse,
    QuickReply,
    TestDriveCardResponse,
    _navigate_payload,
    _session_is_readable,
    _test_drive_card_payload,
)
from src.agents.contracts import TestDriveCardView
from src.agents.core import act as core_act
from src.agents.core.policy import schedule_for
from src.agents.core.state import CoreState
from src.agents.domain.nearby_location import UserLocation
from src.agents.domain.values import VehicleType
from src.agents.logging import get_agent_logger

logger = get_agent_logger("agent.api.test_drive")
router = APIRouter(prefix="/agent/test-drive", tags=["agent-test-drive"])

NO_SHOWROOM_MESSAGE = "Chưa tìm thấy showroom quanh đây"


class TestDriveOptionsRequest(BaseModel):
    """Toạ độ HOẶC chữ tự do — thiếu cả hai là 422, không đoán."""

    session_id: UUID
    vehicle_id: UUID
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    location_text: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _has_location(self) -> TestDriveOptionsRequest:
        has_coords = self.latitude is not None and self.longitude is not None
        has_text = bool((self.location_text or "").strip())
        if not has_coords and not has_text:
            raise ValueError("cần toạ độ (latitude + longitude) hoặc location_text")
        return self


class TestDriveOptionsResponse(BaseModel):
    test_drive_card: TestDriveCardResponse
    quick_replies: list[QuickReply] = Field(default_factory=list)
    #: Cùng `navigate` như lượt chat: client mở bản đồ với ghim showroom ngay sau khi có vị trí.
    navigate: NavigateResponse | None = None
    #: Chỉ khác `None` khi thẻ rỗng (geocode không ra / không showroom quanh đó).
    message: str | None = None


@router.post("/options", response_model=TestDriveOptionsResponse)
async def test_drive_options(
    payload: TestDriveOptionsRequest,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> TestDriveOptionsResponse:
    """Dựng thẻ lái thử đầy đủ từ vị trí khách vừa chọn trên thẻ."""

    if agent is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="agent chưa khởi tạo")
    if customer_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    services = agent.services
    service = getattr(services, "test_drive", None)
    if service is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Chưa nối dịch vụ lái thử")
    session_id = str(payload.session_id)
    # 404 cho cả ba ca "không được đọc phiên này" — cùng lý do với
    # `/test-drive/availability`: không xác nhận cho người lạ phiên nào có thật.
    if not await _session_is_readable(services, payload.session_id, customer_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiên")

    state = await _core_state(services, session_id)
    vehicle_id = str(payload.vehicle_id)
    name = await _vehicle_name(services, state, vehicle_id)
    if not name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy xe")

    location = await _resolve_location(services, state, payload)
    empty = TestDriveCardView(vehicle_name=name, vehicle_id=vehicle_id)
    if location is None:
        return TestDriveOptionsResponse(test_drive_card=_test_drive_card_payload(empty), message=NO_SHOWROOM_MESSAGE)

    # (b) LƯU vị trí đúng kho `act._known_location` đọc — lượt chat kế ("đổi
    # giờ khác") tra lại được showroom mà không hỏi lại.
    saver = getattr(services.conversation, "save_user_location", None)
    if saver is not None:
        await saver(session_id, location.to_payload())

    # (c) thẻ dựng y hệt act `ShowroomOptions`: cùng service, cùng mã nút đã ký.
    criteria = core_act.build_criteria(state)
    result = await service.answer(
        user_message=(payload.location_text or "").strip(),
        vehicle_name=name,
        vehicle_type=VehicleType(str(criteria.vehicle_type)),
        known_location=location,
        session_id=session_id,
        customer_id=customer_id,
    )
    card = core_act.with_vehicle_id(result.card, vehicle_id)
    if card is None or not card.showrooms:
        return TestDriveOptionsResponse(test_drive_card=_test_drive_card_payload(empty), message=NO_SHOWROOM_MESSAGE)

    # (d) ghi state như act `ShowroomOptions` — nút giờ bấm xong đi đúng đường `Book`.
    await _save_core_state(services, schedule_for(state, vehicle_id))
    return TestDriveOptionsResponse(
        test_drive_card=_test_drive_card_payload(card),
        quick_replies=[QuickReply(label=option.label, value=option.value) for option in result.slot_options],
        navigate=_navigate_payload(core_act.map_navigate(str(vehicle_id), card, center=location)),
    )


async def _core_state(services, session_id: str) -> CoreState:
    loader = getattr(services.conversation, "load_core_state", None)
    state = await loader(session_id) if loader is not None else None
    return state if state is not None else CoreState(session_id=session_id)


async def _save_core_state(services, state: CoreState) -> None:
    saver = getattr(services.conversation, "save_core_state", None)
    if saver is None:
        # Không có cửa ghi thì thẻ vẫn về khách; chỉ mất đường `Book` ở lượt chat
        # kế — log để thấy, không giết một response đã dựng xong.
        logger.warning("test_drive.options: conversation khong co save_core_state, khong ghi state")
        return
    await saver(state)


async def _vehicle_name(services, state: CoreState, vehicle_id: str) -> str:
    """Tên xe theo id, tra cửa catalog tất định của lõi v2 (cùng `act._name_of`).

    Thử theo loại xe của phiên trước, rồi cả danh mục: khách có thể chọn thẻ
    của một xe khác loại với slot đang ghi.
    """

    for hint in dict.fromkeys((core_act._vehicle_type(state), None)):
        names = await core_act.catalog_names(services, vehicle_type=hint)
        if vehicle_id in names:
            return names[vehicle_id]
    return ""


async def _resolve_location(services, state: CoreState, payload: TestDriveOptionsRequest) -> UserLocation | None:
    """(a) toạ độ → dùng thẳng; chữ → geocode qua `nearby_location` theo loại xe."""

    if payload.latitude is not None and payload.longitude is not None:
        return UserLocation(latitude=payload.latitude, longitude=payload.longitude, source="browser")
    geocoder = getattr(services, "nearby_location", None)
    text = (payload.location_text or "").strip()
    if geocoder is None or not text:
        return None
    try:
        result = await geocoder.answer(
            user_message=text,
            location_text=text,
            location_kinds=(core_act._showroom_kind(state),),
            assume_request=True,
        )
    except Exception:
        logger.warning("test_drive.options: geocode hong", exc_info=True)
        return None
    resolved = getattr(result, "resolved_location", None) if result is not None else None
    return resolved if isinstance(resolved, UserLocation) else None
