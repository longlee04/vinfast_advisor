"""Thực thi một `Action` của lõi v2 bằng ĐÚNG một service cũ (spec mục 7).

Tầng này là chỗ DUY NHẤT của lõi v2 chạm `AgentServices`. Nó KHÔNG mở
transaction, KHÔNG ghi DB, KHÔNG import `chain`/`nodes`. Mọi thứ nó muốn ghi đi
ra qua `ActResult.state_patch` / `ActResult.hitl_request` để `run_turn` ghi một
lần duy nhất cuối lượt (bài học `_write_pending`).
"""

from __future__ import annotations

import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from types import MappingProxyType
from contextvars import ContextVar
from typing import Any, Final
from uuid import UUID, uuid4

from src.agents.contracts import (
    TCO_COMPONENT_GROUPS,
    FilterCriteria,
    NavigateCenter,
    NavigateShowroomView,
    NavigateView,
    ProvinceOptionView,
    QuickReplyView,
    Recommendation,
    RecommendedVehicleView,
    TcoCardView,
    TcoComponentView,
    TcoRatesView,
    TestDriveCardView,
)
from src.agents.core import fit, render
from src.agents.core.actions import (
    ASPECT_PRICE,
    OPEN_REASON_DEAD_END,
    CONFIRM_OFFER,
    FIT_YES,
    LOOKUP_POLICY,
    PENDING_PROFILE,
    PENDING_VEHICLE,
    REASON_RETRY,
    TEMPLATE_CHOSEN_SUMMARY,
    TEMPLATE_CLARIFY,
    TEMPLATE_NO_BETTER,
    TEMPLATE_SAME_PICK,
    Action,
    Ask,
    Book,
    Compare,
    EnqueueHitl,
    FitCheck,
    Handoff,
    Lookup,
    Nearby,
    NextSteps,
    NotInCatalog,
    OnRoadPrice,
    OpenQuestion,
    Recommend,
    Reply,
    ScopeNote,
    ShowroomOptions,
    Silent,
    Tco,
    VehicleQa,
)
from src.agents.core.state import CoreState, Pending, PendingKind, Stage
from src.agents.core.understand import sanitize_prompt_text, transcript_lines
from src.agents.core.validate import VehicleDirectory, VehicleRef
from src.agents.core.suggest import profile_examples
from src.agents.domain.agent_flag import FLAG_AGENT_FALLBACK, is_enabled_for
from src.agents.domain.agent_tools import (
    AGENT_TOOL_DANH_MUC,
    AGENT_TOOL_SO_SANH,
    AGENT_TOOL_TIM_DIEM,
    AGENT_TOOL_TINH_CHI_PHI,
    AGENT_TOOL_TRA_THONG_SO,
    ERROR_BAD_ARGS,
    ERROR_EMPTY,
    ERROR_TOOL_FAILED,
    ERROR_UNKNOWN_TOOL,
    ERROR_UNKNOWN_VEHICLE,
    AgentToolCall,
    AgentToolResult,
    ValidationError,
    build_agent_tools,
    is_read_only,
    parse_tool_args,
)
from src.agents.domain.bottleneck_signal import ConfirmedBottleneckEvidence
from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.catalog_browse import page_path_for_name, page_slug_for_name
from src.agents.domain.comparative_revision import ComparativeRevision, detect_comparative_revision
from src.agents.domain.customer_profile import Bottleneck, BottleneckEvidence, OfferState, ProfileSnapshot
from src.agents.domain.location_tool import LOCATION_TOOL_NAME, LocationToolArgs
from src.agents.domain.nearby_location import LocationKind, UserLocation, detect_location_kinds
from src.agents.domain.need_tags import need_tag_display
from src.agents.domain.scoring import LONG_TRIP_MIN_RANGE_KM
from src.agents.domain.pricing_intent import (
    PROVINCES,
    assumption_note,
    detect_province,
    province_options,
    region_for_province_code,
)
from src.agents.domain.quote_risk import DeliveryAction, classify_draft_delivery
from src.agents.domain.spec_tool import SPEC_TOOL_NAME
from src.agents.domain.tco_tool import TCO_TOOL_NAME, TcoToolArgs
from src.agents.domain.test_drive import now_in_vietnam
from src.agents.domain.values import SlotName, VehicleType
from src.agents.logging import get_agent_logger
from src.agents.prompts.question_variants import get_profile_variant, get_reask_lead
from src.agents.services.conversation_memory import AdvisorReviewRequest
from src.agents.services.call_budget import CallKind, current_call_budget
from src.agents.services.registry import AgentServices
from src.agents.services.slot_token import read_slot_token
from src.config import get_settings

logger = get_agent_logger("agent.core.act")
#: Bóc đúng mảnh bị chặn từ thông điệp `RenderError` (`render.assert_clean`:
#: "chữ cấm 'X' trong: '...'") — để log CHỈ mảnh đó, không log nguyên câu khách
#: kèm theo (thông điệp gốc có in 80 ký tự đầu của câu để dễ soi lúc dựng lỗi
#: thủ công, nhưng log của lưới an toàn cuối không cần và không nên giữ thêm).
_OFFENDING_FRAGMENT = re.compile(r"chữ cấm '([^']*)'")

FEATURE_SLOT = SlotName.HABIT_NEED_TAGS

#: Số km/ngày tạm tính khi khách chưa nói — lõi không hỏi thêm một lượt chỉ để
#: lấy con số này. Mức đi làm phổ thông ở đô thị Việt Nam.
DEFAULT_DAILY_KM = 30

#: Tham số agent loop. [GIẢ ĐỊNH] chốt theo plan §2.2, hiệu chỉnh sau Bước 9.
AGENT_MAX_STEPS: Final = 3
AGENT_STEP_TIMEOUT_SECONDS: Final = 4.0
AGENT_TOTAL_TIMEOUT_SECONDS: Final = 10.0
#: Trần chữ của một khối chữ service nhét vào payload tool.
MAX_TOOL_TEXT_CHARS: Final = 1200

#: Action cần một `run_id` (đọc snapshot bất biến). `run_turn` tạo run TRƯỚC khi
#: gọi `act` chỉ cho đúng những Action này — không tạo run cho lượt hỏi slot.
#: `EnqueueHitl` PHẢI có run: `AdvisorReviewRequest` cần `run_id`, thiếu là mục
#: ưu đãi không bao giờ vào `review_queue` (prod 2026-08-30: 0 dòng từ lõi v2).
NEEDS_RUN: tuple[type, ...] = (Recommend, VehicleQa, Tco, EnqueueHitl, OpenQuestion)


def needs_run(action: object) -> bool:
    """Action cần `run_id`: bộ NEEDS_RUN + tra chính sách (mục duyệt cần run)."""

    return isinstance(action, NEEDS_RUN) or (isinstance(action, Lookup) and action.mode == LOOKUP_POLICY)


def is_profile_reask(action: object, state: CoreState) -> bool:
    """Lượt hỏi LẠI câu hồ sơ — nhánh duy nhất của `Ask` có thể gọi agent (móc 3).

    Cần `state` nên không gộp vào `needs_run`: lần hỏi ĐẦU không bao giờ gọi
    agent, và tạo một hàng `agent_runs` cho nó là rác đúng như `needs_run` đã
    cảnh báo. Lần hỏi lại thì cần run để agent snapshot evidence trước `verify`.
    """

    return isinstance(action, Ask) and action.key == PENDING_PROFILE and state.ask_counts.get(action.key, 0) > 1


#: Chữ của `Handoff` — lượt lõi v2 bỏ cuộc và chuyển sang người.
#:
#: KHÔNG dùng `_CLARIFY["OFFER_REVIEW"]` như bản đầu: câu đó nói "tư vấn viên
#: đang xem ƯU ĐÃI cho anh/chị" trong khi `Handoff` sinh ra ở ba chỗ khác hẳn
#: (hỏi quá `MAX_ASKS`, hỏi lại quá trần, `UNCLEAR` quá trần) — không ưu đãi nào
#: đang được xem cả, và khách đọc xong sẽ ngồi chờ một thứ không tồn tại.
#: `_CLARIFY` cũng không có khoá `HANDED_OFF` nên `render_reply` rơi về
#: `COLLECTING` ("em chưa rõ ý anh/chị") — càng sai vì lượt này đã hết hỏi.
#:
#: Hằng nằm ở đây chứ không ở `render._CLARIFY` vì nó không phải mẫu theo chặng:
#: mọi chặng chuyển người đều nói đúng câu này.
HANDOFF_TEXT: str = render.assert_clean(
    "Em chưa hỗ trợ được ý này của anh/chị. Em đã chuyển sang tư vấn viên hỗ trợ trực tiếp ạ."
)
#: Khách XIN gặp người: không có gì "chưa hỗ trợ được" cả — xác nhận và bàn giao.
HANDOFF_REQUESTED_TEXT: str = render.assert_clean(
    "Dạ, em chuyển anh/chị sang tư vấn viên ngay ạ. Anh/chị chờ một chút, tư vấn viên sẽ nhắn trực tiếp tại đây."
)


def _frozen(mapping: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(mapping or {}))


@dataclass(frozen=True, slots=True)
class ActResult:
    """Kết quả thực thi một Action.

    - `text`: nội dung chính trả khách (đã qua `render`, hoặc `answer` của
      service cũ). Chuỗi rỗng CHỈ hợp lệ với `Silent`.
    - `cards`: khoá đúng tên field của `TurnResult` (`recommendations`,
      `test_drive_card`, `comparison`, `nearby_locations`, `tco_card`,
      `quick_replies`, `lookup_facts`, `vehicle_details`, `vehicle_type`).
    - `state_patch`: khoá đúng tên field của `CoreState`; `run_turn` áp bằng
      `state.with_(**state_patch)`.
    """

    text: str = ""
    cards: Mapping[str, Any] = field(default_factory=lambda: _frozen({}))
    state_patch: Mapping[str, Any] = field(default_factory=lambda: _frozen({}))
    hitl_request: AdvisorReviewRequest | None = None
    #: [Tool-calling] Vệt các lần LLM gọi tool trong lượt — `run_turn` chép
    #: nguyên vào `TurnTrace.payload["tool_calls"]` để màn admin trả lời được
    #: "vì sao bảng chi phí ra số này" (Sếp 2026-08-31). Rỗng = lượt không gọi.
    tool_calls: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "cards", _frozen(self.cards))
        object.__setattr__(self, "state_patch", _frozen(self.state_patch))


async def act(
    action: Action,
    state: CoreState,
    services: AgentServices,
    *,
    run_id: UUID | None,
    customer_id: str,
    user_message: str,
    transcript: Sequence[Any] = (),
) -> ActResult:
    """Một Action → một lời gọi service cũ → `ActResult`.

    `user_message` có mặt vì SÁU service cũ nhận nguyên câu của khách
    (`catalog_browse`, `compare_vehicles`, `nearby_location`, `test_drive`,
    `on_road_price`, `retrieval.layer2`) — bỏ nó đi thì phải bịa lại câu, đúng
    kiểu sai mà lõi v2 sinh ra để dẹp.
    """

    if isinstance(action, Silent):
        return ActResult()
    if isinstance(action, Handoff):
        text = HANDOFF_REQUESTED_TEXT if action.reason == "requested" else HANDOFF_TEXT
        return ActResult(text=text, state_patch={"stage": Stage.HANDED_OFF, "pending": None})
    if isinstance(action, Ask):
        result = await _ask(
            action,
            state,
            services,
            user_message=user_message,
            run_id=run_id,
            customer_id=customer_id,
            transcript=transcript,
        )
    elif isinstance(action, Reply):
        result = await _reply(action, state, services)
    elif isinstance(action, Lookup):
        result = await _lookup(action, state, services, user_message=user_message, run_id=run_id)
    elif isinstance(action, NotInCatalog):
        result = await _not_in_catalog(action, state, services)
    elif isinstance(action, Compare):
        result = await _compare(action, state, services, user_message=user_message)
    elif isinstance(action, Nearby):
        result = await _nearby(state, services, user_message=user_message)
    elif isinstance(action, VehicleQa):
        result = await _vehicle_qa(action, state, services)
    elif isinstance(action, FitCheck):
        result = await _fit_check(action, state, services, user_message=user_message)
    elif isinstance(action, NextSteps):
        result = await _next_steps(action, state, services)
    elif isinstance(action, ScopeNote):
        result = await _scope_note(action, state, services)
    elif isinstance(action, Recommend):
        result = await _recommend(
            action,
            state,
            services,
            run_id=run_id,
            user_message=user_message,
            customer_id=customer_id,
            transcript=transcript,
        )
    elif isinstance(action, Tco):
        result = await _tco(action, state, services, user_message=user_message, run_id=run_id)
    elif isinstance(action, OnRoadPrice):
        result = await _on_road_price(action, state, services, user_message=user_message, run_id=run_id)
    elif isinstance(action, ShowroomOptions):
        result = await _showroom_options(action, state, services, user_message=user_message, customer_id=customer_id)
    elif isinstance(action, Book):
        result = await _book(action, state, services, customer_id=customer_id, user_message=user_message)
    elif isinstance(action, EnqueueHitl):
        result = await _enqueue_hitl(
            action, state, services, run_id=run_id, user_message=user_message, customer_id=customer_id
        )
    elif isinstance(action, OpenQuestion):
        # Móc 1: lõi tất định đã bí. Agent trả `None` thì lượt ra ĐÚNG câu mà
        # `policy._unclear` vẫn trả hôm nay — không có "câu an toàn riêng".
        agent = await _open_question_or_none(
            action,
            state,
            services,
            run_id=run_id,
            customer_id=customer_id,
            user_message=user_message,
            transcript=transcript,
        )
        result = agent if agent is not None else await _reply(
            Reply(template=TEMPLATE_CLARIFY, args={"stage": state.stage.value}), state, services
        )
    else:  # pragma: no cover - union đã phủ hết
        raise TypeError(f"Action lạ ở act(): {action!r}")

    if getattr(action, "resume_pending", False) and state.pending is not None:
        return ActResult(
            text=render.render_resume(result.text, state.pending),
            cards=result.cards,
            state_patch=result.state_patch,
            hitl_request=result.hitl_request,
        )
    return result


# --------------------------------------------------------------- tên xe


async def catalog_names(services: AgentServices, *, vehicle_type: str | None) -> dict[str, str]:
    """`vehicle_id` (chuỗi) → tên hiển thị, đọc từ catalog TẤT ĐỊNH.

    `catalog_browse` là service cũ duy nhất trả về cả id lẫn tên mà KHÔNG gọi
    LLM (`registry.py:233` — "liệt kê danh mục theo LOẠI xe, không gọi LLM").
    `resolve_vehicle_names` chỉ đi chiều ngược (tên → id) nên không dùng được.

    Catalog hỏng thì trả rỗng: mất nhãn đẹp còn hơn mất câu trả lời.
    """

    service = services.catalog_browse
    if service is None:
        return {}
    try:
        result = await service.answer(user_message="", vehicle_type_hint=vehicle_type)
    except Exception:
        logger.warning("core.act: khong doc duoc ten xe tu catalog", exc_info=True)
        return {}
    if result is None:
        return {}
    return {str(pitch.vehicle_id): pitch.display_name for pitch in result.pitches}


def _vehicle_type(state: CoreState) -> str | None:
    value = state.slots.get(SlotName.VEHICLE_TYPE)
    return str(value) if value else None


async def _name_of(services: AgentServices, state: CoreState, vehicle_id: str | None) -> str:
    if not vehicle_id:
        return ""
    return (await catalog_names(services, vehicle_type=_vehicle_type(state))).get(vehicle_id, "")


async def _closing(
    services: AgentServices,
    state: CoreState,
    *,
    vehicle_name: str,
    has_tco: bool | None = None,
    after_on_road: bool = False,
) -> str:
    """Câu kết theo checklist (`render.closing_question`) cho lượt này.

    Việc "đã có chi phí" suy từ chặng (`COSTING`) trừ khi chỗ gọi biết rõ hơn
    (lượt `Tco` vừa báo số thì `has_tco=True` dù chặng chưa kịp đổi). Tên các mẫu
    đề xuất chỉ tra khi CHƯA chốt xe — đó là nhánh duy nhất cần hai tên.
    """

    names: tuple[str, ...] = ()
    if not state.chosen_vehicle_id and state.recommended_ids:
        directory = await catalog_names(services, vehicle_type=_vehicle_type(state))
        names = tuple(label for vehicle_id in state.recommended_ids if (label := directory.get(str(vehicle_id))))
    return render.closing_question(
        state,
        vehicle_name=vehicle_name,
        has_tco=(state.stage is Stage.COSTING) if has_tco is None else has_tco,
        has_booking=state.booking_id is not None,
        recommended_names=names,
        after_on_road=after_on_road,
    )


# --------------------------------------------------------------- Ask / Reply


async def _profile_catalog(services: AgentServices, *, vehicle_type: str, user_message: str) -> object | None:
    """Danh sách xe của ĐÚNG loại khách vừa nêu, hoặc `None`.

    Cùng cửa `catalog_browse` mà `Lookup(browse)` dùng — chữ của service cũ nên
    KHÔNG qua `assert_clean` (ruling bước 3: chữ đã kiểm chứng ở tầng dưới).
    Catalog hỏng thì trả `None` và lượt lui về đúng câu hỏi trống, không nổ.
    """

    service = services.catalog_browse
    if service is None:
        return None
    try:
        result = await service.answer(user_message=user_message, vehicle_type_hint=vehicle_type)
    except Exception:
        logger.warning("core.act: khong bay duoc danh sach xe cho cau ho so", exc_info=True)
        return None
    return result if result is not None and result.answer.strip() else None


