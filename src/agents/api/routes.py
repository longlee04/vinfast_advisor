"""[A4-4] Endpoint hội thoại agent, thay `/chat` cũ.

Hợp đồng cũ được đóng băng ở `tests/api/test_legacy_contracts.py` (A0-4) trước
khi thay, để việc thay không phải thay mù.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.agents.adapters.rate_limiter import turn_rate_limit_key
from src.agents.api.dependencies import AgentDependency, CustomerDependency
from src.agents.api.nearby_location_schemas import (
    NearbyLocationListResponse,
    nearby_location_payload,
)
from src.agents.api.schemas import (
    CompareRequest,
    ComparisonCellResponse,
    ComparisonRowResponse,
    ComparisonTableResponse,
    ProvinceOptionResponse,
    TcoComponentResponse,
    TcoEstimateRequest,
    TcoEstimateResponse,
)
from src.agents.chain import facts_as_dict, run_turn
from src.agents.contracts import (
    TCO_COMPONENT_GROUPS,
    NavigateView,
    TcoCardView,
    TestDriveCardView,
    VehicleComparisonView,
    VehicleDetailsView,
)
from src.agents.domain.comparison import (
    ComparisonSelectionError,
    ComparisonTable,
    CrossVehicleTypeComparisonError,
)
from src.agents.domain.nearby_location import UserLocation
from src.agents.domain.next_step import NextStepPanel
from src.agents.domain.offer_reply import total_discount
from src.agents.domain.pricing_intent import (
    assumption_note,
    province_options,
    region_for_province_code,
)
from src.agents.domain.values import SlotName, VehicleType
from src.agents.errors import ConversationArchivedError, SessionOwnershipError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


class TurnRequest(BaseModel):
    """Một tin nhắn khách gửi trong một phiên.

    `session_id` là UUID vì `conversation_sessions.session_id` là UUID — nhận
    chuỗi tự do ở đây sẽ vỡ tận repository, nơi lỗi khó lần về nguồn.
    Định danh khách KHÔNG nằm trong body: nó đến từ tầng Auth.
    """

    session_id: UUID
    client_turn_id: UUID | None = None
    message: str = Field(min_length=1)


class CitationResponse(BaseModel):
    """Footnote `[index]` trong pitch. Không phơi `evidence_id`/`source_record` ra khách."""

    index: int


class RecommendedVehicle(BaseModel):
    """Một xe được đề xuất, đủ dữ liệu để client dựng card."""

    vehicle_id: UUID
    rank: int
    display_name: str
    image_url: str | None = None
    starting_price_vnd: str | None = None
    pitch: str
    citations: list[CitationResponse] = []


class ComparisonSpecFieldResponse(BaseModel):
    """Một dòng tiêu chí của bảng so sánh: mã cột catalog + nhãn gửi khách."""

    code: str
    label: str


class ComparedVehicleResponse(BaseModel):
    """Một cột của bảng so sánh, đủ dữ liệu để client dựng ảnh + bảng."""

    vehicle_id: str
    found: bool
    display_name: str = ""
    vehicle_type: str = ""
    image_url: str | None = None
    starting_price_vnd: str | None = None
    specs: dict[str, str] = {}


class VehicleComparisonResponse(BaseModel):
    """[COMPARE_VEHICLES] Bảng so sánh 2–3 mẫu + đoạn tóm tắt dưới phần ảnh.

    Đường riêng, không dùng lại `recommendations`: đó là kết quả xếp hạng của
    luồng tư vấn và bị strip pitch khi lượt chưa qua HITL. Bảng so sánh là tra
    cứu catalog công khai, auto-approve, nên không được thừa hưởng ràng buộc đó.
    """

    vehicles: list[ComparedVehicleResponse] = []
    spec_fields: list[ComparisonSpecFieldResponse] = []
    summary: str = ""
    missing_vehicle_names: list[str] = []


class QuickReply(BaseModel):
    """Nút bấm gợi ý cho lượt hỏi xác nhận / hỏi làm rõ (Lớp 4 nhận diện ý định).

    `value` là chuỗi client gửi lại như một tin nhắn bình thường qua chính
    `POST /agent/turn`, không phải một mã lệnh riêng — nên không cần endpoint mới
    và client chưa hỗ trợ nút bấm vẫn dùng được (khách tự gõ "đúng" cho kết quả
    y hệt).
    """

    label: str
    value: str


class TcoRatesResponse(BaseModel):
    """Hệ số để client tính lại tổng tại chỗ khi khách kéo số km.

    Xem `contracts.TcoRatesView` cho công thức và hai chỗ dễ lệch (360 ngày/năm,
    bảo dưỡng làm tròn LÊN).
    """

    fixed_vnd: str
    energy_vnd_per_km: str
    insurance_vnd_per_year: str
    maintenance_vnd_per_service: str
    maintenance_interval_km: str
    battery_vnd_per_month: str
    years: int
    days_per_year: int
    formula_note: str


class TcoCardResponse(BaseModel):
    """Thẻ chi phí khách chỉnh được ngay trên giao diện."""

    vehicle_id: UUID
    vehicle_name: str
    total_vnd: str | None
    components: list[TcoComponentResponse]
    daily_distance_km: float
    daily_distance_known: bool
    province_code: str | None
    region_code: str
    assumption_note: str
    province_options: list[ProvinceOptionResponse]
    #: `None` với lõi cũ (chưa dựng hệ số) — client phải chịu được cả hai.
    rates: TcoRatesResponse | None = None


class TestDriveShowroomResponse(BaseModel):
    """Một showroom trong thẻ chọn lịch lái thử."""

    showroom_id: str
    name: str
    address: str
    distance_label: str
    lat: float | None = None
    lng: float | None = None
    distance_km: float | None = None


class NavigateShowroomResponse(BaseModel):
    showroom_id: str
    name: str
    address: str
    lat: float | None = None
    lng: float | None = None
    distance_km: float | None = None


class NavigateCenterResponse(BaseModel):
    lat: float
    lng: float


class NavigateResponse(BaseModel):
    """Lệnh dẫn khách đi xem (đợt 9, contract mục 1): `vehicle` mở trang xe, `map` vẽ bản đồ."""

    kind: str
    vehicle_id: str = ""
    slug: str = ""
    path: str = ""
    name: str = ""
    center: NavigateCenterResponse | None = None
    showrooms: list[NavigateShowroomResponse] = []
    needs_location: bool = False


def _navigate_payload(view: NavigateView | None) -> NavigateResponse | None:
    if view is None:
        return None
    return NavigateResponse(
        kind=view.kind,
        vehicle_id=view.vehicle_id,
        slug=view.slug,
        path=view.path,
        name=view.name,
        center=NavigateCenterResponse(lat=view.center.lat, lng=view.center.lng) if view.center else None,
        showrooms=[
            NavigateShowroomResponse(
                showroom_id=item.showroom_id,
                name=item.name,
                address=item.address,
                lat=item.lat,
                lng=item.lng,
                distance_km=item.distance_km,
            )
            for item in view.showrooms
        ],
        needs_location=view.needs_location,
    )


class TestDriveTimeResponse(BaseModel):
    """Một ô giờ trong cột giờ dùng chung."""

    scheduled_at: datetime
    label: str


class TestDriveDayResponse(BaseModel):
    """Một ngày và các ô giờ của nó — hợp của mọi showroom trong thẻ."""

    date: str
    label: str
    times: list[TestDriveTimeResponse]


class TestDriveOptionResponse(BaseModel):
    """Một ô CÒN CHỖ. Ô vắng mặt ở đây là ô client phải làm mờ."""

    showroom_id: str
    scheduled_at: datetime
    value: str


class TestDriveCardResponse(BaseModel):
    """Thẻ chọn showroom + khung giờ, thay cho việc bắt khách gõ vào khung chat."""

    vehicle_name: str
    showrooms: list[TestDriveShowroomResponse]
    days: list[TestDriveDayResponse]
    options: list[TestDriveOptionResponse]
    default_showroom_id: str
    default_date: str
    # Đợt 8 (contract mục 1): id xe để client gọi `/agent/test-drive/options`,
    # và cờ "thẻ đang xin vị trí". Mặc định giữ client cũ chạy nguyên.
    vehicle_id: str = ""
    needs_location: bool = False


class TurnResponse(BaseModel):
    """Kết quả một lượt — `answer` rỗng khi lượt chỉ hỏi slot."""

    answer: str | None
    pending_question: str | None
    lookup_facts: list[dict]
    terminal_reason: str | None
    # A7-4: `True` khi lượt này đã vào hàng đợi tư vấn viên. Field mới, mặc định
    # `False` nên client cũ không vỡ — nhưng client KHÔNG được suy ra điều này từ
    # `answer`/`terminal_reason` nữa: giá niêm yết giờ trả thẳng và có đúng hình
    # dạng đó, nên suy đoán kiểu cũ sẽ dựng màn "đang chờ duyệt" trên một câu trả
    # lời đã hoàn tất.
    awaiting_review: bool = False
    # Bản CÓ CẤU TRÚC của cùng nội dung `answer`. `answer` vẫn chở TOÀN VĂN ghép:
    # client chưa cập nhật — kể cả frontend của chính dự án này trong pha 1 — chỉ
    # render `answer`, nên để nó teo lại thành câu dẫn là một hồi quy.
    # Payload lặp nội dung ở hai nơi; đó là cái giá có chủ đích.
    recommendations: list[RecommendedVehicle] = []
    # Nút bấm gợi ý. Rỗng ở mọi lượt trừ hai nhánh chưa đủ tin cậy của Lớp 4,
    # nên client cũ không đổi gì vẫn chạy đúng như trước.
    quick_replies: list[QuickReply] = []
    # Bảng so sánh. `None` ở mọi lượt trừ `COMPARE_VEHICLES`, nên client cũ không
    # đổi gì vẫn chạy đúng như trước — `answer` vẫn chở toàn văn bảng dạng chữ.
    comparison: VehicleComparisonResponse | None = None
    # [FIND_NEARBY_LOCATION] Danh sách địa điểm. `None` ở mọi lượt khác, nên
    # client cũ không đổi gì vẫn chạy đúng như trước — `answer` vẫn chở câu dẫn,
    # và deep link "Chỉ đường" nằm trong từng phần tử chứ không phải trong chữ.
    nearby_locations: NearbyLocationListResponse | None = None
    # Thẻ chi phí 5 năm CÓ Ô CHỈNH (Sếp 2026-08-27). `None` ở mọi lượt khác, nên
    # client cũ không đổi gì vẫn chạy đúng — `answer` vẫn chở khối chữ như trước.
    # Client mới dùng `vehicle_id` + hai giả định ở đây để dựng ô nhập km và ô
    # chọn tỉnh với ĐÚNG giá trị đang tính, rồi gọi `/tco/estimate` mỗi lần đổi.
    tco_card: TcoCardResponse | None = None
    # Thẻ chọn lịch lái thử (Sếp 2026-08-28). `None` ở mọi lượt khác, nên client
    # cũ không đổi gì vẫn chạy đúng — `answer` và `quick_replies` vẫn như trước.
    test_drive_card: TestDriveCardResponse | None = None
    vehicle_details: VehicleDetailsResponse | None = None
    next_step_panel: NextStepPanelResponse | None = None
    # Đợt 9 "tour guide": lệnh dẫn khách đi xem (trang xe / bản đồ). `None` ở mọi
    # lượt khác nên client cũ không đổi gì vẫn chạy đúng.
    navigate: NavigateResponse | None = None


@router.post("/turn", response_model=TurnResponse)
async def turn(
    request: TurnRequest,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> TurnResponse:
    """Một lượt: hỏi slot, tra cứu theo tên xe, hoặc đề xuất đã qua guardrail."""

    if agent is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="agent chưa khởi tạo")
    if customer_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    # [T7a] Chặn spam ở CỬA. Để nó chạy hết pipeline rồi mới chặn ở hàng duyệt
    # nghĩa là mỗi lượt rác vẫn tốn một lần trích slot và một lần synthesis.
    #
    # Đã biết và chấp nhận: một lượt gửi lại vì mất mạng cũng ăn quota, vì
    # `client_turn_id` còn là tuỳ chọn nên ở đây chưa phân biệt được "lượt mới"
    # với "gửi lại". Khi replay cứng lên (sau demo) thì kiểm idempotency đứng
    # trước chốt này.
    limiter = getattr(agent, "rate_limiter", None)
    if limiter is not None:
        allowed = await limiter.allow(turn_rate_limit_key(customer_id, str(request.session_id)))
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "RATE_LIMITED"},
            )
    try:
        # `shield`: khách ngắt kết nối / FE huỷ request giữa lượt thì lượt vẫn chạy
        # hết và chốt outcome (COMPLETED + lưu tin nhắn), khách tải lại là thấy.
        # Prod 2026-08-29: 5 lượt so sánh/trạm sạc kẹt IN_PROGRESS, khách thấy trống.
        result = await asyncio.shield(
            run_turn(
                agent.graph,
                agent.services,
                session_id=str(request.session_id),
                customer_id=customer_id,
                user_message=request.message,
                client_turn_id=request.client_turn_id,
            )
        )
    except SessionOwnershipError as error:
        # Prod 2026-08-26..28: 8 lần 500 vì khách mở lại một session không phải của
        # mình (đổi tài khoản trên cùng trình duyệt). Đây là 403, không phải lỗi hệ.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="conversation access forbidden") from error
    except ConversationArchivedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONVERSATION_ARCHIVED"},
        ) from error
    return _turn_response(result)


def _turn_response(result) -> TurnResponse:
    return TurnResponse(
        answer=result.answer,
        pending_question=result.pending_question,
        lookup_facts=[facts_as_dict(facts) for facts in result.lookup_facts],
        terminal_reason=result.terminal_reason,
        awaiting_review=result.awaiting_review,
        recommendations=[
            RecommendedVehicle(
                vehicle_id=item.vehicle_id,
                rank=item.rank,
                display_name=item.display_name,
                image_url=item.image_url,
                starting_price_vnd=item.starting_price_vnd,
                pitch=item.pitch,
                citations=[CitationResponse(index=citation.index) for citation in item.citations],
            )
            for item in result.recommendations
        ],
        quick_replies=[QuickReply(label=item.label, value=item.value) for item in result.quick_replies],
        comparison=_comparison_payload(result.comparison),
        nearby_locations=nearby_location_payload(result.nearby_locations),
        tco_card=_tco_card_payload(result.tco_card),
        test_drive_card=_test_drive_card_payload(result.test_drive_card),
        vehicle_details=_vehicle_details_payload(result.vehicle_details),
        next_step_panel=_next_step_payload(result.next_step_panel),
        navigate=_navigate_payload(result.navigate),
    )


def _comparison_payload(
    view: VehicleComparisonView | None,
) -> VehicleComparisonResponse | None:
    """Chuyển view domain thành hợp đồng HTTP, giữ nguyên cả cột `found=False`."""

    if view is None:
        return None
    return VehicleComparisonResponse(
        vehicles=[
            ComparedVehicleResponse(
                vehicle_id=item.vehicle_id,
                found=item.found,
                display_name=item.display_name,
                vehicle_type=item.vehicle_type,
                image_url=item.image_url,
                starting_price_vnd=item.starting_price_vnd,
                specs=dict(item.specs),
            )
            for item in view.vehicles
        ],
        spec_fields=[ComparisonSpecFieldResponse(code=item.code, label=item.label) for item in view.spec_fields],
        summary=view.summary,
        missing_vehicle_names=list(view.missing_vehicle_names),
    )


@router.post("/compare", response_model=ComparisonTableResponse)
async def compare(
    request: CompareRequest,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> ComparisonTableResponse:
    """So sánh cùng loại xe từ snapshot bất biến của một run."""

    if customer_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    if agent is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="agent chưa khởi tạo")
    service = agent.services.recommendation
    if service is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="chua noi dich vu de xuat")
    try:
        table = await service.compare(run_id=request.run_id, vehicle_ids=request.vehicle_ids)
    except CrossVehicleTypeComparisonError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.reason) from error
    except (ComparisonSelectionError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    return _comparison_response(table)


def _comparison_response(table: ComparisonTable) -> ComparisonTableResponse:
    """Chuyển bảng domain thành hợp đồng HTTP không làm mất giá trị null."""

    return ComparisonTableResponse(
        captured_at=table.captured_at,
        vehicle_ids=list(table.vehicle_ids),
        rows=[
            ComparisonRowResponse(
                criterion_code=row.criterion_code,
                cells=[
                    ComparisonCellResponse(
                        vehicle_id=cell.vehicle_id,
                        value_text=cell.value_text,
                        source=cell.source,
                        evidence_ref=cell.evidence_ref,
                        label=cell.label,
                        is_better=cell.is_better,
                    )
                    for cell in row.cells
                ],
            )
            for row in table.rows
        ],
    )


#: Nhãn tiếng Việt của từng khoản, DÙNG CHUNG với khối chữ trong chat
#: (`chain._cost_summary`). Hai bảng nhãn là hai chỗ để lệch nhau, và khách thì
#: nhìn thấy cả hai trong cùng một màn hình.
_TCO_COMPONENT_LABELS: Final[dict[str, str]] = {
    "promoted_purchase_price_vnd": "Giá xe",
    "rolling_fees_vnd": "Lệ phí ban đầu",
    "energy_vnd": "Chi phí năng lượng",
    "battery_vnd": "Chi phí pin",
    "scheduled_maintenance_vnd": "Bảo dưỡng",
}


@router.get("/tco/provinces", response_model=list[ProvinceOptionResponse])
async def tco_provinces() -> list[ProvinceOptionResponse]:
    """Danh sách tỉnh cho ô chọn trên thẻ chi phí.

    Dựng từ chính bảng dùng để ĐỌC lời khách, nên tỉnh nào chọn được trên giao
    diện thì gõ tay cũng nhận ra — xem `domain/pricing_intent.province_options`.
    """

    options, _ = province_options()
    return [
        ProvinceOptionResponse(code=option.code, name=option.name, region_code=option.region_code) for option in options
    ]


@router.post("/tco/estimate", response_model=TcoEstimateResponse)
async def estimate_tco(
    request: TcoEstimateRequest,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> TcoEstimateResponse:
    """Tính lại chi phí 5 năm theo giả định khách vừa chỉnh trên giao diện.

    KHÔNG gọi LLM: đây là cùng bộ tính tất định mà khối chữ trong chat đang dùng
    (`vinfast_tco_v1`), nên kéo thanh km hay đổi tỉnh là rẻ và nhanh như một phép
    cộng — khách chỉnh bao nhiêu lần cũng được.

    Lựa chọn được GHI LẠI vào slot của phiên khi có `session_id`: khách kéo km
    trên thẻ rồi quay lại hỏi tiếp trong chat thì con số phải khớp nhau, nếu
    không hệ thống nói hai điều khác nhau về cùng một chiếc xe.
    """

    if customer_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    if agent is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="agent chưa khởi tạo")
    service = agent.services.tco_estimation
    if service is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="chua noi dich vu chi phi")
    region_code = region_for_province_code(request.province_code)
    # Ưu đãi tư vấn viên đã duyệt phải đi theo cả đường này, không chỉ đường chat:
    # khách kéo thanh km trên thẻ mà con số nhảy về mức CHƯA có ưu đãi thì họ
    # tưởng ưu đãi vừa mất.
    discount = await _session_discount(agent, request)
    try:
        result = await service.estimate(
            vehicle_id=request.vehicle_id,
            daily_distance_km=request.daily_distance_km,
            region_code=region_code,
            discount_vnd=discount,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    await _remember_tco_choice(agent, request, customer_id=customer_id)
    total = getattr(result, "total_vnd", None)
    components = getattr(result, "components_vnd", {}) or {}
    return TcoEstimateResponse(
        vehicle_id=request.vehicle_id,
        total_vnd=None if total is None else str(total),
        components=[
            TcoComponentResponse(
                code=code,
                label=label,
                amount_vnd=str(components[code]),
                group=TCO_COMPONENT_GROUPS.get(code, ""),
            )
            for code, label in _TCO_COMPONENT_LABELS.items()
            if components.get(code) is not None
        ],
        daily_distance_km=request.daily_distance_km,
        province_code=request.province_code,
        region_code=region_code,
        assumption_note=assumption_note(
            daily_km=request.daily_distance_km,
            known_distance=True,
            province=request.province_code,
        ),
        unavailable_reason=None if total is not None else getattr(result, "unavailable_reason", "TCO_UNAVAILABLE"),
    )


async def _remember_tco_choice(agent, request: TcoEstimateRequest, *, customer_id: str) -> None:
    """Ghi km và tỉnh khách vừa chọn vào slot của phiên.

    Lỗi ghi KHÔNG làm hỏng phép tính: khách vẫn phải thấy con số mới. Nhưng cũng
    không nuốt im lặng — lượt chat sau sẽ nói theo con số cũ và không ai biết vì sao.
    """

    if request.session_id is None:
        return
    conversation = getattr(agent.services, "conversation", None)
    saver = getattr(conversation, "save_turn", None)
    if not callable(saver):
        return
    slots: dict[str, object] = {SlotName.REQUIRED_RANGE_KM.value: int(request.daily_distance_km)}
    if request.province_code:
        slots[SlotName.REGISTRATION_PROVINCE.value] = request.province_code
    try:
        await saver(request.session_id, customer_id, slots)
    except Exception:
        logger.warning("api: khong ghi duoc lua chon chi phi cua phien %s", request.session_id, exc_info=True)


def _tco_card_payload(card: TcoCardView | None) -> TcoCardResponse | None:
    """Thẻ chi phí domain → hợp đồng HTTP. `None` giữ nguyên `None`."""

    if card is None:
        return None
    return TcoCardResponse(
        vehicle_id=card.vehicle_id,
        vehicle_name=card.vehicle_name,
        total_vnd=card.total_vnd,
        components=[
            TcoComponentResponse(code=item.code, label=item.label, amount_vnd=item.amount_vnd, group=item.group)
            for item in card.components
        ],
        daily_distance_km=card.daily_distance_km,
        daily_distance_known=card.daily_distance_known,
        province_code=card.province_code,
        region_code=card.region_code,
        assumption_note=card.assumption_note,
        province_options=[
            ProvinceOptionResponse(code=item.code, name=item.name, region_code=item.region_code)
            for item in card.province_options
        ],
        rates=(
            None
            if card.rates is None
            else TcoRatesResponse(
                fixed_vnd=card.rates.fixed_vnd,
                energy_vnd_per_km=card.rates.energy_vnd_per_km,
                insurance_vnd_per_year=card.rates.insurance_vnd_per_year,
                maintenance_vnd_per_service=card.rates.maintenance_vnd_per_service,
                maintenance_interval_km=card.rates.maintenance_interval_km,
                battery_vnd_per_month=card.rates.battery_vnd_per_month,
                years=card.rates.years,
                days_per_year=card.rates.days_per_year,
                formula_note=card.rates.formula_note,
            )
        ),
    )


class SpecGroupResponse(BaseModel):
    title: str
    rows: list[tuple[str, str]]


class VehicleDetailsResponse(BaseModel):
    vehicle_name: str
    spec_groups: list[SpecGroupResponse] = []


class NextStepOptionResponse(BaseModel):
    action: str
    label: str
    primary: bool = False


class NextStepCtaResponse(BaseModel):
    """MỘT hành động theo checklist (đợt 9). `message` rỗng = client tự mở trang lịch."""

    label: str
    message: str


class NextStepPanelResponse(BaseModel):
    title: str
    actions: list[NextStepOptionResponse] = []
    action: NextStepCtaResponse | None = None


def _next_step_payload(panel: NextStepPanel | None) -> NextStepPanelResponse | None:
    if panel is None:
        return None
    return NextStepPanelResponse(
        title=panel.title,
        actions=[
            NextStepOptionResponse(action=option.action.value, label=option.label, primary=option.primary)
            for option in panel.actions
        ],
        action=NextStepCtaResponse(label=panel.action.label, message=panel.action.message) if panel.action else None,
    )


def _vehicle_details_payload(view: VehicleDetailsView | None) -> VehicleDetailsResponse | None:
    if view is None:
        return None
    return VehicleDetailsResponse(
        vehicle_name=view.vehicle_name,
        spec_groups=[SpecGroupResponse(title=group.title, rows=list(group.rows)) for group in view.spec_groups],
    )


def _test_drive_card_payload(card: TestDriveCardView | None) -> TestDriveCardResponse | None:
    """Thẻ lái thử domain → hợp đồng HTTP. `None` giữ nguyên `None`."""

    if card is None:
        return None
    return TestDriveCardResponse(
        vehicle_name=card.vehicle_name,
        showrooms=[
            TestDriveShowroomResponse(
                showroom_id=item.showroom_id,
                name=item.name,
                address=item.address,
                distance_label=item.distance_label,
                lat=item.lat,
                lng=item.lng,
                distance_km=item.distance_km,
            )
            for item in card.showrooms
        ],
        days=[
            TestDriveDayResponse(
                date=day.date,
                label=day.label,
                times=[TestDriveTimeResponse(scheduled_at=t.scheduled_at, label=t.label) for t in day.times],
            )
            for day in card.days
        ],
        options=[
            TestDriveOptionResponse(
                showroom_id=item.showroom_id,
                scheduled_at=item.scheduled_at,
                value=item.value,
            )
            for item in card.options
        ],
        default_showroom_id=card.default_showroom_id,
        default_date=card.default_date,
        vehicle_id=card.vehicle_id,
        needs_location=card.needs_location,
    )


async def _session_discount(agent, request: TcoEstimateRequest) -> Decimal:
    """Tổng ưu đãi ACTIVE của phiên, cộng dồn, trừ vào giá xe.

    Hết hạn thì `active_for_session` không trả về (Sếp 2026-08-27), nên hàm này
    không cần biết gì về thời hạn.

    Lỗi đọc trả 0 chứ không làm hỏng phép tính: khách vẫn phải thấy một con số,
    và một con số chưa trừ ưu đãi vẫn đúng hơn một màn hình trống.
    """

    if request.session_id is None:
        return Decimal("0")
    loader = getattr(getattr(agent.services, "conversation", None), "load_active_offers", None)
    if not callable(loader):
        return Decimal("0")
    try:
        offers = await loader(request.session_id)
    except Exception:
        logger.warning("api: khong doc duoc uu dai cua phien %s", request.session_id, exc_info=True)
        return Decimal("0")
    return total_discount(
        [offer.get("value_snapshot") or offer for offer in offers],
        base_price_vnd=None,
    )


class TestDriveAvailabilityOption(BaseModel):
    """Một khung giờ còn trống, đã kèm sẵn mã nút để đặt."""

    showroom_id: str
    scheduled_at: datetime
    value: str


class TestDriveAvailabilityResponse(BaseModel):
    """Ô giờ của ĐÚNG ngày được hỏi."""

    date: date_type
    options: list[TestDriveAvailabilityOption] = Field(default_factory=list)


@router.get("/test-drive/availability", response_model=TestDriveAvailabilityResponse)
async def test_drive_availability(
    session_id: UUID,
    on_date: date_type = Query(alias="date"),
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> TestDriveAvailabilityResponse:
    """Nạp ô giờ của một ngày khác trên thẻ lái thử.

    Lượt chat chỉ chở ô của ngày mặc định (126 ô → 18). Thẻ vẫn bày đủ bảy ngày,
    nên phải có đúng một đường để xin sáu ngày còn lại — thiếu nó thì khách bấm
    sang ngày thứ tư và thấy mọi khung đều mờ.

    **Toạ độ đọc từ PHIÊN, không nhận từ client.** Cùng nguồn với lượt chat đã
    dựng thẻ. Cho client gửi toạ độ là để bất kỳ ai có `session_id` cũng dò được
    lịch của một showroom họ chưa từng được mời, rồi dựng mã nút từ đó.

    Chưa biết khách ở đâu thì trả 409 chứ KHÔNG trả danh sách rỗng: "hôm đó hết
    chỗ" và "em chưa biết anh/chị ở đâu" là hai chuyện khác nhau, và client phải
    xử lý khác nhau.
    """

    if agent is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="agent chưa khởi tạo")
    if customer_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    service = getattr(agent.services, "test_drive", None)
    reader = getattr(service, "availability", None)
    if not callable(reader):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chưa nối dịch vụ lái thử",
        )
    # Đọc slot TRƯỚC mọi thứ khác: `get_slots` là chỗ duy nhất trong luồng này
    # chốt quyền sở hữu phiên, và nó cũng mang luôn loại xe.
    #
    # `session_id` KHÔNG tự nó là quyền đọc. Chốt toạ độ ở trên mới chặn việc tự
    # chọn nơi tra; thiếu chốt này thì ai có (hoặc đoán được) `session_id` vẫn dò
    # ra vị trí khách đã lưu, showroom quanh đó, và mã nút đặt lịch của người
    # khác. Trả 404 chứ không 403: không xác nhận cho người lạ biết phiên có tồn
    # tại hay không.
    # BA ca "không được đọc phiên này" phải trả CÙNG 404: phiên không tồn tại,
    # phiên của người khác, phiên đã lưu trữ.
    #
    # Lượt chat đã chặn phiên lưu trữ (`ensure_session` ném
    # `ConversationArchivedError`), nhưng `get_slots` chỉ so chủ sở hữu — nên chủ
    # cũ của một phiên đã đóng vẫn đi trọn được: đọc vị trí, lấy showroom, nhận
    # mã đặt lịch. Hai hợp đồng nói hai chuyện khác nhau về cùng một phiên.
    #
    # 404 chứ không 403/409: không xác nhận cho người lạ biết `session_id` nào có
    # thật, và "chưa biết loại xe" là một câu KHÁC hẳn, dành cho phiên hợp lệ.
    if not await _session_is_readable(agent.services, session_id, customer_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiên")
    try:
        slots = await _session_slots(agent.services, str(session_id), customer_id)
    except SessionOwnershipError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiên") from error
    vehicle_type = _vehicle_type_of(slots)
    if vehicle_type is None:
        # KHÔNG âm thầm dùng `CAR`. Khách hỏi lái thử xe máy mà nhận showroom ô
        # tô là một lỗi thấy được — và đoán bừa chỉ khiến nó xảy ra lặng lẽ.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "VEHICLE_TYPE_UNKNOWN"},
        )
    location = await _session_location(agent.services, str(session_id))
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "LOCATION_UNKNOWN"},
        )
    options = await reader(
        latitude=location.latitude,
        longitude=location.longitude,
        vehicle_type=vehicle_type,
        on_date=on_date,
        session_id=str(session_id),
        customer_id=customer_id,
    )
    return TestDriveAvailabilityResponse(
        date=on_date,
        options=[
            TestDriveAvailabilityOption(
                showroom_id=option.showroom_id,
                scheduled_at=option.scheduled_at,
                value=option.value,
            )
            for option in options
        ],
    )


async def _session_location(services, session_id: str) -> UserLocation | None:
    """Vị trí khách đã chia sẻ trong phiên. Cùng phép đọc với `chain`."""

    conversation = getattr(services, "conversation", None)
    loader = getattr(conversation, "load_user_location", None)
    if not callable(loader):
        return None
    return UserLocation.from_payload(await loader(session_id))


async def _session_slots(services, session_id: str, customer_id: str) -> dict:
    """Slot của phiên. Ném `SessionOwnershipError` khi người gọi không phải chủ."""

    conversation = getattr(services, "conversation", None)
    reader = getattr(conversation, "get_slots", None)
    if not callable(reader):
        return {}
    return await reader(session_id, customer_id)


def _vehicle_type_of(slots) -> VehicleType | None:
    """Loại xe của phiên, hoặc `None` khi phiên chưa chốt được loại nào."""

    raw = slots.get(SlotName.VEHICLE_TYPE) if slots else None
    if raw is None:
        return None
    try:
        return VehicleType(str(raw))
    except ValueError:
        # Giá trị lạ trong slot là dữ liệu hỏng, không phải một loại xe thứ ba.
        logger.warning("availability: loai xe la trong phien: %r", raw)
        return None


async def _session_is_readable(services, session_id, customer_id: str) -> bool:
    """Phiên có tồn tại, đúng chủ, và CHƯA lưu trữ."""

    conversation = getattr(services, "conversation", None)
    reader = getattr(conversation, "get_session", None)
    if not callable(reader):
        # Không đọc được hàng phiên thì để `get_slots` gác chủ — nó vẫn chặn
        # người lạ, chỉ không phân biệt được phiên đã lưu trữ.
        return True
    row = await reader(session_id)
    if row is None or getattr(row, "customer_id", None) != customer_id:
        return False
    return getattr(row, "archived_at", None) is None
