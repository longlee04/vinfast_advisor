"""Bảy bước của lõi v2 chạy end-to-end với service giả (spec mục 3, 7, 8).

Understander giả ở đây là CỔNG LLM (`async understand(*, system_prompt,
user_prompt) -> UnderstandOutcome`), cùng hình với `services.understanding` và
với `_Fake` của `test_understand.py` — không phải một callable trả thẳng
`Understanding`. Nhờ vậy test đi qua ĐÚNG đường bước 2 thật: prompt được dựng,
tool call thô được `validate` chuẩn hoá, rồi mới tới policy.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.agents.contracts import (
    CatalogBrowseResult,
    NearbyLocationListView,
    QuickReplyView,
    TcoCardView,
    TurnResult,
    VehicleComparisonView,
    VehiclePitch,
)
from src.agents.contracts import (
    TestDriveCardView as DriveCard,  # alias: tên bắt đầu bằng Test làm pytest tưởng là lớp test
)
from src.agents.core import run_turn as run_turn_module
from src.agents.core.run_turn import build_core_trace, run_turn
from src.agents.core.state import (
    CoreState,
    Pending,
    Stage,
    Understanding,
)
from src.agents.core.state import (
    DialogueAct as A,
)
from src.agents.core.state import (
    Intent as I,  # noqa: N817 -- quy ước test I=Intent, cùng lối test_policy.py
)
from src.agents.core.state import (
    PendingKind as K,
)
from src.agents.core.understand import RawSlots, RawUnderstanding, UnderstandOutcome
from src.agents.domain.conversation_memory import CoreTurnLease
from src.agents.domain.values import SlotName as N
from src.agents.prompts.question_variants import PROFILE_VARIANTS
from src.agents.services.conversation_memory import StartedMemoryTurn
from src.agents.services.registry import AgentServices
from tests.agents.unit.core.memory_fakes import HonestMemory

SESSION = "aaaaaaaa-0000-0000-0000-000000000001"
V1 = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _clear_directory_cache() -> None:
    """Danh bạ xe cache ở cấp module — mỗi test phải bắt đầu từ trang trắng."""

    run_turn_module.reset_vehicle_directory_cache()


class FakeConversation:
    def __init__(
        self,
        state: CoreState | None = None,
        handed_off: bool = False,
        user_location: dict[str, Any] | None = None,
    ) -> None:
        self.state = state
        self.handed_off = handed_off
        self.user_location = user_location
        self.run_ids: list[UUID] = []

    async def load_user_location(self, session_id: str) -> dict[str, Any] | None:
        """Vị trí trình duyệt khách đã chia sẻ ở `/locations/nearest` — cùng cửa
        `act._known_location` đọc."""

        return self.user_location

    async def open_session(self, session_id: str, customer_id: str) -> None:
        return None

    async def load_core_state(self, session_id: str) -> CoreState | None:
        return self.state

    async def load_handoff_state(self, session_id: str) -> bool:
        return self.handed_off

    async def read_transcript(self, session_id: str, customer_id: str, limit: int = 50) -> list[Any]:
        return []

    async def create_run(self, session_id: str, slots: Any = None) -> UUID:
        run_id = uuid4()
        self.run_ids.append(run_id)
        return run_id


#: Đúng những trường `ConversationMemoryService._turn_result` dựng lại được từ
#: hàng `agent_turn_outcomes` (`conversation_memory.py:569`). Mọi trường KHÁC rơi
#: mất trên đường ghi — fake phải mô phỏng đúng chỗ rơi đó, nếu không test xanh
#: giả cho một hợp đồng không có thật.
class FakeCatalogBrowse:
    def __init__(self) -> None:
        self.calls = 0

    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        self.calls += 1
        return CatalogBrowseResult(
            answer="Dải xe hiện có: VF 5.",
            pitches=(VehiclePitch(vehicle_id=UUID(V1), rank=1, display_name="VinFast VF 5", pitch="VF 5."),),
        )


class FakeUnderstander:
    """Cổng LLM giả — cùng hình `_Fake` của `test_understand.py`."""

    def __init__(self, outcome: UnderstandOutcome | Exception) -> None:
        self._outcome = outcome
        self.calls = 0

    async def understand(self, *, system_prompt: str, user_prompt: str) -> UnderstandOutcome:
        self.calls += 1
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def _outcome(
    *,
    dialogue_act: str = "REQUEST",
    intent: str = "ADVISORY",
    slots: RawSlots | None = None,
    confidence: float = 0.9,
    question: str = "",
) -> UnderstandOutcome:
    return UnderstandOutcome(
        raw=RawUnderstanding(
            dialogue_act=dialogue_act,
            intent=intent,
            slots=slots or RawSlots(),
            confidence=confidence,
            question=question,
        )
    )


def _services(conversation: FakeConversation, memory: HonestMemory, **extra: Any) -> AgentServices:
    extra.setdefault("catalog_browse", FakeCatalogBrowse())
    return AgentServices(conversation=conversation, memory=memory, **extra)


def _lease() -> CoreTurnLease:
    """Lease giả cho đường core v2 có lease (PR1 T2)."""
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 9, 1, tzinfo=UTC)
    return CoreTurnLease(
        session_id=UUID(SESSION),
        client_turn_id=uuid4(),
        turn_number=1,
        claim_token=uuid4(),
        claimed_at=now,
        lease_expires_at=now + timedelta(seconds=25),
    )


async def _turn(
    outcome: UnderstandOutcome | Exception,
    *,
    state: CoreState | None = None,
    handed_off: bool = False,
    user_message: str = "tư vấn giúp em",
    user_location: dict[str, Any] | None = None,
    **extra: Any,
) -> tuple[TurnResult, HonestMemory, FakeConversation]:
    conversation = FakeConversation(state=state, handed_off=handed_off, user_location=user_location)
    memory = HonestMemory()
    result = await run_turn(
        None,
        _services(conversation, memory, **extra),
        session_id=SESSION,
        customer_id="c1",
        user_message=user_message,
        client_turn_id=uuid4(),
        understander=FakeUnderstander(outcome),
        lease=_lease(),
    )
    return result, memory, conversation


@pytest.mark.asyncio
async def test_luot_dau_hoi_mot_cau_ho_so_va_ghi_state() -> None:
    result, memory, _ = await _turn(_outcome())
    # 2026-08-29: MỘT câu hỏi mở cho cả luồng tư vấn, không hỏi từng slot.
    # 2026-09-23: câu đó nay có biến thể theo phiên (`prompts/question_variants`),
    # nên khẳng định nó THUỘC bảng biến thể thay vì khoá cứng một chuỗi.
    assert result.answer and result.answer in PROFILE_VARIANTS
    assert result.pending_question == result.answer
    committed = memory.committed[0]
    assert committed["core_state"].pending is not None
    assert committed["core_state"].pending.key == "profile"
    assert committed["core_state"].stage is Stage.COLLECTING


@pytest.mark.asyncio
async def test_ghi_dung_mot_lan_moi_luot() -> None:
    _, memory, _ = await _turn(_outcome(dialogue_act="SOCIAL", intent="NONE"))
    assert len(memory.committed) == 1


@pytest.mark.asyncio
async def test_handed_off_thi_im_va_van_ghi_state() -> None:
    state = CoreState(session_id=SESSION, stage=Stage.CHOSEN, chosen_vehicle_id=V1)
    result, memory, _ = await _turn(_outcome(), state=state, handed_off=True)
    assert result.answer is None or not result.answer.strip()
    assert memory.committed[0]["core_state"].stage is Stage.HANDED_OFF


@pytest.mark.asyncio
async def test_tvv_tra_quyen_thi_chang_ve_chosen_khong_tin_cot_stage() -> None:
    state = CoreState(session_id=SESSION, stage=Stage.HANDED_OFF, chosen_vehicle_id=V1)
    _, memory, _ = await _turn(
        _outcome(intent="VEHICLE_QA", question="sạc bao lâu"),
        state=state,
        user_message="sạc bao lâu",
    )
    payload = memory.committed[0]["trace"].payload
    assert payload["stage_before"] == "CHOSEN"


@pytest.mark.asyncio
async def test_understand_no_thi_unclear_va_ghi_loi_vao_trace() -> None:
    result, memory, _ = await _turn(TimeoutError("provider 504"), user_message="???")
    assert result.answer and result.answer.strip()
    trace = memory.committed[0]["trace"]
    assert trace.payload["understand_error"]
    assert trace.payload["understanding"]["dialogue_act"] == "UNCLEAR"


@pytest.mark.asyncio
async def test_khong_co_cong_hieu_y_thi_luot_van_chay() -> None:
    """Chưa cắm `services.understanding` → lượt vẫn ra chữ, lỗi nằm ở trace."""

    conversation = FakeConversation()
    memory = HonestMemory()
    result = await run_turn(
        None,
        _services(conversation, memory),
        session_id=SESSION,
        customer_id="c1",
        user_message="alo",
        client_turn_id=uuid4(),
        lease=_lease(),
    )
    assert result.answer and result.answer.strip()
    trace = memory.committed[0]["trace"]
    assert trace.payload["understand_error"] == "no_understanding_port"
    assert trace.payload["understanding"]["dialogue_act"] == "UNCLEAR"


@pytest.mark.asyncio
async def test_trace_dien_cot_cu_de_sql_cu_chay() -> None:
    _, memory, _ = await _turn(_outcome(intent="CATALOG_BROWSE", confidence=0.82))
    trace = memory.committed[0]["trace"]
    assert trace.intent_hint == "CATALOG_BROWSE"
    assert trace.confidence == 0.82
    assert trace.scope_label == "IN_SCOPE"
    assert trace.payload["core"] == "v2"
    assert set(trace.payload) >= {
        "core",
        "stage_before",
        "stage_after",
        "understanding",
        "validated_slots",
        "action",
        "resume_pending",
        "understand_error",
        "ask_counts",
    }


@pytest.mark.asyncio
async def test_social_gan_scope_social() -> None:
    _, memory, _ = await _turn(_outcome(dialogue_act="SOCIAL", intent="NONE"))
    assert memory.committed[0]["trace"].scope_label == "SOCIAL"


@pytest.mark.asyncio
async def test_slot_ghi_ra_ngoai_la_chuoi_khong_enum_khong_decimal() -> None:
    _, memory, _ = await _turn(
        _outcome(dialogue_act="SLOT_ANSWER", slots=RawSlots(vehicle_type="CAR")),
        user_message="ô tô ạ",
    )
    slots = memory.committed[0]["core_state"].slots
    assert slots == {"vehicle_type": "CAR"}
    assert all(isinstance(key, str) for key in slots)


@pytest.mark.asyncio
async def test_khong_tao_run_cho_luot_hoi_slot() -> None:
    _, _, conversation = await _turn(_outcome())
    assert conversation.run_ids == []


@pytest.mark.asyncio
async def test_tao_run_cho_luot_can_snapshot() -> None:
    """`Recommend` đọc snapshot bất biến nên PHẢI có `run_id`."""

    state = CoreState(
        session_id=SESSION,
        stage=Stage.COLLECTING,
        intent=I.ADVISORY,
        slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 800_000_000, N.PURPOSE: "đi làm"},
    )
    _, memory, conversation = await _turn(
        _outcome(dialogue_act="SLOT_ANSWER", slots=RawSlots(seats=5)),
        state=state,
        user_message="5 chỗ",
    )
    assert memory.committed[0]["trace"].payload["action"] == "Recommend"
    assert len(conversation.run_ids) == 1


@pytest.mark.asyncio
async def test_act_hong_van_co_chu_tra_khach() -> None:
    """Service cũ ném lỗi → lượt vẫn có tin nhắn, vẫn ghi đúng một lần."""

    class BoomCatalog:
        async def answer(self, **_kwargs: Any) -> CatalogBrowseResult:
            raise RuntimeError("catalog sập")

    result, memory, _ = await _turn(
        _outcome(intent="CATALOG_BROWSE"),
        catalog_browse=BoomCatalog(),
        user_message="có xe nào",
    )
    assert result.answer and result.answer.strip()
    assert len(memory.committed) == 1


@pytest.mark.asyncio
async def test_act_hong_van_giu_cau_hoi_dang_treo() -> None:
    """`act` hỏng ở lượt hỏi: `pending` do POLICY đặt nên state vẫn khớp client.

    `act._ask` chỉ làm giàu thêm (`labels`), `state_patch` mất không xoá được câu
    hỏi treo — nên `pending_question` VẪN đúng là "lượt này là một câu hỏi".
    """

    conversation = FakeConversation()
    memory = HonestMemory()
    original = run_turn_module.act

    async def boom_act(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("act sập")

    run_turn_module.act = boom_act  # type: ignore[assignment]
    try:
        result = await run_turn(
            None,
            _services(conversation, memory),
            session_id=SESSION,
            customer_id="c1",
            user_message="tư vấn giúp em",
            client_turn_id=uuid4(),
            understander=FakeUnderstander(_outcome()),
            lease=_lease(),
        )
    finally:
        run_turn_module.act = original  # type: ignore[assignment]
    assert memory.committed[0]["trace"].payload["action"] == "Ask"
    assert result.answer and result.answer.strip()
    assert result.pending_question == result.answer
    assert memory.committed[0]["core_state"].pending is not None


@pytest.mark.asyncio
async def test_danh_ba_xe_rong_thi_khong_ghim_cache() -> None:
    """Catalog chớp tắt một nhịp không được khoá danh bạ rỗng suốt 10 phút."""

    class FlakyCatalog(FakeCatalogBrowse):
        async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
            self.calls += 1
            if self.calls == 1:
                return CatalogBrowseResult(answer="", pitches=())
            return CatalogBrowseResult(
                answer="Dải xe hiện có: VF 5.",
                pitches=(VehiclePitch(vehicle_id=UUID(V1), rank=1, display_name="VinFast VF 5", pitch="VF 5."),),
            )

    catalog = FlakyCatalog()
    services = _services(FakeConversation(), HonestMemory(), catalog_browse=catalog)
    for _ in range(2):
        await run_turn(
            None,
            services,
            session_id=SESSION,
            customer_id="c1",
            user_message="tư vấn giúp em",
            client_turn_id=uuid4(),
            understander=FakeUnderstander(_outcome()),
        )
    assert catalog.calls == 2


@pytest.mark.asyncio
async def test_khoa_slot_dang_chuoi_khong_giet_luot_o_buoc_ghi() -> None:
    """State cũ đọc lên có khoá chuỗi → ép về chuỗi, KHÔNG `AttributeError`."""

    state = CoreState(session_id=SESSION, stage=Stage.COLLECTING, slots={"vehicle_type": "CAR"})  # type: ignore[dict-item]
    result, memory, _ = await _turn(_outcome(), state=state)
    assert result.answer and result.answer.strip()
    assert memory.committed[0]["core_state"].slots == {"vehicle_type": "CAR"}


async def _turn_with_cards(
    monkeypatch: pytest.MonkeyPatch, cards: dict[str, Any], *, memory: HonestMemory | None = None
) -> TurnResult:
    """Chạy một lượt mà `act` trả sẵn bộ `cards` này (không service cũ nào sinh được khoá lạ)."""

    from src.agents.core.act import ActResult

    async def fake_act(*_args: Any, **_kwargs: Any) -> ActResult:
        return ActResult(text="Dạ em nghe anh/chị ạ.", cards=cards)

    monkeypatch.setattr(run_turn_module, "act", fake_act)
    return await run_turn(
        None,
        _services(FakeConversation(), memory or HonestMemory()),
        session_id=SESSION,
        customer_id="c1",
        user_message="chào em",
        client_turn_id=uuid4(),
        understander=FakeUnderstander(_outcome(dialogue_act="SOCIAL", intent="NONE")),
        lease=_lease(),
    )


@pytest.mark.asyncio
async def test_card_la_khong_lot_vao_turn_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """`cards` đi qua danh sách TƯỜNG MINH — khoá lạ bị bỏ, không `setattr` mù."""

    result = await _turn_with_cards(monkeypatch, {"khong_co_field_nay": 1, "vehicle_type": "CAR"})
    assert result.vehicle_type == "CAR"
    assert not hasattr(result, "khong_co_field_nay")


@pytest.mark.asyncio
async def test_the_song_qua_duong_ghi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Đường ghi dựng lại `TurnResult` từ DB và LÀM RƠI mọi thẻ chỉ-của-lượt.

    Đúng con bọ `chain._restore_turn_only_fields` sinh ra để vá. Không vá thì
    khách chỉ nhận được khối chữ, mọi thẻ bấm được biến mất.
    """

    cards = {
        "comparison": VehicleComparisonView(),
        "nearby_locations": NearbyLocationListView(),
        "tco_card": TcoCardView(vehicle_id=UUID(V1), vehicle_name="VF 5", total_vnd="500000000"),
        "test_drive_card": DriveCard(vehicle_name="VF 5"),
        "quick_replies": [QuickReplyView(label="Đúng", value="đúng")],
        "options": [{"label": "Hà Nội", "value": "HN"}],
        "vehicle_type": "CAR",
    }
    result = await _turn_with_cards(monkeypatch, cards)
    assert result.comparison is cards["comparison"]
    assert result.nearby_locations is cards["nearby_locations"]
    assert result.tco_card is cards["tco_card"]
    assert result.test_drive_card is cards["test_drive_card"]
    assert result.quick_replies == cards["quick_replies"]
    assert result.options == cards["options"]
    assert result.vehicle_type == "CAR"