async def _ask(
    action: Ask,
    state: CoreState,
    services: AgentServices,
    *,
    user_message: str = "",
    run_id: UUID | None = None,
    customer_id: str = "",
    transcript: Sequence[Any] = (),
) -> ActResult:
    """Điền nhãn khách đọc được rồi mới sinh chữ.

    Policy không biết catalog nên `Ask(kind=CHOICE)` từ policy mang id thô ở
    `options` và `labels=()`. `render` sẽ ném `RenderError` nếu id lọt ra khách
    — đây là chỗ (và là chỗ DUY NHẤT) chặn việc đó.
    """

    labels = action.labels
    if action.kind is PendingKind.CHOICE and not labels and action.options:
        names = await catalog_names(services, vehicle_type=_vehicle_type(state))
        labels = tuple(names.get(option, f"mẫu {index}") for index, option in enumerate(action.options, start=1))
    elif action.kind is PendingKind.CONFIRM and action.key == CONFIRM_OFFER and not labels:
        # `policy._guard` treo `vehicle_id` thô (policy.py:228) và policy không
        # biết catalog. Không dịch ở đây thì câu xác nhận đọc nguyên uuid cho
        # khách — `render_ask` nay ném `RenderError` chứ không để nó lọt ra.
        vehicle_id = action.options[0] if action.options else state.chosen_vehicle_id
        labels = (render.confirm_offer_label(await _name_of(services, state, vehicle_id)),)
    # `job` phải đi theo — bản dựng lại từng đánh rơi nó, và câu "đặt lái thử
    # mẫu nào" thành lại câu luồng thông số (Sếp bắt được trên prod 2026-08-31).
    enriched = Ask(key=action.key, kind=action.kind, options=action.options, labels=labels, job=action.job)
    pending = Pending(
        kind=action.kind,
        key=action.key,
        options=action.options,
        labels=labels,
        asked_at_turn=state.turn_count,
        job=action.job,
    )
    text = render.render_ask(enriched)
    asked_before = max(0, state.ask_counts.get(action.key, 0) - 1)
    if action.key == PENDING_PROFILE and asked_before > 0:
        # MÓC 3 (mở rộng plan agent-migration §1.3): khách đã nghe câu hồ sơ một
        # lần và vẫn nói một thứ lõi không dùng được — đó là ngõ cụt thật, đúng
        # loại lượt hai móc kia sinh ra để cứu, chỉ khác là nó xảy ra ở chặng
        # COLLECTING/GREETING mà plan cố ý chừa ra (GĐ-9). Đo trên máy thật
        # 2026-09-23: ba lượt liên tiếp rơi vào đây, và lượt thứ tư sẽ bị đẩy
        # sang tư vấn viên vì chạm `MAX_ASKS`.
        #
        # Agent TRẢ LỜI câu khách vừa hỏi, rồi câu hồ sơ vẫn được nối vào cuối —
        # `pending` không đổi nên lượt sau khách đáp vẫn là SLOT_ANSWER. Cờ TẮT
        # hoặc agent hỏng → `answered is None` → đúng chữ tất định bên dưới.
        answered = await _open_question_or_none(
            OpenQuestion(
                question=user_message,
                reason=OPEN_REASON_DEAD_END,
                vehicle_ids=await _agent_catalog_ids(services, state),
            ),
            state,
            services,
            run_id=run_id,
            customer_id=customer_id,
            user_message=user_message,
            transcript=transcript,
        )
        if answered is not None:
            # Bỏ câu kết của agent (`_closing` mời xem chi phí/lái thử): lượt này
            # còn một câu hỏi đang treo, hai lời mời chồng nhau là hai việc.
            body = answered.text.split("\n\n")[0].strip()
            return ActResult(
                text=f"{body}\n\n{text}",
                cards=dict(answered.cards),
                state_patch={"pending": pending},
                tool_calls=answered.tool_calls,
            )
    if action.key == PENDING_PROFILE:
        # Câu hồ sơ là MỘT chuỗi cố định, nên hỏi lại là lặp y nguyên từng chữ —
        # đo trên máy thật 2026-09-23: ba lượt liên tiếp nhận đúng một câu, khách
        # tưởng bot hỏng. Biến thể tất định theo phiên + số lần đã hỏi
        # (`prompts/question_variants`, cùng cơ chế lõi v1 đã dùng), lần hỏi ĐẦU
        # giữ nguyên văn câu đang chạy.
        text = render.assert_clean(get_profile_variant(asked_before, state.session_id))
    if asked_before > 0:
        # Hỏi LẠI mà không thừa nhận gì thì khách nghe như bot không nghe thấy
        # câu vừa rồi. Câu ghi nhận không hứa hẹn, không khẳng định đã hiểu.
        text = f"{render.assert_clean(get_reask_lead(asked_before, state.session_id))} {text}"
    cards: dict[str, Any] = {}
    vehicle_type = _vehicle_type(state)
    if action.key == PENDING_PROFILE and vehicle_type:
        # Khách đã nói loại xe ("tư vấn ô tô") mà lõi vẫn hỏi một câu trống
        # không là bỏ phí thứ họ vừa cho. Bày danh sách của đúng loại đó TRƯỚC,
        # rồi hỏi — trong CÙNG một tin nhắn và VẪN treo `profile`, nên lượt sau
        # câu trả lời của khách vẫn là SLOT_ANSWER (không phải lỗi cũ "đổ catalog
        # thay cho câu hỏi", 175/188 lượt hỏng trên prod).
        listing = await _profile_catalog(services, vehicle_type=vehicle_type, user_message=user_message)
        if listing is not None:
            text = f"{listing.answer.strip()}\n\n{text}"
            names = [pitch.display_name for pitch in listing.pitches]
            replies = profile_examples(vehicle_type, vehicle_names=names)
            if replies:
                cards["quick_replies"] = [QuickReplyView(label=item, value=item) for item in replies]
    return ActResult(text=text, cards=cards, state_patch={"pending": pending})


async def _reply(action: Reply, state: CoreState, services: AgentServices) -> ActResult:
    vehicle_id = action.args.get("vehicle_id") or state.chosen_vehicle_id
    name = await _name_of(services, state, vehicle_id)
    cards: dict[str, Any] = {}
    if action.template == TEMPLATE_CHOSEN_SUMMARY and vehicle_id:
        # Khách VỪA chốt một mẫu → dẫn sang trang xe (contract đợt 9 mục 1).
        cards["navigate"] = vehicle_navigate(vehicle_id, name)
        # Sếp 2026-08-31: chọn xe khan (chưa kể nhu cầu) thì GIỚI THIỆU NGẮN VỀ
        # XE (dòng, thông số, nhóm người điển hình), KHÔNG hỏi ngược nhu cầu và
        # KHÔNG nói "hợp nhu cầu anh/chị". Lấy thông số từ cùng cửa `_vehicle_qa`.
        intro = await _chosen_intro_text(services, state, name)
        if intro:
            return ActResult(text=intro, cards=cards)
    return ActResult(text=render.render_reply(action, vehicle_name=name or None), cards=cards)


async def _chosen_intro_text(services: AgentServices, state: CoreState, name: str) -> str | None:
    """Một câu giới thiệu mẫu vừa chọn từ thông số catalog. `None` nếu không tra
    được (catalog lỗi / xe không trang) → `render_reply` dựng câu ngắn fallback.
    """
    service = services.vehicle_overview
    if service is None or not name:
        return None
    try:
        result = await service.answer(vehicle_name=name, session_id=state.session_id)
    except Exception:
        logger.warning("core.act: chosen_intro khong lay duoc thong so", exc_info=True)
        return None
    facts = list(result.lookup_facts) if result is not None else []
    if not facts:
        return None
    return render.chosen_intro(vehicle_name=name, specs=dict(facts[0].specs))


def vehicle_navigate(vehicle_id: str, vehicle_name: str) -> NavigateView:
    """`navigate.kind="vehicle"` — slug lấy từ CÙNG bảng với link "Xem thêm"."""

    return NavigateView(
        kind="vehicle",
        vehicle_id=str(vehicle_id),
        slug=page_slug_for_name(vehicle_name),
        path=page_path_for_name(vehicle_name),
        name=vehicle_name,
    )


def map_navigate(
    vehicle_id: str, card: TestDriveCardView | None, *, center: UserLocation | None, needs_location: bool = False
) -> NavigateView:
    """`navigate.kind="map"` — ghim từ thẻ lái thử, tâm là vị trí khách (nếu biết)."""

    showrooms = tuple(
        NavigateShowroomView(
            showroom_id=item.showroom_id,
            name=item.name,
            address=item.address,
            lat=item.lat,
            lng=item.lng,
            distance_km=item.distance_km,
        )
        for item in (card.showrooms if card is not None else ())
    )
    return NavigateView(
        kind="map",
        vehicle_id=str(vehicle_id),
        center=NavigateCenter(lat=center.latitude, lng=center.longitude) if center is not None else None,
        showrooms=showrooms,
        needs_location=needs_location,
    )


# --------------------------------------------------------------- tra cứu


async def _lookup(
    action: Lookup, state: CoreState, services: AgentServices, *, user_message: str, run_id: UUID | None = None
) -> ActResult:
    if action.mode == LOOKUP_POLICY:
        vehicle_id = action.vehicle_ids[0] if action.vehicle_ids else state.chosen_vehicle_id
        return await _policy_lookup(
            services,
            state,
            user_message=user_message,
            run_id=run_id,
            vehicle_id=vehicle_id,
        )
    if action.vehicle_ids and action.aspect == ASPECT_PRICE:
        priced = await _price_lookup(action.vehicle_ids[0], state, services)
        if priced is not None:
            return _with_vehicle_navigate(
                priced, action.vehicle_ids[0], await _name_of(services, state, action.vehicle_ids[0])
            )
    if action.vehicle_ids:
        # Lượt đã trỏ ra được MỘT chiếc thì câu trả lời phải nói về chiếc đó —
        # cùng cửa `vehicle_overview` mà `VehicleQa` dùng, nên hai đường không
        # bao giờ trả hai bộ số khác nhau cho cùng một xe. Không có dữ liệu thì
        # NÓI THẬT: lui về đổ danh mục là đúng lỗi prod vòng 8 (khách hỏi "VF 3
        # giá bao nhiêu" nhận về 27 ô tô + 7 xe máy).
        answered = await _vehicle_qa(
            VehicleQa(vehicle_id=action.vehicle_ids[0], question=user_message), state, services
        )
        return _with_vehicle_navigate(
            answered, action.vehicle_ids[0], await _name_of(services, state, action.vehicle_ids[0])
        )
    service = services.catalog_browse
    hint = _vehicle_type(state)
    result = None
    if service is not None:
        result = await service.answer(user_message=user_message, vehicle_type_hint=hint)
    if result is None or not result.answer.strip():
        # Chỉ số 5 của spec mục 8: KHÔNG lượt nào được đi ra không có tin nhắn.
        return ActResult(text=render.recommend_fallback(()))
    cards: dict[str, Any] = {}
    if result.pitches:
        cards["lookup_facts"] = []
    return ActResult(text=result.answer, cards=cards)


def _with_vehicle_navigate(result: ActResult, vehicle_id: str, name: str) -> ActResult:
    """Khách tra cứu ĐÚNG MỘT mẫu (tên xe kèm câu hỏi) → coi là vừa trỏ ra mẫu đó, dẫn sang trang xe."""

    if not name:
        return result
    return ActResult(
        text=result.text,
        cards={**result.cards, "navigate": vehicle_navigate(vehicle_id, name)},
        state_patch=result.state_patch,
        hitl_request=result.hitl_request,
    )


def _mention_vehicle_type(mention: str) -> str:
    """Loại xe suy từ TÊN khách nêu: "VF …" là ô tô, tên riêng khác là xe máy điện."""

    return VehicleType.CAR.value if mention.upper().startswith("VF") else VehicleType.ELECTRIC_MOTORBIKE.value


async def _not_in_catalog(action: NotInCatalog, state: CoreState, services: AgentServices) -> ActResult:
    """Tên xe không có trong danh mục → nói thật + bày danh mục đúng loại + treo chọn mẫu.

    Loại xe suy từ TÊN ("vf10" → ô tô) chứ không từ slot: khách hỏi "evo" giữa
    lúc đang xem ô tô thì danh mục xe máy mới là thứ họ cần thấy. Thẻ dựng từ
    cửa catalog tất định (`catalog_cards`), nút là TÊN xe (khách gõ lại vào cửa
    hiểu ý là trỏ được). `pending` treo của policy được điền `options`/`labels`
    ở đây để lượt sau "2" cũng trỏ được, và prompt của `understand` đọc được
    nhãn thay vì uuid.
    """

    vehicle_type = _mention_vehicle_type(action.mention)
    names = await catalog_names(services, vehicle_type=vehicle_type)
    ids = tuple(names)
    labels = tuple(names[vehicle_id] for vehicle_id in ids)
    text = render.not_in_catalog(mention=action.mention, vehicle_names=labels)
    cards: dict[str, Any] = {}
    views = await catalog_cards(services, state, ids, vehicle_type=vehicle_type)
    if views:
        cards["recommendations"] = views
    replies = [render.short_vehicle_name(label) for label in labels]
    replies = [item for item in dict.fromkeys(replies) if item][: render.MAX_CATALOG_NAMES_IN_TEXT]
    if replies:
        cards["quick_replies"] = [QuickReplyView(label=item, value=item) for item in replies]
    asked_at = state.pending.asked_at_turn if state.pending is not None else state.turn_count
    patch: dict[str, Any] = {
        "pending": Pending(
            kind=PendingKind.CHOICE, key=PENDING_VEHICLE, options=ids, labels=labels, asked_at_turn=asked_at
        )
    }
    if not _vehicle_type(state):
        # Tên xe đã nói ra loại xe; ghi lại để lượt đề xuất kế không phải suy từ ngân sách.
        patch["slots"] = {**state.slots, SlotName.VEHICLE_TYPE: vehicle_type}
    return ActResult(text=text, cards=cards, state_patch=patch)


async def _price_lookup(vehicle_id: str, state: CoreState, services: AgentServices) -> ActResult | None:
    """ "Giá <mẫu> bao nhiêu" → giá niêm yết trước, kèm ba nút đi tiếp. `None` khi không có giá.

    Prod benchmark2: câu hỏi giá nhận nguyên bảng thông số dài. Số đọc qua ĐÚNG
    cửa `_vehicle_spec` (cùng cửa lượt đối chiếu / câu dẫn đề xuất), nên giá ở
    đây không lệch với giá ở bất kỳ lượt nào khác. Không có giá thì trả `None`
    để chỗ gọi rơi về bảng tổng quan như cũ — thà dài còn hơn bịa.
    """

    name = await _name_of(services, state, vehicle_id)
    spec = await _vehicle_spec(services, state, vehicle_id, name)
    if spec is None or spec.price_vnd is None:
        return None
    service = services.vehicle_overview
    facts: list[Any] = []
    if service is not None and name:
        # `_vehicle_spec` vừa gọi cửa này; gọi lại để lấy `lookup_facts` nguyên
        # vẹn cho thẻ số liệu — rẻ (đọc catalog, không LLM) và giữ act không
        # phải mở một cửa dữ liệu thứ hai.
        try:
            result = await service.answer(vehicle_name=name, session_id=state.session_id)
            facts = list(getattr(result, "lookup_facts", ()) or ())
        except Exception:
            logger.warning("core.act: khong doc duoc lookup_facts cho cau tra loi gia", exc_info=True)
    replies = render.price_lookup_replies(name)
    cards: dict[str, Any] = {"lookup_facts": facts}
    if replies:
        cards["quick_replies"] = [QuickReplyView(label=item, value=item) for item in replies]
    return ActResult(text=render.price_lookup(vehicle_name=name, price_vnd=spec.price_vnd), cards=cards)


async def _policy_lookup(
    services: AgentServices,
    state: CoreState,
    *,
    user_message: str,
    run_id: UUID | None = None,
    vehicle_id: str | None = None,
) -> ActResult:
    """Câu hỏi chính sách (bảo hành, trả góp, đổi trả) — RAG tài liệu, KHÔNG danh mục xe.

    Bản bước 3 gửi `LOOKUP_POLICY` vào `catalog_browse` (món nợ I4).
    `catalog_browse` chỉ biết đọc bảng `vehicles` rồi render danh sách theo loại,
    nên "bảo hành mấy năm ạ?" nhận về một danh mục xe — sai một cách tự tin,
    đúng kiểu lỗi lõi v2 sinh ra để dẹp.

    Ở đây KHÔNG có gì để chép từ lõi cũ: lõi cũ cũng chưa nối đường chính sách
    (`turn_axes._NO_LEGACY_AUTHORITY` ghi thẳng "chính sách … chưa nối", còn
    `adapters/llm.synthesize_policy` tự khai "chưa có node nào gọi hàm này"). Nên
    đường này ghép đúng hai mảnh ĐANG CÓ mà chưa ai nối: `PolicySearchPort`
    (BM25 + vector, `adapters/policy_search.py`) tìm đoạn tài liệu, rồi
    `synthesis.synthesize_policy` viết câu CHỈ dựa trên các đoạn đó.

    Không có nguồn (chưa cắm port, chưa có tài liệu, hay tìm không ra đoạn nào)
    thì nói thật rồi mời tư vấn viên. Đặc biệt KHÔNG gọi tiếp với danh sách rỗng:
    `_fallback_policy_answer([])` của adapter cũ trả về đúng cái đầu đề "Theo tài
    liệu chính sách hiện có của VinFast:" cụt lủn.
    """

    chunks: list[dict] = []
    search = getattr(services, "policy_search", None)
    if search is not None and vehicle_id is None:
        return ActResult(text=render.policy_vehicle_clarification())
    if search is not None:
        try:
            chunks = list(
                await search.search(query=user_message, top_k=4, vehicle_id=vehicle_id) or []
            )
        except Exception:
            logger.warning("core.act: tim tai lieu chinh sach that bai", exc_info=True)
            chunks = []
    if not chunks:
        return _policy_to_advisor(state, run_id=run_id, user_message=user_message)
    synthesis = services.synthesis
    writer = getattr(synthesis, "synthesize_policy", None) if synthesis is not None else None
    if writer is None:
        return _policy_to_advisor(state, run_id=run_id, user_message=user_message)
    try:
        answer = (await writer(query=user_message, chunks=chunks) or "").strip()
    except Exception:
        logger.warning("core.act: viet cau tra loi chinh sach that bai", exc_info=True)
        answer = ""
    if not answer:
        return _policy_to_advisor(state, run_id=run_id, user_message=user_message)
    citations = _policy_citations(chunks)
    return ActResult(text=f"{answer}\n\n{citations}" if citations else answer)


def _policy_citations(chunks: list[dict]) -> str:
    """Append deterministic source URLs/revisions that synthesis cannot omit or invent."""
    sources: list[str] = []
    seen: set[tuple[str, str]] = set()
    for chunk in chunks:
        url = str(chunk.get("source_url") or "").strip()
        if not url:
            continue
        title = str(chunk.get("source_file") or "Tài liệu chính sách").strip()
        revision = str(chunk.get("source_revision") or "").strip()
        key = (url, revision)
        if key in seen:
            continue
        seen.add(key)
        label = f"{title} — bản {revision}" if revision else title
        sources.append(f"- [{label}]({url})")
    return "Nguồn chính thức:\n" + "\n".join(sources) if sources else ""


def _policy_to_advisor(state: CoreState, *, run_id: UUID | None, user_message: str) -> ActResult:
    """Không có tài liệu → CHUYỂN THẬT cho TVV, bot KHÔNG câm.

    Prod 2026-08-31 (phiên "thế còn bảo hành"): câu chỉ NÓI "mời tư vấn viên"
    nhưng không mục duyệt nào được tạo — TVV không biết, khách chờ vô vọng, còn
    phiên thì kẹt. Giờ đi đúng cơ chế ưu đãi: mục duyệt (nháp trả khách) +
    chặng OFFER_REVIEW — khách vẫn hỏi tiếp được trong lúc chờ.
    """

    text = render.policy_handoff_note()
    if run_id is None:
        return ActResult(text=text, state_patch={"stage": Stage.OFFER_REVIEW})
    request = AdvisorReviewRequest(
        run_id=run_id,
        content=render.policy_review_draft(user_message=user_message),
        snapshot=None,
    )
    return ActResult(text=text, state_patch={"stage": Stage.OFFER_REVIEW}, hitl_request=request)


async def _compare(action: Compare, state: CoreState, services: AgentServices, *, user_message: str) -> ActResult:
    names_by_id = await catalog_names(services, vehicle_type=_vehicle_type(state))
    names = [names_by_id[value] for value in action.vehicle_ids if value in names_by_id]
    service = services.compare_vehicles
    result = None
    if service is not None and names:
        result = await service.answer(user_message=user_message, vehicle_names=names)
    if result is None:
        return ActResult(text=render.no_fact(", ".join(names)))
    text = result.answer if not result.follow_up else f"{result.answer}\n\n{result.follow_up}"
    lead = _compare_fit_lead(state, result.comparison, user_message=user_message)
    if lead:
        # Dòng kết luận đứng TRƯỚC bảng: khách hỏi "cái nào hợp hơn" phải đọc
        # được câu trả lời ở dòng đầu, không phải tự xếp hạng hai cột số.
        text = f"{lead}\n\n{text}"
    return ActResult(text=text, cards={"comparison": result.comparison})


