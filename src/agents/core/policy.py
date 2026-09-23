"""Bảng quyết định lõi v2 — thuần, không I/O (spec mục 6).

Luật xét theo thứ tự, dừng ở luật đầu khớp. Mọi thay đổi luật phải có một
hàng test ở `tests/agents/unit/core/test_policy.py` lấy từ câu prod thật.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from src.agents.core.actions import (
    CONFIRM_BOOK,
    CONFIRM_OFFER,
    IRREVERSIBLE,
    LOOKUP_BROWSE,
    LOOKUP_LOOKUP,
    LOOKUP_POLICY,
    OPEN_REASON_UNCLEAR,
    PENDING_PROFILE,
    PENDING_SHOWROOM_SLOT,
    PENDING_VEHICLE,
    REASON_FIRST,
    REASON_RETRY,
    REASON_REVISED,
    REASON_SLOTS_CHANGED,
    TEMPLATE_CANCELLED,
    TEMPLATE_CHOSEN_SUMMARY,
    TEMPLATE_CLARIFY,
    TEMPLATE_CONCERN,
    TEMPLATE_SOCIAL,
    TEMPLATE_STOPPED,
    UNCLEAR_KEY,
    Action,
    Ask,
    Book,
    Compare,
    Decision,
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
from src.agents.core.state import (
    CoreState,
    DialogueAct,
    Intent,
    Pending,
    PendingKind,
    Stage,
    Understanding,
    can_transition,
)
from src.agents.core.validate import BUTTON_PREFIX
from src.agents.domain.values import SlotName, SlotValue

MAX_ASKS = 2
LOW_CONFIDENCE = 0.6
MAX_UNCLEAR = 2
FEATURE_SLOT = SlotName.HABIT_NEED_TAGS


#: Hai giá trị `vehicle_type` LLM có thể trả — bất kỳ giá trị nào khác (rỗng hoặc
#: LLM đoán chệch, vd "xe may dien") bị coi là CHƯA có loại xe (finding 5).
_KNOWN_VEHICLE_TYPES = frozenset({"CAR", "ELECTRIC_MOTORBIKE"})

#: Slot thuộc việc TƯ VẤN. Có BẤT KỲ cái nào là đủ để chạy đề xuất — thiếu phần
#: còn lại thì `act.build_criteria` suy, KHÔNG hỏi thêm (Sếp chốt 2026-08-29).
ADVISORY_SLOTS: tuple[SlotName, ...] = (
    SlotName.VEHICLE_TYPE,
    SlotName.BUDGET_MAX_VND,
    SlotName.PURPOSE,
    SlotName.PASSENGER_COUNT,
    SlotName.REQUIRED_RANGE_KM,
    SlotName.HABIT_NEED_TAGS,
)

#: Slot đủ sức LÀM LẠI bộ lọc khi khách nói thêm giữa chừng — `ADVISORY_SLOTS`
#: trừ loại xe (đổi loại xe có đường riêng, xem `_switched_vehicle_type`).
_ANSWER_ADVISORY_SLOTS = frozenset(ADVISORY_SLOTS) - {SlotName.VEHICLE_TYPE}

INTERRUPT_INTENTS = frozenset(
    {Intent.CATALOG_LOOKUP, Intent.COMPARE, Intent.NEARBY, Intent.POLICY_QA, Intent.VEHICLE_QA}
)
_LOOKUP_INTENTS = INTERRUPT_INTENTS | {Intent.CATALOG_BROWSE}
_ANSWER_ACTS = frozenset({DialogueAct.SLOT_ANSWER, DialogueAct.CHOICE, DialogueAct.CONFIRM, DialogueAct.REJECT})
#: Intent cần một chiếc xe cụ thể để chạy công cụ (không đoán giữa nhiều đề xuất).
_VEHICLE_INTENTS = frozenset({Intent.COST, Intent.ON_ROAD_PRICE, Intent.TEST_DRIVE, Intent.OFFER})
#: Chặng SAU khi khách đã chốt một chiếc xe — từ đây lõi không quay lại đề xuất
#: nữa trừ khi khách nói thẳng là muốn (u.intent ADVISORY hoặc RESTART).
_POST_CHOICE_STAGES = frozenset({Stage.CHOSEN, Stage.COSTING, Stage.SCHEDULING})
#: Intent nhắc tới một chiếc xe cụ thể → nhớ lại xe đó cho lượt sau (finding I3).
#: COMPARE KHÔNG có ở đây: so sánh mở lại lựa chọn (xem `_lookup_decision`).
_REMEMBER_INTENTS = frozenset({Intent.CATALOG_LOOKUP, Intent.VEHICLE_QA})


def decide(state: CoreState, u: Understanding) -> Decision:
    state = state.with_(turn_count=state.turn_count + 1)
    #: Ảnh chụp slot đầu lượt — cuối lượt so lại để biết khách có đổi tiêu chí
    #: không (`Recommend.reason`).
    slots_before = dict(state.slots)

    # 1. TVV đang cầm phiên.
    if state.stage is Stage.HANDED_OFF:
        return Decision(Silent(), state)

    # 1b. Khách xin gặp người thật: dừng ngay, không hỏi thêm, xoá câu treo.
    # Sếp 2026-08-30: "khách yêu cầu gặp tư vấn viên thì TVV nhắn, agent không
    # được phép hoạt động nữa" — `Handoff` ghi ownership, các lượt sau là `Silent`.
    if u.intent is Intent.HANDOFF:
        return Decision(Handoff(reason="requested"), state.with_(stage=Stage.HANDED_OFF, pending=None))

    # 2. Làm lại từ đầu.
    if u.dialogue_act is DialogueAct.RESTART:
        fresh = state.with_(
            stage=Stage.COLLECTING,
            intent=Intent.ADVISORY,
            slots={},
            pending=None,
            chosen_vehicle_id=None,
            recommended_ids=(),
            ask_counts={},
        )
        return _ask(fresh, PENDING_PROFILE, PendingKind.SLOT)

    # Bất kỳ act nào không phải UNCLEAR đều reset đếm UNCLEAR — kể cả SOCIAL (finding 4),
    # nên luôn chạy TRƯỚC nhánh xã giao.
    if u.dialogue_act is not DialogueAct.UNCLEAR:
        state = _reset_unclear(state)

    # 3. Xã giao: giữ mạch.
    if u.dialogue_act is DialogueAct.SOCIAL:
        # `stage` đi kèm để `render` biết đây là lời chào ĐẦU (chào đầy đủ, nói
        # rõ giúp được gì) hay một câu xã giao giữa chừng (đáp ngắn, giữ mạch).
        return Decision(
            Reply(
                template=TEMPLATE_SOCIAL, args={"stage": state.stage.value}, resume_pending=state.pending is not None
            ),
            state,
        )

    # 3a'. Khách nói THÔI ("t ko muốn tư vấn nữa", "thôi khỏi"): dừng hẳn việc
    # đẩy đề xuất. Không có nhánh này thì REJECT ở `RECOMMENDED` rơi xuống
    # `_advise` và khách nhận lại ĐÚNG hai thẻ xe vừa từ chối (đo trên máy
    # 2026-09-23) — đọc như bot không nghe thấy gì.
    #
    # Chỉ bắt lượt REJECT KHÔNG còn câu treo: REJECT trả lời một `pending` là
    # câu trả lời cho câu hỏi đó (huỷ lái thử, bỏ qua tính năng), đã có đường
    # riêng ở nhánh pending bên dưới. Và không đổi chặng: khách quay lại là mạch
    # cũ còn nguyên.
    if u.stop_asked and state.pending is None and not u.slots:
        return Decision(Reply(template=TEMPLATE_STOPPED), state)

    # 3b. Câu LO NGẠI ("pin chai bán ai mua", "hầm chung cư chưa có trụ sạc"):
    # trả lời trấn an rồi giữ mạch — cùng khuôn SOCIAL. Log prod 2026-08-31:
    # thiếu nhánh này, câu lo ngại rơi vào câu mặc định của chặng ("muốn xem kỹ
    # mẫu nào ạ?") — nỗi lo bị nuốt trong im lặng. KHÔNG chen khi lượt là CÂU
    # TRẢ LỜI slot ("chung cư không có chỗ sạc" đáp câu hỏi sạc-tại-nhà): slot
    # phải đi đường thường, và vẫn ghi slot lượt này qua `_merge_slots`.
    if u.concern_topic and u.dialogue_act not in _ANSWER_ACTS:
        state = _merge_slots(state, dict(u.slots))
        return Decision(
            Reply(
                template=TEMPLATE_CONCERN,
                args={"topic": u.concern_topic},
                resume_pending=state.pending is not None,
            ),
            state,
        )

    # C4b: đang treo "mẫu nào?" cho một VIỆC CẦN XE mà khách KỂ NHU CẦU
    # ("tầm 700 triệu, nhà 4 người") — bot vừa mời họ hai lối "chọn mẫu hoặc cho
    # em nhu cầu để em tư vấn" (Sếp 2026-08-31): kể nhu cầu là chọn lối tư vấn,
    # vào thẳng luồng đề xuất với slot vừa kể. Xe chốt xong khách bấm nút "Đặt
    # lái thử" là quay lại đúng việc.
    if (
        state.pending is not None
        and state.pending.kind is PendingKind.CHOICE
        and state.pending.key == PENDING_VEHICLE
        and state.intent in _VEHICLE_INTENTS
        and not u.vehicle_ids
        and u.choice_ref is None
        and any(slot in _ANSWER_ADVISORY_SLOTS for slot in u.slots)
    ):
        state = _merge_slots(state.with_(pending=None), dict(u.slots))
        return _advise(state, slots_before)

    # C4: đang treo "mẫu nào?" cho một VIỆC CẦN XE mà khách trả bằng ĐỊA DANH
    # ("Hà Nội" sau "Tôi muốn đăng ký lái thử") — khách tưởng bot hỏi nơi. Ghi
    # tỉnh (lịch lái thử dùng ngay), hỏi lại câu chọn mẫu — giờ đã mang tên
    # việc. Trước đây lượt này rơi sang Nearby/OUT_OF_SCOPE rồi văng TVV
    # (log prod 2026-08-31 06:53).
    if (
        state.pending is not None
        and state.pending.kind is PendingKind.CHOICE
        and state.pending.key == PENDING_VEHICLE
        and state.intent in _VEHICLE_INTENTS
        and SlotName.REGISTRATION_PROVINCE in u.slots
        and not u.vehicle_ids
        and u.choice_ref is None
    ):
        state = _merge_slots(state, dict(u.slots))
        return _reask(state, state.pending)

    # C2 (1/2): "ô tô điện" bị LLM gắn REQUEST/INTERRUPT + CATALOG_BROWSE trong lúc
    # đang treo câu hỏi vẫn là câu TRẢ LỜI — đưa về đúng luật 4 thay vì đổ catalog.
    if (
        state.pending is not None
        and u.intent is Intent.CATALOG_BROWSE
        and u.dialogue_act not in _ANSWER_ACTS
        and SlotName.VEHICLE_TYPE in u.slots
    ):
        u = replace(u, dialogue_act=DialogueAct.SLOT_ANSWER)

    # C3: câu trả lời cho MỘT SLOT đang treo mà LLM gắn act tra cứu vẫn là câu
    # TRẢ LỜI. Lượt prod: `act` hỏi tỉnh cho giá lăn bánh (`_on_road_price`) hay
    # cho lái thử (`_ask_province`), khách gõ "Hà Nội"/"Đà Nẵng" → LLM trả
    # `REQUEST/INTERRUPT + NEARBY`. Hai act đó KHÔNG nằm trong `_ANSWER_ACTS`
    # nên luật 4 không chạy, luật 5 coi là chen ngang và khách nhận "Dạ Quý
    # khách muốn tìm loại địa điểm nào ạ?". Tín hiệu ở đây CHẶT hơn C2: slot vừa
    # rút ra phải TRÙNG ĐÚNG khoá đang hỏi, nên chen ngang thật (không mang slot
    # nào của câu treo) vẫn đi đường chen ngang.
    if (
        state.pending is not None
        and state.pending.kind is PendingKind.SLOT
        and u.dialogue_act not in _ANSWER_ACTS
        and any(slot.value == state.pending.key for slot in u.slots)
    ):
        u = replace(u, dialogue_act=DialogueAct.SLOT_ANSWER)

    # C4: câu trả lời TỈNH trong lúc đang treo một câu CHỌN vẫn là câu trả lời.
    #
    # Lượt prod vòng 9: lõi treo câu chọn showroom/khung giờ (hoặc câu "chọn mẫu
    # nào"), khách gõ "Hà Nội" → LLM trả `REQUEST/INTERRUPT + NEARBY`, luật 4
    # không nhận và luật 5 chạy `Nearby` ("Quý khách muốn tìm loại địa điểm nào
    # ạ?"). Cùng một lưới với C3, khác ở chỗ pending là CHOICE nên C3 không với
    # tới. Đòi có xe đã chốt để chắc chắn lượt này thuộc việc đặt lịch.
    if (
        state.pending is not None
        and state.pending.kind is PendingKind.CHOICE
        and u.dialogue_act not in _ANSWER_ACTS
        and state.chosen_vehicle_id is not None
        and SlotName.REGISTRATION_PROVINCE in u.slots
    ):
        u = replace(u, dialogue_act=DialogueAct.SLOT_ANSWER)

    # 4. Đang chờ trả lời.
    pending = state.pending
    if pending is not None and u.dialogue_act in _ANSWER_ACTS:
        # Slot đi kèm câu trả lời được ghi MỘT lần, vô điều kiện, cho cả ba loại
        # pending (finding I1: SLOT_ANSWER rơi vào pending CHOICE/CONFIRM trước
        # đây mất trắng slot vì chỉ nhánh pending=SLOT mới merge).
        state = _merge_slots(state, dict(u.slots))
        if pending.kind is PendingKind.CONFIRM:
            if u.dialogue_act is DialogueAct.CONFIRM:
                treo = pending.options[0] if pending.options else ""
                return _run_irreversible(state.with_(pending=None), pending.key, treo)
            if u.dialogue_act is DialogueAct.REJECT:
                back = Stage.CHOSEN if state.chosen_vehicle_id else Stage.RECOMMENDED
                return Decision(
                    Reply(template=TEMPLATE_CANCELLED), state.with_(pending=None, stage=_to(state.stage, back))
                )
        if pending.kind is PendingKind.CHOICE:
            if u.dialogue_act is DialogueAct.CHOICE and pending.key == PENDING_SHOWROOM_SLOT and u.choice_ref:
                if state.chosen_vehicle_id is None:
                    return _ask_vehicle(state, u)
                label = _label_for(pending, u.choice_ref)
                return _guard(
                    state.with_(pending=None),
                    Book(vehicle_id=state.chosen_vehicle_id, choice_ref=u.choice_ref),
                    u,
                    key=CONFIRM_BOOK,
                    treo=u.choice_ref,
                    labels=(label,) if label else (),
                )
            chosen = _pick_vehicle(state, u)
            if chosen is not None:
                return _choose_with_slots(state.with_(pending=None), chosen, u)
            token = _booking_token(u)
            if token:
                return Decision(Book(vehicle_id=state.chosen_vehicle_id or "", choice_ref=token), state)
            if (
                SlotName.REGISTRATION_PROVINCE in u.slots
                and state.chosen_vehicle_id is not None
                and state.intent in _VEHICLE_INTENTS
            ):
                # Khách trả lời TỈNH cho một câu đang treo là "chọn cái nào":
                # đó là tỉnh của đúng việc đang làm (đặt lịch, giá lăn bánh), và
                # xe thì đã chốt rồi. Hỏi lại "muốn xem kỹ mẫu nào ạ?" ở đây là
                # đúng vòng lặp prod vòng 9 — khách gõ "Hà Nội" và nhận lại y
                # nguyên câu hỏi mẫu xe.
                return _run_vehicle_intent(
                    state.with_(pending=None), u, intent=state.intent, vehicle=state.chosen_vehicle_id
                )
            if u.dialogue_act is DialogueAct.CHOICE:
                # Hỏi lại "mẫu nào?" cũng phải qua trần của `_ask_vehicle` (C1),
                # nếu không thì vòng lặp hỏi–đáp không bao giờ thoát.
                if pending.key == PENDING_VEHICLE:
                    return _ask_vehicle(state, u)
                return _ask_capped(
                    state, pending.key, PendingKind.CHOICE, options=pending.options, labels=pending.labels
                )
        if pending.kind is PendingKind.SLOT:
            if pending.key == PENDING_PROFILE and u.dialogue_act is DialogueAct.SLOT_ANSWER and not u.slots:
                # Khách có đáp, nhưng bộ hiểu ý không rút ra được slot nào: đó là
                # KHÔNG HIỂU, không phải "đã thu thập xong". Đi đúng đường UNCLEAR
                # để có trần và có đường chuyển TVV, thay vì đề xuất mù.
                return _unclear(state, slots_before, u)
            if u.dialogue_act is DialogueAct.REJECT and pending.key == FEATURE_SLOT.value:
                state = _merge_slots(state, {FEATURE_SLOT: []}).with_(pending=None)
            elif u.dialogue_act is DialogueAct.SLOT_ANSWER:
                if u.features_all and pending.key == FEATURE_SLOT.value:
                    # policy không biết danh mục tính năng thật (finding 6) — nếu tầng act
                    # chưa kịp điền pending.options thì "có tất cả" = không chọn gì cả.
                    state = _merge_slots(state, {FEATURE_SLOT: list(pending.options) if pending.options else []})
                state = state.with_(pending=None)
            elif u.dialogue_act is DialogueAct.CHOICE:
                # CHOICE tới trong lúc đang chờ SLOT vẫn phải giữ slot đi kèm (finding 2:
                # MỌI lượt CHOICE, không riêng nhánh pending=CHOICE).
                chosen = _pick_vehicle(state, u)
                if chosen is not None:
                    return _choose_with_slots(state.with_(pending=None), chosen, u)
        # rơi xuống luật 6 với intent đang theo.
        #
        # Câu TRẢ LỜI cho slot đang treo THẮNG mọi intent tra cứu LLM gán kèm.
        # Lượt prod: treo `registration_province`, khách gõ "Hà Nội" → LLM trả
        # `SLOT_ANSWER + NEARBY`; luật 6 chạy `Nearby` và khách nhận "Dạ Quý
        # khách muốn tìm loại địa điểm nào ạ?" thay vì khung giờ lái thử. Cùng
        # một lưới với C2 cho CATALOG_BROWSE, khác ở tín hiệu: slot vừa điền
        # ĐÚNG là slot đang hỏi (hoặc một câu SLOT_ANSWER có rút ra slot).
        if _answered_pending(pending, u) and state.intent is not Intent.NONE:
            u = _with_intent(u, state.intent)
        else:
            u = _with_intent(u, state.intent if u.intent in {Intent.NONE, Intent.CATALOG_BROWSE} else u.intent)
    elif u.dialogue_act is DialogueAct.CHOICE:
        state = _merge_slots(state, dict(u.slots))
        chosen = _pick_vehicle(state, u)
        if chosen is not None:
            return _choose_with_slots(state, chosen, u)
        token = _booking_token(u)
        if token:
            # Nút khung giờ tới khi lõi KHÔNG còn treo câu chọn giờ (phiên đã đi
            # tiếp, tab cũ, hoặc mã bịa). Lượt prod LP21 rơi xuống `_ask_vehicle`
            # và khách nhận "Anh/chị muốn xem mẫu nào ạ?" — một câu không dính gì
            # tới việc họ vừa bấm. Mã có CHỮ KÝ nên chỗ duy nhất đọc được nó là
            # `act._book`: nó kiểm chữ ký rồi nói thật khi mã đã hết hạn.
            return Decision(Book(vehicle_id=state.chosen_vehicle_id or "", choice_ref=token), state)
        return _ask_vehicle(state, u)
    else:
        state = _merge_slots(state, dict(u.slots))

    # 4b. Đổi LOẠI XE giữa chừng là làm lại từ đầu cho đúng loại.
    #
    # Lượt prod LP03: ở `RECOMMENDED` với ô tô, khách gõ "thôi xe máy đi" — slot
    # được ghi đúng, nhưng `recommended_ids`/`chosen_vehicle_id` cũ vẫn còn nên
    # lượt sau lõi đọc lại VF 6. Danh sách cũ và mẫu đã chốt thuộc về loại xe cũ:
    # giữ chúng lại là giữ nguyên câu trả lời cho một câu hỏi khách vừa rút lại.
    switched = _switched_vehicle_type(state, slots_before, u)
    if switched:
        after = state.with_(
            intent=Intent.ADVISORY,
            recommended_ids=(),
            chosen_vehicle_id=None,
            pending=None,
            stage=_to(state.stage, Stage.RECOMMENDED),
        )
        return Decision(Recommend(reason=REASON_SLOTS_CHANGED, switched_type=switched), after)

    # 5. Chen ngang tra cứu khi đang có pending: làm, giữ pending, nối lại.
    # CATALOG_BROWSE bị loại khỏi đây — xem C2 ở luật 6.
    if (
        state.pending is not None
        and u.intent is not Intent.CATALOG_BROWSE
        and (u.dialogue_act is DialogueAct.INTERRUPT or u.intent in INTERRUPT_INTENTS)
    ):
        found = _lookup_decision(state, u, resume=True)
        if found is not None:
            return found

    # 5ba. Câu hỏi NGOÀI phạm vi về chiếc xe đang xem → nói thật, kèm tầm chạy.
    #
    # Lượt prod vòng 9: "VF3 thì nên đi du lịch ở Việt Nam, ở đâu" nhận về "em
    # chưa có mẫu nào khác hợp hơn ạ — gần nhất vẫn là VF 3". Câu trả lời sai
    # chủ đề còn tệ hơn một lời từ chối thẳng thắn.
    #
    # Đứng TRƯỚC 5b và 5c (đổi ở vòng 10): câu hỏi điểm đến thường kéo theo một
    # `purpose` do LLM rút ra ("du lịch"), và cả hai luật kia đều nhận lượt mang
    # tiêu chí — 5b đọc thành lời xin CHỈNH đề xuất, 5c thành một bản đánh giá
    # độ phù hợp. Slot vẫn được ghi ở `_merge_slots` phía trên, nên đặt luật này
    # lên trước chỉ đổi CÂU TRẢ LỜI, không mất lời kể nhu cầu nào.
    if u.off_topic_asked and u.intent in {Intent.NONE, Intent.ADVISORY} and state.intent not in _VEHICLE_INTENTS:
        target = _target_vehicle(state, u, fallback_recommended=False)
        if target is not None:
            return Decision(ScopeNote(vehicle_id=target), state)

    # 5a'. Vừa báo chi phí xong, khách sửa số km ("ngày anh đi 60km cơ") HOẶC
    # nhắc tỉnh ("anh ở Đà Nẵng cơ") → tính LẠI ngay theo thông tin mới. Slot đã
    # ghi ở `_merge_slots`; không có luật này thì lượt rơi xuống nhánh chung và
    # trả lại đúng con số cũ (probe V2-32). Tỉnh vào cùng luật từ 2026-08-31:
    # thẻ chi phí gộp cả giá lăn bánh (tỉnh đổi là lệ phí biển đổi), và cờ
    # `refreshed_*` cho `act._tco` nói "em đã cập nhật lại bảng" thay vì đọc
    # một bài dẫn mới — client đang thay số tại chỗ trên thẻ cũ.
    if (
        state.stage is Stage.COSTING
        and state.chosen_vehicle_id
        # Slot phải ĐỔI GIÁ TRỊ thật: LLM hay chép lại slot cũ từ transcript,
        # "giá lăn bánh thì sao" mà kèm km/tỉnh cũ cũng từng kích nhầm chữ
        # "đã cập nhật" (probe 2026-08-31 lượt 4/6).
        # So với slots_before: tới đây slot của lượt ĐÃ merge vào state, so với
        # state là luôn bằng nhau (bẫy 2026-08-31 làm luật câm hoàn toàn).
        and any(
            key in u.slots and u.slots[key] != slots_before.get(key)
            for key in (SlotName.REQUIRED_RANGE_KM, SlotName.REGISTRATION_PROVINCE)
        )
        # ON_ROAD_PRICE cũng vào đây: lăn bánh đã là CÙNG thẻ chi phí, và lối (c)
        # của understand ép intent này khi khách đính chính tỉnh giữa chừng —
        # thiếu nó thì lượt "à anh chuyển vào Đà Nẵng" đọc lại bài dẫn thay vì
        # "em đã cập nhật" (probe prod 2026-08-31, lượt 5/6).
        and u.intent in {Intent.NONE, Intent.COST, Intent.ON_ROAD_PRICE}
        and u.dialogue_act in {DialogueAct.SLOT_ANSWER, DialogueAct.REQUEST, DialogueAct.UNCLEAR}
    ):
        return Decision(
            Tco(
                vehicle_id=state.chosen_vehicle_id,
                refreshed_km=SlotName.REQUIRED_RANGE_KM in u.slots
                and u.slots[SlotName.REQUIRED_RANGE_KM] != slots_before.get(SlotName.REQUIRED_RANGE_KM),
                refreshed_province=SlotName.REGISTRATION_PROVINCE in u.slots
                and u.slots[SlotName.REGISTRATION_PROVINCE] != slots_before.get(SlotName.REGISTRATION_PROVINCE),
            ),
            state.with_(intent=Intent.COST),
        )

    # 5b. Ở chặng thu thập/đề xuất, một lượt mang TIÊU CHÍ mới là lời chỉnh bộ
    # lọc — không bao giờ là câu hỏi lại "muốn xem kỹ mẫu nào".
    #
    # Lượt prod LP03/LP07: sau RESTART, "700 triệu" và "đi làm" về `UNCLEAR` kèm
    # slot đọc được. Luật 6 xét UNCLEAR TRƯỚC nên cả hai rơi vào `_unclear`, và ở
    # `RECOMMENDED` nhánh đó trả câu hỏi lại CHOICE — đúng lúc khách vừa cho lõi
    # thứ nó cần. Điều kiện chặt hai đầu: chỉ khi lõi KHÔNG đang theo việc nào
    # khác (khách nói "40km" giữa lượt tính chi phí là câu trả lời cho việc đó),
    # và lượt phải có slot tư vấn thật (loại xe một mình đã có đường riêng ở 4b).
    if (
        state.stage in {Stage.RECOMMENDED, Stage.COLLECTING}
        and u.dialogue_act in {DialogueAct.SLOT_ANSWER, DialogueAct.UNCLEAR}
        and u.intent in {Intent.NONE, Intent.ADVISORY}
        and state.intent in {Intent.NONE, Intent.ADVISORY}
        and any(slot in _ANSWER_ADVISORY_SLOTS for slot in u.slots)
    ):
        return _advise(state.with_(intent=Intent.ADVISORY), slots_before)

    # 5bb. "Làm sao để tôi chốt VF 3" → các BƯỚC đi tiếp, không phải đề xuất lại.
    #
    # Lượt prod vòng 9: câu đó về một lượt tư vấn và lõi trả `SAME_PICK` — đọc
    # lại đúng chiếc khách vừa nói là muốn chốt, kèm một cái menu. Khách đang ở
    # bước cuối của phễu mà lõi đẩy họ về bước đầu.
    #
    # Chặn hai đầu như mọi cửa tất định khác: lượt không mang một việc cam kết
    # nào (đang tính chi phí thì "cần gì nữa" là câu của việc đó), và phải trỏ
    # ra được MỘT chiếc xe — không có xe thì không có bước nào để kể.
    if u.next_steps_asked and u.intent in {Intent.NONE, Intent.ADVISORY} and state.intent not in _VEHICLE_INTENTS:
        target = _target_vehicle(state, u, fallback_recommended=False)
        if target is not None:
            return Decision(NextSteps(vehicle_id=target), _promote_to_chosen(state, target))

    # 5c. ĐÃ CHỐT xe mà khách kể THÊM nhu cầu → đánh giá lại CHÍNH chiếc đó.
    #
    # Lượt prod vòng 9: đã chọn VF 2, khách gõ "gia đình tôi có 4 người, tôi
    # muốn sử dụng đi chơi xa" và lõi đáp "em vẫn thấy VF 2 hợp nhất" (một lượt
    # `SAME_PICK` trơ). Khách vừa đưa thêm hai tiêu chí mà câu trả lời không
    # nhắc tới cái nào: đó là lượt nói cho có. Không bao giờ được `SAME_PICK`
    # trơ ngay sau khi khách bổ sung nhu cầu.
    #
    # Điều kiện chặt: phải có xe đã chốt (không thì đường 5b/đề xuất lo), phải
    # có slot tư vấn THẬT trong lượt, và lõi không đang theo một việc cam kết
    # (nói "ngày đi 40 km" giữa lượt tính chi phí là trả lời cho việc đó).
    if (
        state.chosen_vehicle_id is not None
        and state.stage in _POST_CHOICE_STAGES
        and u.intent in {Intent.NONE, Intent.ADVISORY}
        and state.intent not in _VEHICLE_INTENTS
        and u.dialogue_act in {DialogueAct.SLOT_ANSWER, DialogueAct.REQUEST, DialogueAct.UNCLEAR}
        and any(slot in _ANSWER_ADVISORY_SLOTS for slot in u.slots)
    ):
        return Decision(
            FitCheck(vehicle_id=state.chosen_vehicle_id, alternative_ids=state.recommended_ids),
            state.with_(pending=None),
        )

    # 6. Theo intent.
    intent = u.intent if u.intent is not Intent.NONE else state.intent
    if u.dialogue_act is DialogueAct.UNCLEAR:
        if u.intent in _VEHICLE_INTENTS:
            # Bộ hiểu ý gọi được đúng tên việc (COST/TEST_DRIVE/…) nhưng không
            # đủ tự tin về hành vi. Vẫn phải NHỚ việc đó: prod (phiên 61c9dbbd)
            # cho thấy lượt "tính chi phí" về UNCLEAR nên `state.intent` kẹt ở
            # ADVISORY, và lượt sau khách đáp "ngày anh đi 30km" bị hiểu là xin
            # tư vấn lại — lõi đề xuất lại từ đầu giữa lúc đã chọn xong xe.
            state = state.with_(intent=u.intent)
        return _unclear(state, slots_before, u)

    # 6a. Đã chọn xe rồi: một câu trả lời rời KHÔNG mang intent là bổ sung cho
    # việc đang làm, không bao giờ là "tư vấn lại từ đầu".
    if (
        state.stage in _POST_CHOICE_STAGES
        and state.chosen_vehicle_id is not None
        and u.intent is Intent.NONE
        and u.dialogue_act in {DialogueAct.SLOT_ANSWER, DialogueAct.REQUEST}
        and intent not in _VEHICLE_INTENTS
        # Lời xin CHỈNH/ĐỔI xe ("xe khác đi") là một REQUEST được
        # `understand._refine_question` cứu vào `question` — không phải "câu trả
        # lời rời"; để nó đi tiếp xuống `_advise(refine=…)` như ở RECOMMENDED.
        # Nuốt nó ở đây là đọc lại tóm tắt chiếc khách vừa nói là KHÔNG muốn.
        # [LỆCH PLAN] Chỉ chừa REQUEST, KHÔNG chừa SLOT_ANSWER: "ngày anh đi
        # 30km" mà LLM quên rút slot cũng mang `question` (prod 61c9dbbd) — đẩy
        # lượt đó về đề xuất lại là đúng lỗi luật này sinh ra để chữa.
        and not (u.dialogue_act is DialogueAct.REQUEST and u.question.strip())
    ):
        # `state.intent` là một việc cam kết (COST/ON_ROAD_PRICE/TEST_DRIVE/
        # OFFER) thì rơi xuống nhánh dưới và chạy việc đó với slot vừa gộp.
        # Không phải thì xác nhận và mở lại ba lối đi — KHÔNG `Recommend`, và
        # KHÔNG rời chặng: khách vừa chốt xe, đẩy họ về danh sách đề xuất là
        # xoá công cả cuộc trò chuyện (prod, phiên 61c9dbbd).
        return Decision(Reply(template=TEMPLATE_CHOSEN_SUMMARY, args={"vehicle_id": state.chosen_vehicle_id}), state)

    # 6c. Khách GỌI TÊN XE đích danh mà lõi chưa có gì để lọc: nói về CHÍNH
    # những mẫu đó, đừng hỏi hồ sơ.
    #
    # Đo trên máy 2026-09-23: "không ý tôi là xe vf 2 và vf 3 ý" rồi "tư vấn lại
    # cho tôi xe vf2 và vf 3" — cả hai lượt đều đọc ra ĐÚNG hai xe, nhưng lõi
    # không có slot nào nên rơi xuống `_advise` → hỏi câu hồ sơ → chạm
    # `MAX_ASKS` → chuyển tư vấn viên. Khách nói rõ tên xe mà bị hỏi ngân sách
    # rồi bị đẩy sang người là lượt hỏng nặng nhất trong phiên đó.
    #
    # Điều kiện là lượt KHÔNG mang tiêu chí mới (`not u.slots`): "1 tỷ, chở 5
    # người, thích VF 8" vẫn phải chạy bộ lọc theo nhu cầu. Chỉ khi lượt CHỈ có
    # tên xe thì tên xe mới là toàn bộ ý khách.
    # Chỉ chen vào đường TƯ VẤN: `TEST_DRIVE`, `COST`, `COMPARE`, `CATALOG_LOOKUP`…
    # đều có nhánh riêng bên dưới và chúng biết dùng `vehicle_ids` đúng cách hơn.
    if (
        u.vehicle_ids
        # Chỉ xét slot TƯ VẤN (bỏ `vehicle_type`): LLM gắn kèm `vehicle_type=CAR`
        # cho gần như mọi lượt nhắc tên ô tô, nên `not u.slots` thẳng là điều kiện
        # không bao giờ đúng — đo trên máy 2026-09-23, luật này câm hoàn toàn.
        and not any(slot in _ANSWER_ADVISORY_SLOTS for slot in u.slots)
        and intent in {Intent.ADVISORY, Intent.NONE}
    ):
        if len(u.vehicle_ids) >= 2:
            # Hai mẫu trở lên → so sánh, và chúng thành bộ ứng viên của phiên
            # (cùng cách `_lookup_decision` xử lý một lượt COMPARE).
            picked = tuple(u.vehicle_ids[:3])
            return Decision(
                Compare(vehicle_ids=picked),
                state.with_(recommended_ids=picked, chosen_vehicle_id=None, pending=None),
            )
        return Decision(
            Lookup(mode=LOOKUP_LOOKUP, vehicle_ids=u.vehicle_ids, aspect=u.aspect),
            _remember_vehicle(state, u).with_(pending=None),
        )

    # 6b. Lời xin CHỈNH bản đề xuất thắng việc đang theo.
    #
    # `understand` điền `question` tất định cho lượt REQUEST/SLOT_ANSWER không
    # rút ra slot nào ở `RECOMMENDED`/`CHOSEN` (lượt prod: "rẻ hơn được không"
    # về `REQUEST, ADVISORY, slots={}, question=""`). Không có luật này thì khi
    # `state.intent` đang là một việc khác — VEHICLE_QA sau một lượt hỏi thông
    # số chẳng hạn — luật 6 lấy việc đó và đem lời xin đổi đi TRA THÔNG SỐ.
    if (
        state.stage is Stage.RECOMMENDED
        and state.recommended_ids
        and u.intent in {Intent.ADVISORY, Intent.NONE}
        and u.dialogue_act in {DialogueAct.SLOT_ANSWER, DialogueAct.REQUEST}
        and u.question.strip()
    ):
        return _advise(state.with_(intent=Intent.ADVISORY), slots_before, refine=u.question.strip())

    if intent is Intent.ADVISORY:
        # Đã có bản đề xuất mà khách còn nói thêm một yêu cầu ("rẻ hơn", "cốp
        # rộng hơn") thì đó là lời CHỈNH bản đó, không phải xin tư vấn lại. Vòng
        # chỉnh chạy cho tới khi khách chọn một mẫu (CHOICE) hoặc thôi không nói
        # thêm. Policy không đọc hiểu câu — nó chuyển nguyên văn cho `act`.
        refine = u.question.strip() if state.stage in {Stage.RECOMMENDED, Stage.CHOSEN} else ""
        return _advise(state.with_(intent=Intent.ADVISORY), slots_before, refine=refine)

    if intent is Intent.VEHICLE_QA:
        # Không còn danh sách chặng được phép (finding I7): chỉ cần trỏ ra được
        # xe thì trả lời, không thì hỏi "mẫu nào".
        target = _target_vehicle(state, u)
        if target is None:
            return _ask_vehicle(state, u)
        return Decision(VehicleQa(vehicle_id=target, question=u.question), _remember_vehicle(state, u))

    if intent in _VEHICLE_INTENTS:
        state = state.with_(intent=intent)
        # Không lấy `recommended_ids[0]` ở đây: đang có nhiều mẫu mà tự chọn hộ
        # thì khách bị tính chi phí / đặt lịch cho xe họ chưa chọn.
        vehicle = _target_vehicle(state, u, fallback_recommended=False)
        if vehicle is None:
            return _ask_vehicle(state, u)
        return _run_vehicle_intent(state, u, intent=intent, vehicle=vehicle)
    if intent in _LOOKUP_INTENTS:
        # C2 (2/2): còn câu hỏi đang treo thì KHÔNG BAO GIỜ đổ catalog — hỏi lại
        # câu cũ. Đây là 175/188 lượt hỏng trên prod.
        if intent is Intent.CATALOG_BROWSE and state.pending is not None:
            if state.pending.kind is PendingKind.CHOICE and state.pending.key == PENDING_VEHICLE:
                # Câu treo là "mẫu nào?" mà khách xin DANH SÁCH mẫu ("thế em có
                # loại nào") thì bày danh mục CHÍNH LÀ trả lời câu treo — không
                # phải chen ngang, càng không phải lý do để hỏi lại. Lượt prod
                # benchmark2 (2026-08-30): hỏi lại y nguyên, ask_counts vehicle=2,
                # và câu tiếp theo của khách đã đủ trần để chuyển TVV.
                return Decision(Lookup(mode=LOOKUP_BROWSE), state.with_(pending=None))
            return _reask(state, state.pending)
        found = _lookup_decision(state, _with_intent(u, intent), resume=False)
        if found is not None:
            return found

    # NONE và không có việc đang theo → bắt đầu tư vấn.
    if state.intent is Intent.NONE:
        return _advise(state.with_(intent=Intent.ADVISORY), slots_before)
    return _advise(state, slots_before)


# ---------------------------------------------------------------- helpers


def _to(src: Stage, dst: Stage) -> Stage:
    return dst if can_transition(src, dst) else src


def _with_intent(u: Understanding, intent: Intent) -> Understanding:
    return replace(u, intent=intent)


def _merge_slots(state: CoreState, incoming: dict[SlotName, SlotValue]) -> CoreState:
    if not incoming:
        return state
    merged = dict(state.slots)
    for k, v in incoming.items():
        if v is None:
            continue
        if k is SlotName.VEHICLE_TYPE and str(v) not in _KNOWN_VEHICLE_TYPES:
            # LLM đoán chệch loại xe (vd "xe may dien"): bỏ qua, coi như chưa nói (finding 5).
            continue
        merged[k] = v
    return state.with_(slots=merged)


def _switched_vehicle_type(state: CoreState, slots_before: dict[SlotName, SlotValue], u: Understanding) -> str:
    """Loại xe MỚI nếu lượt này đổi loại, chuỗi rỗng nếu không.

    Ba điều kiện, thiếu một là không tính: lượt này PHẢI có nói loại xe (không
    đọc lại slot cũ), trước đó PHẢI đã biết một loại (lần đầu nêu loại là bắt
    đầu bình thường, không phải đổi ý), và hai loại phải KHÁC nhau. `_merge_slots`
    đã loại giá trị lạ nên chuỗi lấy từ `state.slots` luôn là loại hợp lệ.
    """

    if SlotName.VEHICLE_TYPE not in u.slots:
        return ""
    before = slots_before.get(SlotName.VEHICLE_TYPE)
    after = state.slots.get(SlotName.VEHICLE_TYPE)
    if not before or not after or str(before) == str(after):
        return ""
    return str(after)


def _bump(state: CoreState, key: str) -> CoreState:
    counts = dict(state.ask_counts)
    counts[key] = counts.get(key, 0) + 1
    return state.with_(ask_counts=counts)


def _reset_unclear(state: CoreState) -> CoreState:
    if UNCLEAR_KEY not in state.ask_counts:
        return state
    counts = {k: v for k, v in state.ask_counts.items() if k != UNCLEAR_KEY}
    return state.with_(ask_counts=counts)


#: Tên việc đọc được của các intent cần xe — cho câu "mẫu nào?" nói đúng khung.
_VEHICLE_INTENT_JOBS: Final[dict[Intent, str]] = {
    Intent.TEST_DRIVE: "đặt lái thử",
    Intent.COST: "tính chi phí",
    Intent.ON_ROAD_PRICE: "xem giá lăn bánh",
    Intent.OFFER: "nhận ưu đãi",
}


def _vehicle_job(state: CoreState) -> str:
    return _VEHICLE_INTENT_JOBS.get(state.intent, "")


def _ask(
    state: CoreState,
    key: str,
    kind: PendingKind,
    options: tuple[str, ...] = (),
    labels: tuple[str, ...] = (),
    job: str = "",
) -> Decision:
    bumped = _bump(state, key)
    pending = Pending(
        kind=kind, key=key, options=tuple(options), labels=tuple(labels), asked_at_turn=bumped.turn_count, job=job
    )
    stage = (
        _to(bumped.stage, Stage.COLLECTING)
        if kind is PendingKind.SLOT and bumped.stage is Stage.GREETING
        else bumped.stage
    )
    return Decision(
        Ask(key=key, kind=kind, options=tuple(options), labels=tuple(labels), job=job),
        bumped.with_(pending=pending, stage=stage),
    )


def _ask_capped(
    state: CoreState,
    key: str,
    kind: PendingKind,
    options: tuple[str, ...] = (),
    labels: tuple[str, ...] = (),
    job: str = "",
) -> Decision:
    """`_ask` có trần `MAX_ASKS` — vòng nào cũng phải thoát được, không hỏi mãi.

    Dùng chung cho mọi vòng Ask có khả năng lặp vô hạn (khách trả lời kiểu lõi
    không trỏ được): quá trần thì chuyển TVV thay vì hỏi lại lần nữa.
    """

    if state.ask_counts.get(key, 0) >= MAX_ASKS:
        return Decision(Handoff(), state.with_(stage=Stage.HANDED_OFF))
    return _ask(state, key, kind, options=options, labels=labels, job=job)


def _ask_vehicle(state: CoreState, u: Understanding | None = None) -> Decision:
    """Hỏi "mẫu nào?" — có trần như mọi câu hỏi khác (C1).

    Không có trần thì mọi nhánh cần xe đều quay vòng vô hạn: hỏi → khách trả lời
    kiểu lõi không trỏ được → hỏi lại. Quá `MAX_ASKS` thì chuyển TVV.

    Khách VỪA nêu một tên xe không có trong danh mục (`u.unresolved_mention`)
    thì không hỏi "mẫu nào?" — họ vừa trả lời câu đó rồi (prod benchmark2:
    "anh muốn mua mẫu vf10" → "Anh/chị muốn xem mẫu nào ạ?"). Nói thật là chưa
    có mẫu đó (`NotInCatalog`), VẪN treo câu chọn mẫu và VẪN đếm vào cùng một
    trần: tên lạ lặp mãi cũng phải thoát được sang TVV.
    """

    mention = u.unresolved_mention if u is not None else ""
    if not mention:
        # `options` là id thô; tầng act điền `labels` (tên xe) trước khi render.
        # `job`: câu hỏi nói đúng VIỆC đang cần xe ("đặt lái thử mẫu nào") —
        # log prod 2026-08-31, khách nhận câu luồng thông số rồi gõ "Hà Nội".
        return _ask_capped(
            state, PENDING_VEHICLE, PendingKind.CHOICE, options=state.recommended_ids, job=_vehicle_job(state)
        )
    if state.ask_counts.get(PENDING_VEHICLE, 0) >= MAX_ASKS:
        return Decision(Handoff(), state.with_(stage=Stage.HANDED_OFF))
    bumped = _bump(state, PENDING_VEHICLE)
    # `options` để trống: act sẽ điền danh mục của đúng loại xe suy từ tên
    # (kèm nhãn), nên lượt sau "2" hay "VF 8" đều trỏ được.
    pending = Pending(kind=PendingKind.CHOICE, key=PENDING_VEHICLE, asked_at_turn=bumped.turn_count)
    return Decision(NotInCatalog(mention=mention), bumped.with_(pending=pending))


def _reask(state: CoreState, pending: Pending) -> Decision:
    """Hỏi lại y nguyên câu đang treo — VẪN đếm như một lượt hỏi.

    Không đếm thì khách hỏi mãi mà LLM cứ gán CATALOG_BROWSE là lõi hỏi lại mãi:
    đúng cái vòng lặp mà `MAX_ASKS` sinh ra để chặn. Quá trần → chuyển TVV.
    """

    if state.ask_counts.get(pending.key, 0) >= MAX_ASKS:
        return Decision(Handoff(), state.with_(stage=Stage.HANDED_OFF))
    bumped = _bump(state, pending.key)
    job = pending.job or (_vehicle_job(state) if pending.key == PENDING_VEHICLE else "")
    return Decision(
        Ask(key=pending.key, kind=pending.kind, options=pending.options, labels=pending.labels, job=job), bumped
    )


def _answered_pending(pending: Pending, u: Understanding) -> bool:
    """Lượt này CÓ trả lời đúng câu slot đang treo không.

    Tín hiệu mạnh nhất là slot vừa rút ra TRÙNG khoá đang hỏi; câu `SLOT_ANSWER`
    rút ra được slot nào đó cũng tính (khách trả lời đúng câu, chỉ là bộ hiểu ý
    quy về khoá khác). Không tính cho pending CHOICE/CONFIRM: ở đó "trả lời" là
    trỏ vào một lựa chọn, và hai nhánh trên đã lo.
    """

    if pending.kind is not PendingKind.SLOT:
        return False
    if any(slot.value == pending.key for slot in u.slots):
        return True
    return u.dialogue_act is DialogueAct.SLOT_ANSWER and bool(u.slots)


def _booking_token(u: Understanding) -> str:
    """Chuỗi NÚT khung giờ khách vừa bấm, hoặc rỗng.

    So khớp NGUYÊN VĂN tiền tố (`validate.BUTTON_PREFIX`) — nhận ra nút KHÔNG
    phải tách nút: chữ ký HMAC chỉ `act` mới được đọc (bẫy spec mục 12).
    """

    raw = (u.choice_ref or "").strip()
    return raw if raw.startswith(BUTTON_PREFIX) else ""


def _label_for(pending: Pending, option: str) -> str | None:
    """Nhãn khách đọc được song song `option`, nếu tầng act đã điền `Pending.labels`.

    Policy KHÔNG tạo chữ (spec mục 7) — chỉ tra lại nhãn act đã ghi kèm khi
    dựng câu hỏi CHOICE ban đầu (VD showroom_slot), để chuyển tiếp sang Ask
    CONFIRM khi khách chọn xong.
    """

    if option not in pending.options or not pending.labels:
        return None
    idx = pending.options.index(option)
    return pending.labels[idx] if idx < len(pending.labels) else None


def _pick_vehicle(state: CoreState, u: Understanding) -> str | None:
    if u.vehicle_ids:
        return u.vehicle_ids[0]
    if u.choice_ref and u.choice_ref in state.recommended_ids:
        return u.choice_ref
    return None


def _target_vehicle(state: CoreState, u: Understanding, *, fallback_recommended: bool = True) -> str | None:
    """Xe mà lượt này đang nói tới — MỘT thứ tự duy nhất cho cả lõi (finding I7).

    Xe vừa nêu ĐÍCH DANH → `chosen_vehicle_id` → xe đang quan tâm (nhớ từ lượt
    tra cứu trước, finding I3) → mẫu đề xuất đầu tiên. `fallback_recommended=False` cho
    các việc cam kết (chi phí, giá lăn bánh, lái thử, ưu đãi): không tự chọn hộ.
    """

    if u.vehicle_ids:
        # Khách gọi ĐÍCH DANH một mẫu thì đó là mẫu họ muốn, kể cả khi trước đó
        # đã chốt mẫu khác ("tính chi phí VF 8" trong lúc đang xem VF 5).
        return u.vehicle_ids[0]
    if state.chosen_vehicle_id:
        return state.chosen_vehicle_id
    interest = state.slots.get(SlotName.INTEREST_VEHICLE)
    if isinstance(interest, str) and interest:
        return interest
    if fallback_recommended and state.recommended_ids:
        return state.recommended_ids[0]
    return None


def _remember_vehicle(state: CoreState, u: Understanding) -> CoreState:
    """Xe khách vừa gọi tên ở một lượt tra cứu phải sống sang lượt sau (finding I3)."""

    if not u.vehicle_ids:
        return state
    return _merge_slots(state, {SlotName.INTEREST_VEHICLE: u.vehicle_ids[0]})


def _promote_to_chosen(state: CoreState, vehicle_id: str) -> CoreState:
    """Đưa state về CHOSEN với xe này, chỉ đi trên cạnh hợp lệ (C1).

    Ở GREETING/COLLECTING không có cạnh thẳng tới CHOSEN. Trước đây lõi trả lời
    bằng cách hỏi "mẫu nào?" — dù khách vừa gọi ĐÍCH DANH tên xe — nên kẹt vòng
    5 lượt trên prod. Nay coi chiếc xe khách gọi tên là một đề xuất tức thì:
    `→ RECOMMENDED` rồi `→ CHOSEN`, hai cạnh đều hợp lệ, trong cùng một lượt.

    Xe NGOÀI danh sách đề xuất cũng được ghi vào `recommended_ids` (lượt prod
    LP35: đang gợi ý VF 3, khách gõ "Tôi chọn VinFast VF 5 All New"). Không ghi
    thì lượt sau không còn chỗ nào tra ra chiếc khách vừa chọn, và câu hỏi "mẫu
    nào?" bày lại đúng danh sách cũ — danh sách không có mẫu họ vừa gọi tên.
    """

    if vehicle_id not in state.recommended_ids:
        state = state.with_(recommended_ids=(*state.recommended_ids, vehicle_id))
    if not can_transition(state.stage, Stage.CHOSEN):
        state = state.with_(stage=_to(state.stage, Stage.RECOMMENDED))
    return state.with_(chosen_vehicle_id=vehicle_id, stage=_to(state.stage, Stage.CHOSEN))


def _run_vehicle_intent(state: CoreState, u: Understanding, *, intent: Intent, vehicle: str) -> Decision:
    """Chạy một việc CẦN XE (chi phí / giá lăn bánh / lái thử / ưu đãi).

    Tách riêng vì có HAI lối vào: khách nói thẳng ("tính chi phí VF 8"), và
    khách vừa CHỌN xe cho đúng việc đang treo ("2" sau khi lõi hỏi "mẫu nào").
    Lối thứ hai trước đây chỉ trả một câu xác nhận rồi bắt khách xin lại việc
    họ vừa xin — một lượt thừa ngay giữa chỗ khách đã sẵn sàng.
    """

    original_stage = state.stage
    state = _promote_to_chosen(state.with_(intent=intent), vehicle)
    # Chặng thứ hai (COSTING/SCHEDULING/OFFER_REVIEW) chỉ hợp lệ khi cạnh nối
    # THẲNG từ chặng gốc của lượt này — tức chặng gốc đã là CHOSEN sẵn. Nếu vừa
    # được "ngầm chọn xe" ở trên, công cụ vẫn chạy nhưng chặng lưu lại dừng ở
    # CHOSEN để không phạm bất biến cạnh chặng.
    # COSTING/SCHEDULING cũng là "đã chốt": lượt Tco đặt COSTING xong mà khách
    # hỏi tiếp giá lăn bánh, coi original là CHƯA chốt thì stage bị kéo về
    # CHOSEN và luật 5a' (cập nhật thẻ) trượt ở lượt kế (probe Đà Nẵng 2026-08-31).
    already_chosen = original_stage in {Stage.CHOSEN, Stage.COSTING}
    if intent is Intent.COST:
        # KHÔNG hỏi số km nữa (Sếp chốt 2026-08-29): thiếu thì `act._tco` tính
        # theo mức mặc định và NÓI RÕ mức đó trong câu trả lời, để khách sửa lại
        # nếu muốn — rẻ hơn chặn họ thêm một lượt.
        costing_stage = _to(state.stage, Stage.COSTING) if already_chosen else state.stage
        return Decision(Tco(vehicle_id=vehicle), state.with_(stage=costing_stage))
    if intent is Intent.ON_ROAD_PRICE:
        # KHÔNG hỏi vị trí: tầng act suy region từ vị trí khách đã có / mặc định
        # cấu hình (spec mục 6). Hỏi thêm một câu ở đây là chặn khách giữa chừng
        # cho một thông tin lõi không cần biết.
        #
        # Sang chặng COSTING như `COST` (Sếp 2026-08-31: "giá lăn bánh với TCO
        # là MỘT" — lượt này trả đúng thẻ chi phí): không sang thì luật 5a' bên
        # trên không bắt được khách nhắc lại tỉnh/km sau khi thẻ đã hiện, và
        # thẻ không bao giờ được cập nhật tại chỗ.
        costing_stage = _to(state.stage, Stage.COSTING) if already_chosen else state.stage
        return Decision(OnRoadPrice(vehicle_id=vehicle), state.with_(stage=costing_stage))
    if intent is Intent.TEST_DRIVE:
        # KHÔNG chặn ở đây vì slot tỉnh trống. Policy THUẦN không đọc được vị
        # trí trình duyệt khách đã chia sẻ ở trang bản đồ (`/locations/nearest`
        # ghi `conversation_sessions.user_location`), nên lượt prod "cho anh lái
        # thử" bị hỏi lại tỉnh dù hệ đã có toạ độ chính xác của khách.
        # `act._showroom_options` đọc được vị trí đó và TỰ hỏi tỉnh — kèm trần
        # hỏi — khi thật sự không có gì để tra.
        sched_stage = _to(state.stage, Stage.SCHEDULING) if already_chosen else state.stage
        sched = state.with_(
            stage=sched_stage,
            pending=Pending(kind=PendingKind.CHOICE, key=PENDING_SHOWROOM_SLOT, asked_at_turn=state.turn_count),
        )
        return Decision(ShowroomOptions(vehicle_id=vehicle), sched)
    offer_stage = _to(state.stage, Stage.OFFER_REVIEW) if already_chosen else state.stage
    return _guard(state.with_(stage=offer_stage), EnqueueHitl(vehicle_id=vehicle), u, key=CONFIRM_OFFER, treo=vehicle)


def schedule_for(state: CoreState, vehicle_id: str) -> CoreState:
    """State SAU khi thẻ lái thử của `vehicle_id` được dựng NGOÀI lượt chat.

    `POST /agent/test-drive/options` (đợt 8) dựng thẻ khi khách chọn vị trí trên
    thẻ, không qua `decide`. Nút giờ bấm xong vẫn đi cửa chat, và luật 4 chỉ
    chạy `Book` khi `pending=showroom_slot` + xe đã chốt — nên state phải được
    ghi ĐÚNG như `_run_vehicle_intent(TEST_DRIVE)` ghi: cùng cạnh chặng, cùng
    khoá treo. Viết ở đây (tầng thuần) để route không tự bịa một bản thứ hai.
    """

    original_stage = state.stage
    after = _promote_to_chosen(state.with_(intent=Intent.TEST_DRIVE), vehicle_id)
    sched_stage = _to(after.stage, Stage.SCHEDULING) if original_stage is Stage.CHOSEN else after.stage
    pending = Pending(kind=PendingKind.CHOICE, key=PENDING_SHOWROOM_SLOT, asked_at_turn=after.turn_count)
    return after.with_(stage=sched_stage, pending=pending)


def _choose_with_slots(state: CoreState, vehicle_id: str, u: Understanding) -> Decision:
    """Khách vừa chỉ ra một mẫu. Đang treo một việc cần xe thì CHẠY LUÔN việc đó.

    "So sánh VF 3 với VF 5" → "tính chi phí" → lõi hỏi "mẫu nào" → khách đáp
    "2": trả một câu xác nhận ở đây là bắt họ gõ lại "tính chi phí" lần nữa.

    MỘT đường duy nhất cho mọi lượt CHỌN — có pending hay không. Nhánh không
    pending trước đây gọi hàm này KHÔNG kèm `u`, nên "chọn VF 5" giữa một việc
    cam kết đang theo chỉ trả câu xác nhận rồi bắt khách xin lại việc đó.
    """

    if state.intent in _VEHICLE_INTENTS:
        return _run_vehicle_intent(state, u, intent=state.intent, vehicle=vehicle_id)
    after = _promote_to_chosen(state, vehicle_id)
    if u.next_steps_asked:
        # "Làm sao để chốt VF 3" mà LLM gắn CHOICE: khách vẫn cần các BƯỚC, và
        # chiếc xe thì đã được ghi nhận ở `_promote_to_chosen` ngay trên.
        return Decision(NextSteps(vehicle_id=vehicle_id), after)
    if u.fit_asked:
        # Câu vừa CHỌN vừa HỎI ("ok chọn VF 2 đi, có hợp với nhu cầu của tôi
        # không") phải được trả lời cả hai vế trong MỘT tin nhắn. Câu xác nhận
        # suông ở đây là đúng lượt prod vòng 9: khách hỏi một câu đánh giá và
        # nhận về một cái menu.
        return Decision(FitCheck(vehicle_id=vehicle_id, alternative_ids=after.recommended_ids, just_chosen=True), after)
    return Decision(Reply(template=TEMPLATE_CHOSEN_SUMMARY, args={"vehicle_id": vehicle_id}), after)


def _lookup_decision(state: CoreState, u: Understanding, *, resume: bool) -> Decision | None:
    if u.intent in _REMEMBER_INTENTS:
        state = _remember_vehicle(state, u)
    if u.intent is Intent.CATALOG_BROWSE:
        return Decision(Lookup(mode=LOOKUP_BROWSE, resume_pending=resume), state)
    if u.intent is Intent.CATALOG_LOOKUP:
        if not u.vehicle_ids and u.unresolved_mention:
            # "vf10 giá bao nhiêu": không xe nào giải được nhưng khách đã nêu
            # tên — đổ cả danh mục là trả lời một câu khách không hỏi.
            return _ask_vehicle(state, u)
        # Xe khách vừa gọi tên đi KÈM quyết định. "VF 3 giá bao nhiêu" về
        # `CATALOG_LOOKUP + vehicle_ids=[VF3]`, mà `Lookup` trước đây không chở
        # `vehicle_ids` nên `act` chỉ còn cửa danh mục và khách nhận cả bảng 27
        # ô tô + 7 xe máy cho một câu hỏi về ĐÚNG MỘT chiếc.
        # `aspect` đi kèm để `act` trả ĐÚNG khía cạnh khách hỏi (giá) thay vì cả
        # bảng thông số — policy không đọc nó, chỉ chuyển tiếp.
        return Decision(
            Lookup(mode=LOOKUP_LOOKUP, vehicle_ids=u.vehicle_ids, aspect=u.aspect, resume_pending=resume), state
        )
    if u.intent is Intent.COMPARE:
        # So sánh cần ĐỦ hai xe; một xe (hoặc không xe nào) thì hỏi, đừng gọi
        # service với danh sách thiếu rồi trả câu vô nghĩa.
        if len(u.vehicle_ids) < 2:
            return _ask_vehicle(state)
        # Một lượt so sánh MỞ LẠI lựa chọn: hai mẫu vừa so thành tập ứng viên,
        # và xe đã chốt trước đó không còn là câu trả lời hiển nhiên. Nhớ mỗi xe
        # ĐẦU TIÊN (như các lượt tra cứu khác) là tự chọn hộ khách đúng lúc họ
        # đang phân vân giữa hai mẫu.
        state = state.with_(recommended_ids=u.vehicle_ids, chosen_vehicle_id=None)
        return Decision(Compare(vehicle_ids=u.vehicle_ids, resume_pending=resume), state)
    if u.intent is Intent.NEARBY:
        return Decision(Nearby(resume_pending=resume), state)
    if u.intent is Intent.POLICY_QA:
        return Decision(
            Lookup(mode=LOOKUP_POLICY, vehicle_ids=u.vehicle_ids, resume_pending=resume), state
        )
    if u.intent is Intent.VEHICLE_QA:
        target = _target_vehicle(state, u)
        if target is None:
            return None
        return Decision(VehicleQa(vehicle_id=target, question=u.question, resume_pending=resume), state)
    return None


def _has_advisory_slot(state: CoreState) -> bool:
    """Khách đã nói ĐƯỢC MỘT thứ nào về nhu cầu chưa — LOẠI TRỪ mỗi loại xe.

    Biết mỗi "ô tô điện" thì bộ lọc không có gì để lọc ngoài chính loại xe: bài
    "đề xuất" chạy ra đúng vài mẫu đầu danh mục, không dính gì tới người đang
    hỏi. Lượt đó `act._ask` bày THẲNG danh sách của loại ấy rồi hỏi câu hồ sơ
    trong CÙNG một tin nhắn — khách vẫn thấy xe ngay ở lượt đầu, và câu hỏi vẫn
    chỉ có MỘT (Sếp chốt 2026-08-29). Loại xe kèm bất kỳ thứ gì khác (ngân sách,
    mục đích, số người) thì đề xuất luôn như cũ.
    """

    return any(state.slots.get(slot) is not None for slot in ADVISORY_SLOTS if slot is not SlotName.VEHICLE_TYPE)


def _criteria_view(slots: Mapping[SlotName, SlotValue]) -> dict[SlotName, SlotValue]:
    """Slot dùng để so "khách có đổi tiêu chí không" — BỎ tính năng rỗng.

    "thôi không cần tính năng gì" chỉ ghi `habit_need_tags=[]`: khách vừa nói
    họ KHÔNG thêm tiêu chí nào. Tính nó là một thay đổi thì `_recommend_reason`
    trả `slots_changed`, lõi chạy lại đúng bộ lọc cũ và khách nhận lại y nguyên
    bài vừa đọc — chỉ số "lặp bài" đo được trên prod (phiên 125bdea8).
    """

    return {key: value for key, value in slots.items() if not (key is FEATURE_SLOT and value == [])}


def _recommend_reason(state: CoreState, slots_before: dict[SlotName, SlotValue]) -> tuple[str, tuple[str, ...]]:
    if state.stage not in {Stage.RECOMMENDED, Stage.CHOSEN} and not state.recommended_ids:
        return REASON_FIRST, ()
    if _criteria_view(state.slots) != _criteria_view(slots_before):
        return REASON_SLOTS_CHANGED, ()
    # Tiêu chí y nguyên mà khách vẫn xin đề xuất → họ muốn mẫu KHÁC.
    return REASON_RETRY, tuple(state.recommended_ids)


def _advise(state: CoreState, slots_before: dict[SlotName, SlotValue], *, refine: str = "") -> Decision:
    """ĐÚNG MỘT câu hỏi cho cả luồng tư vấn, rồi đề xuất (Sếp chốt 2026-08-29).

    Trước đây hỏi lần lượt `vehicle_type → budget → purpose → seats/km`: bốn
    lượt trước khi khách thấy chiếc xe đầu tiên, và 34 phiên prod cho thấy phần
    lớn khách rời đi trước lượt thứ ba. Nay: chưa biết gì thì hỏi MỘT câu mở;
    biết được bất kỳ thứ gì thì đề xuất ngay, phần thiếu `act.build_criteria`
    suy ra. Hỏi lại CHỈ khi không hiểu câu trả lời (`_unclear`), không bao giờ
    vì thiếu một slot.
    """

    if refine and state.recommended_ids:
        # Chặng lùi về RECOMMENDED (khách đang cân lại) nhưng xe đã chốt thì
        # GIỮ NGUYÊN.
        #
        # Lượt prod vòng 9: sau "ok tôi chốt VF3", một lượt xin xem thêm đã xoá
        # `chosen_vehicle_id`; tới lượt "tôi muốn đặt lịch lái thử" thì
        # `_target_vehicle(fallback_recommended=False)` không còn trỏ ra chiếc
        # nào và khách nhận "Anh/chị muốn xem kỹ mẫu nào ạ?" — rồi gõ "Hà Nội"
        # lại nhận đúng câu đó lần nữa. Xe đã chốt là thứ khách nói ra, không
        # phải suy đoán của lõi: chỉ chính khách mới được rút lại.
        after = state.with_(stage=_to(state.stage, Stage.RECOMMENDED), pending=None)
        return Decision(Recommend(reason=REASON_REVISED, exclude_ids=state.recommended_ids, refine=refine), after)
    if not _has_advisory_slot(state):
        return _ask_capped(state, PENDING_PROFILE, PendingKind.SLOT)
    reason, exclude_ids = _recommend_reason(state, slots_before)
    return Decision(
        Recommend(reason=reason, exclude_ids=exclude_ids),
        state.with_(stage=_to(state.stage, Stage.RECOMMENDED), pending=None),
    )


def _guard(
    state: CoreState, action: Action, u: Understanding, *, key: str, treo: str, labels: tuple[str, ...] = ()
) -> Decision:
    if isinstance(action, IRREVERSIBLE) and u.confidence < LOW_CONFIDENCE:
        pending = Pending(
            kind=PendingKind.CONFIRM, key=key, options=(treo,), labels=labels, asked_at_turn=state.turn_count
        )
        back = _to(state.stage, Stage.CHOSEN) if state.stage is Stage.OFFER_REVIEW else state.stage
        return Decision(
            Ask(key=key, kind=PendingKind.CONFIRM, options=(treo,), labels=labels),
            state.with_(pending=pending, stage=back),
        )
    return Decision(action, state)


def _run_irreversible(state: CoreState, key: str, treo: str) -> Decision:
    """Chạy việc đang treo sau khi khách xác nhận — khớp khoá TƯỜNG MINH.

    Trước đây mọi khoá không phải "book" đều rơi xuống `EnqueueHitl`: một khoá
    lạ (đổi tên, lỗi ghi state) là âm thầm gửi khách sang TVV (finding I2).
    """

    if state.chosen_vehicle_id is None:
        return _ask_vehicle(state)
    vehicle = state.chosen_vehicle_id
    if key == CONFIRM_BOOK:
        return Decision(Book(vehicle_id=vehicle, choice_ref=treo), state)
    if key == CONFIRM_OFFER:
        return Decision(EnqueueHitl(vehicle_id=vehicle), state.with_(stage=_to(state.stage, Stage.OFFER_REVIEW)))
    return Decision(Reply(template=TEMPLATE_CLARIFY, args={"stage": state.stage.value}), state.with_(pending=None))


def _unclear(state: CoreState, slots_before: dict[SlotName, SlotValue], u: Understanding) -> Decision:
    n = state.ask_counts.get(UNCLEAR_KEY, 0)
    if n >= MAX_UNCLEAR:
        return Decision(Handoff(), state.with_(stage=Stage.HANDED_OFF))
    bumped = _bump(state, UNCLEAR_KEY)
    if bumped.stage is Stage.COLLECTING or bumped.stage is Stage.GREETING:
        # Đang trong luồng tư vấn: hỏi lại ĐÚNG câu hồ sơ (một câu duy nhất) khi
        # chưa biết gì; biết được gì rồi thì đề xuất luôn thay vì hỏi vòng vo.
        return _advise(bumped, slots_before)
    # MÓC 1 (plan agent-migration §1.3): nhánh CUỐI của `_unclear` là ngõ cụt
    # thật — lõi sắp trả câu "em chưa rõ ý anh/chị". `act` thử agent trước; agent
    # tắt/hỏng thì chính `act` trả ĐÚNG `Reply(TEMPLATE_CLARIFY)` này, nên hành
    # vi khi cờ OFF không đổi một ký tự. Trần `MAX_UNCLEAR` ở trên vẫn chạy
    # trước: quá trần vẫn `Handoff`, agent không được kéo dài vòng không hiểu.
    return Decision(
        OpenQuestion(question=u.question.strip(), reason=OPEN_REASON_UNCLEAR, vehicle_ids=tuple(u.vehicle_ids)),
        bumped,
    )
