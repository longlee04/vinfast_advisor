"""Bảy bước của một lượt lõi v2, cùng chữ ký với `chain.run_turn` (spec mục 3).

    (1) nạp transcript + core_state   (5) act      — gọi service cũ
    (2) understand — 1 call LLM       (6) render   — sinh chữ
    (3) validate   — tất định         (7) ghi core_state + outcome + HITL + trace
    (4) policy     — bảng quyết định       trong MỘT transaction

Điểm ghi DUY NHẤT là `_commit`. Mọi thứ trước đó chỉ đọc. Đó là cách lõi v2
tránh bẫy `_write_pending` của lõi cũ (`chain.py:2699`): cột trạng thái chỉ có
một, mà lõi cũ ghi nó ở sáu chỗ và mỗi chỗ xoá mất việc của chỗ kia.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from src.agents.contracts import PENDING_HANDOFF_REASON, QuickReplyView, TurnResult
from src.agents.core import render
from src.agents.core.act import ActResult, act, catalog_names, needs_run
from src.agents.core.actions import TEMPLATE_CLARIFY, Action, Ask, EnqueueHitl, Handoff, Reply, Silent
from src.agents.core.policy import decide
from src.agents.core.render import short_vehicle_name
from src.agents.core.state import (
    UNCLEAR_UNDERSTANDING,
    CoreState,
    DialogueAct,
    Pending,
    Stage,
    Understanding,
)
from src.agents.core.suggest import quick_replies
from src.agents.core.understand import Understander
from src.agents.core.understand import understand as _understand_step
from src.agents.core.validate import VehicleDirectory, VehicleRef
from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.moderation_blocklist import CONTENT_BLOCKED_REASON, MODERATION_BLOCK_MESSAGE, is_system_probe
from src.agents.domain.next_step import NextStepPanel, build_next_step_panel, build_single_action_panel
from src.agents.domain.post_pitch import PostPitchStage
from src.agents.domain.turn_trace import TurnTrace
from src.agents.domain.values import SlotName, SlotValue
from src.agents.errors import CoreTurnTimeoutError, TurnPersistenceError
from src.agents.logging import get_agent_logger
from src.agents.services.conversation_memory import AdvisorReviewRequest
from src.agents.services.registry import AgentServices

logger = get_agent_logger("agent.core.run_turn")

#: Khoá `cards` của `ActResult` → field `TurnResult`. Danh sách TƯỜNG MINH: mỗi
#: field mới của `TurnResult` phải được thêm vào đây một cách có ý thức, không
#: `setattr` mù (bài học `_restore_turn_only_fields`, `chain.py:1352`).
_CARD_FIELDS: frozenset[str] = frozenset(
    {
        "recommendations",
        "test_drive_card",
        "vehicle_details",
        "next_step_panel",
        "quick_replies",
        "options",
        "comparison",
        "nearby_locations",
        "tco_card",
        "lookup_facts",
        "vehicle_type",
        "navigate",
    }
)

_TRANSCRIPT_LIMIT = 6

#: Danh bạ xe đổi rất hiếm (thêm mẫu mới là việc của tháng, không phải của lượt)
#: nên đọc lại mỗi lượt là một truy vấn catalog thừa trên đường trả lời.
_DIRECTORY_TTL_SECONDS = 600.0
_DIRECTORY_CACHE: tuple[float, VehicleDirectory] | None = None


def reset_vehicle_directory_cache() -> None:
    """Xoá cache danh bạ xe. Chỉ dùng cho test — chạy thật thì TTL lo việc này."""

    global _DIRECTORY_CACHE  # noqa: PLW0603
    _DIRECTORY_CACHE = None


async def run_turn(
    graph: Any,
    services: AgentServices,
    *,
    session_id: str,
    customer_id: str,
    user_message: str,
    client_turn_id: UUID | None = None,
    understander: Understander | None = None,
    lease: Any = None,
    hard_timeout_seconds: float = 20.0,
    timeout_runner: Callable[[Awaitable[TurnResult], float], Awaitable[TurnResult]] | None = None,
) -> TurnResult:
    """Một lượt lõi v2. `graph` không dùng — lõi v2 không đi qua LangGraph.

    `lease` (PR1): route đã gọi `begin_core_turn` thì lõi KHÔNG claim lại —
    replay/busy đã xử lý ở tầng trên; lõi chỉ chạy understand/policy/act rồi
    commit bằng đúng token lease.

    Hai lỗi CỐ Ý không bắt, vì cả hai đều nghĩa là lượt này không có sự thật để
    trả về và nuốt chúng chỉ tạo một lượt ma:
    - `_load_state` hỏng → không biết bot đang hỏi gì, đang ở chặng nào; trả lời
      bằng trạng thái GREETING bịa ra là xoá phiên của khách trong im lặng.
    - `_commit` hỏng → không có gì được ghi; trả `result` như thể xong là hứa với
      khách một việc chưa xảy ra, và lượt sau sẽ đọc ra một lịch sử có lỗ.
    `api/` có sẵn lưới cho lỗi lượt (`fail_turn`); đây là chỗ để nó làm việc.

    Hard timeout (PR1 T1.10): có `lease` thì toàn bộ orchestration post-claim
    bị bọc trong 20s. Hết budget → `CoreTurnTimeoutError` (route map 503
    TURN_TIMEOUT); outcome GIỮ `IN_PROGRESS` — worker KHÔNG finalize FAILED, khách
    recovery 202 tới khi lease 25s hết rồi mới takeover. Đúng hai re-check lease:
    trước act (side effect) và trước commit (ghi).
    """

    del graph
    turn_id = client_turn_id or uuid4()

    async def _orchestrate() -> TurnResult:
        # ---- (1) nạp
        await _open_session(services, session_id, customer_id)
        if lease is None:
            replayed = await _start_memory(
                services,
                session_id=session_id,
                customer_id=customer_id,
                client_turn_id=turn_id,
                user_message=user_message,
            )
            if replayed is not None:
                return replayed

        # ---- (1b) kiểm duyệt — TRƯỚC understand và TRƯỚC khi text vào transcript
        blocked = await _blocked_turn(
            services, session_id=session_id, customer_id=customer_id, client_turn_id=turn_id, user_message=user_message
        )
        if blocked is not None:
            return blocked
        # [PR1 T2] Có lease: USER message ghi TRONG transaction commit_core_turn
        # (cùng ASSISTANT/outcome/state/trace), không còn ghi riêng trước act.
        # Legacy path (lease=None) vẫn cần `_persist_user_message` vì finalize_turn
        # không ghi USER.
        if lease is None:
            await _persist_user_message(
                services,
                session_id=session_id,
                customer_id=customer_id,
                client_turn_id=turn_id,
                user_message=user_message,
            )

        state = await _load_state(services, session_id)
        state = await _project_ownership(services, state)
        state_before = state

        # ---- (2)+(3) understand (đã gồm validate của bước 2)
        #
        # TVV đang cầm phiên thì KHÔNG hiểu ý làm gì: `policy.decide` đã chốt `Silent`
        # ngay ở luật 1, nên kết quả của `understand` không lái được một quyết định
        # nào — nó chỉ tốn đúng một call LLM mỗi lượt cho một lượt bot im lặng (ghi
        # nhận ở sổ bước 3, Task 4). Lượt vẫn ghi vệt như mọi lượt khác, kèm lý do bỏ
        # qua, để bộ đo bước 4 không đọc nhầm "lõi v2 hiểu ý kém đi" ở các phiên HITL.
        understand_skipped = "handed_off" if state.stage is Stage.HANDED_OFF else None
        if understand_skipped is not None:
            understanding, understand_error = UNCLEAR_UNDERSTANDING, None
        else:
            transcript = await _transcript(services, session_id, customer_id)
            understanding, understand_error = await _understand(
                services, state=state, transcript=transcript, user_message=user_message, understander=understander
            )

        # ---- (4) policy
        decision = decide(state, understanding)
        action = decision.action
        state_after = decision.state_after

        # ---- (5) act
        # [PR1 T1.10] Re-check lease TRƯỚC side effect. Worker cũ tỉnh sau
        # takeover bị bắt ở đây: token đã đổi, đừng để nó gọi API ngoài rồi mới
        # biết mình hết quyền. `CoreTurnLeaseStaleError` thoát lên route map 409.
        await _assert_core_turn_lease(services, lease)
        run_id = await _run_id_for(services, action, session_id=session_id, state=state_after)
        try:
            outcome = await act(
                action, state_after, services, run_id=run_id, customer_id=customer_id, user_message=user_message
            )
        except Exception:
            logger.warning("core.run_turn: act hong, tra loi an toan", exc_info=True)
            outcome = ActResult(text=_fallback_text(state_after))

        # ---- (6) render đã xảy ra trong act; ở đây chỉ áp state_patch
        state_after = _apply_patch(state_after, outcome.state_patch)

        # ---- (7) ghi một lần
        name_by_id = (await _vehicle_directory(services)).name_by_id
        result = _build_result(
            session_id,
            action,
            outcome,
            awaiting_review=outcome.hitl_request is not None,
            resumed_question=_resumed_question(action, decision.state_after),
            state=state_after,
            suggestions=quick_replies(state_after, action, vehicle_names=name_by_id),
            vehicle_names=name_by_id,
        )
        trace = build_core_trace(
            session_id=session_id,
            client_turn_id=str(turn_id),
            user_message=user_message,
            state_before=state_before,
            state_after=state_after,
            understanding=understanding,
            action_name=type(action).__name__,
            resume_pending=bool(getattr(action, "resume_pending", False)),
            tool_calls=outcome.tool_calls,
            understand_error=understand_error,
            understand_skipped=understand_skipped,
        )
        await _mark_handoff_pending(services, action, session_id=session_id)
        # [PR1 T1.10] Re-check lease TRƯỚC commit — chỗ ghi DUY NHẤT. Lease hết
        # hạn giữa chừng thì worker phải bỏ lượt, không được chốt gì.
        await _assert_core_turn_lease(services, lease)
        persisted = await _commit(
            services,
            lease=lease,
            session_id=session_id,
            client_turn_id=turn_id,
            customer_id=customer_id,
            user_message=user_message,
            result=result,
            state=state_after,
            trace=trace,
            hitl_request=outcome.hitl_request,
        )
        return _restore_turn_fields(persisted, result)

    if lease is None:
        return await _orchestrate()
    if timeout_runner is not None:
        runner = timeout_runner
    else:

        async def _wait_for(coro: Awaitable[TurnResult], seconds: float) -> TurnResult:
            return await asyncio.wait_for(coro, timeout=seconds)

        runner = _wait_for
    try:
        return await runner(_orchestrate(), hard_timeout_seconds)
    except TimeoutError:
        raise CoreTurnTimeoutError(session_id=session_id, client_turn_id=str(turn_id)) from None


# --------------------------------------------------------------- (1) nạp


async def _assert_core_turn_lease(services: AgentServices, lease: Any | None) -> None:
    """Re-check lease TRƯỚC side effect và TRƯỚC commit (PR1 T1.10).

    `lease=None` (đường fallback không đi qua `begin_core_turn`) thì không có gì
    để check. Không có `assert_core_turn_lease` (fake cũ) cũng bỏ qua — guard này
    chỉ chặn được khi port có mặt.
    """

    if lease is None:
        return
    checker = getattr(services.memory, "assert_core_turn_lease", None)
    if checker is None:
        return
    await checker(lease)


async def _open_session(services: AgentServices, session_id: str, customer_id: str) -> None:
    opener = getattr(services.conversation, "open_session", None)
    if opener is not None:
        await opener(session_id, customer_id)


async def _start_memory(
    services: AgentServices, *, session_id: str, customer_id: str, client_turn_id: UUID, user_message: str
) -> TurnResult | None:
    """Khử trùng lặp: cùng `client_turn_id` thì trả nguyên kết quả cũ.

    `persist_message=False` là bắt buộc, không phải tuỳ chọn: text chỉ được vào
    transcript SAU khi qua kiểm duyệt (T9 của lõi cũ, `chain.py:381`). Bản bước 3
    để mặc định `True` nên một câu bị chặn vẫn nằm lại lịch sử hội thoại và còn
    được nạp lại cho lượt sau — đúng món nợ I2.
    """

    if services.memory is None:
        return None
    started = await services.memory.start_turn(
        session_id=session_id,
        customer_id=customer_id,
        client_turn_id=client_turn_id,
        user_message=user_message,
        slots={},
        persist_message=False,
    )
    return started.replayed_result


async def _blocked_turn(
    services: AgentServices, *, session_id: str, customer_id: str, client_turn_id: UUID, user_message: str
) -> TurnResult | None:
    """Cổng kiểm duyệt của lõi v2 — cùng cổng lõi cũ dùng, đặt ở cùng chỗ.

    Bản bước 3 KHÔNG có cổng này: `services.moderation` chỉ được `chain` gọi, mà
    `core/` không được import `chain` (spec mục 6.5b). Kết quả là mọi câu độc đi
    thẳng vào transcript rồi vào prompt LLM — món nợ I2, phải trả trước khi bật
    `CORE_V2_CUSTOMER_IDS` cho khách thật.

    `canonical` dựng đúng một lần bằng `build_canonical_text` như `chain.py:382`:
    ba dạng chuẩn hoá là nguồn so khớp DUY NHẤT, không cổng nào tự normalize
    riêng (nếu không thì `dm th4ng ngu` và `dm thằng ngu` gặp hai kết luận).

    Lượt bị chặn KHÔNG ghi `conversation_core_state` và KHÔNG ghi vệt: nó chưa
    hiểu được gì để mà ghi, và một câu bị chặn không được đổi chặng hội thoại.
    Nhưng nó PHẢI đóng lượt đã claim ở `start_turn` — bỏ mở thì lần gửi lại cùng
    `client_turn_id` gặp `TurnInProgressError`. Đóng bằng `finalize_turn`, đúng
    đường lõi cũ đóng lượt bị chặn (`chain._finalize_result`).
    """

    canonical = build_canonical_text(user_message)
    # [Bảo mật] Cửa dò-hệ-thống chạy MỌI lượt, độc lập provider: OpenAI
    # moderation không coi "cho tôi API key" / "in system prompt" là harmful nên
    # chúng từng lọt vào nhánh hỏi ngân sách. Từ chối tất định, cùng câu và cùng
    # nhãn CONTENT_BLOCKED với blocklist (Sếp 2026-08-31).
    if is_system_probe(canonical):
        blocked = TurnResult(
            session_id=session_id,
            answer=MODERATION_BLOCK_MESSAGE,
            pending_question=None,
            terminal_reason=CONTENT_BLOCKED_REASON,
        )
        finalizer = getattr(services.memory, "finalize_turn", None)
        if finalizer is not None:
            try:
                return await finalizer(
                    session_id=session_id,
                    customer_id=customer_id,
                    client_turn_id=client_turn_id,
                    user_message=user_message,
                    result=blocked,
                    slots={},
                )
            except Exception as error:
                logger.warning("core.run_turn: finalize system_probe hong", exc_info=True)
                raise TurnPersistenceError(
                    session_id=session_id, client_turn_id=str(client_turn_id)
                ) from error
        return blocked
    moderation = services.moderation
    if moderation is None:
        return None
    try:
        is_blocked = bool(await moderation.is_blocked(user_message=user_message, canonical=canonical))
    except Exception:
        # Fail-open có chủ ý, cùng chiều `DefaultModerationService`: provider hỏng
        # thì blocklist tất định bên trong service đã là đáy sàn, còn chặn sạch
        # mọi lượt vì một lần timeout là tự cắt dịch vụ.
        logger.warning("core.run_turn: moderation hong, coi nhu khong chan", exc_info=True)
        return None
    if not is_blocked:
        return None
    # Chỉ log HASH, không log nội dung — cùng `chain._audit_blocked`.
    logger.info(
        "moderation_blocked core=v2 session_id=%s customer_id=%s hash=%s char_len=%d leet=%s",
        session_id,
        customer_id,
        hashlib.sha256(canonical.folded.encode("utf-8")).hexdigest(),
        len(user_message),
        canonical.folded != canonical.leet_decoded,
    )
    result = TurnResult(
        session_id=session_id,
        answer=MODERATION_BLOCK_MESSAGE,
        pending_question=None,
        terminal_reason=CONTENT_BLOCKED_REASON,
    )
    finalizer = getattr(services.memory, "finalize_turn", None)
    if finalizer is not None:
        try:
            return await finalizer(
                session_id=session_id,
                customer_id=customer_id,
                client_turn_id=client_turn_id,
                user_message=user_message,
                result=result,
                slots={},
            )
        except Exception as error:
            logger.warning("core.run_turn: khong dong duoc luot bi chan", exc_info=True)
            raise TurnPersistenceError(
                session_id=session_id, client_turn_id=str(client_turn_id)
            ) from error
    return result


async def _persist_user_message(
    services: AgentServices, *, session_id: str, customer_id: str, client_turn_id: UUID, user_message: str
) -> None:
    """Ghi câu của khách vào transcript SAU khi qua kiểm duyệt (T9)."""

    appender = getattr(services.memory, "append_user_message", None)
    if appender is None:
        return
    await appender(
        session_id=session_id,
        customer_id=customer_id,
        user_message=user_message,
        client_turn_id=client_turn_id,
    )


async def _load_state(services: AgentServices, session_id: str) -> CoreState:
    loader = getattr(services.conversation, "load_core_state", None)
    if loader is None:
        return CoreState(session_id=session_id)
    loaded = await loader(session_id)
    return loaded or CoreState(session_id=session_id)


async def _project_ownership(services: AgentServices, state: CoreState) -> CoreState:
    """`HANDED_OFF` là CHIẾU của `conversation_sessions.ownership`, không phải cột.

    Spec mục 4: `review_routes` trả quyền → ownership `AI` → lõi v2 coi chặng là
    `CHOSEN`. Tin cột `stage` trong DB thì bot câm vĩnh viễn sau một lần HITL,
    vì không ai ghi ngược cột đó khi TVV bấm duyệt.
    """

    probe = getattr(services.conversation, "load_handoff_state", None)
    if probe is None:
        return state
    try:
        held_by_human = bool(await probe(state.session_id))
    except Exception:
        logger.warning("core.run_turn: khong doc duoc ownership, coi nhu AI", exc_info=True)
        return state.with_(stage=Stage.CHOSEN) if state.stage is Stage.HANDED_OFF else state
    if held_by_human:
        # OFFER_REVIEW: chỉ MỘT câu (ưu đãi) đang chờ TVV, khách vẫn được hỏi
        # tiếp và bot vẫn trả lời (Sếp 2026-08-30: gợi ý "Hỏi thêm về xe" mà bot
        # câm là bỏ rơi khách). Câu trả lời của TVV về sau theo đường duyệt riêng.
        # Chuyển người THẬT (`Handoff`) ghi thẳng `HANDED_OFF` nên không rơi vào đây.
        if state.stage is Stage.OFFER_REVIEW:
            return state
        return state.with_(stage=Stage.HANDED_OFF)
    if state.stage is Stage.HANDED_OFF:
        return state.with_(stage=Stage.CHOSEN)
    return state


async def _transcript(services: AgentServices, session_id: str, customer_id: str) -> Sequence[Any]:
    reader = getattr(services.conversation, "read_transcript", None)
    if reader is None:
        return ()
    try:
        return list(await reader(session_id, customer_id, _TRANSCRIPT_LIMIT))[-_TRANSCRIPT_LIMIT:]
    except Exception:
        logger.warning("core.run_turn: khong doc duoc transcript", exc_info=True)
        return ()


# --------------------------------------------------------------- (2) understand


async def _understand(
    services: AgentServices,
    *,
    state: CoreState,
    transcript: Sequence[Any],
    user_message: str,
    understander: Understander | None,
) -> tuple[Understanding, str | None]:
    """LLM hỏng / sai kiểu / rác → `UNCLEAR`, KHÔNG raise (spec mục 5).

    `understander` là CỔNG LLM (`services.understanding`), không phải một hàm
    thay thế cả bước 2: tham số này chỉ để test và để `composition` cắm adapter
    khác nhau, còn luật chuẩn hoá vẫn là `core.understand.understand`.
    """

    port = understander if understander is not None else services.understanding
    if port is None:
        return UNCLEAR_UNDERSTANDING, "no_understanding_port"
    try:
        vehicles = await _vehicle_directory(services)
        result = await _understand_step(
            state=state, transcript=transcript, user_message=user_message, vehicles=vehicles, understander=port
        )
    except Exception as error:
        # `understand` tự nuốt lỗi rồi, nên lưới này chỉ bắt thứ ngoài nó
        # (dựng danh bạ xe hỏng chẳng hạn) — một lượt vẫn không được chết.
        logger.warning("core.run_turn: understand hong", exc_info=True)
        return UNCLEAR_UNDERSTANDING, f"{type(error).__name__}: {error}"[:300]
    return result.understanding, result.error


async def _vehicle_directory(services: AgentServices) -> VehicleDirectory:
    """Danh bạ id → tên từ catalog, cache 10 phút (danh mục đổi hiếm).

    Nguồn là `act.catalog_names` — đúng một chỗ đọc tên xe cho cả lõi v2, thay vì
    một bản đọc catalog thứ hai lệch với bản của `act`. Không truyền
    `vehicle_type` nên `catalog_browse` trả CẢ HAI loại trong một lần gọi.
    Rỗng/hỏng → `VehicleDirectory()` rỗng: LLM vẫn chạy, chỉ không giải được tên xe.
    """

    global _DIRECTORY_CACHE  # noqa: PLW0603
    now = time.monotonic()
    cached = _DIRECTORY_CACHE
    if cached is not None and now - cached[0] < _DIRECTORY_TTL_SECONDS:
        return cached[1]
    names = await catalog_names(services, vehicle_type=None)
    refs = tuple(VehicleRef(vehicle_id=vehicle_id, display_name=name) for vehicle_id, name in names.items())
    directory = VehicleDirectory(refs=refs)
    if refs:
        # KHÔNG cache bản rỗng. `catalog_names` nuốt lỗi nên "rỗng" ở đây có thể
        # là catalog vừa chớp tắt một nhịp; ghim nó lại 10 phút là mười phút LLM
        # không giải nổi tên xe nào, cho một sự cố đã hết từ lâu.
        _DIRECTORY_CACHE = (now, directory)
    return directory


# --------------------------------------------------------------- (5) act


async def _run_id_for(services: AgentServices, action: Action, *, session_id: str, state: CoreState) -> UUID | None:
    """Tạo run CHỈ cho Action cần đọc snapshot bất biến.

    Tạo run mọi lượt là thêm một hàng `agent_runs` cho cả lượt "anh/chị ở tỉnh
    nào ạ" — rác cho bảng và một lần ghi DB thừa trên đường trả lời.
    """

    if not needs_run(action):
        return None
    creator = getattr(services.conversation, "create_run", None)
    if creator is None:
        return None
    try:
        return await creator(session_id, _slots_for_persist(state))
    except Exception:
        logger.warning("core.run_turn: khong tao duoc run", exc_info=True)
        return None


def _apply_patch(state: CoreState, patch: Mapping[str, Any]) -> CoreState:
    return state.with_(**dict(patch)) if patch else state


def _fallback_text(state: CoreState) -> str:
    """Act hỏng vẫn phải có chữ: KHÔNG lượt nào đi ra không tin nhắn (spec mục 8)."""

    return render.render_reply(Reply(template=TEMPLATE_CLARIFY, args={"stage": state.stage.value}))


# --------------------------------------------------------------- (7) ghi


async def _mark_handoff_pending(services: AgentServices, action: Action, *, session_id: str) -> None:
    """`Handoff`/`EnqueueHitl` phải đặt `conversation_sessions.ownership`.

    `HANDED_OFF` là CHIẾU của ownership (spec mục 4), không phải cột `stage`:
    `_project_ownership` đọc ownership mỗi lượt và ownership `AI` kéo chặng về
    `CHOSEN`. Nên nếu lượt chuyển người chỉ ghi `stage=HANDED_OFF` mà không ghi
    ownership thì ngay lượt sau nó TỰ XOÁ — bot nói "đã chuyển tư vấn viên" rồi
    lượt kế lại trả lời như thường, và mục duyệt của `EnqueueHitl` không dừng
    được bot. Đó là món nợ I1 của bước 3.

    NGOÀI transaction của `commit_core_turn`, ngay TRƯỚC nó — có chủ ý:
    `ConversationService.set_handoff_pending` tự mở transaction trên unit-of-work
    riêng của nó (`services/conversation.py:174`), còn `commit_core_turn` chạy
    trên unit-of-work của `ConversationMemoryService`. Nối được hai bên vào một
    transaction là đổi hợp đồng của cả `ConversationService`, quá tầm một món nợ
    vá. Đặt TRƯỚC vì hai chiều hỏng không đối xứng: cờ đặt xong mà lượt hỏng →
    bot im, người vào tiếp (an toàn); lượt ghi xong mà cờ hỏng → bot nói chồng
    lên bản đang chờ duyệt (đúng con bug cần dẹp).

    Lỗi đặt cờ KHÔNG giết lượt — cùng chiều `chain._mark_handoff_pending`
    (`chain.py:1405`): khách mất câu trả lời tệ hơn một cờ thiếu.
    """

    if not isinstance(action, Handoff | EnqueueHitl):
        return
    setter = getattr(services.conversation, "set_handoff_pending", None)
    if setter is None:
        logger.warning("core.run_turn: khong co set_handoff_pending, chuyen nguoi se tu xoa o luot sau")
        return
    try:
        await setter(session_id)
    except Exception:
        logger.warning("core.run_turn: khong dat duoc ownership PENDING_HANDOFF", exc_info=True)


def _external_slots(slots: Mapping[Any, SlotValue]) -> dict[str, SlotValue]:
    """Khoá CHUỖI ở biên ngoài (`SlotName.value`), enum ở biên trong.

    `ConversationService` khai rõ khoá là chuỗi thô (`registry.py:63`); truyền
    enum xuống là hỏng ở tầng repository và chỉ lộ ra lúc chạy thật.

    ÉP kiểu chứ không lọc: `CoreState.slots` khai khoá `SlotName`, nhưng một khoá
    chuỗi lọt vào (state cũ đọc lên, hay một `state_patch` viết tay) thì `.value`
    ném `AttributeError` và giết lượt ở đúng bước GHI — chỗ đắt nhất để hỏng.
    Bỏ im lặng cũng không đúng: khoá `"vehicle_type"` là khoá HỢP LỆ ở biên này.
    Tầng dưới (`slot_codec.coerce_slots`) đã lọc khoá lạ, nên ép ở đây là an toàn.
    """

    return {(key.value if isinstance(key, SlotName) else str(key)): value for key, value in slots.items()}


def _slots_for_persist(state: CoreState) -> dict[str, SlotValue]:
    return _external_slots(state.slots)


def _resumed_question(action: Action, state: CoreState) -> str | None:
    """Câu hỏi đang treo được NỐI LẠI ở cuối lượt chen ngang, hoặc `None`.

    `act` nối nó vào `answer` (`render.render_resume`), nhưng client đọc
    `pending_question` để biết lượt này còn đang chờ khách trả lời gì. Không
    điền thì lượt chen ngang trông như đã xong việc: khách trả lời tiếp câu treo
    mà giao diện không hiển thị nó ở đâu cả.
    """

    pending = state.pending
    if not getattr(action, "resume_pending", False) or pending is None:
        return None
    question = render.render_ask(
        Ask(key=pending.key, kind=pending.kind, options=pending.options, labels=pending.labels)
    )
    return render.RESUME_PREFIX + question


#: Chặng lõi v2 → chặng "sau đề xuất" của lõi cũ, CHỈ để dựng panel trình bày
#: (`domain/next_step`). Không phải một máy trạng thái thứ hai: panel không đổi
#: cách đọc lượt sau, nó chỉ nói cho khách biết họ làm được gì tiếp.
_PANEL_STAGE: Mapping[Stage, PostPitchStage] = {
    Stage.CHOSEN: PostPitchStage.AWAITING_DECISION,
    Stage.COSTING: PostPitchStage.AWAITING_DECISION,
    Stage.SCHEDULING: PostPitchStage.AWAITING_SLOT,
    Stage.OFFER_REVIEW: PostPitchStage.IN_HITL,
    Stage.HANDED_OFF: PostPitchStage.IN_HITL,
}


def _next_step_panel(
    state: CoreState, outcome: ActResult, *, vehicle_names: Mapping[str, str] = MappingProxyType({})
) -> NextStepPanel | None:
    """Panel "Bước tiếp theo": bộ nút cũ (`actions`) + MỘT hành động theo checklist (`action`).

    `actions` vẫn dựng bằng đúng hàm lõi cũ gọi (`chain.py:1268`) cho client cũ.
    `action` (đợt 9) đọc từ `CoreState`: xe đã chốt / mẫu đầu đang đề xuất /
    `booking_id` — tất định, không cần lượt này làm gì đặc biệt.
    """

    stage = _PANEL_STAGE.get(state.stage)
    # `act._tco` đặt khoá `tco_card` (giá trị còn `None`, thẻ chưa dựng) ở đúng
    # những lượt vừa đưa ra con số chi phí — đó là dấu hiệu "đã báo giá xong".
    legacy = build_next_step_panel(stage=stage, cost_shown="tco_card" in outcome.cards) if stage else None

    def _short(vehicle_id: str | None) -> str:
        return short_vehicle_name(vehicle_names.get(str(vehicle_id), "")) if vehicle_id else ""

    single = build_single_action_panel(
        chosen_name=_short(state.chosen_vehicle_id),
        recommended_name=_short(state.recommended_ids[0]) if state.recommended_ids else "",
        has_booking=state.booking_id is not None,
        waiting_advisor=state.stage in (Stage.HANDED_OFF, Stage.OFFER_REVIEW),
        picking_slot=outcome.cards.get("test_drive_card") is not None,
    )
    if single is None:
        return legacy
    if legacy is None:
        return single
    return replace(single, actions=legacy.actions)


def _build_result(
    session_id: str,
    action: Action,
    outcome: ActResult,
    *,
    awaiting_review: bool,
    resumed_question: str | None = None,
    state: CoreState | None = None,
    suggestions: Sequence[str] = (),
    vehicle_names: Mapping[str, str] = MappingProxyType({}),
) -> TurnResult:
    if isinstance(action, Silent):
        # `Silent` chỉ sinh ra ở MỘT chỗ: `policy.decide` luật 1, khi phiên đang
        # chờ NGƯỜI (`policy.py:90`). Nên lượt này soi gương đúng cái lõi cũ trả
        # ở nhánh `_handoff_active` (`chain.py:445-451`): `answer=""`,
        # `pending_question=None`, `terminal_reason=PENDING_HANDOFF`.
        #
        # `answer=None` + `terminal_reason=None` như bản bước 3 KHÔNG ghi được:
        # `TurnOutcome.__post_init__` (`domain/conversation_memory.py:208`) đòi một
        # lượt COMPLETED phải có gì đó trả khách, nên `commit_core_turn` ném
        # `ValueError` — tức MỌI lượt khi TVV đang cầm phiên đều chết ở bước ghi.
        # Không test đơn vị nào bắt được vì các fake `commit_core_turn` không dựng
        # `TurnOutcome` thật (đã vá bằng `memory_fakes.HonestMemory`).
        return TurnResult(
            session_id=session_id,
            answer="",
            pending_question=None,
            terminal_reason=PENDING_HANDOFF_REASON,
            turn_status="COMPLETED",
        )
    text = outcome.text.strip()
    cards = {key: value for key, value in outcome.cards.items() if key in _CARD_FIELDS and value is not None}
    if suggestions and not cards.get("quick_replies"):
        # Nút khung giờ lái thử (`act._showroom_options`) LUÔN thắng: đó là gợi
        # ý của chính lượt đó, và nó chở giấy phép đã ký chứ không phải chữ.
        # `value` bằng đúng `label` vì client gửi lại nguyên văn vào cùng cửa
        # hiểu ý — đó là lý do chữ ở `suggest.py` phải viết như khách sẽ gõ.
        cards["quick_replies"] = [QuickReplyView(label=item, value=item) for item in suggestions]
    if state is not None and "next_step_panel" not in cards:
        panel = _next_step_panel(state, outcome, vehicle_names=vehicle_names)
        if panel is not None:
            cards["next_step_panel"] = panel
    return TurnResult(
        session_id=session_id,
        answer=text or None,
        # Client dùng `pending_question` để biết lượt này là một câu hỏi. Cùng
        # nội dung với `answer` là đúng ý: `_delivered_content` ưu tiên `answer`
        # nên transcript chỉ có MỘT bản.
        # `act` cũng tự treo câu hỏi (`_ask_province` của giá lăn bánh/lái thử):
        # `state_patch["pending"]` khác None là một câu hỏi y như `Ask`.
        pending_question=(text if isinstance(action, Ask) or outcome.state_patch.get("pending") is not None else None)
        or resumed_question,
        awaiting_review=awaiting_review,
        turn_status="WAITING_REVIEW" if awaiting_review else "COMPLETED",
        **cards,
    )


def _restore_turn_fields(persisted: TurnResult, built: TurnResult) -> TurnResult:
    """Trả lại các thẻ CHỈ-CỦA-LƯỢT mà đường ghi không giữ.

    `commit_core_turn` không trả `result` — nó dựng LẠI `TurnResult` từ hàng
    `agent_turn_outcomes` vừa ghi (`conversation_memory.py:371` →
    `_turn_result`, :569). Hàng đó chỉ có chín trường; mọi thẻ khác
    (`comparison`, `nearby_locations`, `tco_card`, `test_drive_card`,
    `quick_replies`, `vehicle_details`, `next_step_panel`, `options`,
    `vehicle_type`) rơi mất trên đường về. Đúng con bọ mà
    `chain._restore_turn_only_fields` (`chain.py:1350`) sinh ra để vá, và không
    vá ở đây thì cả `_CARD_FIELDS` là công cốc.

    Chép TƯỜNG MINH theo `_CARD_FIELDS`, và CHỈ khi bản đã ghi còn trống: giá trị
    đi qua DB (bị strip pitch/citation lúc chờ duyệt chẳng hạn) mới là giá trị
    đúng để trả khách, bản trong bộ nhớ không được phép đè lên nó.
    """

    missing = {
        name: getattr(built, name)
        for name in _CARD_FIELDS
        if not getattr(persisted, name, None) and getattr(built, name, None)
    }
    return replace(persisted, **missing) if missing else persisted


async def _commit(
    services: AgentServices,
    *,
    lease: Any | None = None,
    session_id: str = "",
    client_turn_id: UUID | None = None,
    customer_id: str,
    user_message: str,
    result: TurnResult,
    state: CoreState,
    trace: TurnTrace,
    hitl_request: AdvisorReviewRequest | None,
) -> TurnResult:
    """Commit lượt dùng lease-based path hoặc fallback legacy path.

    `lease` có → `commit_core_turn(lease=lease, ...)`. `lease=None` → dùng
    `finalize_turn` (legacy, không có begin_core_turn).
    """
    if lease is not None:
        committer = getattr(services.memory, "commit_core_turn", None)
        if committer is None:
            logger.warning("core.run_turn: khong co commit_core_turn, luot khong duoc ghi")
            return result
        return await committer(
            lease=lease,
            customer_id=customer_id,
            user_message=user_message,
            result=result,
            core_state=state,
            trace=trace,
            advisor_review=hitl_request,
        )
    # Legacy path: không lease → dùng finalize_turn (giữ nguyên behavior cũ).
    finalizer = getattr(services.memory, "finalize_turn", None)
    if finalizer is None:
        return result
    return await finalizer(
        session_id=session_id,
        customer_id=customer_id,
        client_turn_id=client_turn_id,
        user_message=user_message,
        result=result,
        slots=_slots_for_persist(state),
    )


def build_core_trace(
    *,
    session_id: str,
    client_turn_id: str | None,
    user_message: str,
    state_before: CoreState,
    state_after: CoreState,
    understanding: Understanding,
    action_name: str,
    resume_pending: bool,
    understand_error: str | None,
    understand_skipped: str | None = None,
    tool_calls: tuple[Mapping[str, Any], ...] = (),
) -> TurnTrace:
    """Vệt của một lượt v2 (spec mục 8). Thuần, không I/O.

    Ba cột VÔ HƯỚNG (`intent_hint`, `confidence`, `scope_label`) được điền từ
    `Understanding` để **SQL cũ chạy nguyên**: bộ đo của lõi cũ lọc theo đúng ba
    cột đó, và một hàng v2 để trống chúng sẽ biến mất khỏi mọi báo cáo so sánh.
    """

    return TurnTrace(
        session_id=str(session_id),
        client_turn_id=str(client_turn_id) if client_turn_id is not None else None,
        user_message=user_message,
        intent_hint=understanding.intent.value,
        confidence=understanding.confidence,
        tier="core_v2",
        scope_label="SOCIAL" if understanding.dialogue_act is DialogueAct.SOCIAL else "IN_SCOPE",
        terminal_reason=None,
        routing_enabled=True,
        payload=trace_payload(
            state_before=state_before.stage,
            state_after=state_after,
            action_name=action_name,
            understanding={
                "dialogue_act": understanding.dialogue_act.value,
                "intent": understanding.intent.value,
                "choice_ref": understanding.choice_ref,
                "confidence": understanding.confidence,
                "features_all": understanding.features_all,
                "vehicle_ids": list(understanding.vehicle_ids),
                "question": understanding.question[:200],
            },
            validated_slots=_external_slots(understanding.slots),
            resume_pending=resume_pending,
            understand_error=understand_error,
            #: [Tool-calling] Vệt LLM gọi tool trong act — đủ ba tầng đã-biết/
            #: LLM-trả/được-dùng để màn admin thấy QUÁ TRÌNH, không chỉ kết quả.
            **({"tool_calls": [dict(t) for t in tool_calls]} if tool_calls else {}),
            #: `None` = có chạy understand. Chuỗi = lý do bỏ qua ("handed_off").
            #: Phân biệt được "hiểu ra UNCLEAR" với "không hỏi câu nào" là điều
            #: kiện để chỉ số hiểu ý của bước 4 không bị pha loãng bởi các lượt
            #: bot cố ý im lặng.
            understand_skipped=understand_skipped,
        ),
    )


def _pending_snapshot(pending: Pending | None) -> dict[str, object] | None:
    """Ảnh chụp pending cuối lượt cho trace — KHÔNG chép options.

    `options` có thể là uuid xe: đưa vào trace thì trace phình mà SQL đo không
    dùng tới. Chỉ số 2 chỉ cần biết "cuối lượt có treo câu hỏi không".
    """

    if pending is None:
        return None
    return {"kind": pending.kind.value, "key": pending.key, "asked_at_turn": pending.asked_at_turn}


def trace_payload(*, state_before: Stage, state_after: CoreState, action_name: str, **extra: object) -> dict:
    """Payload JSON của một vệt v2. Thuần — tách ra để đo được mà không dựng lượt.

    `pending_after` là khoá chỉ số 2 ("lượt ngay sau khi bot vừa hỏi") đọc. Lõi v1
    có sẵn `payload.outcome.has_pending_question`; lõi v2 trước đây chỉ ghi
    `stage_*`/`action`/`resume_pending`, không đủ. Và KHÔNG suy từ `ask_counts`:
    nó chỉ tăng, còn pending bị xoá ngay khi khách trả lời.
    """

    payload: dict[str, object] = {
        "core": "v2",
        "stage_before": state_before.value,
        "stage_after": state_after.stage.value,
        "action": action_name,
        "pending_after": _pending_snapshot(state_after.pending),
        "ask_counts": dict(state_after.ask_counts),
    }
    payload.update(extra)
    return payload


__all__ = ["Understander", "build_core_trace", "reset_vehicle_directory_cache", "run_turn", "trace_payload"]