def _compare_fit_lead(state: CoreState, comparison: object, *, user_message: str = "") -> str:
    """Dòng "mẫu nào hợp nhu cầu hơn" dựng từ CHÍNH bảng vừa tra — không gọi thêm service.

    `VehicleComparisonView` đã chở đủ số của cả hai cột (`specs` cùng bộ tên cột
    với `VehicleFacts.specs`), nên không có lý do gì đọc catalog thêm một vòng.
    Nhu cầu chưa đủ để đối chiếu (`checked == 0`) thì IM LẶNG: một dòng "hai mẫu
    ngang nhau" dựng trên số không có thật còn tệ hơn không có dòng nào.
    """

    columns = [item for item in (getattr(comparison, "vehicles", ()) or ()) if getattr(item, "found", False)]
    if len(columns) < 2:
        return ""
    specs = [
        fit.build_spec(
            vehicle_id=str(getattr(column, "vehicle_id", "")),
            name=getattr(column, "display_name", "") or "",
            specs=dict(getattr(column, "specs", {}) or {}),
            price_vnd=getattr(column, "starting_price_vnd", None),
        )
        for column in columns
    ]
    need = fit.customer_need(state.slots, user_message=user_message)
    order = fit.compare_fit(specs, need)
    if not order or order[0][1].checked == 0:
        return ""
    (best, verdict), (other, _other_verdict) = order[0], order[1]
    # Thế "ngang nhau" hỏi thẳng `fit` bằng ĐÚNG khoá nó vừa xếp — chép lại khoá
    # ở đây là dựng nguồn sự thật thứ hai, và dòng kết luận sẽ nói ngược với thứ
    # tự ngay dưới nó (khách đi xa: 470 km và 326 km KHÔNG ngang nhau).
    tie = fit.tied(best, other, need)
    try:
        return render.compare_fit_lead(
            better_name=best.name, better_reasons=verdict.reasons, other_name=other.name, tie=tie
        )
    except render.RenderError:
        logger.warning("core.act: khong dung duoc dong ket luan so sanh theo nhu cau")
        return ""


def _merge_location_tool_args(
    kinds: tuple[LocationKind, ...],
    area: str | None,
    tool_args: LocationToolArgs | None,
) -> tuple[tuple[LocationKind, ...], str | None]:
    """Chỉ LẤP CHỖ TRỐNG: bộ dò từ khoá và slot tỉnh luôn thắng tham số LLM.

    Loại điểm LLM trả phải khớp đúng `LocationKind` — giá trị lạ bị vứt, không
    đoán; khu vực chỉ nhận khi hệ chưa biết gì về vị trí khách.
    """
    if tool_args is None:
        return kinds, area
    if not kinds and tool_args.kinds:
        valid = {member.value for member in LocationKind}
        kinds = tuple(LocationKind(value) for value in tool_args.kinds if value in valid)
    if area is None and tool_args.area and tool_args.area.strip():
        area = tool_args.area.strip()
    return kinds, area


def _location_tool_record(
    *,
    known_kinds: tuple[str, ...],
    known_area: str | None,
    tool_args: LocationToolArgs | None,
    kinds_after: tuple[LocationKind, ...],
    area_after: str | None,
) -> dict[str, Any]:
    """Một dòng vệt `payload["tool_calls"]` — cùng hình ba tầng với `tinh_chi_phi`."""
    return {
        "tool": LOCATION_TOOL_NAME,
        "known": {"kinds": list(known_kinds), "area": known_area},
        "returned": None
        if tool_args is None
        else {"kinds": list(tool_args.kinds), "area": tool_args.area},
        "used": {"kinds": [kind.value for kind in kinds_after], "area": area_after},
    }


async def _nearby(state: CoreState, services: AgentServices, *, user_message: str) -> ActResult:
    service = services.nearby_location
    kinds = detect_location_kinds(user_message)
    area = _province_text(state)
    tool_calls: tuple[dict[str, Any], ...] = ()
    # [Tool-calling] Bộ dò từ khoá chịu thua (không ra loại điểm) hoặc chưa biết
    # vị trí thì mới hỏi LLM — nó đọc "chỗ nào cắm điện được" ra CHARGING_STATION
    # và địa danh tự do. Hỏng/None thì đi tiếp đường cũ: hỏi loại bằng nút bấm.
    if services.location_arg_resolver is not None and (not kinds or area is None):
        known_kinds = tuple(kind.value for kind in kinds)
        known_area = area
        tool_args = await services.location_arg_resolver.resolve(
            user_message=user_message,
            known_kinds=known_kinds,
            known_area=known_area,
        )
        kinds, area = _merge_location_tool_args(kinds, area, tool_args)
        tool_calls = (
            _location_tool_record(
                known_kinds=known_kinds,
                known_area=known_area,
                tool_args=tool_args,
                kinds_after=kinds,
                area_after=area,
            ),
        )
    result = None
    if service is not None:
        result = await service.answer(
            user_message=user_message,
            location_kinds=kinds,
            location_text=area,
            assume_request=True,
        )
    if result is None:
        return ActResult(text=render.no_fact(""), tool_calls=tool_calls)
    return ActResult(
        text=result.answer,
        cards={"nearby_locations": result.locations, "quick_replies": list(result.quick_replies)},
        tool_calls=tool_calls,
    )


#: Trần số mẫu đem ra so khi xe đang xét chưa hợp. Mỗi mẫu tốn một lượt đọc
#: catalog; hai mẫu là đủ để nói "có mẫu khác hợp hơn", nhiều hơn là đọc lại cả
#: bản đề xuất trong một lượt khách chỉ hỏi một câu.
MAX_FIT_ALTERNATIVES = 2


def _facts_of(result: object, vehicle_id: str) -> Any | None:
    """`VehicleFacts` của ĐÚNG chiếc xe trong kết quả `vehicle_overview`.

    Cửa `answer` nhận TÊN nên một dòng xe nhiều phiên bản trả về nhiều hàng —
    lấy đúng id đang xét trước, không có thì lấy hàng đầu (bản mặc định của
    dòng đó, đúng thứ `catalog_browse` cũng bày ra).
    """

    items = [item for item in (getattr(result, "lookup_facts", ()) or ()) if item is not None]
    for item in items:
        if str(getattr(item, "vehicle_id", "")) == str(vehicle_id):
            return item
    return items[0] if items else None


async def _vehicle_spec(
    services: AgentServices, state: CoreState, vehicle_id: str, name: str
) -> fit.VehicleSpec | None:
    """Số của một chiếc xe cho lượt đối chiếu — CÙNG cửa `VehicleQa` đang dùng.

    Không mở cửa catalog thứ hai: hai cửa là hai bộ số cho cùng một chiếc xe,
    và khách sẽ đọc được cả hai trong cùng một phiên.
    """

    service = services.vehicle_overview
    if service is None or not name:
        return None
    try:
        result = await service.answer(vehicle_name=name, session_id=state.session_id)
    except Exception:
        logger.warning("core.act: khong doc duoc so lieu xe de doi chieu nhu cau", exc_info=True)
        return None
    facts = _facts_of(result, vehicle_id)
    if facts is None:
        return None
    return fit.build_spec(
        vehicle_id=vehicle_id,
        name=getattr(facts, "display_name", "") or name,
        specs=dict(getattr(facts, "specs", {}) or {}),
        price_vnd=getattr(facts, "starting_price_vnd", None),
    )


async def _fit_specs(
    services: AgentServices, state: CoreState, ids: Sequence[str], *, exclude: str
) -> list[fit.VehicleSpec]:
    names = await catalog_names(services, vehicle_type=_vehicle_type(state))
    specs: list[fit.VehicleSpec] = []
    for vehicle_id in dict.fromkeys(str(value) for value in ids):
        if vehicle_id == str(exclude) or len(specs) >= MAX_FIT_ALTERNATIVES:
            continue
        name = names.get(vehicle_id, "")
        spec = await _vehicle_spec(services, state, vehicle_id, name) if name else None
        if spec is not None:
            specs.append(spec)
    return specs


async def _fresh_candidates(services: AgentServices, state: CoreState, *, exclude: str) -> tuple[str, ...]:
    """Ứng viên theo tiêu chí MỚI của lượt này — cho ca khách vừa kể thêm nhu cầu.

    `recommended_ids` là bộ xe của bộ lọc CŨ. Khách vừa nói "gia đình 4 người,
    đi chơi xa" thì mẫu vá được chỗ thiếu có thể chưa từng nằm trong danh sách
    đó, và trả lời "em chưa có mẫu nào khác" lúc ấy là nói sai.
    """

    retrieval = services.retrieval
    if retrieval is None:
        return ()
    try:
        found = await retrieval.layer1(build_criteria(state))
    except Exception:
        logger.warning("core.act: khong loc duoc ung vien theo tieu chi moi", exc_info=True)
        return ()
    return tuple(value for item in found if (value := str(item)) != str(exclude))[:MAX_FIT_ALTERNATIVES]


async def _fit_check(
    action: FitCheck, state: CoreState, services: AgentServices, *, user_message: str = ""
) -> ActResult:
    """ "Xe này có hợp với nhu cầu của tôi không" — trả lời bằng SỐ, không bằng lời hứa.

    `user_message` đi cùng vì nhu cầu của lượt này có thể CHƯA kịp thành slot:
    lượt prod vòng 10 ("gia đình tôi có 4 người, tôi muốn sử dụng đi chơi xa")
    về slot chỉ có `seats=4`, và đọc mỗi slot thì kết luận là "hợp" trong khi xe
    chạy được 210 km. Xem `fit.customer_need`.
    """

    name = await _name_of(services, state, action.vehicle_id)
    spec = await _vehicle_spec(services, state, action.vehicle_id, name)
    if spec is None:
        return ActResult(text=render.no_fact(name))
    need = fit.customer_need(state.slots, user_message=user_message)
    assessment = fit.assess(spec, need)
    if assessment.verdict != FIT_YES:
        # Chỉ đi tìm mẫu thay thế khi có chỗ để vá: lượt "hợp" không tốn thêm
        # một vòng đọc catalog nào.
        assessment = await _fit_alternative(services, state, action, spec=spec, need=need, current=assessment)
    text = render.fit_assessment(
        vehicle_name=name or spec.name,
        verdict=assessment.verdict,
        reasons=assessment.reasons,
        alternative_name=assessment.alternative_name,
        just_chosen=action.just_chosen,
        closing=await _closing(services, state, vehicle_name=name or spec.name),
    )
    cards = await _kept_cards(state, services, (assessment.alternative_id,)) if assessment.alternative_id else {}
    if action.just_chosen and (name or spec.name):
        cards = {**cards, "navigate": vehicle_navigate(action.vehicle_id, name or spec.name)}
    return ActResult(text=text, cards=cards)


async def _fit_alternative(
    services: AgentServices,
    state: CoreState,
    action: FitCheck,
    *,
    spec: fit.VehicleSpec,
    need: fit.CustomerNeed,
    current: fit.FitAssessment,
) -> fit.FitAssessment:
    """Hai nguồn ứng viên, theo thứ tự: bộ đã đề xuất, rồi bộ lọc theo tiêu chí MỚI.

    Bộ đã đề xuất đứng trước vì khách đang nhìn thấy chúng trên màn hình; chỉ
    khi không mẫu nào trong đó vá được chỗ thiếu mới bỏ công lọc lại catalog.
    """

    seen = await _fit_specs(services, state, action.alternative_ids, exclude=spec.vehicle_id)
    if seen:
        found = fit.assess(spec, need, seen)
        if found.alternative_id:
            return found
    fresh_ids = await _fresh_candidates(services, state, exclude=spec.vehicle_id)
    fresh = await _fit_specs(services, state, fresh_ids, exclude=spec.vehicle_id)
    if not fresh:
        return current
    found = fit.assess(spec, need, fresh)
    return found if found.alternative_id else current


async def _next_steps(action: NextSteps, state: CoreState, services: AgentServices) -> ActResult:
    """Các bước để chốt xe. Nút đi kèm là hai bước ĐẦU — thứ khách bấm được ngay."""

    name = await _name_of(services, state, action.vehicle_id)
    return ActResult(
        text=render.next_steps(name),
        cards={"quick_replies": [QuickReplyView(label=item, value=item) for item in render.NEXT_STEP_REPLIES]},
    )


async def _scope_note(action: ScopeNote, state: CoreState, services: AgentServices) -> ActResult:
    """Câu hỏi ngoài phạm vi — nói thật, rồi trả về thứ lõi CÓ dữ liệu: tầm chạy.

    Đọc số qua đúng cửa `_vehicle_spec` (cùng cửa lượt đối chiếu nhu cầu dùng),
    nên con số trong câu từ chối này không bao giờ lệch với con số ở lượt trước.
    Không có số thì vẫn nói thật, chỉ bỏ phần tầm chạy.
    """

    name = await _name_of(services, state, action.vehicle_id)
    spec = await _vehicle_spec(services, state, action.vehicle_id, name)
    return ActResult(text=render.scope_note(vehicle_name=name, range_km=spec.range_km if spec is not None else None))


async def _vehicle_qa(action: VehicleQa, state: CoreState, services: AgentServices) -> ActResult:
    name = await _name_of(services, state, action.vehicle_id)
    service = services.vehicle_overview
    result = None
    if service is not None and name:
        result = await service.answer(vehicle_name=name, session_id=state.session_id)
    if result is None or not (result.answer or "").strip():
        return ActResult(text=render.no_fact(name))
    facts = list(result.lookup_facts)
    closing = await _closing(services, state, vehicle_name=name)
    tool_calls: tuple[dict[str, Any], ...] = ()
    if action.question and facts:
        # Câu hỏi MỘT thông số → trả đúng cột đó kèm ĐÁNH GIÁ; câu kết mời soi
        # tiếp về xe (Sếp 2026-08-31), không lái sang chi phí giữa mạch thắc mắc.
        pointed = render.spec_answer(
            vehicle_name=name, question=action.question, specs=dict(facts[0].specs), closing=render.qa_follow_up(name)
        )
        # [Tool-calling] Từ khoá chịu thua ("cốp nuốt nổi hai vali không?") thì
        # hỏi LLM xếp NHÓM — con số và lời đánh giá vẫn tất định từ catalog.
        # Hỏng/None/nhóm lạ → rơi về bảng tổng quan như cũ.
        if pointed is None and services.spec_arg_resolver is not None:
            tool_args = await services.spec_arg_resolver.resolve(question=action.question, vehicle_name=name)
            group_used = None
            if tool_args is not None and tool_args.group:
                pointed = render.spec_answer_by_group(
                    vehicle_name=name,
                    group=tool_args.group,
                    specs=dict(facts[0].specs),
                    closing=render.qa_follow_up(name),
                )
                group_used = tool_args.group if pointed else None
            tool_calls = (
                {
                    "tool": SPEC_TOOL_NAME,
                    "known": {"group": None},
                    "returned": None if tool_args is None else {"group": tool_args.group},
                    "used": {"group": group_used},
                },
            )
        if pointed:
            return ActResult(text=pointed, cards={"lookup_facts": facts}, tool_calls=tool_calls)
    # Bảng tổng quan là chữ của service cũ (không có câu kết); nối câu kết theo
    # checklist vào sau để lượt này cũng chỉ ra việc kế tiếp.
    return ActResult(text=f"{(result.answer or '').rstrip()}\n\n{closing}", cards={"lookup_facts": facts}, tool_calls=tool_calls)


# --------------------------------------------------------------- Task 2: nghiệp vụ


def _as_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


#: Ngân sách từ mức này trở xuống thì khách đang hỏi XE MÁY điện, không phải ô
#: tô: mẫu ô tô rẻ nhất của hãng vẫn trên 200 triệu, còn xe máy điện nằm gọn
#: dưới 100 triệu. Chốt ở 150 triệu để chừa khoảng đệm cho câu nói áng chừng.
MOTORBIKE_BUDGET_CEILING_VND = 150_000_000


def infer_vehicle_type(state: CoreState) -> VehicleType:
    """Loại xe cho bộ lọc: khách nói thì nghe, không nói thì SUY từ ngân sách.

    Luồng tư vấn chỉ hỏi MỘT câu (Sếp chốt 2026-08-29) nên `vehicle_type` hay
    trống. `FilterCriteria.vehicle_type` không nhận `None`, mà mặc định cứng
    `CAR` thì "anh có 40 triệu" nhận về một danh sách ô tô — vô nghĩa với khách
    và đúng kiểu sai mà lõi v2 sinh ra để dẹp.
    """

    raw = state.slots.get(SlotName.VEHICLE_TYPE)
    try:
        return VehicleType(str(raw))
    except ValueError:
        pass
    budget = _as_int(state.slots.get(SlotName.BUDGET_MAX_VND))
    if budget is not None and budget <= MOTORBIKE_BUDGET_CEILING_VND:
        return VehicleType.ELECTRIC_MOTORBIKE
    return VehicleType.CAR


#: Nhu cầu ĐI XA định tính → ngưỡng tầm-chạy tối thiểu định lượng. 300 km loại
#: nhóm đô thị (VF 2/3 ~210 km), giữ VF 5 trở lên. Bug Sếp thấy prod 2026-08-31:
#: "xe 200tr đi xa" → bot pitch VF 2 (210 km) "hợp đi xa" — khớp ngân sách mà mù
#: nhu cầu. Ngưỡng này để layer1 loại xe không đủ tầm; ngân sách thấp thì
#: `_relaxed_candidates` tự nới rồi `relax_lead` NÓI THẲNG (Sếp: không từ chối
#: cụt, nới ngân sách để giữ cơ hội bán).
LONG_DISTANCE_RANGE_KM: Final = int(LONG_TRIP_MIN_RANGE_KM)

#: Ngân sách dưới tỉ lệ này của giá sàn RẺ NHẤT toàn danh mục (mọi loại xe) thì
#: bậc "gần giá nhất" hết nghĩa — 5 triệu vs sàn 12 triệu là hỏi lại, không gợi ý.
BUDGET_HOPELESS_RATIO: Final = Decimal("0.5")

#: Chữ báo hiệu đi đường dài — HẸP, chỉ cụm bỏ ngữ cảnh vẫn đúng.
_LONG_DISTANCE = re.compile(r"đi xa|đường dài|đi tỉnh|liên tỉnh|phượt|du lịch xa|chạy tỉnh|đường trường")


def _wants_long_range(state: CoreState) -> bool:
    """Khách có nêu nhu cầu đi xa không — đọc từ purpose + chữ nhu cầu tự do."""
    return any(_LONG_DISTANCE.search(phrase.casefold()) for phrase in customer_wording(state))


def build_criteria(state: CoreState) -> FilterCriteria:
    """Bộ lọc Lớp 1 cho lượt đề xuất. **`vehicle_type` luôn được ép vào.**

    Bug thật đã đo trên prod: khách 700 triệu, gia đình 5 người, hệ trả xe máy
    Theon S. Nguyên nhân là scoring chạy trên tập ứng viên KHÔNG khoá loại xe.
    Slot còn trống thì `infer_vehicle_type` suy từ ngân sách — thà lệch một lượt
    còn hơn đổ cả danh mục hai loại.
    """

    vehicle_type = infer_vehicle_type(state)
    budget_max = state.slots.get(SlotName.BUDGET_MAX_VND)
    budget_min = state.slots.get(SlotName.BUDGET_MIN_VND)
    required_range = _as_int(state.slots.get(SlotName.REQUIRED_RANGE_KM))
    # Nhu cầu "đi xa" mà khách chưa nêu số km → ép ngưỡng tối thiểu, CHỈ cho ô
    # tô (xe máy điện không phải phương án đường dài; ngưỡng 300 km loại sạch
    # danh mục xe máy thì nới thành vô nghĩa).
    if required_range is None and vehicle_type is VehicleType.CAR and _wants_long_range(state):
        required_range = LONG_DISTANCE_RANGE_KM
    return FilterCriteria(
        vehicle_type=vehicle_type,
        # `Decimal` CHỈ sống trong contract này, không bao giờ quay lại `slots`.
        budget_max_vnd=Decimal(str(int(budget_max))) if _as_int(budget_max) else None,
        budget_min_vnd=Decimal(str(int(budget_min))) if _as_int(budget_min) else None,
        passenger_count=_as_int(state.slots.get(SlotName.PASSENGER_COUNT)),
        required_range_km=required_range,
    )


def _feature_codes(state: CoreState) -> list[str]:
    value = state.slots.get(FEATURE_SLOT)
    return [str(item) for item in value] if isinstance(value, list) else []