@pytest.mark.asyncio
async def test_ban_da_ghi_thang_ban_trong_bo_nho(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trường nào đường ghi CÓ trả về thì giữ nguyên bản đó — không đè ngược."""

    class StrippingMemory(HonestMemory):
        async def commit_core_turn(self, **kwargs: Any) -> TurnResult:
            persisted = await super().commit_core_turn(**kwargs)
            # Bản đi qua DB mới là bản đúng để trả khách (chờ duyệt thì pitch bị
            # cắt); bản trong bộ nhớ không được phép giành lại chỗ.
            return replace(persisted, lookup_facts=["tu-db"])

    result = await _turn_with_cards(monkeypatch, {"lookup_facts": ["tu-bo-nho"]}, memory=StrippingMemory())
    assert result.lookup_facts == ["tu-db"]


@pytest.mark.asyncio
async def test_danh_ba_xe_cache_khong_doc_lai_catalog_moi_luot() -> None:
    catalog = FakeCatalogBrowse()
    conversation = FakeConversation()
    memory = HonestMemory()
    services = _services(conversation, memory, catalog_browse=catalog)
    for _ in range(2):
        await run_turn(
            None,
            services,
            session_id=SESSION,
            customer_id="c1",
            user_message="tư vấn giúp em",
            client_turn_id=uuid4(),
            understander=FakeUnderstander(_outcome()),
        )
    assert catalog.calls == 1


@pytest.mark.asyncio
async def test_replay_tra_ket_qua_cu_khong_chay_lai() -> None:
    class ReplayMemory(HonestMemory):
        async def start_turn(self, **_kwargs: Any) -> StartedMemoryTurn:
            return StartedMemoryTurn(
                context="",
                replayed_result=TurnResult(session_id=SESSION, answer="cũ", pending_question=None),
            )

    conversation = FakeConversation()
    memory = ReplayMemory()
    understander = FakeUnderstander(_outcome())
    result = await run_turn(
        None,
        _services(conversation, memory),
        session_id=SESSION,
        customer_id="c1",
        user_message="lặp",
        client_turn_id=uuid4(),
        understander=understander,
    )
    assert result.answer == "cũ"
    assert memory.committed == []
    assert understander.calls == 0


def test_build_core_trace_thuan() -> None:
    before = CoreState(session_id=SESSION, stage=Stage.COLLECTING, ask_counts={"purpose": 1})
    after = before.with_(stage=Stage.RECOMMENDED, pending=Pending(kind=K.SLOT, key="habit_need_tags"))
    trace = build_core_trace(
        session_id=SESSION,
        client_turn_id="ct1",
        user_message="đủ rồi",
        state_before=before,
        state_after=after,
        understanding=Understanding(dialogue_act=A.SLOT_ANSWER, intent=I.ADVISORY, slots={N.PURPOSE: "đi làm"}),
        action_name="Recommend",
        resume_pending=False,
        understand_error=None,
    )
    assert trace.payload["stage_before"] == "COLLECTING"
    assert trace.payload["stage_after"] == "RECOMMENDED"
    assert trace.payload["validated_slots"] == {"purpose": "đi làm"}
    assert trace.payload["action"] == "Recommend"
    assert trace.payload["ask_counts"] == {"purpose": 1}
    assert trace.routing_enabled is True


def test_build_core_trace_chiu_duoc_khoa_slot_dang_chuoi() -> None:
    """Vệt KHÔNG được là chỗ giết lượt: một khoá chuỗi phải ép được, không nổ."""

    state = CoreState(session_id=SESSION)
    trace = build_core_trace(
        session_id=SESSION,
        client_turn_id=None,
        user_message="ô tô ạ",
        state_before=state,
        state_after=state,
        understanding=Understanding(
            dialogue_act=A.SLOT_ANSWER,
            intent=I.ADVISORY,
            slots={"vehicle_type": "CAR", N.PURPOSE: "đi làm"},  # type: ignore[dict-item]
        ),
        action_name="Ask",
        resume_pending=False,
        understand_error=None,
    )
    assert trace.payload["validated_slots"] == {"vehicle_type": "CAR", "purpose": "đi làm"}
    assert trace.client_turn_id is None


# ---------- bước 6: lượt chen ngang phải trả kèm câu hỏi đang treo ----------


@pytest.mark.asyncio
async def test_chen_ngang_van_giu_pending_question() -> None:
    """Client đọc `pending_question` để biết lượt này còn chờ khách trả lời gì.

    Lượt chen ngang (`resume_pending=True`) nối câu treo vào cuối `answer` nhưng
    trước đây để `pending_question=None` — giao diện không hiển thị câu đang chờ
    ở đâu cả, và khách tưởng việc cũ đã xong.
    """

    from src.agents.core.state import Intent, Pending, PendingKind

    state = CoreState(
        session_id=SESSION,
        stage=Stage.COLLECTING,
        intent=Intent.ADVISORY,
        pending=Pending(kind=PendingKind.SLOT, key="profile"),
    )
    result, _, _ = await _turn(
        _outcome(dialogue_act="INTERRUPT", intent="CATALOG_BROWSE"),
        state=state,
        user_message="mà có những xe nào",
    )
    assert result.pending_question is not None
    assert result.pending_question in PROFILE_VARIANTS
    assert result.pending_question in (result.answer or "")


@pytest.mark.asyncio
async def test_sau_khi_chon_xe_co_panel_buoc_tiep_theo() -> None:
    """`next_step_panel` là DỮ LIỆU TRÌNH BÀY của lõi cũ (`chain.py:1268`); lõi
    v2 để trống ở mọi lượt nên khách không thấy lối đi tiếp nào."""

    from src.agents.core.state import Intent

    state = CoreState(
        session_id=SESSION,
        stage=Stage.CHOSEN,
        intent=Intent.ADVISORY,
        recommended_ids=(V1,),
        chosen_vehicle_id=V1,
    )
    result, _, _ = await _turn(
        _outcome(dialogue_act="SLOT_ANSWER", intent="NONE"),
        state=state,
        user_message="ngày anh đi 30km",
    )
    assert result.next_step_panel is not None
    assert result.next_step_panel.actions


@pytest.mark.asyncio
async def test_moi_luot_deu_co_goi_y_buoc_tiep() -> None:
    result, _, _ = await _turn(_outcome())
    labels = [reply.label for reply in result.quick_replies]
    assert labels
    # Nút gửi lại NGUYÊN VĂN vào cùng cửa hiểu ý, nên nhãn và giá trị phải bằng nhau.
    assert all(reply.value == reply.label for reply in result.quick_replies)


# ---------- bước 4-5 mục 3: thẻ chi phí kèm hệ số phải RA TỚI client ----------


class FakeTcoLine:
    def __init__(self, code: str, value: str) -> None:
        self.code = code
        self.value = value


class FakeTcoResult:
    """Hình THẬT của kết quả `vinfast_tco_v1` — `TcoResult` trong contracts
    không có `breakdown_detail`/`assumption_lines`, mà `build_tco_rates` đọc cả hai."""

    unavailable_reason = None

    def __init__(self) -> None:
        from decimal import Decimal

        self.vehicle_id = UUID(V1)
        self.total_vnd = Decimal("1200000000")
        self.components_vnd = {
            "promoted_purchase_price_vnd": Decimal("1000000000"),
            "rolling_fees_vnd": Decimal("120000000"),
            "energy_vnd": Decimal("50000000"),
            "scheduled_maintenance_vnd": Decimal("20000000"),
            "battery_vnd": Decimal("0"),
        }
        self.breakdown_detail = {"mandatory_insurance_year1_vnd": Decimal("480700")}
        self.assumption_lines = (
            FakeTcoLine("maintenance_vnd_per_service", "1200000"),
            FakeTcoLine("maintenance_interval_km", "15000"),
        )


class FakeTcoEstimation:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def estimate(self, **kwargs: Any) -> FakeTcoResult:
        self.calls.append(kwargs)
        return FakeTcoResult()


@pytest.mark.asyncio
async def test_the_chi_phi_kem_he_so_di_toi_turn_result() -> None:
    """`run_turn._build_result` phải chuyển `ActResult.cards["tco_card"]` sang
    `TurnResult.tco_card` — thiếu `rates` thì client không kéo được thanh trượt
    số km và phải chờ một lượt chat cho mỗi con số."""

    state = CoreState(session_id=SESSION, stage=Stage.CHOSEN, chosen_vehicle_id=V1, intent=I.ADVISORY)
    result, _, _ = await _turn(
        _outcome(intent="COST"),
        state=state,
        user_message="chi phí nuôi xe bao nhiêu",
        tco_estimation=FakeTcoEstimation(),
    )
    assert result.tco_card is not None
    assert result.tco_card.total_vnd == "1200000000"
    assert result.tco_card.rates is not None
    assert result.tco_card.rates.days_per_year == 360


@pytest.mark.asyncio
async def test_tu_van_o_to_thi_bay_danh_sach_va_hoi_trong_cung_mot_luot() -> None:
    """Bước 6: khách vào bằng "tư vấn ô tô". Danh sách của đúng loại đó ĐI KÈM
    câu hồ sơ trong một tin nhắn, và câu treo vẫn là `profile` — không phải lỗi
    cũ "đổ catalog thay cho câu hỏi"."""

    result, memory, _ = await _turn(
        _outcome(slots=RawSlots(vehicle_type="CAR")),
        user_message="tư vấn ô tô",
    )
    assert result.answer and "Dải xe hiện có: VF 5." in result.answer
    assert any(variant in result.answer for variant in PROFILE_VARIANTS)
    assert result.pending_question == result.answer
    assert memory.committed[0]["core_state"].pending.key == "profile"
    labels = [reply.label for reply in result.quick_replies or []]
    assert labels and labels[0].startswith("Ô tô khoảng")


# ---------- prod: đã chia sẻ vị trí thì lượt lái thử KHÔNG hỏi tỉnh ----------


class FakeTestDrive:
    def __init__(self) -> None:
        self.seen: dict[str, Any] = {}

    async def answer(self, *, user_message, vehicle_name, vehicle_type, known_location, session_id, customer_id):
        from datetime import UTC, datetime

        from src.agents.contracts import TestDriveResult, TestDriveSlotOption

        self.seen.update(known_location=known_location)
        if known_location is None:
            return TestDriveResult(answer="Anh/chị đang ở khu vực nào ạ?", needs_location=True)
        when = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
        option = TestDriveSlotOption(
            showroom="VinFast HTA", scheduled_at=when, label="VinFast HTA - 09:00", value="__lichlaithu__|x"
        )
        return TestDriveResult(answer="Showroom gần anh/chị: VinFast HTA.", card=None, slot_options=(option,))


@pytest.mark.asyncio
async def test_da_chia_se_vi_tri_thi_lai_thu_ra_thang_khung_gio() -> None:
    drive = FakeTestDrive()
    state = CoreState(session_id=SESSION, stage=Stage.CHOSEN, chosen_vehicle_id=V1, intent=I.ADVISORY)
    result, _, _ = await _turn(
        _outcome(intent="TEST_DRIVE"),
        state=state,
        user_message="cho anh lái thử",
        user_location={"latitude": 21.0278, "longitude": 105.8342, "source": "browser", "label": "Hà Nội"},
        test_drive=drive,
    )
    assert drive.seen["known_location"] is not None
    assert result.answer and "khu vực nào" not in result.answer
    assert result.quick_replies and len(result.quick_replies) >= 1


@pytest.mark.asyncio
async def test_khong_co_vi_tri_thi_hoi_tinh_dung_mot_lan_roi_moi_ra_nut() -> None:
    drive = FakeTestDrive()
    state = CoreState(session_id=SESSION, stage=Stage.CHOSEN, chosen_vehicle_id=V1, intent=I.ADVISORY)
    asked, memory, _ = await _turn(
        _outcome(intent="TEST_DRIVE"),
        state=state,
        user_message="cho anh lái thử",
        test_drive=drive,
    )
    # Đợt 8: không hỏi tỉnh bằng chữ — thẻ `needs_location=True` mời chọn vị
    # trí ngay trên thẻ; pending tỉnh vẫn treo cho ai gõ tỉnh vào chat.
    assert asked.answer and "trong thẻ" in asked.answer
    assert asked.test_drive_card is not None and asked.test_drive_card.needs_location is True
    assert asked.test_drive_card.vehicle_id == V1
    after = memory.committed[0]["core_state"]
    assert after.pending is not None and after.pending.key == "registration_province"
    assert after.ask_counts.get("registration_province") == 1


def test_act_tu_treo_cau_hoi_thi_pending_question_co_chu() -> None:
    # Giá lăn bánh hỏi tỉnh qua `act._ask_province` (không phải `Ask`): client
    # và probe đọc `pending_question` để biết lượt này là câu hỏi (probe V2-34).
    from src.agents.core.act import ActResult
    from src.agents.core.actions import OnRoadPrice
    from src.agents.core.run_turn import _build_result
    from src.agents.core.state import Pending, PendingKind

    outcome = ActResult(
        text="Anh/chị đăng ký xe ở tỉnh nào ạ?",
        state_patch={"pending": Pending(kind=PendingKind.SLOT, key="registration_province")},
    )
    result = _build_result(SESSION, OnRoadPrice(vehicle_id="v1"), outcome, awaiting_review=False)
    assert result.pending_question == outcome.text


@pytest.mark.asyncio
async def test_panel_buoc_tiep_co_mot_hanh_dong_theo_checklist() -> None:
    """Đợt 9: `next_step_panel.action` là MỘT hành động — đã chốt xe, chưa lịch → đặt lái thử."""

    from src.agents.core.state import Intent

    state = CoreState(
        session_id=SESSION, stage=Stage.CHOSEN, intent=Intent.ADVISORY, recommended_ids=(V1,), chosen_vehicle_id=V1
    )
    result, _, _ = await _turn(_outcome(dialogue_act="SLOT_ANSWER", intent="NONE"), state=state, user_message="30km")
    assert result.next_step_panel is not None and result.next_step_panel.action is not None
    assert result.next_step_panel.action.label == "Đặt lịch lái thử"
    assert result.next_step_panel.action.message == "Đặt lái thử VF 5"


@pytest.mark.asyncio
async def test_panel_da_co_lich_thi_xem_lich_cua_toi() -> None:
    from src.agents.core.state import Intent

    state = CoreState(
        session_id=SESSION,
        stage=Stage.CHOSEN,
        intent=Intent.ADVISORY,
        recommended_ids=(V1,),
        chosen_vehicle_id=V1,
        booking_id="b1",
    )
    result, _, _ = await _turn(_outcome(dialogue_act="SLOT_ANSWER", intent="NONE"), state=state, user_message="30km")
    assert result.next_step_panel is not None and result.next_step_panel.action is not None
    assert result.next_step_panel.action.label == "Xem lịch của tôi"
    assert result.next_step_panel.action.message == ""


def test_navigate_la_the_cua_luot_di_qua_build_result() -> None:
    from src.agents.contracts import NavigateView
    from src.agents.core.act import ActResult
    from src.agents.core.actions import Reply
    from src.agents.core.run_turn import _build_result

    nav = NavigateView(kind="vehicle", vehicle_id="v1", slug="vf-5", name="VinFast VF 5")
    outcome = ActResult(text="Dạ, em ghi nhận.", cards={"navigate": nav})
    result = _build_result(SESSION, Reply(template="chosen_summary"), outcome, awaiting_review=False)
    assert result.navigate == nav


# ---------- [agent-migration Bước 6] OpenQuestion đi hết lượt mà không vỡ contract ----------


@pytest.mark.asyncio
async def test_build_result_voi_open_question() -> None:
    """Lượt UNCLEAR ở RECOMMENDED giờ đi qua Action `OpenQuestion` (cờ agent TẮT).

    Contract phải nguyên: `answer` có chữ, không khoá lạ ngoài `_CARD_FIELDS`,
    `terminal_reason` không bị đặt, và trace ghi đúng tên Action mới.
    """

    from src.agents.core.run_turn import _CARD_FIELDS

    state = CoreState(session_id=SESSION, stage=Stage.RECOMMENDED, recommended_ids=(V1,))
    result, memory, _ = await _turn(
        _outcome(dialogue_act="UNCLEAR", intent="NONE"), state=state, user_message="ờ thế à"
    )
    assert result.answer and result.answer.strip()
    assert result.terminal_reason is None
    trace = memory.committed[-1]["trace"]
    assert trace.payload["action"] == "OpenQuestion"
    # Không field nào của TurnResult bị điền ngoài danh sách thẻ đã khai.
    assert {key for key in _CARD_FIELDS if getattr(result, key, None)} <= _CARD_FIELDS
