"""Lớp hội thoại tự nhiên + bộ ghép câu trả lời xe — tái hiện log thật 2026-09-23.

Lượt 1 "thông tin xe vf9": chunk RAG trùng, mục "Tiện nghi" hai lần, "- Bản Plus"
dính giữa câu, hai câu mời liền nhau, giá chỉ "từ …".
Lượt 2 "ok xe đẹp đấy": bot đáp bằng lời chào giới thiệu — mất ngữ cảnh.

Assert trên NHÃN + CẤU TRÚC (số câu hỏi, số lần một mục xuất hiện), không trên
nguyên văn câu chữ. LLM đều là fake.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from src.agents.contracts import CatalogBrowseResult, VehiclePitch
from src.agents.core import render
from src.agents.core.act import act
from src.agents.core.actions import ShowroomOptions, Silent
from src.agents.core.policy import decide
from src.agents.core.state import CoreState, DialogueAct, Intent, Stage, Understanding
from src.agents.core.understand import RawSlots, RawUnderstanding, UnderstandOutcome, understand
from src.agents.core.validate import VehicleDirectory, VehicleRef
from src.agents.domain.conversational import ConversationalIntent
from src.agents.domain.values import SlotName
from src.agents.domain.vehicle_overview import DimensionsInfo, EvidenceItem, PriceVariant, VehicleOverview
from src.agents.services.registry import AgentServices
from src.agents.services.vehicle_overview import render_overview_response

V9 = "99999999-9999-9999-9999-999999999999"
V9_NAME = "VinFast VF 9"
INTRO = "Em là trợ lý tư vấn"
VF9_CLOSING = (
    "Dạ, VinFast VF 9 là mẫu xe thuần điện của VinFast.\n\nAnh/chị ưng VinFast VF 9 không, hay để em so với mẫu khác?"
)
SEAT_PARAGRAPH = "Hàng ghế thứ hai bản Plus có ghế cơ trưởng chỉnh điện, sưởi và thông gió"

pytestmark = pytest.mark.asyncio


@dataclass(frozen=True)
class _Msg:
    role: str
    content: str


class _FakeUnderstander:
    def __init__(self, dialogue_act: str, intent: str = "NONE", slots: RawSlots | None = None) -> None:
        self.raw = RawUnderstanding(dialogue_act=dialogue_act, intent=intent, slots=slots or RawSlots(), confidence=0.7)

    async def understand(self, *, system_prompt: str, user_prompt: str) -> UnderstandOutcome:
        return UnderstandOutcome(raw=self.raw)


class _Catalog:
    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        return CatalogBrowseResult(
            answer=V9_NAME, pitches=(VehiclePitch(vehicle_id=UUID(V9), rank=1, display_name=V9_NAME, pitch=""),)
        )


DIRECTORY = VehicleDirectory(refs=(VehicleRef(vehicle_id=V9, display_name=V9_NAME),))


def _after_vf9_state(**changes: Any) -> CoreState:
    """State ngay sau lượt "thông tin xe vf9": chặng VẪN là GREETING (lượt tra cứu
    không đổi chặng) và VF 9 được nhớ ở `INTEREST_VEHICLE`."""

    base: dict[str, Any] = {"turn_count": 1, "slots": {SlotName.INTEREST_VEHICLE: V9}}
    base.update(changes)
    return CoreState(session_id="s1", **base)


TRANSCRIPT_AFTER_VF9 = (_Msg("USER", "thông tin xe vf9"), _Msg("ASSISTANT", VF9_CLOSING))


async def _understand(message: str, fake: _FakeUnderstander, *, state: CoreState, transcript=TRANSCRIPT_AFTER_VF9):
    result = await understand(
        state=state, transcript=transcript, user_message=message, vehicles=DIRECTORY, understander=fake
    )
    return result.understanding


async def _reply_text(message: str, state: CoreState, u: Understanding, transcript=TRANSCRIPT_AFTER_VF9) -> str:
    decision = decide(state, u)
    result = await act(
        decision.action,
        decision.state_after,
        AgentServices(catalog_browse=_Catalog()),
        run_id=None,
        customer_id="c1",
        user_message=message,
        transcript=transcript,
    )
    return result.text


# ------------------------------------------------------------------ 1. lượt VF 9


def _vf9_overview() -> VehicleOverview:
    """Dữ liệu đúng kiểu log lỗi: đoạn ghế Plus có ở CẢ highlights lẫn features,
    một câu marketing "ổ gà ổ voi", gạch đầu dòng "- Bản Plus" dính giữa câu."""

    return VehicleOverview(
        vehicle_name="VF 9",
        price_variants=[
            PriceVariant(
                vehicle_id=UUID(V9),
                variant_name="Eco",
                amount_vnd=Decimal("1348000000"),
                price_type="LIST",
                region_code="VN",
            ),
            PriceVariant(
                vehicle_id=UUID(V9),
                variant_name="Plus",
                amount_vnd=Decimal("1548000000"),
                price_type="LIST",
                region_code="VN",
            ),
        ],
        dimensions=DimensionsInfo(
            length_mm=5118, width_mm=2254, height_mm=1696, wheelbase_mm=3150, ground_clearance_mm=197
        ),
        highlights=[
            EvidenceItem(content=f"{SEAT_PARAGRAPH}. Xe rộng rãi cho cả gia đình.", evidence_id="h1"),
            EvidenceItem(
                content="Khoảng sáng gầm cao giúp xe tự tin vượt qua ổ gà ổ voi trên mọi cung đường Việt Nam.",
                evidence_id="h2",
            ),
        ],
        safety_systems=[EvidenceItem(content="Xe có ABS, EBD và ESC tiêu chuẩn.", evidence_id="s1")],
        features=[
            EvidenceItem(content=f"{SEAT_PARAGRAPH}.", evidence_id="f1"),
            EvidenceItem(
                content="Hệ thống 13 loa cao cấp cho âm thanh sống động - Bản Plus có thêm cửa sổ trời toàn cảnh.",
                evidence_id="f2",
            ),
        ],
    )


def test_1_thong_tin_vf9_khong_trung_moi_muc_mot_lan_dung_mot_cau_hoi() -> None:
    feature_groups = (("An toàn", "ADAS giữ làn"), ("Tiện nghi", "Ghế bọc da, điều hòa tự động"))
    answer = render_overview_response(_vf9_overview(), feature_groups=feature_groups)

    # Không đoạn nào lặp lại, không câu marketing lạc đề.
    assert answer.count(SEAT_PARAGRAPH) <= 1
    assert "ổ gà" not in answer
    # Mỗi mục lớn đúng MỘT lần; dòng "Tiện nghi" cũng chỉ một lần.
    for heading in ("Thông số kỹ thuật", "Nội thất & Tiện nghi", "Trang bị", "Giá bán"):
        assert answer.count(f"**{heading}**") <= 1
    assert answer.count("**Tiện nghi**") == 1
    assert answer.count("**An toàn**") == 1
    # Gạch đầu dòng không còn dính giữa câu.
    assert all(" - Bản" not in line for line in answer.splitlines())
    # Giá tách theo phiên bản vì catalog có hai bản.
    assert "**Eco**" in answer and "**Plus**" in answer
    # Bảng không tự hỏi; câu kết do act nối vào là câu hỏi DUY NHẤT của lượt.
    closing = render.closing_question(
        _after_vf9_state(), vehicle_name="VF 9", has_tco=False, has_booking=False, recommended_names=("VF 9",)
    )
    full = f"{answer}\n\n{closing}"
    assert full.count("?") == 1 and full.rstrip().endswith("?")
    assert len(answer.split()) <= 250


# ------------------------------------------------------- 2. "ok xe đẹp đấy"


async def test_2_ok_xe_dep_day_la_feedback_giu_vf9_khong_gioi_thieu_lai() -> None:
    state = _after_vf9_state()
    # LLM hay đọc câu này thành CONFIRM dù bot không chờ câu trả lời nào.
    u = await _understand("ok xe đẹp đấy", _FakeUnderstander("CONFIRM"), state=state)

    assert u.conversational == ConversationalIntent.FEEDBACK_POSITIVE
    assert u.dialogue_act is DialogueAct.SOCIAL
    decision = decide(state, u)
    assert decision.state_after.slots[SlotName.INTEREST_VEHICLE] == V9

    text = await _reply_text("ok xe đẹp đấy", state, u)
    assert INTRO not in text
    assert "VF 9" in text
    assert text.count("?") == 1


# ---------------------------------------------------------------- 3. "đắt quá"


async def test_3_dat_qua_sau_vf9_la_feedback_negative() -> None:
    u = await _understand("đắt quá", _FakeUnderstander("SOCIAL"), state=_after_vf9_state())

    assert u.conversational == ConversationalIntent.FEEDBACK_NEGATIVE
    text = await _reply_text("đắt quá", _after_vf9_state(), u)
    assert INTRO not in text and text.count("?") == 1


# ------------------------------------------------------------ 4. "ok" = đồng ý


async def test_4_ok_sau_cau_hoi_co_khong_lai_thu_la_ack_va_vao_luong_dat_lich() -> None:
    transcript = (_Msg("ASSISTANT", "Dạ VF 9 rất rộng ạ. Em đặt lịch lái thử cho anh/chị nhé?"),)
    state = _after_vf9_state()
    u = await _understand("ok", _FakeUnderstander("UNCLEAR"), state=state, transcript=transcript)

    assert u.conversational == ConversationalIntent.ACK
    assert (u.dialogue_act, u.intent) == (DialogueAct.REQUEST, Intent.TEST_DRIVE)
    assert isinstance(decide(state, u).action, ShowroomOptions)


# ---------------------------------------------------------------- 5. "chào em"


async def test_5_chao_em_luot_dau_la_greeting_luot_5_khong_gioi_thieu_lai() -> None:
    fresh = CoreState(session_id="s1")
    first = await _understand("chào em", _FakeUnderstander("SOCIAL"), state=fresh, transcript=())
    assert first.conversational == ConversationalIntent.GREETING
    assert await _reply_text("chào em", fresh, first, transcript=()) == render.GREETING_TEXT

    later = _after_vf9_state(turn_count=4)
    fifth = await _understand("chào em", _FakeUnderstander("SOCIAL"), state=later)
    text = await _reply_text("chào em", later, fifth)
    assert INTRO not in text


# ------------------------------------------------- 6. câu hỏi nghiệp vụ thắng


async def test_6_xe_dep_nhung_gia_bao_nhieu_thi_intent_gia_thang() -> None:
    fake = _FakeUnderstander("REQUEST", "CATALOG_LOOKUP", slots=RawSlots(vehicle_names=(V9_NAME,)))
    u = await _understand("xe đẹp nhưng giá bao nhiêu", fake, state=_after_vf9_state())

    assert u.conversational == ""
    assert (u.dialogue_act, u.intent) == (DialogueAct.REQUEST, Intent.CATALOG_LOOKUP)


# ------------------------------------------------ 7. HITL: lớp này im lặng


async def test_7_dang_cho_tu_van_vien_thi_lop_hoi_thoai_khong_tra_loi() -> None:
    state = _after_vf9_state(stage=Stage.HANDED_OFF)
    u = Understanding(
        dialogue_act=DialogueAct.SOCIAL, intent=Intent.NONE, conversational=ConversationalIntent.FEEDBACK_POSITIVE
    )

    assert isinstance(decide(state, u).action, Silent)


# ------------------------------------------------ writer LLM: lưới an toàn


class _Writer:
    def __init__(self, text: str) -> None:
        self.text = text
        self.system_prompts: list[str] = []

    async def write(self, *, system_prompt: str, user_prompt: str) -> str | None:
        self.system_prompts.append(system_prompt)
        return self.text


async def test_writer_nap_persona_va_cau_bia_so_bi_thay_bang_mau() -> None:
    from src.agents.domain.conversational import ConversationContext
    from src.agents.services.conversational import handle_conversational

    context = ConversationContext(active_vehicle="VF 9", has_bot_turn=True)
    good = _Writer("Dạ chuẩn luôn ạ, VF 9 nhìn ngoài bề thế lắm 😄 Anh/chị định dùng xe cho gia đình hay công việc ạ?")
    text = await handle_conversational(
        ConversationalIntent.FEEDBACK_POSITIVE, context, user_message="ok xe đẹp đấy", writer=good
    )
    assert text == good.text
    assert "Vivi" in good.system_prompts[0] and "VF 9" in good.system_prompts[0]

    # Con số không có trong dữ kiện xe = bịa → rơi về mẫu câu tất định.
    liar = _Writer("Dạ VF 9 chạy 900 km một lần sạc đấy ạ, anh/chị lái thử không?")
    fallback = await handle_conversational(
        ConversationalIntent.FEEDBACK_POSITIVE, context, user_message="ok xe đẹp đấy", writer=liar
    )
    assert "900" not in fallback and fallback.count("?") == 1