def customer_wording(state: CoreState) -> list[str]:
    """Chữ khách tự nói về NHU CẦU, đúng như `nodes/synthesize._customer_wording`.

    Đây là thứ làm bài đề xuất nói được "bảy chỗ nên hợp việc đưa đón con" thay
    vì đọc thông số suông: `synthesis` nhét khối này vào prompt để mỗi tính năng
    được diễn giải theo việc khách vừa kể. Bỏ nó đi (bản bước 3) là bài viết ra
    đúng, đủ số, nhưng không dính gì tới người đang đọc.

    Mã tính năng được ĐỔI RA NHÃN trước khi vào đây: `render.feature_label` dịch
    được thì lấy nhãn, không thì bỏ hẳn mã — mã thô trong prompt là mời LLM chép
    "ADAS" nguyên văn ra câu trả lời (đúng lỗi đã lộ 80 lần trên prod).
    """

    wording: list[str] = []
    purpose = state.slots.get(SlotName.PURPOSE)
    if isinstance(purpose, str) and purpose.strip() and not purpose.startswith("__"):
        wording.append(purpose.strip())
    for code in _feature_codes(state):
        label = render.feature_label(code)
        if label:
            wording.append(label)
    return list(dict.fromkeys(wording))


async def catalog_prices(services: AgentServices, *, vehicle_type: str | None) -> dict[str, Decimal]:
    """`vehicle_id` → giá khởi điểm, đọc từ CÙNG cửa catalog tất định `catalog_names`.

    Cần cho lượt "cho em mẫu rẻ hơn": trần mới là NGAY DƯỚI chiếc rẻ nhất khách
    vừa xem (`domain/comparative_revision.budget_ceiling_below_seen` chốt như
    vậy — mọi con số kiểu "hạ 10%" đều là số bịa). Không có giá thì không hạ
    trần, và lượt vẫn chạy như một lần xin mẫu khác bình thường.
    """

    service = services.catalog_browse
    if service is None:
        return {}
    try:
        result = await service.answer(user_message="", vehicle_type_hint=vehicle_type)
    except Exception:
        logger.warning("core.act: khong doc duoc gia tu catalog", exc_info=True)
        return {}
    if result is None:
        return {}
    prices: dict[str, Decimal] = {}
    for pitch in result.pitches:
        raw = getattr(pitch, "starting_price_vnd", None)
        value = _decimal_of(raw) if raw is not None else None
        if value is not None:
            prices[str(pitch.vehicle_id)] = value
    return prices


def _budget_relaxed(state: CoreState, criteria: FilterCriteria) -> bool:
    """Lượt này có cố ý đi QUÁ trần ngân sách khách đã nêu không.

    `recommendation.recommend` xếp hạng trên snapshot nhưng vẫn đọc ngân sách từ
    `conversation_slots` và LOẠI mọi mẫu vượt trần (`scoring._is_unlabelled_over_budget`).
    Nên hai đường đã nới trần ở Lớp 1 — khách xin xe đắt hơn, và bậc thang tự nới
    khi lọc chặt ra rỗng — đều bị chính bộ xếp hạng loại sạch kết quả, và lượt
    rơi về "em chưa có mẫu nào khác hợp hơn" kèm y nguyên thẻ cũ (đo trên máy
    2026-09-23: hai lượt "đắt hơn" liên tiếp).

    So TRẦN CỦA LƯỢT với trần trong slot: cao hơn (hoặc đã bỏ) nghĩa là lượt này
    cố ý vượt, và bộ xếp hạng phải biết. Lượt xin RẺ hơn siết trần xuống nên
    không lọt vào đây.
    """

    slot_budget = _as_int(state.slots.get(SlotName.BUDGET_MAX_VND))
    if not slot_budget:
        return False
    return criteria.budget_max_vnd is None or Decimal(slot_budget) < criteria.budget_max_vnd


async def _refined(
    services: AgentServices, state: CoreState, *, criteria: FilterCriteria, refine: str, seen_ids: Sequence[str]
) -> tuple[FilterCriteria, ComparativeRevision | None]:
    """Đọc lời xin chỉnh và siết lại bộ lọc theo đúng hướng khách vừa nêu.

    Dùng LẠI `domain/comparative_revision` của lõi cũ thay vì viết bộ đọc thứ
    hai: nó đã nối sẵn vào hai bảng từ vựng đang chạy (28 mã tính năng, 4 cảm
    quan), nên "cốp rộng hơn" / "gầm cao hơn" chạy mà không có dòng nào viết
    riêng. Đọc không ra hướng vẫn là một lời xin đổi HỢP LỆ — lượt vẫn chạy và
    vẫn loại những mẫu khách vừa xem.
    """

    revision = detect_comparative_revision(build_canonical_text(refine))
    if revision is None or not (revision.cheaper or revision.pricier):
        return criteria, revision
    prices = await catalog_prices(services, vehicle_type=str(criteria.vehicle_type))
    seen = [prices[value] for value in seen_ids if value in prices]
    if not seen:
        return criteria, revision
    if revision.pricier:
        # Khách XIN xe đắt hơn: sàn mới là trên giá mẫu đắt nhất vừa xem, và
        # trần ngân sách cũ phải BỎ — chính khách vừa nới nó. Giữ trần cũ là
        # bảo đảm không còn mẫu nào lọt, tức lượt nào cũng ra "chưa có mẫu nào
        # khác hợp hơn" kèm y nguyên hai thẻ cũ (đo trên máy 2026-09-23).
        return replace(criteria, budget_min_vnd=max(seen) + 1, budget_max_vnd=None), revision
    ceiling = min(seen) - 1
    if criteria.budget_max_vnd is not None and criteria.budget_max_vnd <= ceiling:
        return criteria, revision
    return replace(criteria, budget_max_vnd=ceiling), revision


async def catalog_cards(
    services: AgentServices, state: CoreState, ids: Sequence[str], *, vehicle_type: str | None = None
) -> list[RecommendedVehicleView]:
    """Thẻ xe cho một danh sách id ĐÃ đề xuất, đọc từ cửa catalog tất định.

    Lượt prod LP15/16/19/31: câu "em vẫn thấy VF 3 hợp nhất…" đi ra với
    `recommendations=[]`, nên khách chỉ còn CHỮ trên màn hình — thẻ của lượt
    trước đã cuộn đi. Lượt đó không có bài mới để viết, nhưng vẫn phải có thẻ:
    đó là thứ khách bấm để đi tiếp.

    Dùng LẠI `catalog_browse` (cùng cửa `catalog_names`/`catalog_prices`): nó
    trả sẵn tên, giá và một đoạn giới thiệu đã kiểm chứng ở tầng dưới, nên
    không phải gọi `synthesis` lần nữa để dựng lại đúng bộ thẻ vừa gửi. Id
    không có trong catalog thì BỎ hẳn thẻ đó — thẻ rỗng tên là thẻ không bấm
    được.
    """

    service = services.catalog_browse
    if service is None:
        return []
    try:
        # `vehicle_type` ĐÈ slot: loại xe của lượt đề xuất có thể là loại SUY ra
        # từ ngân sách (`infer_vehicle_type`) khi khách chưa nói. Hỏi catalog
        # theo slot rỗng thì nó trả danh sách ô tô, không id nào khớp, và lượt
        # xe máy đi ra KHÔNG CÓ THẺ NÀO.
        result = await service.answer(user_message="", vehicle_type_hint=vehicle_type or _vehicle_type(state))
    except Exception:
        logger.warning("core.act: khong dung duoc the xe tu catalog", exc_info=True)
        return []
    if result is None:
        return []
    by_id = {str(pitch.vehicle_id): pitch for pitch in result.pitches}
    images = await _image_urls(services, [pitch.vehicle_id for pitch in result.pitches])
    views: list[RecommendedVehicleView] = []
    for vehicle_id in ids:
        pitch = by_id.get(str(vehicle_id))
        if pitch is None:
            continue
        views.append(
            RecommendedVehicleView(
                vehicle_id=pitch.vehicle_id,
                rank=len(views) + 1,
                display_name=pitch.display_name,
                image_url=images.get(pitch.vehicle_id),
                starting_price_vnd=pitch.starting_price_vnd,
                pitch=pitch.pitch,
            )
        )
    return views


async def _kept_cards(state: CoreState, services: AgentServices, ids: Sequence[str]) -> dict[str, Any]:
    views = await catalog_cards(services, state, ids)
    return {"recommendations": views} if views else {}


async def _no_better(state: CoreState, services: AgentServices) -> ActResult:
    """Đã chỉnh theo yêu cầu nhưng không còn mẫu nào hợp hơn — nói thật, GIỮ thẻ."""

    vehicle_id = state.recommended_ids[0] if state.recommended_ids else state.chosen_vehicle_id
    name = await _name_of(services, state, vehicle_id)
    return ActResult(
        text=render.render_reply(Reply(template=TEMPLATE_NO_BETTER), vehicle_name=name or None),
        cards=await _kept_cards(state, services, state.recommended_ids),
    )


async def _same_pick(state: CoreState, services: AgentServices, *, ids: tuple[str, ...] | None = None) -> ActResult:
    """Không có mẫu nào MỚI để nói: một câu ngắn về lựa chọn cũ, không đọc lại bài.

    Hai lối vào: (a) `reason=retry` mà lọc hết ứng viên, (b) chạy xong lại ra
    đúng bộ xe cũ. Cả hai đều KHÔNG được trả `recommend_fallback(())` ("chưa tìm
    được mẫu nào khớp"): lõi vừa tìm ra ba mẫu và khách đang đọc chúng.

    Chữ ngắn nhưng THẺ vẫn đủ: `recommendations` rỗng ở đây là lượt prod
    LP15/16/19/31 — màn hình khách chỉ còn một dòng chữ, không còn gì để bấm.
    """

    vehicle_id = state.chosen_vehicle_id or (state.recommended_ids[0] if state.recommended_ids else None)
    name = await _name_of(services, state, vehicle_id)
    shown = ids if ids is not None else state.recommended_ids
    closing = await _closing(services, state.with_(recommended_ids=shown), vehicle_name=name)
    text = render.render_reply(Reply(template=TEMPLATE_SAME_PICK), vehicle_name=name or None, closing=closing)
    cards = await _kept_cards(state, services, shown)
    if state.chosen_vehicle_id and name:
        # Khách đã chốt mẫu này và lõi xác nhận không có mẫu mới → dẫn sang trang xe.
        cards["navigate"] = vehicle_navigate(state.chosen_vehicle_id, name)
    return ActResult(
        text=text,
        cards=cards,
        state_patch={"recommended_ids": ids} if ids is not None else {},
    )


#: Hai mức nới ngân sách, theo đúng thứ tự Sếp chốt 2026-08-29 (+20% rồi +40%).
#: KHÔNG dùng `candidate_tuning.relax`: bậc thang của nó (+10%, +20%, bỏ tầm
#: hoạt động, bỏ ngân sách) không có bậc BỎ SỐ CHỖ — mà đúng số chỗ mới là thứ
#: chặn lượt prod LP18 ("300 triệu, 5 người"), và nó ném lỗi khi hết bậc.
RELAX_BUDGET_MULTIPLIERS: tuple[Decimal, ...] = (Decimal("1.2"), Decimal("1.4"))


def _relax_ladder(criteria: FilterCriteria) -> list[tuple[FilterCriteria, str]]:
    """Các bậc nới TÍCH LUỸ, mỗi bậc kèm mã để `render` viết câu.

    Loại xe KHÔNG bao giờ được nới: khách hỏi xe máy mà nhận về ô tô thì không
    phải nới tiêu chí, mà là trả lời sai câu hỏi.
    """

    base = criteria.budget_max_vnd
    current = criteria
    steps: list[tuple[FilterCriteria, str]] = []
    if base is not None:
        for multiplier in RELAX_BUDGET_MULTIPLIERS:
            widened = (base * multiplier).to_integral_value(rounding=ROUND_HALF_UP)
            current = replace(current, budget_max_vnd=widened, budget_min_vnd=None)
            steps.append((current, render.RELAX_BUDGET))
    if criteria.passenger_count is not None:
        current = replace(current, passenger_count=None)
        steps.append((current, render.RELAX_SEATS))
    if current.required_range_km is not None:
        # Bỏ TẦM CHẠY nhưng GIỮ ngân sách trước khi bỏ tất (Sếp 2026-08-31):
        # khách "200 triệu + đi xa" được xem mẫu gần túi tiền kèm câu nói thẳng
        # thiếu tầm (render.RELAX_RANGE), thay vì nhận mẫu đắt gấp đôi và một
        # câu "bỏ bớt các tiêu chí phụ" không nói bỏ cái gì.
        current = replace(current, required_range_km=None)
        steps.append((current, render.RELAX_RANGE))
    if current.budget_max_vnd is not None:
        current = replace(current, budget_max_vnd=None, budget_min_vnd=None)
        steps.append((current, render.RELAX_OTHER))
    return steps


async def _relaxed_candidates(
    services: AgentServices, criteria: FilterCriteria, *, excluded: set[str]
) -> tuple[FilterCriteria, list[UUID], tuple[str, ...]]:
    """Nới dần cho tới khi Lớp 1 ra được ứng viên. Luôn có đề xuất (Sếp chốt).

    Trả về bộ lọc CUỐI đã dùng, ứng viên tìm được, và các bậc đã nới — `render`
    cần cả ba để nói ra đúng việc lõi vừa làm.
    """

    relaxed: list[str] = []
    current = criteria
    retrieval = services.retrieval
    if retrieval is None:
        return criteria, [], ()
    for step, code in _relax_ladder(criteria):
        current = step
        relaxed.append(code)
        found = [value for value in await retrieval.layer1(current) if str(value) not in excluded]
        if found:
            return current, found, tuple(relaxed)
    return current, [], tuple(relaxed)


async def _nearest_by_price(services: AgentServices, state: CoreState, criteria: FilterCriteria) -> ActResult:
    """Bậc CUỐI: hai mẫu gần giá nhất của đúng loại xe, đọc từ catalog tất định.

    Không có giá nào để so (catalog hỏng, loại xe lạ) thì mới quay về câu cũ —
    nói thật còn hơn bịa một danh sách.
    """

    prices = await catalog_prices(services, vehicle_type=str(criteria.vehicle_type))
    names = await catalog_names(services, vehicle_type=str(criteria.vehicle_type))
    priced = [(vehicle_id, price) for vehicle_id, price in prices.items() if names.get(vehicle_id)]
    if not priced:
        return ActResult(text=render.recommend_fallback(()))
    budget = _as_int(state.slots.get(SlotName.BUDGET_MAX_VND))
    if budget:
        # Ngân sách dưới hẳn sàn MỌI loại (Sếp 2026-08-31: "5 củ" nhận VF 2
        # 188 triệu): "gần giá nhất" hết nghĩa, nói thật sàn hai loại + hỏi lại.
        # Đọc giá sàn loại còn lại qua CÙNG cửa catalog; đọc hỏng thì bỏ qua
        # ngưỡng chứ không chặn đường gợi ý.
        floors: dict[str, Decimal] = {}
        for type_name in ("ELECTRIC_MOTORBIKE", "CAR"):
            type_prices = (
                prices if type_name == str(criteria.vehicle_type) else await catalog_prices(services, vehicle_type=type_name)
            )
            if type_prices:
                floors[type_name] = min(type_prices.values())
        if floors and Decimal(budget) < min(floors.values()) * BUDGET_HOPELESS_RATIO:
            return ActResult(
                text=render.budget_below_any_floor(
                    budget_vnd=budget,
                    motorbike_floor_vnd=floors.get("ELECTRIC_MOTORBIKE"),
                    car_floor_vnd=floors.get("CAR"),
                )
            )
    target = Decimal(str(budget)) if budget else min(price for _, price in priced)
    nearest = sorted(priced, key=lambda item: (abs(item[1] - target), item[1]))[:2]
    text = render.nearest_by_price(
        [(names[vehicle_id], render.format_number(float(price), "đ")) for vehicle_id, price in nearest]
    )
    # Hai mẫu này là bản đề xuất của lượt — nên vừa có THẺ để bấm, vừa được ghi
    # vào `recommended_ids`. Chỉ có chữ thì khách không bấm được gì; có thẻ mà
    # không ghi danh sách thì lượt sau `_pick_vehicle` không tra ra chúng và lõi
    # hỏi lại "muốn xem mẫu nào".
    ids = tuple(vehicle_id for vehicle_id, _ in nearest)
    views = await catalog_cards(services, state, ids, vehicle_type=str(criteria.vehicle_type))
    if not views:
        return ActResult(text=text)
    return ActResult(text=text, cards={"recommendations": views}, state_patch={"recommended_ids": ids})


async def _dead_end(
    state: CoreState,
    services: AgentServices,
    *,
    criteria: FilterCriteria,
    retrying: bool,
    refine: str,
    ids: tuple[str, ...] | None = None,
    run_id: UUID | None,
    customer_id: str,
    user_message: str,
    transcript: Sequence[Any] = (),
) -> ActResult:
    """MÓC 2 (plan agent-migration §1.3): ba ngõ cụt của `_recommend`.

    Thử agent trước; `None` thì gọi ĐÚNG nhánh cũ (`_no_better` / `_same_pick` /
    `_nearest_by_price`) với đúng tham số cũ — nên cờ OFF cho ra từng ký tự y
    như hôm nay.

    Điểm gọi đầu tiên (`candidates` rỗng) xảy ra TRƯỚC `snapshotting.snapshot`
    của `_recommend`, nên `_open_question` tự snapshot lấy — nếu không thì
    `verify` từ chối mọi con số (§0.2 của plan).
    """

    agent = await _open_question_or_none(
        OpenQuestion(
            question=refine or user_message,
            reason=OPEN_REASON_DEAD_END,
            vehicle_ids=tuple(ids or state.recommended_ids),
        ),
        state,
        services,
        run_id=run_id,
        customer_id=customer_id,
        user_message=user_message,
        transcript=transcript,
    )
    if agent is not None:
        return agent
    if ids is not None:
        return await _same_pick(state, services, ids=ids)
    if refine:
        return await _no_better(state, services)
    if retrying:
        return await _same_pick(state, services)
    return await _nearest_by_price(services, state, criteria)


