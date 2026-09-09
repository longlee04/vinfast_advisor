"""[COMPARE_VEHICLES] Use case so sánh xe: chốt tập xe → đọc catalog → gọi tool.

Đứng riêng khỏi `IntentRoutingServiceImpl` dù cùng đọc catalog, cùng lý do đã
tách `CatalogBrowseServiceImpl`: `IntentRoutingService` nhận tên xe và trả về
danh tính + bảng thông số của TỪNG xe; service này trả về MỘT bảng đặt các xe
cạnh nhau theo cùng bộ tiêu chí, cộng một đoạn văn nói về khác biệt giữa chúng.
Nhét cả hai vào một Protocol thì `lookup_facts` phải vừa trả một bảng vừa trả n
bảng, và nơi gọi không còn cách nào biết mình đang nhận cái nào.

**Không qua HITL.** Xem docstring `tools/compare_vehicles.py`: đây là tra cứu
catalog công khai, tất định, không cá nhân hoá và không có cam kết thương mại.
Service KHÔNG đặt `lookup_facts` vào state (việc đó do `nodes/route_intent` quyết
định) — cùng cách nhánh `CATALOG_BROWSE` đang làm, và vì đúng một lý do: cổng rủi
ro báo giá (A7-4) đếm giá trong `lookup_facts` để quyết định lượt có phải chờ
người duyệt không, nên đổ bảng so sánh vào đó là tự dựng hàng đợi duyệt cho một
câu hỏi vô hại.

**Một lần gọi LLM, và chỉ để viết câu chữ.** Việc chọn xe, đọc số và xếp bảng đều
tất định. Mô hình chỉ nhận đúng bảng đã chốt và viết lại thành văn xuôi; hỏng hay
chưa nối thì bảng vẫn gửi được, chỉ thiếu đoạn tóm tắt (`_fallback_summary` viết
một câu deterministic thay thế).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from src.agents.contracts import (
    ComparedVehicleView,
    CompareVehiclesResult,
    ComparisonSpecField,
    VehicleComparisonView,
)
from src.agents.domain.pending_slot import PendingSlotRequest
from src.agents.domain.reply_format import bold, field_line
from src.agents.domain.values import Intent
from src.agents.domain.vehicle_comparison import (
    COMPARE_TARGETS_SLOT,
    MAX_COMPARISON_VEHICLES,
    ComparisonOutcome,
    asks_which_to_choose,
    plan_comparison,
)
from src.agents.ports import CatalogReadPort
from src.agents.prompts.comparison_prompts import build_comparison_prompt
from src.agents.prompts.comparison_replies import (
    COMPARE_TARGETS_QUESTION,
    COMPARISON_HEADING,
    DUPLICATE_REPLY,
    MISSING_TEMPLATE,
    TOO_MANY_REPLY_TEMPLATE,
    second_vehicle_question,
)
from src.agents.tools.compare_vehicles import (
    ComparedVehicle,
    VehicleComparison,
    compare_vehicles,
)

logger = logging.getLogger(__name__)


class ComparisonSummaryWriter(Protocol):
    """Cổng viết đoạn tóm tắt. Chỉ cần đúng `LLMPort.synthesize` — không mở rộng.

    Khai lại thành Protocol hẹp thay vì nhận `LLMPort`: service này không dùng
    `extract_slots`, và nhận cả cổng rộng sẽ mời gọi lần gọi LLM thứ hai lẻn vào
    đây ở lần sửa sau.
    """

    async def synthesize(self, *, prompt: str) -> str: ...


class VehicleImageSource(Protocol):
    """Ảnh catalog theo `vehicle_id`. Cùng chữ ký với `VehicleMediaService`."""

    async def image_urls(self, vehicle_ids: Sequence[UUID]) -> dict[UUID, str]: ...


class VehicleIdentityResolver(Protocol):
    """Tên xe → `vehicle_id`. Cùng chữ ký với `IntentRoutingService`."""

    async def resolve_vehicle_mentions(self, mentions: Sequence[str], user_message: str = "") -> list[UUID]: ...


class CompareVehiclesServiceImpl:
    """Trả bảng so sánh, hoặc `None` khi lượt này không phải câu hỏi so sánh."""

    def __init__(
        self,
        *,
        catalog: CatalogReadPort,
        identity: VehicleIdentityResolver,
        media: VehicleImageSource | None = None,
        summary_writer: ComparisonSummaryWriter | None = None,
    ) -> None:
        self._catalog = catalog
        self._identity = identity
        self._media = media
        self._summary_writer = summary_writer

    async def answer(
        self,
        *,
        user_message: str,
        vehicle_names: Sequence[str],
        assume_comparison: bool = False,
    ) -> CompareVehiclesResult | None:
        """`None` nghĩa là "lượt này không thuộc nhánh so sánh" — không phải lỗi.

        Nơi gọi rơi tiếp xuống nhánh cũ khi nhận `None`, đúng khuôn
        `OnRoadPriceServiceImpl.answer_with_pending` (A7-9).

        `assume_comparison=True` bỏ qua bước dò cue: lượt đang ở trong trạng thái
        `COMPARE_TARGETS_SLOT` thì câu "VF3 và VF5" KHÔNG mang từ khoá so sánh
        nào, và bắt nó phải mang thì trạng thái chờ trở thành một cái bẫy —
        khách trả lời đúng câu bot vừa hỏi nhưng câu trả lời không được nhận.
        """

        plan = plan_comparison(
            user_message=user_message,
            vehicle_names=vehicle_names,
            assume_comparison=assume_comparison,
        )
        match plan.outcome:
            case ComparisonOutcome.NOT_A_COMPARISON:
                return None
            case ComparisonOutcome.NEED_ANY_VEHICLE:
                # Mở trạng thái chờ: khách nói rõ muốn so sánh nhưng chưa nêu xe
                # nào. Đây là ca mà entity match trả về 0 xe, nên không nhánh nào
                # khác trong graph trả lời được — `CATALOG_LOOKUP` cần một tên
                # mẫu, `ADVISORY` cần một tiêu chí, và câu này không có cả hai.
                return CompareVehiclesResult(
                    answer=COMPARE_TARGETS_QUESTION,
                    pending_request=_awaiting_targets(),
                )
            case ComparisonOutcome.NEED_MORE_VEHICLES:
                # Rơi về intent cũ: `answer` để RỖNG nên nơi gọi giữ nguyên câu
                # trả lời tra cứu của nhánh cũ, chỉ nối thêm lời mời nêu xe thứ
                # hai. Cướp lượt ở đây sẽ xoá mất bảng thông số mà khách vừa
                # được trả lời đúng.
                #
                # `resolved_vehicle_names` mang xe đã chốt sang lượt sau: nhờ nó,
                # khách chỉ cần gõ đúng mẫu CÒN THIẾU thay vì nhắc lại cả hai.
                if not plan.vehicle_names:
                    return None
                return CompareVehiclesResult(
                    answer="",
                    follow_up=second_vehicle_question(plan.vehicle_names[0]),
                    pending_request=_awaiting_targets(plan.vehicle_names),
                )
            case ComparisonOutcome.DUPLICATE_VEHICLE:
                return CompareVehiclesResult(answer=DUPLICATE_REPLY)
            case ComparisonOutcome.TOO_MANY_VEHICLES:
                return CompareVehiclesResult(
                    answer=TOO_MANY_REPLY_TEMPLATE.format(count=plan.requested_count, limit=MAX_COMPARISON_VEHICLES)
                )
            case ComparisonOutcome.COMPARE:
                return await self._compare(user_message, plan.vehicle_names)

    async def _compare(self, user_message: str, vehicle_names: Sequence[str]) -> CompareVehiclesResult | None:
        resolved, unresolved = await self._resolve(vehicle_names, user_message)
        if len(resolved) < 2:
            # Một tên không khớp catalog thì tập còn lại không đủ để so sánh.
            # Trả `None` để lượt rơi về nhánh tra cứu cũ, nơi đã có sẵn câu "chưa
            # tìm thấy mẫu này" — viết lại câu đó ở đây là hai giọng cho một ca.
            return None
        ids = [vehicle_id for _, vehicle_id in resolved]
        facts = await self._catalog.vehicle_facts(ids)
        images = await self._image_urls(ids)
        payload = compare_vehicles([str(vehicle_id) for vehicle_id in ids], facts=facts, image_urls=images)
        summary = await self._summary(user_message, payload)
        view = _as_view(payload, summary=summary, missing_names=unresolved)
        return CompareVehiclesResult(answer=_render_answer(view, unresolved), comparison=view)

    async def _resolve(
        self, vehicle_names: Sequence[str], user_message: str
    ) -> tuple[list[tuple[str, UUID]], list[str]]:
        """Tên → id, giữ được tên nào KHÔNG khớp để câu trả lời nói đúng tên đó.

        Gọi từng tên một chứ không gọi cả danh sách: `resolve_vehicle_mentions`
        trả về một danh sách id phẳng, không nói id nào thuộc tên nào, nên gọi
        gộp thì một tên trượt sẽ biến mất im lặng. Tối đa ba lần gọi
        (`MAX_COMPARISON_VEHICLES`), không phải một vòng lặp mở.
        """

        resolved: list[tuple[str, UUID]] = []
        unresolved: list[str] = []
        for name in vehicle_names:
            ids = await self._identity.resolve_vehicle_mentions([name], user_message)
            if len(ids) == 1:
                resolved.append((name, ids[0]))
            else:
                # 0 id: không có mẫu này. >1 id: tên khớp nhiều DÒNG xe khác nhau
                # và A4-1 cấm chọn bừa. Cả hai đều là "chưa chốt được danh tính".
                unresolved.append(name)
        return resolved, unresolved

    async def _image_urls(self, ids: Sequence[UUID]) -> dict[UUID, str]:
        """Ảnh xe; hỏng thì bảng vẫn gửi được, chỉ thiếu ảnh.

        Cùng lựa chọn với `chain._recommended_vehicles`: một lỗi đọc ảnh không
        được phép làm rớt một câu trả lời đã dựng xong.
        """

        if self._media is None:
            return {}
        try:
            return await self._media.image_urls(ids)
        except Exception:
            logger.warning("khong doc duoc anh xe cho bang so sanh", exc_info=True)
            return {}

    async def _summary(self, user_message: str, payload: VehicleComparison) -> str:
        writer = self._summary_writer
        if writer is None:
            return _fallback_summary(payload)
        prompt = build_comparison_prompt(
            user_message=user_message,
            vehicle_rows=_prompt_rows(payload),
            # Chỉ khách hỏi thẳng "nên chọn xe nào" mới mở khoá khuyến nghị.
            # Bộ cue dùng chung với `domain/vehicle_comparison`, không viết bảng
            # từ khoá thứ hai — bảng thứ hai lệch đi là một đoạn tóm tắt thiên vị
            # trong một câu hỏi trung tính.
            asks_for_recommendation=asks_which_to_choose(user_message),
        )
        try:
            text = (await writer.synthesize(prompt=prompt) or "").strip()
        except Exception:
            logger.warning("khong sinh duoc tom tat so sanh", exc_info=True)
            return _fallback_summary(payload)
        return text or _fallback_summary(payload)


def _awaiting_targets(resolved: Sequence[str] = ()) -> PendingSlotRequest:
    """Bản ghi trạng thái chờ khách nêu xe để so sánh.

    `partial_form` mang những xe ĐÃ chốt được: nhờ nó, khách chỉ phải gõ mẫu còn
    thiếu ở lượt sau thay vì nhắc lại cả hai. Rỗng ở lượt mở trạng thái, một
    phần tử ở nhánh "mới nắm được một xe".

    `asked_at` lấy `datetime.now(UTC)` tại chỗ, cùng cách
    `OnRoadPriceServiceImpl.answer_with_pending` đang làm: TTL của pending
    (`domain/pending_slot.PENDING_TTL`, 15 phút) đo tuổi của câu hỏi, không phải
    của một mốc nghiệp vụ nào cần tiêm `ClockPort` để test tất định.
    """

    return PendingSlotRequest(
        intent=Intent.COMPARE_VEHICLES.value,
        missing_slot=COMPARE_TARGETS_SLOT,
        partial_form={"resolved_vehicle_names": list(resolved)},
        asked_at=datetime.now(UTC),
    )


def _prompt_rows(
    payload: VehicleComparison,
) -> list[tuple[str, list[tuple[str, str]]]]:
    """Bảng đưa vào prompt — ĐÚNG những ô sẽ hiện trên màn hình khách."""

    rows: list[tuple[str, list[tuple[str, str]]]] = []
    for vehicle in payload.found_vehicles:
        values: list[tuple[str, str]] = []
        if vehicle.price_vnd is not None:
            values.append(("Giá niêm yết (VND)", vehicle.price_vnd))
        values.extend((label, vehicle.specs[code]) for code, label in payload.spec_fields if code in vehicle.specs)
        rows.append((vehicle.name, values))
    return rows


def _fallback_summary(payload: VehicleComparison) -> str:
    """Câu tóm tắt deterministic khi chưa nối LLM hoặc lời gọi thất bại.

    Cố ý KHÔNG nêu con số nào: bản dự phòng chỉ nói bảng đang so sánh những gì.
    Tự ghép một câu "xe A đi xa hơn xe B" ở đây là dựng một bộ so sánh thứ hai,
    và nó sẽ mâu thuẫn với bảng ngay khi bộ tiêu chí đổi.
    """

    names = _join_names([vehicle.name for vehicle in payload.found_vehicles])
    if not names:
        return ""
    return (
        f"Bảng trên đặt {names} cạnh nhau theo cùng bộ tiêu chí. "
        "Anh/chị cho em biết ưu tiên của mình (quãng đường, ngân sách, số chỗ) "
        "để em tư vấn kỹ hơn ạ."
    )


def _as_view(payload: VehicleComparison, *, summary: str, missing_names: Sequence[str]) -> VehicleComparisonView:
    return VehicleComparisonView(
        vehicles=[_as_column(vehicle) for vehicle in payload.vehicles],
        spec_fields=[ComparisonSpecField(code=code, label=label) for code, label in payload.spec_fields],
        summary=summary,
        missing_vehicle_names=list(missing_names),
    )


def _as_column(vehicle: ComparedVehicle) -> ComparedVehicleView:
    return ComparedVehicleView(
        vehicle_id=vehicle.vehicle_id,
        found=vehicle.found,
        display_name=vehicle.name,
        vehicle_type=vehicle.vehicle_type,
        image_url=vehicle.image_url,
        starting_price_vnd=vehicle.price_vnd,
        specs=dict(vehicle.specs),
    )


def _render_answer(view: VehicleComparisonView, missing_names: Sequence[str]) -> str:
    """Câu chữ đi kèm bảng — client CHƯA hỗ trợ bảng vẫn đọc được lượt này.

    Cùng lý do `TurnResponse.recommendations` lặp nội dung của `answer`: một
    client cũ chỉ render `answer`, nên để `answer` teo lại thành một dòng dẫn là
    biến lượt so sánh thành lượt im lặng trên client đó.
    """

    names = _join_names([vehicle.display_name for vehicle in view.vehicles if vehicle.found])
    blocks = [COMPARISON_HEADING.format(names=names)]
    blocks.extend(_column_block(vehicle, view) for vehicle in view.vehicles if vehicle.found)
    if missing_names:
        blocks.append(MISSING_TEMPLATE.format(names=_join_names(list(missing_names))))
    if view.summary:
        blocks.append(view.summary)
    return "\n\n".join(block for block in blocks if block)


def _column_block(vehicle: ComparedVehicleView, view: VehicleComparisonView) -> str:
    """Một khối `* **Nhãn**: giá trị` cho một xe, theo `domain/reply_format`."""

    lines = [f"{bold(vehicle.display_name)}:"]
    if vehicle.starting_price_vnd is not None:
        lines.append(field_line("Giá niêm yết", f"{vehicle.starting_price_vnd} VND"))
    lines.extend(
        field_line(item.label, vehicle.specs[item.code]) for item in view.spec_fields if item.code in vehicle.specs
    )
    return "\n".join(lines)


def _join_names(names: Sequence[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} và {names[-1]}"


__all__ = ["CompareVehiclesServiceImpl"]
