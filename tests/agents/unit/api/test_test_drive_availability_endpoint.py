"""Hợp đồng HTTP cho việc nạp ô giờ của một ngày khác.

Thẻ lái thử bày bảy ngày nhưng lượt chat chỉ chở ô của ngày mặc định. Không có
endpoint này thì khách bấm sang ngày thứ tư và thấy mọi khung đều mờ — thẻ hứa
bảy ngày mà chỉ giao được một.

Điểm quan trọng nhất ở đây là **toạ độ không đi qua tham số**: route đọc vị trí
từ phiên, đúng nguồn mà lượt chat đã dùng để dựng thẻ. Cho client gửi toạ độ là
để bất kỳ ai cũng moi được lịch của một nơi họ chưa từng ở.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.agents.api import routes
from src.agents.api.dependencies import get_current_customer_id
from src.agents.domain.test_drive import VIETNAM_TZ
from src.agents.domain.values import SlotName
from src.agents.errors import SessionOwnershipError
from src.agents.ports import NearbyPlace
from src.agents.services.registry import AgentServices
from src.agents.services.test_drive import TestDriveServiceImpl

SESSION = "11111111-1111-1111-1111-111111111111"
NOW = datetime.now(VIETNAM_TZ)


class _Locations:
    def __init__(self) -> None:
        self.seen: list[dict] = []

    async def nearest(self, **kwargs) -> list[NearbyPlace]:
        self.seen.append(kwargs)
        return [
            NearbyPlace(
                id="sr-1",
                location_type="showroom_car",
                category_label="Showroom",
                name="Showroom Long Biên",
                address="Số 1 Nguyễn Văn Cừ",
                latitude=21.05,
                longitude=105.87,
                distance_km=1.2,
                hotline=None,
                open_time="09:00",
                close_time="18:00",
                status="1",
            )
        ]


class _NoBookings:
    async def count_active_at(self, showroom: str, moment: datetime) -> int:
        del showroom, moment
        return 0


class _Conversation:
    """Vị trí + slot của phiên, kèm chốt quyền sở hữu như repo thật."""

    def __init__(
        self,
        payload: dict | None,
        *,
        owner: str | None = "customer-1",
        slots: dict | None = None,
        archived: bool = False,
    ) -> None:
        self._payload = payload
        self._owner = owner
        self._slots = slots if slots is not None else {SlotName.VEHICLE_TYPE: "CAR"}
        self._archived = archived
        self.asked: list[str] = []

    async def load_user_location(self, session_id: str) -> dict | None:
        self.asked.append(session_id)
        return self._payload

    async def get_session(self, session_id):
        """Hàng phiên, hoặc `None` khi không có — như repo thật."""

        if self._owner is None:
            return None
        return SimpleNamespace(
            customer_id=self._owner,
            archived_at=datetime.now(VIETNAM_TZ) if self._archived else None,
        )

    async def get_slots(self, session_id: str, customer_id: str) -> dict:
        if self._owner is None:
            # Repo thật trả `{}` cho phiên KHÔNG TỒN TẠI — không ném.
            return {}
        if customer_id != self._owner:
            raise SessionOwnershipError(session_id=session_id, customer_id=customer_id)
        return dict(self._slots)


def _client(
    *,
    location: dict | None,
    locations: _Locations | None = None,
    caller: str = "customer-1",
    owner: str | None = "customer-1",
    slots: dict | None = None,
    archived: bool = False,
    with_service: bool = True,
) -> AsyncClient:
    service = TestDriveServiceImpl(locations=locations or _Locations(), bookings=_NoBookings())
    application = FastAPI()
    application.include_router(routes.router, prefix="/api/v1")
    conversation = _Conversation(location, owner=owner, slots=slots, archived=archived)
    application.state.agent = SimpleNamespace(
        services=AgentServices(
            test_drive=service if with_service else None,
            conversation=conversation,
        )
    )
    application.dependency_overrides[get_current_customer_id] = lambda: caller
    return AsyncClient(transport=ASGITransport(app=application), base_url="http://test")


HANOI = {"latitude": 21.0285, "longitude": 105.8542}


@pytest.mark.asyncio
async def test_tra_ve_o_gio_cua_dung_ngay_duoc_hoi() -> None:
    target = (NOW + timedelta(days=3)).date().isoformat()

    async with _client(location=HANOI) as client:
        response = await client.get(
            "/api/v1/agent/test-drive/availability",
            params={"session_id": SESSION, "date": target},
        )

    body = response.json()
    assert response.status_code == 200
    assert body["date"] == target
    assert body["options"], "ngày trong cửa sổ phải còn khung"
    assert all(option["scheduled_at"].startswith(target) for option in body["options"])
    assert all(option["value"] for option in body["options"]), "ô nào cũng phải bấm đặt được"


@pytest.mark.asyncio
async def test_toa_do_doc_tu_phien_chu_khong_nhan_tu_client() -> None:
    """Gửi kèm toạ độ lạ cũng không đổi được nơi tra.

    Đây là chốt an toàn của endpoint: thiếu nó thì bất kỳ ai có `session_id` cũng
    dò được lịch showroom ở một tỉnh khác, và tệ hơn là dựng được mã nút cho một
    khung giờ chưa bao giờ được mời.
    """

    locations = _Locations()

    async with _client(location=HANOI, locations=locations) as client:
        await client.get(
            "/api/v1/agent/test-drive/availability",
            params={
                "session_id": SESSION,
                "date": (NOW + timedelta(days=1)).date().isoformat(),
                "latitude": 10.77,
                "longitude": 106.69,
            },
        )

    assert locations.seen, "phải có một lần tra địa điểm"
    assert locations.seen[0]["latitude"] == pytest.approx(HANOI["latitude"])
    assert locations.seen[0]["longitude"] == pytest.approx(HANOI["longitude"])


@pytest.mark.asyncio
async def test_phien_chua_chia_se_vi_tri_thi_noi_thang() -> None:
    """Chưa biết khách ở đâu thì KHÔNG đoán — trả 409 kèm mã đọc được.

    Trả 200 với danh sách rỗng ở đây là nói dối: "hôm đó hết chỗ" và "em chưa
    biết anh/chị ở đâu" là hai chuyện khác nhau, và client phải xử lý khác nhau.
    """

    async with _client(location=None) as client:
        response = await client.get(
            "/api/v1/agent/test-drive/availability",
            params={"session_id": SESSION, "date": (NOW + timedelta(days=1)).date().isoformat()},
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "LOCATION_UNKNOWN"


@pytest.mark.asyncio
async def test_ngay_ngoai_cua_so_tra_danh_sach_rong() -> None:
    async with _client(location=HANOI) as client:
        response = await client.get(
            "/api/v1/agent/test-drive/availability",
            params={"session_id": SESSION, "date": (NOW + timedelta(days=60)).date().isoformat()},
        )

    assert response.status_code == 200
    assert response.json()["options"] == []


@pytest.mark.asyncio
async def test_ngay_sai_dinh_dang_bi_tu_choi() -> None:
    async with _client(location=HANOI) as client:
        response = await client.get(
            "/api/v1/agent/test-drive/availability",
            params={"session_id": SESSION, "date": "hom-nao-do"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_khach_khac_khong_doc_duoc_lich_cua_phien_nay() -> None:
    """`session_id` KHÔNG tự nó là quyền đọc dữ liệu phiên.

    Chốt toạ độ ở trên mới chặn được việc tự chọn nơi tra. Thiếu chốt này thì ai
    có (hoặc đoán được) `session_id` vẫn dò ra vị trí khách đã lưu, showroom
    quanh đó, và mã nút để đặt lịch trong phiên của người khác.
    """

    async with _client(location=HANOI, caller="customer-2", owner="customer-1") as client:
        response = await client.get(
            "/api/v1/agent/test-drive/availability",
            params={"session_id": SESSION, "date": (NOW + timedelta(days=1)).date().isoformat()},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_phien_xe_may_thi_tra_showroom_xe_may() -> None:
    """Loại xe đọc TỪ PHIÊN, không khoá cứng `CAR`.

    Khoá cứng `CAR` không phải nợ kỹ thuật mà là lỗi thấy được: khách hỏi lái
    thử xe máy nhận về showroom ô tô, rồi đặt lịch vào đúng nơi không có xe họ
    muốn thử.
    """

    locations = _Locations()

    async with _client(
        location=HANOI,
        locations=locations,
        slots={SlotName.VEHICLE_TYPE: "ELECTRIC_MOTORBIKE"},
    ) as client:
        await client.get(
            "/api/v1/agent/test-drive/availability",
            params={"session_id": SESSION, "date": (NOW + timedelta(days=1)).date().isoformat()},
        )

    assert locations.seen
    kinds = set(locations.seen[0]["location_types"])
    assert kinds == {"showroom_escooter"}, kinds


@pytest.mark.asyncio
async def test_phien_chua_biet_loai_xe_thi_noi_thang() -> None:
    """Thiếu loại xe thì KHÔNG âm thầm dùng `CAR`.

    Đoán bừa ở đây dẫn tới đúng cái lỗi trên, chỉ khác là không ai thấy nó xảy
    ra. Nói thẳng để client hỏi lại khách.
    """

    async with _client(location=HANOI, slots={}) as client:
        response = await client.get(
            "/api/v1/agent/test-drive/availability",
            params={"session_id": SESSION, "date": (NOW + timedelta(days=1)).date().isoformat()},
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "VEHICLE_TYPE_UNKNOWN"


@pytest.mark.asyncio
async def test_phien_da_luu_tru_bi_chan_nhu_phien_la() -> None:
    """Lượt chat đã chặn phiên lưu trữ; endpoint này phải chặn giống hệt.

    `ensure_session` ném `ConversationArchivedError` cho phiên đã lưu trữ, nhưng
    `get_slots` chỉ so chủ sở hữu — nên chủ cũ của một phiên đã đóng vẫn đi trọn
    được: đọc vị trí, lấy showroom, nhận mã đặt lịch. Hai hợp đồng nói hai chuyện
    khác nhau về cùng một phiên.
    """

    async with _client(location=HANOI, archived=True) as client:
        response = await client.get(
            "/api/v1/agent/test-drive/availability",
            params={"session_id": SESSION, "date": (NOW + timedelta(days=1)).date().isoformat()},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_phien_khong_ton_tai_cung_tra_404() -> None:
    """Ba ca "không được đọc phiên này" phải trả CÙNG một mã.

    Trước bản này, phiên không tồn tại rơi vào nhánh `{}` rồi bị kể thành
    "chưa biết loại xe" (409) — một câu nói sai chuyện, và nó còn xác nhận cho
    người lạ biết `session_id` nào có thật.
    """

    async with _client(location=HANOI, owner=None) as client:
        response = await client.get(
            "/api/v1/agent/test-drive/availability",
            params={"session_id": SESSION, "date": (NOW + timedelta(days=1)).date().isoformat()},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_chua_noi_dich_vu_thi_bao_503_chu_khong_bao_loi_nghiep_vu() -> None:
    """Thiếu service là lỗi VẬN HÀNH, không phải "phiên thiếu loại xe"."""

    async with _client(location=HANOI, with_service=False) as client:
        response = await client.get(
            "/api/v1/agent/test-drive/availability",
            params={"session_id": SESSION, "date": (NOW + timedelta(days=1)).date().isoformat()},
        )

    assert response.status_code == 503