async def _recommend(
    action: Recommend,
    state: CoreState,
    services: AgentServices,
    *,
    run_id: UUID | None,
    user_message: str,
    customer_id: str = "",
    transcript: Sequence[Any] = (),
) -> ActResult:
    """`retrieval → snapshotting → recommendation → synthesis → verification`.

    Đây là MỘT use case của lõi cũ, chỉ là lõi cũ rải nó qua 5 node. `act` gọi
    lại đúng thứ tự đó, không thêm cửa nào.
    """

    if run_id is None or services.retrieval is None or services.recommendation is None:
        return ActResult(text=render.recommend_fallback(()))
    #: Lượt đề xuất LẠI mà lõi vẫn còn một lựa chọn cũ để nói tới. Khác lượt đầu
    #: ở chỗ câu "chưa tìm được mẫu nào khớp" là một câu SAI: vừa tìm ra xong.
    retrying = action.reason == REASON_RETRY and bool(state.recommended_ids or state.chosen_vehicle_id)
    criteria = build_criteria(state)
    revision: ComparativeRevision | None = None
    if action.refine:
        criteria, revision = await _refined(
            services, state, criteria=criteria, refine=action.refine, seen_ids=action.exclude_ids
        )
    candidates = await services.retrieval.layer1(criteria)
    excluded = {str(value) for value in action.exclude_ids}
    candidates = [value for value in candidates if str(value) not in excluded]
    if revision is not None and revision.pricier and criteria.budget_min_vnd is not None:
        # `catalog_reader.hard_filter` CHỈ đọc `budget_max_vnd` — sàn trong
        # `FilterCriteria` không có ai thi hành. Không chặn ở đây thì lượt "đắt
        # hơn" lần hai trả về đúng mấy mẫu RẺ mà khách vừa bỏ qua ở lượt trước
        # (đo trên máy 2026-09-23: VF 9/VF 8 xong lại rơi về VF 3/VF 2).
        #
        # Chặn tại đây chứ không sửa `hard_filter`: sàn ở tầng SQL sẽ đổi luôn
        # hành vi của lượt khách nêu KHOẢNG ("từ 400 đến 600 triệu"), mà khoảng
        # đó đang cố ý được xử lý mềm ở `scoring._prefer_budget_band` (hết mẫu
        # trong biên thì trả lại thứ có, không trả rỗng).
        floor_prices = await catalog_prices(services, vehicle_type=str(criteria.vehicle_type))
        candidates = [
            value
            for value in candidates
            if (price := floor_prices.get(str(value))) is not None and price >= criteria.budget_min_vnd
        ]
    relaxed: tuple[str, ...] = ()
    if not candidates and not action.refine and not retrying:
        # Bộ lọc chặt ra rỗng: TỰ nới rồi nói ra, không đẩy việc nới sang khách
        # ("anh/chị nới ngân sách giúp em" là chỗ hai lượt prod chết hẳn).
        budget_before = criteria.budget_max_vnd
        range_before = criteria.required_range_km
        criteria, candidates, relaxed = await _relaxed_candidates(services, criteria, excluded=excluded)
        lead = render.relax_lead(
            relaxed,
            budget_vnd=budget_before,
            widened_vnd=criteria.budget_max_vnd,
            passenger_count=_as_int(state.slots.get(SlotName.PASSENGER_COUNT)),
            required_range_km=range_before,
        )
    else:
        lead = ""
    if action.switched_type:
        # Câu chuyển loại đứng TRƯỚC mọi câu dẫn khác: đó là việc khách vừa xin.
        lead = "\n".join(part for part in (render.type_switch_lead(action.switched_type), lead) if part)
    if not candidates:
        # Đã siết đúng hướng khách xin mà không còn mẫu nào: câu "chưa tìm được
        # mẫu nào khớp tiêu chí" nghe như lỗi hệ thống, trong khi sự thật là
        # "không có mẫu nào rẻ hơn/rộng hơn nữa".
        return await _dead_end(
            state,
            services,
            criteria=criteria,
            retrying=retrying,
            refine=action.refine,
            run_id=run_id,
            customer_id=customer_id,
            user_message=user_message,
            transcript=transcript,
        )
    assertions = await services.retrieval.layer2(
        utterance=user_message, vehicle_type=str(criteria.vehicle_type), candidate_ids=candidates
    )
    if services.snapshotting is not None:
        await services.snapshotting.snapshot(run_id=run_id, candidate_ids=candidates, assertions=assertions)
    features = _feature_codes(state)
    traits: tuple[str, ...] = ()
    if revision is not None:
        # Mã tính năng đọc được đẩy vào bảng chấm điểm; mã cảm quan ("cốp rộng",
        # "gầm cao") đi đường `preferred_trait_codes` — đúng hai cửa mà
        # `RecommendationService.recommend` đã mở sẵn.
        features = list(dict.fromkeys([*features, *revision.feature_codes]))
        traits = revision.trait_codes
    vehicle_type_value = str(criteria.vehicle_type)
    try:
        recommendations = await services.recommendation.recommend(
            run_id,
            customer_asked_feature_codes=features,
            preferred_trait_codes=traits,
            vehicle_type=vehicle_type_value,
            budget_relaxed=_budget_relaxed(state, criteria),
        )
    except ValueError:
        # Bug prod 15:20:30: `_profile_from_slots` (services/recommendation.py:234)
        # ném khi slot đã chốt trong `conversation_slots` chưa có VEHICLE_TYPE —
        # dù tham số `vehicle_type` ở trên đã bịt đúng lỗ này, giữ lưới an toàn
        # cho mọi lỗi ValueError khác của cùng dịch vụ (không log câu khách,
        # chỉ log slot để soi lại được lượt hỏng).
        logger.warning(
            "core.act: recommendation.recommend loi (vehicle_type=%s), hoi lai loai xe. slots=%s",
            vehicle_type_value,
            dict(state.slots),
            exc_info=True,
        )
        return await _ask(Ask(key="vehicle_type", kind=PendingKind.SLOT), state, services, user_message=user_message)
    # `RecommendationService.recommend` KHÔNG có tham số loại trừ (services/
    # recommendation.py:84) — nó xếp hạng trên snapshot, mà snapshot đã dựng từ
    # `candidates` đã lọc, nên lần lọc này chỉ là lưới thứ hai cho những cài đặt
    # đọc rộng hơn snapshot của chính run này.
    recommendations = [item for item in recommendations if str(item.vehicle_id) not in excluded]
    if not recommendations:
        return await _dead_end(
            state,
            services,
            criteria=criteria,
            retrying=retrying,
            refine=action.refine,
            run_id=run_id,
            customer_id=customer_id,
            user_message=user_message,
            transcript=transcript,
        )
    ids = tuple(str(item.vehicle_id) for item in recommendations)
    if state.recommended_ids and ids == state.recommended_ids:
        # Cùng bộ xe → cùng bài chữ. Đọc lại nguyên văn bài khách vừa đọc là
        # đúng chỉ số "lặp bài" (spec mục 8) — nói ngắn và mở đường đi tiếp.
        return await _dead_end(
            state,
            services,
            criteria=criteria,
            retrying=retrying,
            refine=action.refine,
            ids=ids,
            run_id=run_id,
            customer_id=customer_id,
            user_message=user_message,
            transcript=transcript,
        )

    text, views = await _pitch_text(
        services,
        run_id=run_id,
        recommendations=recommendations,
        state=state,
        features=features,
        vehicle_type=vehicle_type_value,
    )
    if lead:
        # Câu nói-ra-đã-nới-gì đứng TRƯỚC bài: khách 300 triệu nhận về mẫu 420
        # triệu phải đọc lý do ở dòng đầu, không phải tự đoán giữa bài.
        text = f"{lead}\n\n{text}"
    patch: dict[str, Any] = {"recommended_ids": ids}
    if state.slots.get(SlotName.VEHICLE_TYPE) != vehicle_type_value:
        # Slot vừa SUY (không phải khách nói) — ghi lại để lượt sau đọc
        # `conversation_slots` ra cùng loại xe, không lặp lại đúng lỗ hổng vừa vá.
        patch["slots"] = {**state.slots, SlotName.VEHICLE_TYPE: vehicle_type_value}
    pending = await _feature_pending(state, services, candidates=candidates)
    if pending is not None:
        patch["pending"] = pending
    return ActResult(text=text, cards={"recommendations": views}, state_patch=patch)


#: Hai kết quả cổng thương mại cho phép chữ đi tới khách (`domain/quote_risk`).
_DELIVERABLE: Final[frozenset[DeliveryAction]] = frozenset(
    {DeliveryAction.AUTO_DELIVER, DeliveryAction.DELIVER_WITH_AUDIT}
)


async def _commercial_guard(text: str, state: CoreState, services: AgentServices) -> bool:
    """Cửa CAM KẾT THƯƠNG MẠI cho chữ bot sắp gửi. `True` = đi thẳng.

    `services.quote_gate is None` → `True`: đường hôm nay y nguyên, và đó cũng
    là nút lùi khi cổng chặn nhầm trên prod (đặt `quote_gate=None` ở
    `composition.py`, không cần revert code). Có cổng thì đọc bảng khuyến mãi
    chuẩn từ chính cấu hình của nó, rồi giao cho luật thuần
    `quote_risk.classify_draft_delivery` — KHÔNG gọi `quote_gate.evaluate`:
    hàm đó cần `canonical`/`session_id` của lượt, ép HITL theo ý định khách
    (TCO, xin gặp người) và ghi audit — cả ba đều không phải việc của `act`.
    """

    gate = services.quote_gate
    if gate is None:
        return True
    config = getattr(gate, "config", None)
    promotions = getattr(config, "standard_promotions", None)
    decision = classify_draft_delivery(
        text,
        facts_verified=True,
        **({"standard_promotions": frozenset(promotions)} if promotions is not None else {}),
    )
    if decision.action in _DELIVERABLE:
        return True
    logger.info("core.act: quote_gate chan chu bot stage=%s reasons=%s", state.stage.value, ",".join(decision.reasons))
    return False


async def _pitch_text(
    services: AgentServices,
    *,
    run_id: UUID,
    recommendations: Sequence[Recommendation],
    state: CoreState,
    features: Sequence[str],
    vehicle_type: str | None = None,
) -> tuple[str, list[RecommendedVehicleView]]:
    """Bài đề xuất đã kiểm chứng, hoặc đường dự phòng TẤT ĐỊNH.

    Spec mục 7: synthesis/verify hỏng thì trả `render.recommend_fallback` (tên xe
    + số thật + vì sao khớp slot), KHÔNG boilerplate và KHÔNG câu rỗng.
    """

    pitches: Sequence[Any] = ()
    if services.synthesis is not None:
        try:
            pitches = await services.synthesis.synthesize(
                run_id=run_id,
                recommendations=list(recommendations),
                tco=None,
                # Nhu cầu khách tự kể — thiếu nó thì bài viết ra không diễn giải
                # được tính năng nào theo việc khách đang cần (xem `customer_wording`).
                customer_wording=customer_wording(state),
                budget_min_vnd=float(state.slots.get(SlotName.BUDGET_MIN_VND) or 0) or None,
                budget_max_vnd=float(state.slots.get(SlotName.BUDGET_MAX_VND) or 0) or None,
                feature_mention_codes=list(features),
            )
        except Exception:
            logger.warning("core.act: synthesis hong, dung duong du phong", exc_info=True)
            pitches = ()
    verified = bool(pitches)
    if verified and services.verification is not None:
        draft = "\n\n".join(pitch.pitch for pitch in pitches)
        try:
            verified = await services.verification.verify(run_id=run_id, draft_answer=draft)
        except Exception:
            logger.warning("core.act: verify hong, dung duong du phong", exc_info=True)
            verified = False
    if verified and not await _commercial_guard(draft, state, services):
        # Số đúng nhưng chữ hứa một cam kết thương mại (giảm giá, ưu đãi ngoài
        # bảng, trả góp…): đi đường dự phòng tất định như khi `verify` trượt.
        verified = False
    if verified:
        reasons = {str(item.vehicle_id): (item.reasons[0] if item.reasons else "") for item in recommendations}
        bodies = [
            (pitch, await _with_need_lead(services, state, pitch, reasons.get(str(pitch.vehicle_id), "")))
            for pitch in pitches
        ]
        images = await _image_urls(services, [pitch.vehicle_id for pitch in pitches])
        views = [
            RecommendedVehicleView(
                vehicle_id=pitch.vehicle_id,
                rank=pitch.rank,
                display_name=pitch.display_name,
                image_url=images.get(pitch.vehicle_id),
                starting_price_vnd=pitch.starting_price_vnd,
                pitch=body,
                citations=pitch.citations,
            )
            for pitch, body in bodies
        ]
        return "\n\n".join(body for _, body in bodies), views
    try:
        fallback_text = render.recommend_fallback(
            await _fallback_vehicles(services, run_id=run_id, recommendations=recommendations),
            needs=tuple(customer_wording(state)),
        )
    except render.RenderError as exc:
        # Lưới an toàn CUỐI: reason/claim đã qua `render._sanitize_reasons`, nhưng
        # `needs` là chữ khách tự gõ chưa lọc (VD khách gõ nguyên "budget_max_vnd")
        # nên vẫn có đường lọt. Không được để `RenderError` bắn lên và giết cả
        # lượt (đúng bug prod 2026-08-29) — chỉ log MẢNH bị chặn, không log
        # nguyên câu khách (câu khách có thể dài, không cần thiết cho log).
        match = _OFFENDING_FRAGMENT.search(str(exc))
        fragment = match.group(1) if match else "khong-ro"
        logger.warning("core.act: bai du phong van dinh chu cam %r, dung bac cuoi", fragment)
        fallback_text = await _ultra_fallback_text(services, run_id=run_id, recommendations=recommendations)
    # Đường dự phòng vẫn là một lượt ĐỀ XUẤT: bài chữ đổi, bộ xe thì không.
    # Trả `[]` ở đây là lượt prod vòng 8 — khách đọc "Em gợi ý anh/chị mấy mẫu
    # sau ạ:" trên một màn hình không có thẻ nào để bấm. Thẻ dựng từ CỬA CATALOG
    # tất định (`catalog_cards`), không gọi lại `synthesis` — bộ viết vừa hỏng
    # xong ở ngay trên.
    ids = [str(item.vehicle_id) for item in recommendations]
    return (fallback_text, await catalog_cards(services, state, ids, vehicle_type=vehicle_type))


async def _lead_facts(services: AgentServices, state: CoreState, pitch: Any) -> tuple[str, ...]:
    """Số thật của một xe cho câu dẫn: giá từ (có sẵn trên pitch), số chỗ, tầm chạy.

    Đọc qua đúng cửa `_vehicle_spec` (cùng cửa lượt đối chiếu nhu cầu dùng) nên
    con số ở câu dẫn không lệch với con số khách sẽ thấy khi hỏi "có hợp không".
    Đọc hỏng thì còn giá trên pitch; không có gì thì rỗng, câu dẫn tự lo.
    """

    name = getattr(pitch, "display_name", "") or ""
    price: object = _decimal_of(getattr(pitch, "starting_price_vnd", None))
    spec = await _vehicle_spec(services, state, str(getattr(pitch, "vehicle_id", "")), name)
    if spec is not None and spec.price_vnd is not None and price is None:
        price = spec.price_vnd
    return render.spec_facts(
        price_vnd=price,
        seats=spec.seats if spec is not None else None,
        range_km=spec.range_km if spec is not None else None,
    )


async def _with_need_lead(services: AgentServices, state: CoreState, pitch: Any, reason: str) -> str:
    """Bài của một xe, mở đầu bằng câu dẫn nhu cầu TẤT ĐỊNH (xem `render.need_lead`).

    Câu dẫn ĐỨNG TRƯỚC chứ không thay bài: bài của bộ viết đã qua kiểm chứng,
    còn câu dẫn chỉ nói lại việc khách kể bằng chính chữ họ dùng. `RenderError`
    (chữ khách có gạch dưới, trông như mã máy) thì BỎ câu dẫn — một lượt không
    có câu dẫn vẫn tốt hơn một lượt nổ.

    Lý do chấm điểm không có gì đáng nói (chỉ còn claim loại xe — lượt prod "đi
    rạo") thì đọc số thật của xe để câu dẫn có nội dung, thay vì một câu độn lặp
    cho cả ba mẫu.
    """

    purpose = state.slots.get(SlotName.PURPOSE)
    text = purpose.strip() if isinstance(purpose, str) and not purpose.startswith("__") else ""
    if not text:
        # Khách chưa gõ mục đích bằng chữ nhưng thẻ nhu cầu đã nói họ đi xa / chở
        # cả nhà: im lặng ở đây là bỏ đúng thứ `fit` vừa dùng để xếp hạng.
        text = fit.need_phrase(fit.customer_need(state.slots))
    if text and _LONG_DISTANCE.search(text.casefold()):
        # "Với nhu cầu đi du lịch đường dài, VinFast VF 2..." là một KHẲNG ĐỊNH
        # hợp-nhu-cầu, mà xe tầm ngắn chỉ lọt vào đây khi tiêu chí tầm chạy đã
        # bị nới (bug Sếp báo hai lần 2026-08-31). Xe không đủ tầm thì BỎ tiền
        # tố — bài của bộ viết (đã qua kiểm chứng, không chứa claim đi-xa nhờ
        # ngưỡng ở `scoring._purpose_reasons`) đứng một mình. Không đọc được
        # spec thì giữ nguyên: không kết tội xe khi chưa có số.
        spec = await _vehicle_spec(
            services, state, str(getattr(pitch, "vehicle_id", "")), getattr(pitch, "display_name", "") or ""
        )
        if spec is not None and spec.range_km is not None and spec.range_km < LONG_DISTANCE_RANGE_KM:
            return str(pitch.pitch)
    facts: tuple[str, ...] = ()
    if text and render.reason_text(reason) is None:
        facts = await _lead_facts(services, state, pitch)
    try:
        lead = render.need_lead(
            purpose=text,
            passenger_count=state.slots.get(SlotName.PASSENGER_COUNT),
            vehicle_name=getattr(pitch, "display_name", "") or "",
            reason=reason,
            facts=facts,
        )
    except render.RenderError:
        logger.warning("core.act: chu khach khong dung duoc cho cau dan nhu cau")
        return str(pitch.pitch)
    return f"{lead}\n{pitch.pitch}" if lead else str(pitch.pitch)


#: Giá trị ô bảng so sánh KHÔNG phải chữ khách đọc được: cờ máy (`YES`/`NO`/
#: `UNKNOWN`) và mã hằng. Bảng so sánh dùng chúng đúng mục đích của nó (đánh dấu
#: có/không), nhưng đường dự phòng in "{nhãn} {giá trị}" nên chúng ra tới khách
#: thành "theo tài liệu, chưa xác minh UNKNOWN" — đo trên máy thật 2026-09-23.
_MACHINE_CELL_VALUE: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _readable_fact(label: str, value: str) -> bool:
    """Ô này có đọc thành chữ cho khách được không."""

    return bool(label.strip()) and bool(value.strip()) and not _MACHINE_CELL_VALUE.match(value.strip())


async def _fallback_vehicles(
    services: AgentServices, *, run_id: UUID, recommendations: Sequence[Recommendation]
) -> tuple[render.FallbackVehicle, ...]:
    """Số cho đường dự phòng đọc từ SNAPSHOT của chính run này, không từ LLM."""

    facts: dict[str, list[tuple[str, str]]] = {}
    service = services.recommendation
    if service is not None and hasattr(service, "compare"):
        try:
            table = await service.compare(run_id=run_id, vehicle_ids=[item.vehicle_id for item in recommendations])
            for row in table.rows:
                for cell in row.cells:
                    if cell.value_text and cell.label and _readable_fact(cell.label, cell.value_text):
                        facts.setdefault(str(cell.vehicle_id), []).append((cell.label, cell.value_text))
        except Exception:
            logger.warning("core.act: khong doc duoc bang so sanh cho duong du phong", exc_info=True)
    return tuple(
        render.FallbackVehicle(
            name=item.display_name or "mẫu xe",
            facts=tuple(facts.get(str(item.vehicle_id), ())[:3]),
            reasons=tuple(item.reasons[:2]),
        )
        for item in recommendations
    )


async def _ultra_fallback_text(
    services: AgentServices, *, run_id: UUID, recommendations: Sequence[Recommendation]
) -> str:
    """Bậc dự phòng CUỐI (spec mục 7 bước 2): chỉ tên xe thật + giá thật.

    Chỉ chạy khi `render.recommend_fallback` — vốn tự dịch mọi reason/claim
    trước khi dựng câu — VẪN bị `assert_clean` chặn (VD `needs` mang nguyên
    chữ khách gõ dính mã máy, ngoài tầm sanitize của bước 1). Không được ném
    lỗi ở đây: qua khỏi lưới này rồi thì không còn gì đỡ khách khỏi câu an
    toàn ("act hong") — đúng bug prod 2026-08-29.

    `lookup_fact`/`compare` không nằm trong `RecommendationService` Protocol
    (`registry.py`), cùng lý do `_fallback_vehicles` ở trên dùng `hasattr`
    thay vì gọi thẳng.
    """

    service = services.recommendation
    lines: list[str] = []
    for item in recommendations:
        name = item.display_name or "mẫu xe"
        price_text = "liên hệ trực tiếp"
        if service is not None and hasattr(service, "lookup_fact"):
            try:
                cell = await service.lookup_fact(
                    run_id=run_id, vehicle_id=item.vehicle_id, fact_code="STARTING_PRICE_VND"
                )
                if cell is not None and cell.value_text:
                    price_text = render.format_number(float(cell.value_text), "đ")
            except Exception:
                logger.warning("core.act: khong lay duoc gia cho bac du phong cuoi", exc_info=True)
        lines.append(f"{name} — giá {price_text}")
    return "\n".join(lines)


