"""[FIND_NEARBY_LOCATION] Use case "tìm địa điểm VinFast gần nhất".

Bốn việc, đúng theo thứ tự này, và thứ tự là phần quan trọng nhất:

1. **Chốt LOẠI địa điểm.** Năm loại: showroom ô tô, showroom xe máy điện, trạm
   sạc ô tô, trạm sạc xe máy, tủ đổi pin. Không nhận ra loại nào thì HỎI kèm năm
   nút bấm — không đoán. Một danh sách đúng khoảng cách nhưng sai loại trông y
   hệt một danh sách đúng, và khách chỉ phát hiện khi đã tới nơi.
2. **Chốt vị trí khách.** Đúng HAI nguồn, không có nguồn thứ ba: toạ độ trình
   duyệt đã gửi lên, hoặc một địa danh khách tự gõ rồi đem đi geocode. Không suy
   từ IP, không hỏi trước khi khách cần.
3. **Đọc địa điểm.** Tất định, qua `NearbyLocationPort`, đã lọc theo loại. Quét
   nới dần (`SEARCH_RADII_KM`) thay vì bắn thẳng bán kính tối đa.
4. **Viết câu dẫn.** MỘT lần gọi LLM, và chỉ để viết câu chữ. Việc chọn địa điểm,
   đo khoảng cách, xếp thứ tự và dựng deep link đều tất định. Mô hình chưa nối
   hoặc hỏng thì danh sách vẫn gửi được, chỉ thiếu phần văn xuôi.

Hỏi LOẠI trước rồi mới hỏi VỊ TRÍ là có chủ đích: chỉ MỘT bản ghi chờ tồn tại mỗi
phiên (`conversation_sessions.pending_slot_request`), nên hai câu hỏi bắt buộc
phải nối tiếp. Loại đi trước vì nó là một cú bấm nút, còn vị trí cần quyền trình
duyệt — hỏi thứ đắt trước rồi mới phát hiện còn thiếu thứ rẻ là bắt khách trả giá
hai lần.

**Không qua HITL.** Đây là tra cứu dữ liệu địa điểm công khai, tất định, không cá
nhân hoá và không có cam kết thương mại nào — cùng nhóm với `CATALOG_BROWSE` và
`COMPARE_VEHICLES` (`domain/quote_risk.py`). Service KHÔNG ghi `lookup_facts` vào
state: cổng rủi ro báo giá (A7-4) đếm giá trong field đó để quyết định lượt có
phải chờ người duyệt không, và một danh sách địa chỉ không mang giá nào.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol

from src.agents.contracts import (
    FindNearbyLocationResult,
    NearbyLocationListView,
    NearbyLocationView,
    QuickReplyView,
)
from src.agents.domain.nearby_location import (
    DEFAULT_LOCATION_LIMIT,
    KIND_LABELS,
    MAX_SEARCH_RADIUS_KM,
    SEARCH_RADII_KM,
    LocationKind,
    UserLocation,
    charger_type_of,
    detect_location_kinds,
    format_distance,
    is_nearby_location_request,
    join_labels,
    kind_of,
    label_of,
    location_text_from,
    location_types_for,
    maps_directions_url,
    pending_for_location_kind,
    pending_for_user_location,
    quick_replies_for_kinds,
    round_distance_km,
)
from src.agents.ports import GeocodePort, NearbyLocationPort, NearbyPlace
from src.agents.prompts.nearby_location_prompts import build_nearby_location_prompt
from src.agents.prompts.nearby_location_replies import (
    ASK_LOCATION_KIND_QUESTION,
    ASK_LOCATION_QUESTION_TEMPLATE,
    FALLBACK_LEAD_TEMPLATE,
    GEOCODE_FAILED_TEMPLATE,
    NEAREST_HINT_TEMPLATE,
    NO_RESULT_TEMPLATE,
)

logger = logging.getLogger(__name__)


class NearbyLocationLeadWriter(Protocol):
    """Cổng viết câu dẫn. Chỉ cần đúng `LLMPort.synthesize` — không mở rộng.

    Khai lại thành Protocol hẹp thay vì nhận `LLMPort`, cùng lý do
    `ComparisonSummaryWriter` đã làm: service này không dùng `extract_slots`, và
    nhận cả cổng rộng sẽ mời gọi một lần gọi LLM thứ hai lẻn vào đây ở lần sửa sau.
    """

    async def synthesize(self, *, prompt: str) -> str: ...


class NearbyLocationServiceImpl:
    """Trả danh sách địa điểm, hoặc `None` khi lượt này không phải câu hỏi đường."""

    def __init__(
        self,
        *,
        locations: NearbyLocationPort,
        geocoder: GeocodePort | None = None,
        lead_writer: NearbyLocationLeadWriter | None = None,
        limit: int = DEFAULT_LOCATION_LIMIT,
    ) -> None:
        self._locations = locations
        self._geocoder = geocoder
        self._lead_writer = lead_writer
        self._limit = max(1, limit)

    async def answer(
        self,
        *,
        user_message: str,
        known_location: UserLocation | None = None,
        location_text: str | None = None,
        location_kinds: Sequence[LocationKind] = (),
        assume_request: bool = False,
    ) -> FindNearbyLocationResult | None:
        """`None` nghĩa là "lượt này không thuộc nhánh địa điểm" — không phải lỗi.

        Nơi gọi rơi tiếp xuống nhánh cũ khi nhận `None`, đúng khuôn
        `CompareVehiclesServiceImpl.answer` và `OnRoadPriceServiceImpl`.

        `assume_request=True` bỏ qua bước dò cue: lượt đang ở trong trạng thái
        chờ thì câu "Cầu Giấy" hay "Tủ đổi pin" KHÔNG mang từ khoá địa điểm nào,
        và bắt nó phải mang thì trạng thái chờ trở thành một cái bẫy — khách trả
        lời đúng câu bot vừa hỏi nhưng câu trả lời không được nhận.
        """

        if not assume_request and not is_nearby_location_request(user_message):
            return None

        kinds = tuple(location_kinds) or detect_location_kinds(user_message)
        if not kinds:
            # Chưa biết khách tìm gì. DỪNG ở đây kèm năm nút bấm — hỏi loại là
            # một cú bấm, rẻ hơn nhiều so với xin quyền vị trí rồi mới phát hiện
            # mình đang tra nhầm bảng.
            return FindNearbyLocationResult(
                answer=ASK_LOCATION_KIND_QUESTION,
                locations=_ask_view(needs_kind=True),
                needs_location_kind=True,
                quick_replies=[QuickReplyView(label=label, value=value) for label, value in quick_replies_for_kinds()],
                pending_request=pending_for_location_kind(user_message=user_message),
            )

        location, failure = await self._resolve_location(known_location, location_text, kinds)
        if failure is not None:
            return failure
        if location is None:
            # Đã biết loại, chưa biết vị trí. Tính khoảng cách từ một toạ độ mặc
            # định nào đó sẽ trả về một danh sách trông rất thuyết phục và sai
            # hoàn toàn.
            return FindNearbyLocationResult(
                answer=ASK_LOCATION_QUESTION_TEMPLATE.format(
                    kinds=join_labels([KIND_LABELS[kind] for kind in kinds]).lower()
                ),
                locations=_ask_view(needs_location=True, kinds=kinds),
                needs_location=True,
                pending_request=pending_for_user_location(user_message=user_message, kinds=kinds),
            )
        return await self._nearest(user_message, location, kinds)

    async def _resolve_location(
        self,
        known_location: UserLocation | None,
        location_text: str | None,
        kinds: Sequence[LocationKind],
    ) -> tuple[UserLocation | None, FindNearbyLocationResult | None]:
        """Toạ độ dùng cho lượt này, hoặc một kết quả kết thúc lượt sớm.

        Vị trí đã có trong phiên được dùng LUÔN, không hỏi lại: khách đã chia sẻ
        một lần trong cùng phiên thì hỏi lại ở câu thứ hai là quên mất họ vừa nói
        gì.
        """

        if known_location is not None:
            return known_location, None
        text = location_text_from(location_text or "") if location_text else None
        if text is None:
            return None, None
        if self._geocoder is None:
            logger.info("chua noi geocoder; coi nhu khong tra duoc %r", text[:80])
            return None, self._geocode_failure(text, kinds)
        place = await self._geocoder.geocode(text)
        if place is None:
            # Geocode thất bại KHÔNG ném lỗi ra ngoài (`ports.GeocodePort`): mở
            # lại trạng thái chờ để khách gõ rõ hơn, thay vì trả một lượt chết.
            return None, self._geocode_failure(text, kinds)
        return (
            UserLocation(
                latitude=place.latitude,
                longitude=place.longitude,
                source="geocode",
                label=place.display_name,
            ),
            None,
        )

    def _geocode_failure(self, text: str, kinds: Sequence[LocationKind]) -> FindNearbyLocationResult:
        """Không tra ra địa danh: mời khách nói rõ hơn, giữ nguyên loại đã chốt."""

        return FindNearbyLocationResult(
            answer=GEOCODE_FAILED_TEMPLATE.format(location_text=text),
            locations=_ask_view(needs_location=True, kinds=kinds),
            needs_location=True,
            pending_request=pending_for_user_location(user_message=text, kinds=kinds),
        )

    async def _nearest(
        self,
        user_message: str,
        location: UserLocation,
        kinds: Sequence[LocationKind],
    ) -> FindNearbyLocationResult:
        """Quét nới dần rồi dựng payload. Rỗng vẫn là một câu trả lời tử tế."""

        types = location_types_for(kinds)
        rows: list[NearbyPlace] = []
        radius = MAX_SEARCH_RADIUS_KM
        for candidate in SEARCH_RADII_KM:
            radius = candidate
            rows = await self._locations.nearest(
                latitude=location.latitude,
                longitude=location.longitude,
                radius_km=float(candidate),
                location_types=types,
                limit=self._limit,
            )
            if rows:
                break
        view = _as_view(rows, origin=location, radius_km=float(radius), kinds=kinds)
        if not view.locations:
            # Nói rõ ĐÃ QUÉT BAO XA thay vì trả một danh sách rỗng im lặng.
            return FindNearbyLocationResult(
                answer=NO_RESULT_TEMPLATE.format(
                    kinds=join_labels([KIND_LABELS[kind] for kind in kinds]).lower(),
                    radius_km=float(MAX_SEARCH_RADIUS_KM),
                ),
                locations=view,
                resolved_location=location,
            )
        return FindNearbyLocationResult(
            answer=await self._lead(user_message, location, view),
            locations=view,
            resolved_location=location,
        )

    async def _lead(
        self,
        user_message: str,
        location: UserLocation,
        view: NearbyLocationListView,
    ) -> str:
        writer = self._lead_writer
        if writer is None:
            return _fallback_lead(view)
        prompt = build_nearby_location_prompt(
            user_message=user_message,
            origin_label=location.label,
            kind_labels=[KIND_LABELS[kind] for kind in LocationKind if kind.value in view.location_types],
            places=[(item.name, item.address, format_distance(item.distance_km)) for item in view.locations],
        )
        try:
            text = (await writer.synthesize(prompt=prompt) or "").strip()
        except Exception:
            logger.warning("khong sinh duoc cau dan dia diem", exc_info=True)
            return _fallback_lead(view)
        return text or _fallback_lead(view)


def _ask_view(
    *,
    needs_kind: bool = False,
    needs_location: bool = False,
    kinds: Sequence[LocationKind] = (),
) -> NearbyLocationListView:
    """Payload của lượt CHƯA đủ dữ kiện để tra.

    Rỗng nhưng KHÁC `None`: xem chú thích `needs_location` ở
    `contracts.NearbyLocationListView` về lý do client cần đúng một tín hiệu để
    rẽ nhánh render.
    """

    return NearbyLocationListView(
        location_types=[kind.value for kind in kinds],
        needs_location_kind=needs_kind,
        needs_location=needs_location,
    )


def _as_view(
    rows: Sequence[NearbyPlace],
    *,
    origin: UserLocation,
    radius_km: float,
    kinds: Sequence[LocationKind],
) -> NearbyLocationListView:
    return NearbyLocationListView(
        locations=[_as_card(row, origin) for row in rows],
        location_types=[kind.value for kind in kinds],
        origin_latitude=origin.latitude,
        origin_longitude=origin.longitude,
        origin_label=origin.label,
        searched_radius_km=radius_km,
    )


def _as_card(row: NearbyPlace, origin: UserLocation) -> NearbyLocationView:
    kind = kind_of(row.location_type)
    return NearbyLocationView(
        id=row.id,
        name=row.name,
        address=row.address,
        latitude=row.latitude,
        longitude=row.longitude,
        distance_km=round_distance_km(row.distance_km),
        # Loại lạ (năm loại xưởng dịch vụ còn nằm trong bảng) đi qua nguyên văn
        # chuỗi kho lưu trữ thay vì bị nuốt thành rỗng: nếu một truy vấn nào đó
        # lỡ kéo chúng về, client vẫn hiện được thay vì dựng một card không nhãn.
        location_type=kind.value if kind is not None else row.location_type,
        category_label=label_of(row.location_type, row.category_label),
        # `origin` luôn được gắn: toạ độ khách đã có trong tay ở đúng nhánh này,
        # và thiếu nó thì Google Maps phải tự xin quyền vị trí một lần nữa trên
        # máy khách — người vừa từ chối quyền đó ở trang này.
        maps_url=maps_directions_url(
            destination_latitude=row.latitude,
            destination_longitude=row.longitude,
            origin=origin,
        ),
        charger_type=charger_type_of(row.location_type),
        hotline=row.hotline,
        open_time=row.open_time,
        close_time=row.close_time,
        status=row.status,
    )


def _fallback_lead(view: NearbyLocationListView) -> str:
    """Câu dẫn deterministic khi chưa nối LLM hoặc lời gọi thất bại.

    Cố ý CHỈ nói số lượng, không nhắc lại địa chỉ của địa điểm nào: những con số
    đó đã có trong card, và chép chúng vào một câu viết tay là dựng một bộ định
    dạng thứ hai — nó sẽ lệch khỏi card ngay lần đổi đơn vị đầu tiên.
    """

    labels = [KIND_LABELS[kind] for kind in LocationKind if kind.value in view.location_types]
    lead = FALLBACK_LEAD_TEMPLATE.format(
        count=len(view.locations),
        kinds=join_labels(labels).lower() or "địa điểm",
    )
    nearest = view.locations[0]
    return f"{lead} " + NEAREST_HINT_TEMPLATE.format(name=nearest.name, distance=format_distance(nearest.distance_km))


__all__ = ["NearbyLocationLeadWriter", "NearbyLocationServiceImpl"]