async def _feature_pending(state: CoreState, services: AgentServices, *, candidates: Sequence[UUID]) -> Pending | None:
    """Điền `options` cho câu hỏi tính năng mà policy để trống.

    Policy không biết danh mục (ruling #6 bước 1): nó chỉ đặt `Pending(key=
    habit_need_tags, options=())`. Không điền ở đây thì khách đáp "có tất cả"
    nhận về danh sách rỗng và lượt sau hỏi lại y câu vừa hỏi.
    """

    pending = state.pending
    if pending is None or pending.key != FEATURE_SLOT.value or pending.options:
        return None
    tuning = services.candidate_tuning
    if tuning is None:
        return None
    try:
        choice = await tuning.delegated_features(
            list(candidates),
            vehicle_type=_vehicle_type(state),
            purpose=state.slots.get(SlotName.PURPOSE),
        )
    except Exception:
        logger.warning("core.act: khong lay duoc danh sach tinh nang", exc_info=True)
        return None
    if choice is None or not choice.feature_codes:
        return None
    # `feature_label` trả `None` cho mã không bảng nào dịch được — LOẠI hẳn mã
    # đó khỏi câu hỏi thay vì đọc mã thô cho khách (bước 1 đã chốt).
    pairs = [(code, label) for code in choice.feature_codes if (label := render.feature_label(code))]
    if not pairs:
        return None
    return Pending(
        kind=pending.kind,
        key=pending.key,
        options=tuple(code for code, _ in pairs),
        labels=tuple(label for _, label in pairs),
        asked_at_turn=pending.asked_at_turn,
    )


def _region_code(state: CoreState, user_message: str) -> str:
    """Khu vực tính phí: slot → câu khách vừa nói → mặc định. KHÔNG hỏi lại.

    Ruling bước 1 cho `ON_ROAD_PRICE`: không thêm một lượt hỏi nữa cho một con
    số mà hệ đã có cách suy ra.
    """

    province = state.slots.get(SlotName.REGISTRATION_PROVINCE)
    code = (
        _province_code(str(province)) if province else detect_province(user_message, build_canonical_text(user_message))
    )
    if code:
        return region_for_province_code(code)
    return province_options()[1]


def _province_code(text: str) -> str | None:
    """Chữ trong slot → MÃ tỉnh ("Hà Nội" → "HN"), hoặc `None`.

    Bước 2 (`validate.py:~257`) ghi chữ TỰ DO vào `REGISTRATION_PROVINCE`, không
    ghi mã. Đưa thẳng "Hà Nội" cho `region_for_province_code` thì nó không khớp
    `_KHU_VUC_I_PROVINCE_CODES` và rơi về `KHU_VUC_II` — sai khu vực phí cho
    đúng hai tỉnh đông khách nhất. Slot đã là mã hợp lệ thì giữ nguyên.
    """

    value = text.strip()
    if not value:
        return None
    if value.upper() in set(PROVINCES.values()):
        return value.upper()
    return detect_province(value, build_canonical_text(value))


async def _location_province(services: AgentServices, state: CoreState) -> str | None:
    """Tỉnh suy từ VỊ TRÍ khách đã chia sẻ, hoặc `None`.

    Dùng lại `_test_drive_location` (vị trí trình duyệt → nếu không có thì đổi
    tỉnh trong slot ra toạ độ) rồi đọc `label` của nó — chính nhãn địa danh mà
    bộ tra vị trí trả về. Không có nhãn, hoặc nhãn không khớp tỉnh nào, thì trả
    `None` để lượt đi đường HỎI: đoán tỉnh từ một toạ độ là bịa, và tiền phí
    trước bạ thì không được bịa.
    """

    location = await _test_drive_location(services, state)
    label = getattr(location, "label", None) if location is not None else None
    return _province_code(str(label)) if isinstance(label, str) and label.strip() else None


#: Nhãn khoản mục của thẻ chi phí — cùng bảng lõi cũ dùng (`chain.py:3506`).
#: Chép sang đây vì `core/` KHÔNG được import `chain`; lệch một nhãn thì khách
#: thấy hai tên khác nhau cho cùng một khoản giữa hai lõi.
TCO_COMPONENT_LABELS: Mapping[str, str] = {
    "promoted_purchase_price_vnd": "Giá xe",
    "rolling_fees_vnd": "Lệ phí ban đầu",
    "energy_vnd": "Chi phí năng lượng",
    "battery_vnd": "Chi phí pin",
    "scheduled_maintenance_vnd": "Bảo dưỡng",
}

#: Kỳ tính chi phí: 60 tháng = 5 năm, 30 ngày/tháng (`tools/tco.DAYS_PER_MONTH`)
#: → 360 ngày/năm. KHÔNG phải 365: xem docstring `TcoRatesView`.
TCO_YEARS = 5
TCO_DAYS_PER_YEAR = 360

TCO_FORMULA_NOTE = (
    "Tổng = chi phí cố định + tiền điện mỗi km × số km × 360 ngày × 5 năm "
    "+ bảo hiểm mỗi năm × 5 + số lần bảo dưỡng (làm tròn lên) × đơn giá "
    "+ phí thuê pin mỗi tháng × 60."
)


def _decimal_of(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return None


def _vnd(value: Decimal) -> str:
    return str(int(value.to_integral_value(rounding=ROUND_HALF_UP)))


def build_tco_rates(result: object, *, daily_km: float) -> TcoRatesView | None:
    """Hệ số để client tính lại tổng tại chỗ, hoặc `None` khi thiếu dữ liệu.

    Dựng NGƯỢC từ chính con số máy chủ vừa tính (`components_vnd` +
    `breakdown_detail` + `assumption_lines`), không tính lại một lần thứ hai:
    hai phép tính song song là hai chỗ để lệch, và chỗ lệch chỉ lộ ra khi khách
    so con số trên thẻ với con số trong câu trả lời.

    `fixed_vnd` là phần KHÔNG đổi theo quãng đường (giá xe + trước bạ + biển số
    + đăng kiểm + phí đường bộ), lấy bằng tổng trừ đi bốn khoản có hệ số — nhờ
    vậy công thức của client dựng lại đúng tổng của máy chủ, không xấp xỉ.
    """

    total = _decimal_of(getattr(result, "total_vnd", None))
    components = getattr(result, "components_vnd", None) or {}
    detail = getattr(result, "breakdown_detail", None) or {}
    if total is None or not components or not detail:
        return None
    energy = _decimal_of(components.get("energy_vnd")) or Decimal("0")
    maintenance_total = _decimal_of(components.get("scheduled_maintenance_vnd")) or Decimal("0")
    battery_total = _decimal_of(components.get("battery_vnd")) or Decimal("0")
    insurance_year = _decimal_of(detail.get("mandatory_insurance_year1_vnd")) or Decimal("0")
    lines = {line.code: line.value for line in getattr(result, "assumption_lines", ()) or ()}
    per_service = _decimal_of(lines.get("maintenance_vnd_per_service")) or Decimal("0")
    interval = _decimal_of(lines.get("maintenance_interval_km")) or Decimal("0")
    total_km = Decimal(str(daily_km)) * TCO_DAYS_PER_YEAR * TCO_YEARS
    if total_km <= 0:
        return None
    fixed = total - energy - maintenance_total - battery_total - insurance_year * TCO_YEARS
    return TcoRatesView(
        fixed_vnd=_vnd(fixed),
        # Số duy nhất KHÔNG làm tròn về đồng: sai một đồng mỗi km là sai vài
        # chục nghìn trên tổng năm năm.
        energy_vnd_per_km=str((energy / total_km).quantize(Decimal("0.000001"))),
        insurance_vnd_per_year=_vnd(insurance_year),
        maintenance_vnd_per_service=_vnd(per_service),
        maintenance_interval_km=_vnd(interval),
        battery_vnd_per_month=_vnd(battery_total / (12 * TCO_YEARS)),
        years=TCO_YEARS,
        days_per_year=TCO_DAYS_PER_YEAR,
        formula_note=TCO_FORMULA_NOTE,
    )


def build_tco_card(
    result: object, *, vehicle_id: str, vehicle_name: str, daily_km: float, known_distance: bool, province: str | None
) -> TcoCardView:
    """Thẻ chi phí — cùng hình dạng lõi cũ dựng (`chain.py:3597`), cộng `rates`."""

    components = getattr(result, "components_vnd", None) or {}
    total = _decimal_of(getattr(result, "total_vnd", None))
    return TcoCardView(
        vehicle_id=UUID(vehicle_id),
        vehicle_name=vehicle_name,
        total_vnd=str(total) if total is not None else None,
        components=tuple(
            # `group` để client chia hai nhóm "lăn bánh ban đầu" / "vận hành
            # 5 năm" trên CÙNG một thẻ (Sếp 2026-08-31: lăn bánh với TCO là MỘT).
            TcoComponentView(
                code=code,
                label=label,
                amount_vnd=str(components[code]),
                group=TCO_COMPONENT_GROUPS.get(code, ""),
            )
            for code, label in TCO_COMPONENT_LABELS.items()
            if components.get(code) is not None
        ),
        daily_distance_km=float(daily_km),
        daily_distance_known=known_distance,
        province_code=province or None,
        region_code=region_for_province_code(province),
        assumption_note=assumption_note(daily_km=float(daily_km), known_distance=known_distance, province=province),
        province_options=tuple(
            ProvinceOptionView(code=option.code, name=option.name, region_code=option.region_code)
            for option in province_options()[0]
        ),
        rates=build_tco_rates(result, daily_km=daily_km),
    )


def _merge_tco_tool_args(
    daily: int | None, province_code: str | None, tool_args: TcoToolArgs | None
) -> tuple[int | None, str | None]:
    """Chỉ LẤP CHỖ TRỐNG: slot khách đã nói luôn thắng tham số LLM chọn.

    LLM trả km ngoài khoảng 1..1000 hay tỉnh không tra ra mã thì coi như
    không có — tiền phí trước bạ không được dựng trên một tham số bịa.
    """
    if tool_args is None:
        return daily, province_code
    if daily is None and tool_args.daily_km is not None and 1 <= tool_args.daily_km <= 1000:
        daily = int(tool_args.daily_km)
    if province_code is None and tool_args.province:
        province_code = _province_code(tool_args.province)
    return daily, province_code


def _tco_tool_record(
    *,
    known_daily_km: int | None,
    known_province: str | None,
    tool_args: TcoToolArgs | None,
    daily_after: int | None,
    province_after: str | None,
) -> dict[str, Any]:
    """Một dòng vệt cho `TurnTrace.payload["tool_calls"]`.

    Ghi đủ ba tầng để đọc lại không phải đoán: hệ ĐÃ BIẾT gì trước khi gọi,
    LLM TRẢ gì khi gọi tool, và sau lớp kiểm thì cái gì ĐƯỢC DÙNG thật.
    """
    return {
        "tool": TCO_TOOL_NAME,
        "known": {"daily_km": known_daily_km, "province": known_province},
        "returned": None
        if tool_args is None
        else {"daily_km": tool_args.daily_km, "province": tool_args.province},
        "used": {"daily_km": daily_after, "province_code": province_after},
    }


async def _tco(
    action: Tco, state: CoreState, services: AgentServices, *, user_message: str, run_id: UUID | None
) -> ActResult:
    service = services.tco_estimation
    name = await _name_of(services, state, action.vehicle_id)
    if service is None:
        return ActResult(text=render.no_fact(name))
    daily = _as_int(state.slots.get(SlotName.REQUIRED_RANGE_KM))
    slot_province = state.slots.get(SlotName.REGISTRATION_PROVINCE)
    province_code = _province_code(str(slot_province)) if slot_province else None
    # [Tool-calling] LLM cầm tool `tinh_chi_phi` tự đọc câu khách để LẤP CHỖ
    # TRỐNG (km/ngày, tỉnh) khi slot chưa có. Slot khách đã nói luôn thắng;
    # resolver hỏng/None thì lượt đi tiếp đường tất định như cũ — tool-calling
    # là đường phụ, không phải điểm chết của lượt (Sếp 2026-08-31).
    tool_calls: tuple[dict[str, Any], ...] = ()
    if services.tco_arg_resolver is not None and (daily is None or province_code is None):
        known_province = str(slot_province) if slot_province else None
        known_daily = daily
        tool_args = await services.tco_arg_resolver.resolve(
            user_message=user_message,
            vehicle_name=name,
            known_daily_km=daily,
            known_province=known_province,
        )
        daily, province_code = _merge_tco_tool_args(daily, province_code, tool_args)
        tool_calls = (
            _tco_tool_record(
                known_daily_km=known_daily,
                known_province=known_province,
                tool_args=tool_args,
                daily_after=daily,
                province_after=province_code,
            ),
        )
    # Lõi KHÔNG hỏi số km nữa (Sếp chốt 2026-08-29): thiếu thì tạm tính mức mặc
    # định và NÓI RA mức đó, để khách sửa ngay ở câu sau nếu lệch.
    assumed = None if daily is not None else DEFAULT_DAILY_KM
    result = await service.estimate(
        vehicle_id=UUID(action.vehicle_id),
        daily_distance_km=float(daily if daily is not None else DEFAULT_DAILY_KM),
        run_id=run_id,
        region_code=region_for_province_code(province_code) if province_code else _region_code(state, ""),
    )
    if result.unavailable_reason is not None or result.total_vnd is None:
        return ActResult(text=render.no_fact(name), tool_calls=tool_calls)
    total = render.format_number(float(result.total_vnd), "đ")
    if action.refreshed_km or action.refreshed_province:
        # Khách vừa nhắc lại km/tỉnh SAU khi thẻ đã hiện (policy 5a'): client
        # thay số TẠI CHỖ trên thẻ cũ, nên chữ chỉ xác nhận đúng thứ vừa đổi —
        # đọc lại bài dẫn là khách tưởng có thẻ thứ hai (Sếp 2026-08-31).
        text = render.tco_updated(
            vehicle_name=name,
            km=daily if action.refreshed_km else None,
            province_name=_province_label(province_code) if action.refreshed_province and province_code else None,
        )
    else:
        text = render.tco_summary(
            vehicle_name=name,
            total_text=total,
            assumed_daily_km=assumed,
            daily_km=daily,
            closing=await _closing(services, state, vehicle_name=name, has_tco=True),
        )
    card = build_tco_card(
        result,
        vehicle_id=action.vehicle_id,
        vehicle_name=name,
        daily_km=float(daily if daily is not None else DEFAULT_DAILY_KM),
        known_distance=daily is not None,
        province=province_code,
    )
    return ActResult(text=text, cards={"tco_card": card}, tool_calls=tool_calls)


async def _image_urls(services: AgentServices, vehicle_ids: Sequence[UUID]) -> dict[UUID, str]:
    """Ảnh catalog cho thẻ xe — cùng nguồn lõi cũ (`chain.py` `media.image_urls`).

    Lõi v2 trước đây ghi `image_url=None` ở mọi thẻ nên trên prod thẻ đề xuất
    v2 trống ảnh. Ảnh không phải khẳng định sự thật: lỗi DB thì thẻ đi không
    ảnh, KHÔNG rớt lượt — nhưng ghi log, không nuốt im lặng.
    """

    media = getattr(services, "vehicle_media", None)
    if media is None or not vehicle_ids:
        return {}
    try:
        return dict(await media.image_urls(list(vehicle_ids)))
    except Exception:
        logger.error("core.act: bo anh catalog do loi media", exc_info=True)
        return {}


async def _on_road_price(
    action: OnRoadPrice, state: CoreState, services: AgentServices, *, user_message: str, run_id: UUID | None
) -> ActResult:
    """Giá lăn bánh = THẺ chi phí dùng chung với TCO (Sếp 2026-08-31).

    Sếp chốt: "giá lăn bánh với TCO là MỘT" — các khoản lăn bánh (giá xe, lệ phí
    ban đầu) đứng ngay nhóm đầu của thẻ chi phí, nên lượt này trả ĐÚNG thẻ đó
    thay vì một khối chữ. Hai hệ quả cố ý:

    - KHÔNG hỏi tỉnh nữa (đảo ruling LP35 lần thứ hai, có chỗ dựa mới): tỉnh
      không suy ra được thì tính theo mặc định Khu vực II — đúng như thẻ chi phí
      vẫn làm — và khách sửa NGAY bằng ô chọn tỉnh trên thẻ, rẻ hơn một lượt
      hỏi-đáp. Số không bịa cho một tỉnh cụ thể: `assumption_note` của thẻ nói
      rõ đang tính theo khu vực nào.
    - KHÔNG đi qua `services.on_road_price` (đường chữ của lõi cũ) nữa: hai
      đường tính song song là hai chỗ để lệch số trên cùng một màn hình.

    Tỉnh vẫn suy BA tầng như trước (câu khách vừa nói → slot → vị trí đã chia
    sẻ) để PREFILL ô chọn trên thẻ — khách đã nói tỉnh từ trước thì không phải
    chọn lại bằng tay.
    """

    service = services.tco_estimation
    name = await _name_of(services, state, action.vehicle_id)
    if service is None:
        return ActResult(text=render.no_fact(name))
    province = state.slots.get(SlotName.REGISTRATION_PROVINCE)
    code = (
        detect_province(user_message, build_canonical_text(user_message))
        or (_province_code(str(province)) if province else None)
        or await _location_province(services, state)
    )
    daily = _as_int(state.slots.get(SlotName.REQUIRED_RANGE_KM))
    result = await service.estimate(
        vehicle_id=UUID(action.vehicle_id),
        daily_distance_km=float(daily if daily is not None else DEFAULT_DAILY_KM),
        run_id=run_id,
        region_code=region_for_province_code(code) if code else province_options()[1],
    )
    if result.unavailable_reason is not None or result.total_vnd is None:
        return ActResult(text=render.no_fact(name))
    card = build_tco_card(
        result,
        vehicle_id=action.vehicle_id,
        vehicle_name=name,
        daily_km=float(daily if daily is not None else DEFAULT_DAILY_KM),
        known_distance=daily is not None,
        province=code,
    )
    # Thẻ vừa trả ĐÃ có chi phí 5 năm (lăn bánh và TCO là MỘT thẻ), nên câu kết
    # không được mời khách "xem chi phí 5 năm" — thứ đang hiện ngay trên màn
    # hình. `_closing` suy `has_tco` từ chặng, mà `_run_vehicle_intent` giữ
    # `stage=CHOSEN` khi khách chưa chốt trước đó, nên phải nói rõ ở đây.
    closing = await _closing(services, state, vehicle_name=name, has_tco=True, after_on_road=True)
    return ActResult(text=render.on_road_card_lead(vehicle_name=name, closing=closing), cards={"tco_card": card})


def _province_text(state: CoreState) -> str | None:
    """Tỉnh trong slot, ở dạng TÊN người/dịch vụ đọc được — không bao giờ là mã.

    `understand` ghi MÃ tỉnh vào slot (bước 4-5 mục 2) để bảng khu vực phí tra
    đúng. Nhưng `nearby_location.answer(location_text=...)` là bộ tra ĐỊA DANH:
    đưa nó chuỗi "HN" thì không ra toạ độ nào, `known_location` vẫn `None`, và
    lượt lái thử lại rơi về câu "cho em biết vị trí" — đúng lỗi prod mục 2 sinh
    ra để dẹp. Slot còn giữ chữ tự do (phiên cũ) thì trả nguyên chữ đó.
    """

    raw = state.slots.get(SlotName.REGISTRATION_PROVINCE)
    value = str(raw).strip() if raw else ""
    if not value:
        return None
    return _province_label(value) if value.upper() in set(PROVINCES.values()) else value


#: MÃ tỉnh → TÊN THẬT ("HN" → "Hà Nội"), dựng từ chính `province_options()` —
#: cùng danh sách ô chọn trên thẻ chi phí, nên tên trên giao diện và tên gửi cho
#: bộ tra địa danh không bao giờ lệch. Bảng `PROVINCES` là bảng BÍ DANH viết
#: thường ("hà nội", "hn"): đọc thẳng từ đó ra chữ cho người/dịch vụ là trả về
#: một bí danh gõ vội, không phải tên tỉnh.
_PROVINCE_NAMES: Mapping[str, str] = MappingProxyType({option.code: option.name for option in province_options()[0]})


def _province_label(code: str) -> str:
    return _PROVINCE_NAMES.get(code.upper(), code)


async def _known_location(services: AgentServices, session_id: str) -> UserLocation | None:
    """Vị trí khách đã chia sẻ trong phiên, hoặc `None`.

    Bản tối giản của `chain._load_user_location` (`chain.py:2653`) — cùng một
    cửa service (`conversation.load_user_location`), KHÔNG import `chain`.
    Không đọc chỗ này thì `test_drive.answer` luôn thấy `known_location=None`,
    luôn trả `needs_location=True`: không bao giờ ra thẻ, không bao giờ ra
    `slot_options`, và `Book` không bao giờ tới lượt.
    """

    loader = getattr(services.conversation, "load_user_location", None)
    if loader is None:
        return None
    return UserLocation.from_payload(await loader(session_id))


def _showroom_kind(state: CoreState) -> LocationKind:
    """Loại showroom đi tìm — suy từ loại xe khách nói ra, mặc định ô tô.

    KHÔNG dùng `infer_vehicle_type` (suy từ ngân sách) ở đây: đoán thêm một tầng
    nữa là gửi khách ô tô tới cửa hàng xe máy vì họ khai ngân sách thấp.
    """

    if str(state.slots.get(SlotName.VEHICLE_TYPE) or "") == VehicleType.ELECTRIC_MOTORBIKE.value:
        return LocationKind.SHOWROOM_MOTORBIKE
    return LocationKind.SHOWROOM_CAR


async def _test_drive_location(services: AgentServices, state: CoreState) -> UserLocation | None:
    """Toạ độ để tra showroom: vị trí khách đã chia sẻ, HOẶC tỉnh trong slot.

    Đây là lý do lõi v2 chưa bao giờ ra được thẻ chọn giờ: `test_drive.answer`
    trả về câu hỏi vị trí (`card=None`, `slot_options=()`) bất cứ khi nào
    `known_location is None`, mà lõi v2 chỉ ghi tỉnh vào `slots[
    registration_province]` — không ai đổi chữ đó thành toạ độ. Kết quả: mọi
    lượt lái thử đều không có nút, và đường `__lichlaithu__` không bao giờ chạm
    tới được.

    Cách đổi chữ → toạ độ chép đúng lõi cũ (`chain._resume_nearby_location`):
    `nearby_location.answer(location_text=...)` trả kèm `resolved_location`.
    """

    known = await _known_location(services, state.session_id)
    if known is not None:
        return known
    province = _province_text(state)
    service = services.nearby_location
    if not province or service is None:
        return None
    try:
        result = await service.answer(
            user_message=province,
            location_text=province,
            # THIẾU tham số này là lượt chết trong im lặng: `NearbyLocationServiceImpl
            # .answer` (services/nearby_location.py:129) chưa biết khách tìm loại địa
            # điểm nào thì DỪNG ở câu "Quý khách muốn tìm loại địa điểm nào ạ?" và trả
            # `resolved_location=None` — `known_location` vẫn `None`, `test_drive.answer`
            # lại đáp "cho em biết vị trí", đúng lỗi prod mà mục 2 sinh ra để dẹp.
            # Lượt này KHÔNG phải khách đi tìm địa điểm: lõi tự tra toạ độ tỉnh để đặt
            # lịch, nên loại địa điểm suy thẳng từ loại xe chứ không hỏi ai.
            location_kinds=(_showroom_kind(state),),
            assume_request=True,
        )
    except Exception:
        logger.warning("core.act: khong doi duoc ten tinh ra toa do", exc_info=True)
        return None
    resolved = getattr(result, "resolved_location", None) if result is not None else None
    return resolved if isinstance(resolved, UserLocation) else None


#: Trần số lần hỏi tỉnh cho lượt lái thử. Bằng `policy.MAX_ASKS` và CỐ Ý chép
#: lại: `act` không được import `policy` (một bên là I/O, một bên là bảng quyết
#: định thuần). Không có trần thì khách trả lời kiểu lõi không đọc ra tỉnh sẽ bị
#: hỏi mãi — đúng vòng lặp mà `_ask_capped` sinh ra để chặn.
MAX_PROVINCE_ASKS = 2


def _ask_province(state: CoreState, *, text: str | None = None) -> ActResult:
    """Hỏi tỉnh (lái thử hoặc giá lăn bánh), hoặc chuyển TVV khi đã quá trần.

    `act` tự phát ra câu hỏi thay vì để policy chặn trước, vì CHỈ act đọc được
    vị trí khách đã chia sẻ (`_known_location`). Câu hỏi vẫn đi qua `render` và
    vẫn ghi `pending` như mọi `Ask` khác, nên lượt sau bộ hiểu ý thấy đúng "Câu
    bot vừa hỏi". `text` cho phép nói ĐÚNG lý do hỏi (phí lăn bánh khác showroom
    gần nhất) mà vẫn dùng chung một khoá `pending` và chung một trần hỏi.
    """

    key = SlotName.REGISTRATION_PROVINCE.value
    if state.ask_counts.get(key, 0) >= MAX_PROVINCE_ASKS:
        return ActResult(text=HANDOFF_TEXT, state_patch={"stage": Stage.HANDED_OFF, "pending": None})
    counts = dict(state.ask_counts)
    counts[key] = counts.get(key, 0) + 1
    return ActResult(
        text=text or render.render_ask(Ask(key=key, kind=PendingKind.SLOT)),
        state_patch={
            "pending": Pending(kind=PendingKind.SLOT, key=key, asked_at_turn=state.turn_count),
            "ask_counts": counts,
        },
    )


def with_vehicle_id(card: TestDriveCardView | None, vehicle_id: str) -> TestDriveCardView | None:
    """Gắn id xe vào thẻ lái thử. Service dựng thẻ theo TÊN nên không biết id.

    Công khai vì `api/test_drive_routes` dựng thẻ qua cùng cửa service và cần
    cùng một cách gắn — hai chỗ tự gắn là hai chỗ để quên.
    """

    if card is None:
        return None
    return replace(card, vehicle_id=vehicle_id)


async def _showroom_options(
    action: ShowroomOptions, state: CoreState, services: AgentServices, *, user_message: str, customer_id: str
) -> ActResult:
    service = services.test_drive
    name = await _name_of(services, state, action.vehicle_id)
    if service is None:
        return ActResult(text=render.no_fact(name))
    # Thứ tự vị trí (Sếp 2026-08-31): GPS thật trước — FE tự xin ngay khi thẻ
    # hiện; tỉnh trong slot chỉ còn là đường KHÁCH GÕ vào chat sau khi thẻ hỏi
    # (một kiểu "điền tay"), không phải nguồn tự suy.
    known_location = await _test_drive_location(services, state)
    if known_location is None:
        # Gọi `test_drive.answer` lúc này chỉ để nhận về đúng câu hỏi vị trí là
        # một vòng service thừa — và câu của service cũ không ghi được `pending`
        # nào cho lõi v2, nên lượt sau khách đáp "Hà Nội" mà bộ hiểu ý thấy
        # "Câu bot vừa hỏi: không có".
        #
        # Đợt 8: KHÔNG hỏi tỉnh bằng chữ — trả thẻ `needs_location=True` để
        # khách bấm "Dùng vị trí của tôi" / gõ quận huyện ngay trên thẻ (một
        # lượt là xong, `POST /agent/test-drive/options` dựng thẻ đầy đủ). Vẫn
        # treo `registration_province` (và vẫn có trần) để ai gõ tỉnh vào chat
        # thì đường cũ chạy như trước.
        asked = _ask_province(state, text=render.test_drive_needs_location())
        if asked.state_patch.get("stage") is Stage.HANDED_OFF:
            return asked
        card = TestDriveCardView(vehicle_name=name, vehicle_id=action.vehicle_id, needs_location=True)
        return ActResult(
            text=asked.text,
            cards={
                "test_drive_card": card,
                "navigate": map_navigate(action.vehicle_id, card, center=None, needs_location=True),
            },
            state_patch=asked.state_patch,
        )
    criteria = build_criteria(state)
    # Chữ ký THẬT là `TestDriveServiceImpl.answer` (services/test_drive.py:202),
    # không phải Protocol trong `registry.py` (đã cũ, thiếu hai tham số cuối).
    result = await service.answer(
        user_message=user_message,
        vehicle_name=name,
        vehicle_type=VehicleType(str(criteria.vehicle_type)),
        known_location=known_location,
        session_id=state.session_id,
        customer_id=customer_id,
    )
    card = with_vehicle_id(result.card, action.vehicle_id)
    cards: dict[str, Any] = {"test_drive_card": card}
    if card is not None:
        # Khách VỪA xin lái thử và đã có showroom → dẫn sang bản đồ (contract mục 1).
        cards["navigate"] = map_navigate(action.vehicle_id, card, center=known_location)
    if result.slot_options:
        # Cùng hình dạng lõi cũ dựng ở `chain.py:2247`: nhãn để đọc, `value` là
        # giấy phép đã ký ở service — act KHÔNG tự ghép chuỗi nút.
        cards["quick_replies"] = [
            QuickReplyView(label=option.label, value=option.value) for option in result.slot_options
        ]
    return ActResult(text=result.answer, cards=cards)


async def _book(
    action: Book, state: CoreState, services: AgentServices, *, customer_id: str, user_message: str
) -> ActResult:
    """Đặt lịch từ GIẤY PHÉP đã ký, không từ chuỗi tự tách.

    `read_slot_token` kiểm chữ ký HMAC + phiên + khách + hạn dùng
    (`domain/test_drive_booking`). Tách `choice_ref.split("|")` là mở lại đúng
    cái cửa đã đóng: showroom bịa, giờ đã qua, mã của phiên khác.
    """

    choice = read_slot_token(
        action.choice_ref or user_message, session_id=state.session_id, customer_id=customer_id, now=now_in_vietnam()
    )
    if choice is None or not action.vehicle_id:
        # Mã hết hạn / sai chữ ký / của phiên khác — và cũng là đường tới đây khi
        # policy nhận một nút khung giờ lúc không còn treo câu chọn giờ (LP21).
        return await _slot_expired(action, state, services, customer_id=customer_id, user_message=user_message)
    name = await _name_of(services, state, action.vehicle_id)
    if services.test_drive is None:
        return ActResult(text=render.booking_invalid())
    booking_id = await services.test_drive.book(
        customer_id=customer_id,
        vehicle_id=UUID(action.vehicle_id),
        showroom=choice.showroom,
        scheduled_at=choice.scheduled_at,
    )
    if booking_id is None:
        return ActResult(text=render.booking_invalid())
    summary = render.booking_summary(vehicle_name=name, showroom=choice.showroom, scheduled_at=choice.scheduled_at)
    # Câu xác nhận THAY bài đề xuất — không nối sau (bẫy spec mục 12).
    # `booking_id` ghi vào state để câu kết/panel các lượt sau biết "đã có lịch".
    return ActResult(
        text=render.booking_confirmed(summary, showroom=choice.showroom),
        state_patch={"stage": Stage.CHOSEN, "pending": None, "booking_id": str(booking_id)},
    )


async def _slot_expired(
    action: Book, state: CoreState, services: AgentServices, *, customer_id: str, user_message: str
) -> ActResult:
    """Nút khung giờ không dùng được: nói thật rồi BÀY LẠI khung giờ mới.

    Lượt prod LP21: khách bấm lại nút của một lượt cũ và nhận "Anh/chị muốn xem
    mẫu nào ạ?" — một câu không dính gì tới việc họ vừa làm. Biết xe thì chạy
    lại đúng đường `ShowroomOptions` (nó tự lo phần vị trí, kể cả khi phải hỏi
    tỉnh); chưa biết xe thì hỏi mẫu nào, nhưng kèm LÝ DO ở dòng trước.
    """

    lead = render.slot_expired()
    vehicle_id = action.vehicle_id or state.chosen_vehicle_id or ""
    if vehicle_id and services.test_drive is not None:
        again = await _showroom_options(
            ShowroomOptions(vehicle_id=vehicle_id), state, services, user_message=user_message, customer_id=customer_id
        )
        return ActResult(text=f"{lead}\n\n{again.text}", cards=again.cards, state_patch=again.state_patch)
    asked = await _ask(
        Ask(key=PENDING_VEHICLE, kind=PendingKind.CHOICE, options=state.recommended_ids), state, services
    )
    return ActResult(text=f"{lead}\n\n{asked.text}", cards=asked.cards, state_patch=asked.state_patch)


async def _enqueue_hitl(
    action: EnqueueHitl,
    state: CoreState,
    services: AgentServices,
    *,
    run_id: UUID | None,
    user_message: str,
    customer_id: str = "",
) -> ActResult:
    """Dựng mục hàng duyệt, KHÔNG tự ghi: `run_turn` ghi cùng transaction.

    Ghi ở đây thì mục duyệt và lượt của khách nằm ở hai transaction — đúng lỗi
    "mục duyệt mồ côi" mà `AdvisorReviewRequest` sinh ra để dẹp
    (`services/conversation_memory.py:39`).
    """

    name = await _name_of(services, state, action.vehicle_id)
    text = render.offer_pending(name)
    if run_id is None:
        return ActResult(text=text, state_patch={"stage": Stage.OFFER_REVIEW})
    # Tổng hợp khách cho TVV (Sếp 2026-08-31): quan tâm xe nào, nhu cầu gì, còn
    # lăn tăn gì — TRƯỚC ĐÂY `snapshot=None` nên màn duyệt trống ba mục này.
    snapshot = await _customer_snapshot(state, services, customer_id=customer_id, chosen_name=name)
    # `content` là BẢN NHÁP TRẢ KHÁCH (TVV sửa/duyệt xong hệ gửi thẳng) — tuyệt
    # đối không nhét chữ nội bộ vào đây; tổng hợp khách nằm trong `snapshot`,
    # màn TVV render riêng (bài học prod 2026-08-31: khách từng nhận nguyên dòng
    # "Khách hỏi ưu đãi… Tổng hợp khách —…").
    promo_count = len(getattr(snapshot, "matched_promotions", []) or []) if snapshot is not None else 0
    content = render.offer_review_draft(vehicle_name=name, promo_count=promo_count)
    request = AdvisorReviewRequest(run_id=run_id, content=content, snapshot=snapshot)
    return ActResult(text=text, state_patch={"stage": Stage.OFFER_REVIEW}, hitl_request=request)


#: Từ khoá trong lời khách → điểm lăn tăn. Tất định, đọc transcript của CHÍNH phiên.
_BOTTLENECK_HINTS: tuple[tuple[Bottleneck, tuple[str, ...]], ...] = (
    (
        Bottleneck.PRICE,
        ("đắt", "giá cao", "hơi cao", "rẻ hơn", "mắc", "quá tiền", "vượt ngân sách", "trả góp", "giảm giá"),
    ),
    (Bottleneck.CHARGING, ("sạc", "trạm sạc", "sạc ở đâu", "sạc bao lâu")),
    (Bottleneck.BATTERY, ("pin", "thuê pin", "chai pin", "tuổi thọ pin")),
    (Bottleneck.RANGE, ("bao xa", "tầm", "quãng đường", "đi xa", "đường dài", "hết điện")),
)


def _needs_lines(state: CoreState) -> list[str]:
    """Nhu cầu đã biết, viết cho NGƯỜI đọc (màn TVV in nguyên chuỗi)."""

    slots = state.slots
    lines: list[str] = []
    vehicle_type = str(slots.get(SlotName.VEHICLE_TYPE) or "")
    if vehicle_type:
        lines.append("Loại xe: " + ("ô tô điện" if vehicle_type.upper() == "CAR" else "xe máy điện"))
    budget = _as_int(slots.get(SlotName.BUDGET_MAX_VND))
    if budget:
        lines.append(f"Ngân sách tối đa: {render.format_number(float(budget), 'đ')}")
    purpose = str(slots.get(SlotName.PURPOSE) or "").strip()
    if purpose:
        lines.append(f"Mục đích: {purpose}")
    passengers = _as_int(slots.get(SlotName.PASSENGER_COUNT))
    if passengers:
        lines.append(f"Thường chở: {passengers} người")
    daily = _as_int(slots.get(SlotName.REQUIRED_RANGE_KM))
    if daily:
        lines.append(f"Đi khoảng {daily} km mỗi ngày")
    tags = slots.get(SlotName.HABIT_NEED_TAGS)
    if isinstance(tags, list | tuple) and tags:
        lines.append("Thói quen: " + ", ".join(need_tag_display(str(tag)) for tag in tags[:4]))
    return lines


def _bottlenecks_from_transcript(transcript: Sequence[object]) -> list[ConfirmedBottleneckEvidence]:
    found: dict[Bottleneck, str] = {}
    for index, message in enumerate(transcript):
        if str(getattr(message, "role", "")).upper() != "USER":
            continue
        text = str(getattr(message, "content", "") or "")
        lowered = text.casefold()
        for label, keywords in _BOTTLENECK_HINTS:
            if label not in found and any(keyword in lowered for keyword in keywords):
                found[label] = text.strip()[:200]
    return [
        ConfirmedBottleneckEvidence(
            signal_id=uuid4(), client_turn_id=uuid4(), turn_number=index, label=label, evidence_quote=quote
        )
        for index, (label, quote) in enumerate(found.items())
    ]


async def _customer_snapshot(
    state: CoreState, services: AgentServices, *, customer_id: str, chosen_name: str
) -> ProfileSnapshot | None:
    """Hồ sơ khách cho mục hàng duyệt: nhu cầu, xe đã xem, điểm lăn tăn, ưu đãi khớp.

    Lỗi ở đây KHÔNG được làm rớt mục duyệt: thiếu tổng hợp còn hơn thiếu cả mục.
    """

    try:
        names = await catalog_names(services, vehicle_type=_vehicle_type(state))
        considered = [chosen_name] if chosen_name else []
        considered += [
            names[value] for value in state.recommended_ids if value in names and names[value] not in considered
        ]
        transcript: Sequence[object] = ()
        reader = getattr(services.conversation, "read_transcript", None)
        if reader is not None and customer_id:
            transcript = list(await reader(state.session_id, customer_id, 40))
        evidence = _bottlenecks_from_transcript(transcript)
        builder = services.profile_snapshot_service
        if builder is not None:
            snapshot = builder.build(
                slots={key.value: value for key, value in state.slots.items()}, confirmed_evidence=evidence
            )
        else:
            snapshot = ProfileSnapshot(
                bottlenecks=[
                    BottleneckEvidence(bottleneck=item.label, verbatim_quote=item.evidence_quote) for item in evidence
                ],
                offer_state=OfferState.NONE_BOTTLENECK,
            )
        snapshot = snapshot.model_copy(update={"needs": _needs_lines(state), "considered_vehicles": considered[:5]})
        suggestion = services.offer_suggestion_service
        if suggestion is not None:
            offer = await suggestion.suggest(snapshot, datetime.now(UTC))
            snapshot = snapshot.model_copy(
                update={
                    "offer_state": offer.offer_state,
                    "matched_promotions": [
                        {
                            "promotion_code": item.promotion.promotion_code,
                            "promotion_type": item.promotion.promotion_type.value,
                            "gift_group_unclassified": item.gift_group_unclassified,
                        }
                        for item in offer.matched
                    ],
                    "unmet_demand_flag": offer.unmet_demand_flag,
                    "unmet_bottleneck": offer.unmet_bottleneck,
                }
            )
        return snapshot
    except Exception:
        logger.warning("core.act: khong dung duoc tong hop khach cho muc duyet", exc_info=True)
        return None


# --------------------------------------------------------------- OpenQuestion (agent)

#: Trần chữ của câu trả lời agent — dài hơn thế là đọc bài, không phải trả lời.
AGENT_MAX_ANSWER_CHARS: Final = 700
#: Trần số mẫu xe nhét vào prompt agent (cùng tinh thần `understand.MAX_VEHICLE_LINES`).
AGENT_MAX_CATALOG_LINES: Final = 40

AGENT_SYSTEM_PROMPT: Final = """Ban la Vivi, tro ly ban hang xe dien VinFast, xung "em" voi khach la "anh/chi".

Loi cua he thong tat dinh da khong tra loi duoc cau nay, nen ban duoc goi de tra loi.

LUAT CUNG:
1. Chi dung du lieu tu ket qua tool. Khong tu suy, khong doan, khong nho tu kien thuc chung.
2. TUYET DOI khong viet chu so nao trong cau tra loi (gia, km, so cho, nam...). Neu khach
   can con so, noi ho co the xem the chi phi hoac hoi tiep de em bay so chinh xac.
3. Khong hua giam gia, khuyen mai, tra gop, tang qua, dat coc hay bat ky cam ket thuong mai nao.
4. Khong nhac ma may, ma field, id xe. Chi goi ten xe dung nhu trong khoi "Danh sach xe".
5. Khong hen dat lich lai thu va khong noi se chuyen sang tu van vien.
6. Tra loi ngan (2-4 cau), dung chu de khach vua hoi, bang tieng Viet co dau.

Cach lam: goi toi da hai tool de lay du lieu, roi goi tool tra_loi_khach de nop cau tra loi.
Neu tool khong co du lieu, van goi tra_loi_khach va noi that la em chua co thong tin do."""


def _agent_vehicle_directory(names: Mapping[str, str]) -> VehicleDirectory:
    """Danh bạ của lượt agent — khớp tên CHÍNH XÁC, không đoán (`validate.py`)."""

    return VehicleDirectory(
        refs=tuple(VehicleRef(vehicle_id=vehicle_id, display_name=name) for vehicle_id, name in names.items() if name)
    )


def _agent_user_prompt(
    state: CoreState,
    *,
    question: str,
    user_message: str,
    names: Mapping[str, str],
    transcript: Sequence[Any] = (),
) -> str:
    """Ngữ cảnh lượt cho agent: hội thoại gần nhất, slot, xe đang xét, danh mục.

    Transcript là BẮT BUỘC cho lớp câu tham chiếu ("xe vừa nãy", "tôi đang hỏi
    cái gì đấy"): thiếu nó agent trả lời một câu khác hẳn câu khách hỏi — quan
    sát trên máy 2026-09-23, lượt "không hiểu tôi đang hỏi cái j à" nhận lại một
    đoạn về ngân sách. Dòng transcript đi qua ĐÚNG bộ rào `<utterance>` của
    `understand`, không có bản thứ hai.
    """

    lines: list[str] = []
    recent = tuple(transcript_lines(transcript))
    if recent:
        lines.append("Hoi thoai gan nhat (cu -> moi):")
        lines.extend(recent)
    lines.append(f"Cau khach vua hoi: {sanitize_prompt_text(question or user_message)}")
    if state.slots:
        lines.append("Da biet ve khach: " + "; ".join(f"{key.value}={value}" for key, value in state.slots.items()))
    chosen = names.get(str(state.chosen_vehicle_id or ""), "")
    if chosen:
        lines.append(f"Xe khach da chon: {chosen}")
    shown = [label for vehicle_id in state.recommended_ids if (label := names.get(str(vehicle_id)))]
    if shown:
        lines.append("Xe dang hien tren man hinh: " + ", ".join(shown))
    catalog = [name for name in names.values() if name][:AGENT_MAX_CATALOG_LINES]
    lines.append("Danh sach xe (chi duoc goi ten trong danh sach nay): " + ", ".join(catalog))
    return "\n".join(lines)


async def _agent_flag_on(services: AgentServices, customer_id: str) -> bool:
    """Cổng G1 + G2. Đọc hỏng / chưa cắm / chưa có hàng → TẮT (chiều an toàn)."""

    port = services.agent_flag
    if port is None:
        return False
    try:
        flag = await port.load(FLAG_AGENT_FALLBACK)
    except Exception:
        logger.warning("agent.flag doc loi, coi nhu TAT", exc_info=True)
        return False
    return is_enabled_for(flag, customer_id, kill_switch=get_settings().agent_fallback_kill_switch)


def _agent_gates_local(state: CoreState, services: AgentServices) -> bool:
    """Cổng G4-G7 — thuần, không I/O, chạy TRƯỚC khi đọc cờ (rẻ hơn một query)."""

    if state.stage is Stage.HANDED_OFF:
        return False
    if state.pending is not None and state.pending.kind is PendingKind.CONFIRM:
        # Đang chờ khách xác nhận một việc KHÔNG ĐẢO NGƯỢC: chen một câu trả lời
        # tự do vào đây là làm loãng đúng câu hỏi đang cần một chữ "vâng".
        return False
    if services.agent_loop is None or services.verification is None or services.snapshotting is None:
        return False
    budget = current_call_budget()
    return budget is None or budget.remaining(CallKind.AGENT) > 0


def _agent_candidate_ids(action: OpenQuestion, state: CoreState) -> tuple[UUID, ...]:
    """Ứng viên để snapshot: xe đang đề xuất ∪ xe đã chốt ∪ xe trong Action."""

    ordered: dict[str, None] = {}
    for raw in (*state.recommended_ids, state.chosen_vehicle_id or "", *action.vehicle_ids):
        if raw:
            ordered.setdefault(str(raw), None)
    found: list[UUID] = []
    for raw in ordered:
        try:
            found.append(UUID(raw))
        except ValueError:
            continue
    return tuple(found)


def _agent_executor(
    state: CoreState, services: AgentServices, *, run_id: UUID | None, names: Mapping[str, str], user_message: str
) -> Any:
    """Bộ chạy tool cho agent loop — CHỈ ĐỌC, mọi lỗi thành `AgentToolResult`."""

    directory = _agent_vehicle_directory(names)

    def _resolve(name: str) -> str | None:
        return directory.resolve(name)

    async def execute(call: AgentToolCall) -> AgentToolResult:
        name = call.name
        if not is_read_only(name):
            return AgentToolResult(name=name, ok=False, error=ERROR_UNKNOWN_TOOL)
        try:
            args = parse_tool_args(name, call.args)
        except KeyError:
            return AgentToolResult(name=name, ok=False, error=ERROR_UNKNOWN_TOOL)
        except ValidationError:
            return AgentToolResult(name=name, ok=False, error=ERROR_BAD_ARGS)
        try:
            return await _run_agent_tool(
                name, args, state, services, run_id=run_id, names=names, resolve=_resolve, user_message=user_message
            )
        except Exception:
            # KHÔNG log args: args mang chữ khách (`agent_tools` §2.1).
            logger.warning("agent.tool loi ten=%s", name, exc_info=True)
            return AgentToolResult(name=name, ok=False, error=ERROR_TOOL_FAILED)

    return execute


def _agent_unknown_vehicle(name: str, names: Mapping[str, str]) -> AgentToolResult:
    return AgentToolResult(
        name=name,
        ok=False,
        error=ERROR_UNKNOWN_VEHICLE,
        payload={"vehicles": [label for label in names.values() if label][:AGENT_MAX_CATALOG_LINES]},
    )


async def _run_agent_tool(
    name: str,
    args: Any,
    state: CoreState,
    services: AgentServices,
    *,
    run_id: UUID | None,
    names: Mapping[str, str],
    resolve: Any,
    user_message: str,
) -> AgentToolResult:
    """Một tool → ĐÚNG một service cũ. Không service nào ở đây ghi gì."""

    if name == AGENT_TOOL_DANH_MUC:
        catalog = await catalog_names(services, vehicle_type=args.vehicle_type)
        labels = [label for label in catalog.values() if label][:AGENT_MAX_CATALOG_LINES]
        return AgentToolResult(name=name, ok=True, payload={"vehicles": labels}, error="" if labels else ERROR_EMPTY)

    if name == AGENT_TOOL_TRA_THONG_SO:
        vehicle_id = resolve(args.vehicle_name)
        if vehicle_id is None:
            return _agent_unknown_vehicle(name, names)
        service = services.vehicle_overview
        if service is None:
            return AgentToolResult(name=name, ok=False, error=ERROR_TOOL_FAILED)
        result = await service.answer(vehicle_name=names.get(vehicle_id, args.vehicle_name), session_id=state.session_id)
        answer = (getattr(result, "answer", "") or "").strip() if result is not None else ""
        if not answer:
            return AgentToolResult(name=name, ok=True, error=ERROR_EMPTY)
        facts = list(getattr(result, "lookup_facts", ()) or ())
        payload: dict[str, Any] = {"overview": answer[:MAX_TOOL_TEXT_CHARS]}
        if facts:
            payload["specs"] = {key: str(value) for key, value in dict(facts[0].specs).items()}
        return AgentToolResult(name=name, ok=True, payload=payload)

    if name == AGENT_TOOL_TINH_CHI_PHI:
        vehicle_id = resolve(args.vehicle_name)
        if vehicle_id is None:
            return _agent_unknown_vehicle(name, names)
        service = services.tco_estimation
        if service is None:
            return AgentToolResult(name=name, ok=False, error=ERROR_TOOL_FAILED)
        code = _province_code(args.province) if args.province else None
        daily = args.daily_km if args.daily_km is not None else _as_int(state.slots.get(SlotName.REQUIRED_RANGE_KM))
        result = await service.estimate(
            vehicle_id=UUID(vehicle_id),
            daily_distance_km=float(daily if daily is not None else DEFAULT_DAILY_KM),
            run_id=run_id,
            region_code=region_for_province_code(code) if code else province_options()[1],
        )
        if result is None or result.unavailable_reason is not None or result.total_vnd is None:
            return AgentToolResult(name=name, ok=True, error=ERROR_EMPTY)
        return AgentToolResult(
            name=name,
            ok=True,
            payload={
                "vehicle": names.get(vehicle_id, ""),
                "total_5_nam_vnd": str(result.total_vnd),
                "components_vnd": {key: str(value) for key, value in dict(result.components_vnd).items()},
            },
        )

    if name == AGENT_TOOL_SO_SANH:
        service = services.compare_vehicles
        if service is None:
            return AgentToolResult(name=name, ok=False, error=ERROR_TOOL_FAILED)
        wanted: list[str] = []
        for raw in args.vehicle_names:
            vehicle_id = resolve(raw)
            if vehicle_id is None:
                return _agent_unknown_vehicle(name, names)
            wanted.append(names.get(vehicle_id, raw))
        result = await service.answer(user_message=user_message, vehicle_names=wanted)
        answer = (getattr(result, "answer", "") or "").strip() if result is not None else ""
        if not answer:
            return AgentToolResult(name=name, ok=True, error=ERROR_EMPTY)
        return AgentToolResult(name=name, ok=True, payload={"comparison": answer[:MAX_TOOL_TEXT_CHARS]})

    if name == AGENT_TOOL_TIM_DIEM:
        service = services.nearby_location
        if service is None:
            return AgentToolResult(name=name, ok=False, error=ERROR_TOOL_FAILED)
        result = await service.answer(
            user_message=user_message,
            location_kinds=(args.kind,),
            location_text=args.area or _province_text(state),
            assume_request=True,
        )
        answer = (getattr(result, "answer", "") or "").strip() if result is not None else ""
        if not answer:
            return AgentToolResult(name=name, ok=True, error=ERROR_EMPTY)
        return AgentToolResult(name=name, ok=True, payload={"locations": answer[:MAX_TOOL_TEXT_CHARS]})

    return AgentToolResult(name=name, ok=False, error=ERROR_UNKNOWN_TOOL)


#: Vệt của lần thử agent trong lượt HIỆN TẠI, kể cả lần THẤT BẠI.
#:
#: Agent hỏng thì `_open_question` trả `None` và lượt đi đường tất định — nhưng
#: `ActResult` của đường đó không mang vệt nào, nên bảng đo mất trắng mọi lần
#: agent thử và trượt (đúng thứ ngưỡng A7/A8 cần đếm). `ContextVar` vì `act`
#: chạy trong một task của đúng một lượt; `run_turn` đọc lại ở cuối lượt.
_AGENT_ATTEMPT: ContextVar[tuple[Mapping[str, Any], ...]] = ContextVar("agent_attempt", default=())


def _with_agent_error(steps: tuple[Mapping[str, Any], ...], error: str) -> tuple[Mapping[str, Any], ...]:
    """Đổi lý do ở bước cuối — cửa nào chặn thì bảng đo phải đọc ra đúng cửa đó."""

    if not steps:
        return ({"tool": "", "args_keys": [], "ok": False, "error": error, "ms": 0, "agent": True},)
    return (*steps[:-1], {**dict(steps[-1]), "ok": False, "error": error})


def take_agent_attempt() -> tuple[Mapping[str, Any], ...]:
    """Lấy và XOÁ vệt lần thử agent của lượt vừa chạy."""

    steps = _AGENT_ATTEMPT.get()
    _AGENT_ATTEMPT.set(())
    return steps


def _record_agent_attempt(steps: tuple[Mapping[str, Any], ...]) -> None:
    _AGENT_ATTEMPT.set(steps)


async def _agent_catalog_ids(services: AgentServices, state: CoreState, *, limit: int = 6) -> tuple[str, ...]:
    """Vài mẫu xe của đúng loại đang xét — làm EVIDENCE cho lượt chưa đề xuất gì.

    Móc 1 và móc 2 luôn có `recommended_ids` để snapshot; móc 3 chạy ở chặng thu
    thập, nơi chưa có mẫu nào. Không có evidence thì `verify` từ chối mọi con số,
    nên lấy thẳng từ cửa catalog TẤT ĐỊNH (`catalog_names`), cắt `limit` mẫu để
    snapshot không phình.
    """

    names = await catalog_names(services, vehicle_type=_vehicle_type(state))
    return tuple(list(names)[:limit])


async def _open_question(
    action: OpenQuestion,
    state: CoreState,
    services: AgentServices,
    *,
    run_id: UUID | None,
    customer_id: str,
    user_message: str,
    transcript: Sequence[Any] = (),
) -> ActResult | None:
    """Trả lời câu MỞ bằng agent loop (plan agent-migration §2.3).

    Trả `None` = KHÔNG dùng được kết quả agent; nơi gọi PHẢI chạy đúng đường
    tất định đang chạy hôm nay. Đây là hợp đồng quan trọng nhất của hàm này:
    agent là đường PHỤ, không bao giờ là điểm chết của lượt.

    Thứ tự bắt buộc: cổng → snapshot → loop → verify → quote_gate → assert_clean.
    Trượt bất kỳ cửa nào là `None`, và KHÔNG cửa nào được bỏ qua.
    """

    if not _agent_gates_local(state, services) or not await _agent_flag_on(services, customer_id):
        return None  # chưa phát một call LLM nào
    if run_id is None or services.snapshotting is None or services.verification is None:
        return None
    candidates = _agent_candidate_ids(action, state)
    if not candidates:
        # Không có evidence thì `verify` chắc chắn từ chối — đừng tốn call LLM.
        return None
    await services.snapshotting.snapshot(run_id=run_id, candidate_ids=candidates, assertions=())

    names = await catalog_names(services, vehicle_type=_vehicle_type(state))
    loop = services.agent_loop
    if loop is None:
        return None
    started = time.monotonic()
    outcome = await loop.run(
        system_prompt=AGENT_SYSTEM_PROMPT,
        user_prompt=_agent_user_prompt(
            state, question=action.question, user_message=user_message, names=names, transcript=transcript
        ),
        tools=build_agent_tools(),
        execute=_agent_executor(state, services, run_id=run_id, names=names, user_message=user_message),
        max_steps=AGENT_MAX_STEPS,
        step_timeout_seconds=AGENT_STEP_TIMEOUT_SECONDS,
        total_timeout_seconds=AGENT_TOTAL_TIMEOUT_SECONDS,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    steps_so_far = (
        *outcome.steps,
        {"tool": "", "args_keys": [], "ok": False, "error": outcome.error, "ms": elapsed_ms, "agent": True},
    )
    _record_agent_attempt(steps_so_far)
    answer = (outcome.answer or "").strip()
    if not answer:
        logger.info("agent.loop khong ra cau tra loi error=%s", outcome.error)
        return None
    answer = answer[:AGENT_MAX_ANSWER_CHARS]

    # Cửa 1 — SỐ: mọi chữ số phải có citation khớp `run_evidence` cùng run.
    if not await services.verification.verify(run_id=run_id, draft_answer=answer):
        logger.info("agent.loop verify tu choi reason=%s", "verify_rejected")
        _record_agent_attempt(_with_agent_error(steps_so_far, "verify_rejected"))
        return None
    # Cửa 2 — CAM KẾT THƯƠNG MẠI.
    if not await _commercial_guard(answer, state, services):
        _record_agent_attempt(_with_agent_error(steps_so_far, "quote_gate_blocked"))
        return None
    # Cửa 3 — MÃ MÁY / XƯNG HÔ.
    try:
        text = render.assert_clean(answer)
    except render.RenderError as exc:
        match = _OFFENDING_FRAGMENT.search(str(exc))
        logger.info("agent.loop render chan manh %r", match.group(1) if match else "khong-ro")
        _record_agent_attempt(_with_agent_error(steps_so_far, "render_blocked"))
        return None

    name = await _name_of(services, state, state.chosen_vehicle_id or (state.recommended_ids[0] if state.recommended_ids else None))
    closing = await _closing(services, state, vehicle_name=name)
    # Khoá `agent` là DẤU NHẬN BIẾT của vệt agent: `run_turn._agent_trace_fields`
    # đọc nó thay vì đoán theo tên Action — móc 2 và móc 3 chạy bên trong
    # `Recommend`/`Ask` nên khoá theo tên Action là bỏ sót đúng hai móc đó.
    steps = (
        *outcome.steps,
        {"tool": "", "args_keys": [], "ok": True, "error": outcome.error, "ms": elapsed_ms, "agent": True},
    )
    _record_agent_attempt(())  # thành công thì vệt đi theo `ActResult`, không cần đường phụ
    return ActResult(
        text=f"{text}\n\n{closing}" if closing else text,
        cards=await _kept_cards(state, services, state.recommended_ids),
        # `state_patch` RỖNG là bất biến của Action này (§2.4): agent không ghi gì.
        tool_calls=steps,
    )


async def _open_question_or_none(
    action: OpenQuestion,
    state: CoreState,
    services: AgentServices,
    *,
    run_id: UUID | None,
    customer_id: str,
    user_message: str,
    transcript: Sequence[Any] = (),
) -> ActResult | None:
    """`_open_question` bọc lưới: exception lạ KHÔNG được thoát lên `act()`.

    Lưới ở `run_turn` sẽ trả `_fallback_text` (câu clarify trơ) — TỆ HƠN kết quả
    tất định mà nhánh `None` dẫn tới.
    """

    try:
        return await _open_question(
            action,
            state,
            services,
            run_id=run_id,
            customer_id=customer_id,
            user_message=user_message,
            transcript=transcript,
        )
    except Exception:
        logger.warning("agent.open_question loi la, ve duong tat dinh", exc_info=True)
        return None
