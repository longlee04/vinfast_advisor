"""A2-3 typed slot extraction use case."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from typing import Final

from src.agents.contracts import ExtractedSlots, LLMExtractionPayload
from src.agents.domain.budget_parsing import BudgetRange, mentions_money, parse_budget_range
from src.agents.domain.canonical_text import CanonicalText, build_canonical_text
from src.agents.domain.claim_policy import feature_codes_mentioned, negated_feature_codes
from src.agents.domain.comparative_revision import detect_comparative_revision
from src.agents.domain.conversation_memory import (
    WorkingMemoryProjection,
    render_working_memory_projection,
)
from src.agents.domain.conversation_references import resolve_vehicle_references
from src.agents.domain.intent_reconciliation import reconcile_intents
from src.agents.domain.need_tags import describes_travel_habit, need_tag_display
from src.agents.domain.pricing_intent import detect_province
from src.agents.domain.range_normalizer import daily_distance_from_message, normalize_range_km
from src.agents.domain.slot_policy import next_slot
from src.agents.domain.slot_salvage import (
    is_non_answer,
    salvage_slot,
    salvaged_budget_floor,
    salvaged_budget_stated,
)
from src.agents.domain.slot_tree import is_applicable
from src.agents.domain.turn_axes import TurnAxes, coerce_topic, coerce_topics
from src.agents.domain.turn_understanding import reconcile_scope, reconcile_task_action
from src.agents.domain.values import (
    DECLINED_SLOT_VALUE,
    Intent,
    IntentType,
    Severity,
    SlotName,
    SlotValue,
    Topic,
    VehicleType,
)
from src.agents.domain.vehicle_type_lock import explicit_vehicle_type, keeps_known_vehicle_type
from src.agents.ports import FeatureVocabularyPort, LLMPort, UnitOfWorkPort
from src.agents.services.call_budget import CallKind, current_call_budget
from src.agents.services.slot_codec import coerce_vehicle_type

_COMMUTE_PURPOSE_PATTERN = re.compile(r"\b(?:để|de)\s+(?:đi|di)\s+(?:làm|lam)\b", re.IGNORECASE)
_EXPLICIT_SEAT_COUNT_PATTERN = re.compile(
    r"\b([1-9]\d?)\s*(?:người|nguoi|chỗ|cho|thành\s*viên|thanh\s*vien)\b",
    re.IGNORECASE,
)
_PASSENGER_COUNT_EVIDENCE_PATTERN = re.compile(
    r"\b(?:\d+|một|mot|hai|ba|bốn|bon|năm|nam|sáu|sau|bảy|bay|tám|tam|"
    r"chín|chin|mười|muoi)\s*(?:người|nguoi|chỗ|cho|thành\s*viên|thanh\s*vien)\b",
    re.IGNORECASE,
)
#: Câu CHỈ nói "xe điện" (hoặc "xe" trần) — không hề chọn nhánh nào.
#:
#: "Xe điện" ở Việt Nam phủ cả ô tô lẫn xe máy. Có mặt cụm này mà VẮNG mọi dấu
#: hiệu nhánh (`vehicle_type_lock.explicit_vehicle_type` trả `None`) thì lời đoán
#: loại xe của mô hình là đoán suông, và nó khoá toàn bộ phần còn lại của phiên.
_GENERIC_EV_ONLY_PATTERN = re.compile(
    r"\bxe\s*(?:điện|dien|đien|di[eệ]n)\b|\bev\b|\bxe\b",
    re.IGNORECASE,
)
_EXPLICIT_CAR_NOUN_OR_MODEL_PATTERN = re.compile(
    r"\b(?:[ôo]\s*t[ôo]|oto|xe\s*h[ơo]i|suv|s[ée]dan|vf\s*\d+)\b",
    re.IGNORECASE,
)
_NEGATED_SEAT_PREFIX_PATTERN = re.compile(
    r"(?:không|khong|chẳng|chang)\s+"
    r"(?:(?:cần|can|muốn|muon|chọn|chon|lấy|lay|phải|phai)\s+)?"
    r"(?:(?:loại|loai|mẫu|mau|xe|ô\s*tô|oto)\s+)?$",
    re.IGNORECASE,
)
_RESOLVED_SEAT_SUFFIX_PATTERN = re.compile(
    r"^\s*(?:(?:(?:là|la)\s+)?(?:đủ|du|được|duoc)|(?:thôi|thoi)|"
    r"(?:mới|moi)\s+(?:đúng|dung))\b",
    re.IGNORECASE,
)
_DIRECT_SEAT_NEED_PATTERN = re.compile(
    r"\b(?:cần|can|muốn|muon|tìm|tim|chọn|chon|lấy|lay|ưu\s*tiên|uu\s*tien)\b",
    re.IGNORECASE,
)
_STANDALONE_POSITIVE_INTEGER_PATTERN = re.compile(r"^\s*([1-9]\d*)\s*$")
_MONTHLY_INSTALLMENT_PATTERN = re.compile(
    r"(?:trả\s*góp|tra\s*gop).*(?:mỗi\s*tháng|moi\s*thang|hàng\s*tháng|"
    r"hang\s*thang|/\s*tháng|/\s*thang)|(?:mỗi\s*tháng|moi\s*thang|"
    r"hàng\s*tháng|hang\s*thang|/\s*tháng|/\s*thang)",
    re.IGNORECASE,
)
_EXPLICIT_BUDGET_PATTERN = re.compile(
    r"\b(?:ngân\s*sách|ngan\s*sach|tài\s*chính|tai\s*chinh|"
    r"triệu|trieu|tr|tỷ|tỉ|ty|ti|củ|cu)\b",
    re.IGNORECASE,
)
#: Câu đang nói về chuyện SẠC.
#:
#: "ổ cắm"/"ổ điện" phải có mặt: đọc từ `turn_traces` prod 2026-08-26, khách gõ
#: "nha anh co o cam o cho de xe" — đúng câu trả lời cho `HOME_CHARGING` — và bị
#: đóng lượt vì lạc đề. Người Việt mô tả chỗ sạc tại nhà bằng cái ổ cắm nhiều
#: hơn bằng chữ "sạc".
_CHARGING_SIGNAL_PATTERN = re.compile(
    r"\b(?:sạc|sac|trụ\s*sạc|tru\s*sac|ổ\s*(?:cắm|điện)|o\s*(?:cam|dien))\b",
    re.IGNORECASE,
)
_BARE_BOOLEAN_ANSWER_PATTERN = re.compile(
    r"^\s*(?:có|co|không|khong|ko|k|chưa|chua)(?:\s+(?:ạ|a|nhé|nhe))?\s*[.!]?\s*$",
    re.IGNORECASE,
)
_INNER_CITY_PATTERN = re.compile(r"\b(?:đi|di)\s+(?:nội\s*thành|noi\s*thanh)\b", re.IGNORECASE)
_COUNTRYSIDE_PATTERN = re.compile(
    r"\b(?:(?:thỉnh\s*thoảng|thinh\s*thoang)\s+)?(?:về|ve)\s+(?:quê|que)\b",
    re.IGNORECASE,
)
_VF_MODEL_PATTERN = re.compile(r"\bvf\s*-?\s*(e?\d+)\b", re.IGNORECASE)
#: Tên dòng xe máy gõ trơ trọi ("Evo", "Klara", "Vero X"): LLM hay bỏ qua, và
#: không có nó thì "Evo giá nhiêu" bị hỏi ngân sách như chưa nghe tên xe (đo
#: 2026-08-28). Lấy cả đuôi kế tiếp nếu có ("Evo Grand", "Klara S").
_MOTORBIKE_FAMILY_PATTERN = re.compile(
    r"\b(evo|klara|feliz|vento|theon|ludo|impes|vero\s*x|motio)(?:\s+(grand|max|neo|lite|s|ii|200|plus))?\b",
    re.IGNORECASE,
)


def _clean_secondary_topics(payload: LLMExtractionPayload) -> tuple[Topic, ...]:
    """Chủ đề phụ đã khử trùng, bỏ chủ đề chính, cắt trần — dùng chung luật với
    `TurnAxes` để hai chỗ không lệch nhau."""

    primary = coerce_topic(payload.primary_topic) if payload.primary_topic is not None else Topic.OTHER
    axes = TurnAxes(
        dialogue_act=payload.dialogue_act,
        task=payload.task or IntentType.OTHER,
        primary_topic=primary,
        secondary_topics=coerce_topics(payload.secondary_topics),
    )
    return axes.secondary_topics


class SlotExtractionServiceImpl:
    """Parse one LLM function-call payload and persist unresolved mentions."""

    def __init__(
        self,
        llm: LLMPort,
        unit_of_work: UnitOfWorkPort,
        feature_vocabulary: FeatureVocabularyPort | None = None,
    ) -> None:
        self._llm = llm
        self._unit_of_work = unit_of_work
        self._feature_vocabulary = feature_vocabulary

    async def extract(
        self,
        *,
        session_id: str,
        customer_id: str,
        vehicle_type: str | None,
        user_message: str,
        conversation_history: str | WorkingMemoryProjection = "",
        active_task: Mapping[str, object] | None = None,
        canonical: CanonicalText | None = None,
    ) -> ExtractedSlots:
        """Understand one turn, normalize it, and retain supported state changes.

        `canonical` sinh tại chain (ENG REVIEW AMENDMENT 2) — mọi gate con
        (reconcile_task_action) đọc nó, không tự normalize. Vắng mặt thì tự
        dựng từ `user_message` (đường tương thích cho test double).
        """

        canonical = canonical or build_canonical_text(user_message)

        resolved_type = coerce_vehicle_type(vehicle_type)
        feature_codes: tuple[str, ...] = ()
        if resolved_type is not None and self._feature_vocabulary is not None:
            active_features = await self._feature_vocabulary.list_active_features(resolved_type)
            feature_codes = tuple(code for code, _ in active_features)
        async with self._unit_of_work.transaction() as transaction:
            known_slots = await transaction.sessions.get_slots(session_id, customer_id)
        if resolved_type is not None:
            known_slots.setdefault(SlotName.VEHICLE_TYPE, resolved_type.value)
        expected_slot = next_slot(resolved_type, known_slots)
        context_parts = [_expected_slot_context(expected_slot)]
        if active_task:
            context_parts.append(_active_task_context(active_task))
        llm_context = _merge_context(conversation_history, "\n".join(context_parts))
        reference_context = (
            render_working_memory_projection(conversation_history)
            if isinstance(conversation_history, WorkingMemoryProjection)
            else conversation_history
        )
        # Một THAO TÁC trích slot = một slot bắt buộc. Xin ở đây chứ không ở
        # wrapper provider: đây là chỗ biết ranh giới thao tác, còn wrapper chỉ
        # thấy từng lần chạm mạng.
        budget = current_call_budget()
        if budget is not None:
            budget.claim(CallKind.REQUIRED)
        raw_payload = await self._llm.extract_slots(
            vehicle_type=resolved_type,
            feature_vocabulary=feature_codes,
            conversation_history=llm_context,
            user_message=user_message,
        )
        payload = LLMExtractionPayload.model_validate(raw_payload)
        vehicle_mentions = _vehicle_name_mentions(payload.vehicle_name_mentions, user_message)
        vehicle_mentions = resolve_vehicle_references(
            user_message=user_message,
            conversation_context=reference_context,
            raw_mentions=vehicle_mentions,
        )
        slots, range_reason = _slots_from_payload(
            payload,
            user_message,
            current_vehicle_type=resolved_type,
            expected_slot=expected_slot,
        )
        slots = _lock_vehicle_type(slots, resolved_type, user_message)
        slots = _applicable_slots(slots, resolved_type)
        slots = _drop_unsupported_slots(slots, user_message, expected_slot)
        if payload.purpose_bucket is not None:
            slots[SlotName.PURPOSE_BUCKET] = payload.purpose_bucket.value
        slots.update(
            _salvaged_slots(
                payload=payload,
                user_message=user_message,
                vehicle_type=resolved_type,
                pending=expected_slot,
                extracted=slots,
            )
        )
        intents = reconcile_intents(
            user_message=user_message,
            raw_intents=payload.intents,
            normalized_slots=slots,
            vehicle_mentions=vehicle_mentions,
            known_slots=known_slots,
            expected_slot=expected_slot,
            canonical=canonical,
        )
        if Intent.ADVISORY in intents:
            # SAU `reconcile_intents` và chỉ cho lượt tư vấn. Chạy sớm hơn thì
            # "Hôm nay thời tiết Hà Nội thế nào?" — câu ngoài phạm vi, không
            # intent nào — cũng bị nhặt tỉnh `HN` (ca SC050 của bộ eval bắt
            # được). Bộ định tuyến cần biết điều này trước
            # `reconcile_task_action` ngay bên dưới, nên đây là đúng khe hở.
            slots.update(_travel_context_slots(user_message, canonical, extracted=slots))
        scope = reconcile_scope(
            raw_scope=payload.scope,
            intents=intents,
            user_message=user_message,
            vehicle_mentions=vehicle_mentions,
        )
        task_action, excluded_vehicle_ids = reconcile_task_action(
            user_message=user_message,
            raw_action=payload.task_action,
            intents=intents,
            active_task_payload=active_task,
            current_slots=slots,
            known_slots=known_slots,
            vehicle_mentions=vehicle_mentions,
            canonical=canonical,
        )
        if (Intent.CATALOG_LOOKUP in intents or Intent.COMPARE_VEHICLES in intents) and Intent.ADVISORY not in intents:
            # [COMPARE_VEHICLES] Lượt so sánh đứng cùng nhóm với tra cứu ở đây:
            # khách nêu đích danh xe để đối chiếu, không khai nhu cầu cá nhân.
            # Giữ slot suy ra từ một câu như vậy sẽ nạp `vehicle_type` vào hồ sơ
            # tư vấn và làm lệch bộ lọc của lượt tư vấn kế tiếp.
            slots = {}
            range_reason = None
        # Tính năng khách nói KHÔNG cần thì không phải yêu cầu — lọc ở cả hai
        # nguồn (LLM và bảng cụm chữ), nếu không "không cần camera 360" cộng điểm
        # cho xe có camera 360 (đo 2026-08-28).
        negated = negated_feature_codes(user_message)
        mentions = [
            code
            for code in (_feature_mention_codes(payload.feature_mentions) if payload.feature_mentions else [])
            if code not in negated
        ]
        # Thu nhận TẤT ĐỊNH từ lời khách, hợp với danh sách của LLM.
        #
        # Đo trên prod 2026-08-26: prompt đã khai đúng `COMPACT_SIZE = thân xe
        # nhỏ gọn` (kiểm bằng cách đọc thẳng schema trong container) mà mô hình
        # vẫn trả rỗng cho "anh chỉ cần 1 chiếc nhỏ gọn" — rồi hệ đề xuất VF 8,
        # SUV cỡ D. Cùng khuôn `_vehicle_name_mentions` ngay dưới: giữ bản của
        # LLM và thu hồi thêm bằng bảng cụm chữ đã curate.
        for code in sorted(feature_codes_mentioned(user_message) - negated):
            if code not in mentions:
                mentions.append(code)
        # Lời xin đổi đề xuất phải thành ĐIỂM, không chỉ thành nhãn định tuyến.
        #
        # `REVISE_RESULTS` một mình chỉ LOẠI xe khách đã xem rồi bốc tiếp theo
        # đúng bộ lọc cũ — nên câu "nhỏ hơn" cho ra ba chiếc khác, cũng to y như
        # vậy. Mã tính năng đọc được là thứ kéo bảng xếp hạng đi đúng hướng khách
        # vừa chỉ.
        #
        # `feature_codes` rỗng là chuyện bình thường và KHÔNG phải lỗi: "rẻ hơn"
        # là chuyện giá, "đi lại tiện lợi hơn" không quy về mã nào. Lượt vẫn chạy
        # tiếp và vẫn loại xe đã xem — xem `comparative_revision.attribute_known`.
        traits: list[str] = []
        if Intent.ADVISORY in intents:
            revision = detect_comparative_revision(canonical, vehicle_mentions=bool(vehicle_mentions))
            for code in revision.feature_codes if revision is not None else ():
                if code not in mentions:
                    mentions.append(code)
            # Cảm quan đi đường RIÊNG, không trộn vào `mentions`: `mentions` là mã
            # TÍNH NĂNG và `scoring._feature_mention_reasons` tra chúng trong cờ đã
            # duyệt. Nhét "TRAIT_LARGE_CARGO" vào đó là tra một mã không cờ nào
            # mang — cộng 0 điểm trong im lặng, đúng bẫy `HIGH_PAYLOAD`.
            traits = list(revision.trait_codes) if revision is not None else []
        if scope.value != "IN_SCOPE":
            slots = {}
            intents = []
            mentions = []
            traits = []
            vehicle_mentions = []
            excluded_vehicle_ids = ()
        if slots or mentions:
            # Ghi `conversation_slots` NGAY tại đây, không đợi `_save_slots` cuối
            # `run_turn` (`src/agents/chain.py`). `ScoreNode` chạy TRONG cùng
            # `graph.ainvoke` của lượt này và đọc slot trực tiếp từ DB qua
            # `SqlAlchemyRecommendationDataSource` — nếu đợi ghi ở cuối lượt,
            # ScoreNode luôn thấy trạng thái của lượt TRƯỚC (thiếu ngân sách, số
            # người, quãng đường...) nên không đủ dữ liệu tính điểm/xếp hạng.
            # Ghi lại lần nữa ở `_save_slots` không phải trùng lặp thừa: đây là
            # `upsert_slot` ghi đè theo khoá composite, không tạo bản ghi mới, và
            # nó vẫn cần thiết cho nhánh chỉ hỏi slot / nhánh terminal — những
            # nhánh không đi qua `extract` lần nữa trong lượt đó.
            async with self._unit_of_work.transaction() as transaction:
                if slots:
                    vehicle_type_hint = coerce_vehicle_type(slots.get(SlotName.VEHICLE_TYPE))
                    await transaction.sessions.ensure_session(session_id, customer_id, vehicle_type_hint)
                    for slot_name, value in slots.items():
                        await transaction.sessions.upsert_slot(session_id, slot_name, value)
                if mentions:
                    await transaction.pending_mentions.record(session_id, customer_id, mentions)
        return ExtractedSlots(
            slots=slots,
            intents=intents,
            vehicle_name_mentions=vehicle_mentions,
            scope=scope,
            dialogue_act=payload.dialogue_act,
            task_action=task_action,
            excluded_vehicle_ids=excluded_vehicle_ids,
            feature_mentions=mentions,
            trait_mentions=traits,
            range_clarify_reason=range_reason,
            rejected_vehicle_mention=payload.rejected_vehicle_mention,
            rejection_reason=payload.rejection_reason,
            # Bốn trục: chuẩn hoá ở BIÊN này, không để nhãn thô của mô hình đi
            # sâu vào graph. `coerce_*` rơi về giá trị an toàn thay vì raise.
            task=payload.task,
            primary_topic=coerce_topic(payload.primary_topic) if payload.primary_topic is not None else Topic.OTHER,
            secondary_topics=_clean_secondary_topics(payload),
            severity=payload.severity or Severity.NORMAL,
            human_requested=bool(payload.human_requested),
        )

    async def consume_pending(self, session_id: str, customer_id: str) -> list[str]:
        """Read and clear unresolved feature mentions after they are applicable."""

        async with self._unit_of_work.transaction() as transaction:
            mentions = await transaction.pending_mentions.consume(session_id, customer_id)
        return mentions


def _merge_context(
    working_memory: str | WorkingMemoryProjection, expected_slot_context: str
) -> str | WorkingMemoryProjection:
    if isinstance(working_memory, WorkingMemoryProjection):
        if not expected_slot_context.strip():
            return working_memory
        return replace(
            working_memory,
            instruction_context=(
                *working_memory.instruction_context,
                expected_slot_context.strip(),
            ),
        )
    parts = [part.strip() for part in (working_memory, expected_slot_context) if part.strip()]
    return "\n\n".join(parts)


def _active_task_context(payload: Mapping[str, object]) -> str:
    """Expose bounded machine state without presenting it as user-authored text."""

    task_type = str(payload.get("task_type") or "")
    status = str(payload.get("status") or "")
    return f"ACTIVE_TASK: task_type={task_type}; status={status}"


def _slots_from_payload(
    payload: LLMExtractionPayload,
    user_message: str = "",
    *,
    current_vehicle_type: VehicleType | None = None,
    expected_slot: SlotName | None = None,
) -> tuple[dict[str, SlotValue], str | None]:
    explicit_seat_count = _explicit_seat_count(user_message)
    has_explicit_seat_mention = _EXPLICIT_SEAT_COUNT_PATTERN.search(user_message) is not None
    has_passenger_evidence = _PASSENGER_COUNT_EVIDENCE_PATTERN.search(user_message) is not None
    passenger_count = payload.passenger_count
    if explicit_seat_count is not None:
        passenger_count = explicit_seat_count
    elif has_explicit_seat_mention:
        passenger_count = None
    elif expected_slot is SlotName.PASSENGER_COUNT:
        if _VF_MODEL_PATTERN.search(user_message) is not None and not has_passenger_evidence:
            passenger_count = None
        elif passenger_count is None:
            passenger_count = _standalone_positive_integer(user_message)
    elif passenger_count is not None and not has_passenger_evidence:
        passenger_count = None

    explicit_type = _explicit_vehicle_type_for_slot(user_message)
    proposed_type = payload.vehicle_type
    if (
        proposed_type is not None
        and explicit_type is None
        and current_vehicle_type is None
        # Số chỗ hay tải trọng là bằng chứng CÓ CẤU TRÚC — "phân vân giữa xe 5
        # chỗ và 7 chỗ" chọn nhánh ô tô rõ ràng dù không có chữ "ô tô" nào.
        # Chỉ bỏ lời đoán khi câu KHÔNG có gì thu hẹp nhánh cả.
        and not has_explicit_seat_mention
        and payload.max_load_kg is None
        and _GENERIC_EV_ONLY_PATTERN.search(user_message) is not None
    ):
        # BUG THẬT trên prod 2026-08-27, lượt ĐẦU TIÊN của phiên: khách gõ *"tôi
        # muốn tư vấn mua xe điện"* và mô hình trả `vehicle_type=
        # ELECTRIC_MOTORBIKE`. Không có gì trong câu nói thế — "xe điện" phủ CẢ
        # HAI nhánh. Từ đó cả phiên chạy nhánh xe máy: khách nói ngân sách 700
        # triệu, gia đình 5 người, và vẫn nhận về Theon với Klara.
        #
        # Đoán sai ở đây đắt hơn hẳn hỏi lại: `_quick_replies` đã sẵn hai nút
        # "Ô tô điện / Xe máy điện" khi `pending_slot` là loại xe, nên bỏ lời
        # đoán này không để khách bơ vơ — nó chỉ đổi một câu bịa thành một câu hỏi.
        proposed_type = None
    effective_type = explicit_type or proposed_type or current_vehicle_type
    if explicit_seat_count is not None and explicit_seat_count >= 3:
        # Chỉ khẳng định ô tô khi đủ 3 chỗ trở lên (T3): 1–2 người + ngân sách
        # thấp thường là xe máy — để node infer quyết định thay vì khoá nhầm nhánh.
        # Khi <3 chỗ, GIỮ loại xe đã suy từ câu ("xe máy thì 2 chỗ" vẫn là xe máy),
        # không ép None rồi làm mất slot loại xe khách vừa nêu.
        effective_type = VehicleType.CAR
    elif effective_type is None:
        if passenger_count is not None and passenger_count >= 3 and payload.max_load_kg is None:
            effective_type = VehicleType.CAR
        elif payload.max_load_kg is not None and passenger_count is None:
            effective_type = VehicleType.ELECTRIC_MOTORBIKE

    slots: dict[str, SlotValue] = {}
    if effective_type is not None and (
        proposed_type is not None or current_vehicle_type is None or effective_type is not current_vehicle_type
    ):
        slots[SlotName.VEHICLE_TYPE] = effective_type.value
    budget_source: str | int | float | None = payload.budget_max_vnd
    if budget_source is None and _EXPLICIT_BUDGET_PATTERN.search(user_message):
        budget_source = user_message
    if budget_source is not None:
        budget = parse_budget_range(budget_source)
        if budget_source is not user_message:
            # LLM trả một con số đơn lẻ nên đã LÀM PHẲNG khoảng khách nói: "từ 300
            # đến 700 triệu" về đây chỉ còn 700 triệu và cái sàn biến mất. Đọc lại
            # câu gốc để lấy hướng — xem `_recovered_range`.
            budget = _recovered_range(budget, user_message)
        if budget.max_vnd is not None:
            slots[SlotName.BUDGET_MAX_VND] = budget.max_vnd
        if budget.min_vnd is not None:
            slots[SlotName.BUDGET_MIN_VND] = budget.min_vnd
        if budget.stated_vnd is not None:
            slots[SlotName.BUDGET_STATED_VND] = budget.stated_vnd
    values: Mapping[SlotName, SlotValue | None] = {
        SlotName.HOME_CHARGING: payload.home_charging,
        SlotName.PURPOSE: payload.purpose,
    }
    slots.update({name: value for name, value in values.items() if value is not None})
    range_reason: str | None = None
    if payload.required_range_km is not None:
        normalized_km, range_reason = normalize_range_km(payload.required_range_km, payload.range_period)
        if normalized_km is not None:
            slots[SlotName.REQUIRED_RANGE_KM] = normalized_km
        # `range_reason` khác None → không ghi slot; `ask_or_retrieve` phát câu
        # xác nhận đơn vị cho lượt này (T2 Lớp 3).
    if passenger_count is not None and (explicit_seat_count is not None or has_passenger_evidence):
        slots[SlotName.PASSENGER_COUNT] = passenger_count
    if payload.max_load_kg is not None:
        slots[SlotName.MAX_LOAD_KG] = payload.max_load_kg
    if payload.purpose is None and _COMMUTE_PURPOSE_PATTERN.search(user_message):
        slots[SlotName.PURPOSE] = "di lam"
    # `need_tag_display`: nhãn tập đóng LLM chọn được viết ra bằng TIẾNG VIỆT,
    # chữ tự do giữ nguyên. Giá trị slot này còn đi thẳng vào prompt tổng hợp
    # (`nodes/synthesize._customer_wording`), nên để nguyên mã ở đây là mời LLM
    # chép mã thô vào câu trả lời rồi bị guardrail loại cả pitch (bẫy 3.9).
    habit_need_tags = list(dict.fromkeys(need_tag_display(tag) for tag in payload.habit_need_tags if tag.strip()))
    habit_need_tags.extend(tag for tag in _explicit_habit_need_tags(user_message) if tag not in habit_need_tags)
    if habit_need_tags:
        slots[SlotName.HABIT_NEED_TAGS] = habit_need_tags
        _fill_purpose_from_travel_habit(slots, habit_need_tags)
    return slots, range_reason


def _fill_purpose_from_travel_habit(slots: dict[str, SlotValue], habit_need_tags: list[str]) -> None:
    """Đã nói nhu cầu đi lại thì coi như đã trả lời mục đích — đừng hỏi lại.

    BUG THẬT trên prod 2026-08-26. Khách viết:

        "anh có khoảng 500 triệu và muốn 1 chiếc xe nhỏ gọn đi trong nội thành"

    Slot lưu về `habit_need_tags = ["Đi lại nội thành"]`, `budget_max_vnd` đủ,
    `purpose` RỖNG. Mà cụm hỏi mở đầu (`combined_intake.INTAKE_TOPICS`) gồm đúng
    hai mục ngân sách + mục đích, nên lượt ấy trả về câu hỏi *"anh/chị mua xe để
    dùng vào mục đích gì ạ — đi làm, giao hàng hay đi cá nhân?"* — hỏi lại đúng
    điều khách vừa nói, và KHÔNG xe nào được đề xuất.

    Bản vá cũ ở đây chỉ có `_COMMUTE_PURPOSE_PATTERN`, khớp đúng chuỗi "để đi
    làm" — quá hẹp để đỡ nổi cách nói thật.

    Chỉ nhận nhãn mô tả CÁCH ĐI LẠI. `COMPACT_SIZE` cũng nằm trong
    `habit_need_tags` (đo trên phiên `dc79722d`) nhưng nó tả xe trông thế nào,
    không tả khách dùng xe để làm gì — gán nó thành mục đích là đặt vào miệng
    khách một câu họ chưa nói, đúng thứ `need_tag_display` cố tránh.
    """

    if SlotName.PURPOSE in slots:
        return
    travel_habits = [tag for tag in habit_need_tags if describes_travel_habit(tag)]
    if travel_habits:
        slots[SlotName.PURPOSE] = ", ".join(travel_habits)


def _expected_slot_context(expected_slot: SlotName | None) -> str:
    if expected_slot is None:
        return ""
    return (
        "Nếu lượt hiện tại là câu trả lời ngắn, trường đang chờ được trả lời là "
        f"{expected_slot.value}. Vẫn trích tất cả thông tin mới khách nói trong lượt hiện tại."
    )


def _explicit_seat_count(user_message: str) -> int | None:
    matches = list(_EXPLICIT_SEAT_COUNT_PATTERN.finditer(user_message))
    if not matches:
        return None

    candidates: list[tuple[int, bool]] = []
    for match in matches:
        prefix_segment = re.split(r"[,;.!?]|\b(?:nhưng|nhung|mà|ma)\b", user_message[: match.start()])[-1]
        if _NEGATED_SEAT_PREFIX_PATTERN.search(prefix_segment):
            continue
        resolved = _RESOLVED_SEAT_SUFFIX_PATTERN.search(user_message[match.end() :]) is not None
        candidates.append((int(match.group(1)), resolved))

    resolved_counts = {count for count, resolved in candidates if resolved}
    if len(resolved_counts) == 1:
        return next(iter(resolved_counts))
    if len(resolved_counts) > 1:
        return None

    counts = {count for count, _ in candidates}
    if len(counts) != 1:
        return None
    if "?" in user_message and not _DIRECT_SEAT_NEED_PATTERN.search(user_message):
        return None
    return next(iter(counts))


def _standalone_positive_integer(user_message: str) -> int | None:
    match = _STANDALONE_POSITIVE_INTEGER_PATTERN.fullmatch(user_message)
    return int(match.group(1)) if match is not None else None


def _explicit_vehicle_type_for_slot(user_message: str) -> VehicleType | None:
    """Infer a branch without treating a negated/compared seat category as confirmed input."""

    inferred = explicit_vehicle_type(user_message)
    if (
        inferred is VehicleType.CAR
        and _EXPLICIT_SEAT_COUNT_PATTERN.search(user_message)
        and _EXPLICIT_CAR_NOUN_OR_MODEL_PATTERN.search(user_message) is None
    ):
        return None
    return inferred


def _explicit_habit_need_tags(user_message: str) -> list[str]:
    """Return stable tags only for usage phrases stated verbatim by the customer."""

    tags: list[str] = []
    if _INNER_CITY_PATTERN.search(user_message):
        tags.append("đi nội thành")
    countryside = _COUNTRYSIDE_PATTERN.search(user_message)
    if countryside is not None:
        prefix = countryside.group(0).casefold()
        tags.append("thỉnh thoảng về quê" if "thoảng" in prefix or "thoang" in prefix else "về quê")
    return tags


def _parse_budget(value: str | int | float) -> int | None:
    """Trần ngân sách. Giữ lại vì đây là điểm vào đã được test của module này."""

    return parse_budget_range(value).max_vnd


def _recovered_range(budget: BudgetRange, user_message: str) -> BudgetRange:
    """Lấy lại HƯỚNG của câu gốc khi giá trị LLM trả đã làm phẳng khoảng.

    `LLMExtractionPayload` chỉ có một ô `budget_max_vnd`, nên mọi câu của khách về
    tới đây đều đã bị ép thành MỘT con số và mất sạch hướng: "khoảng 900 triệu",
    "từ 900 triệu" và "dưới 900 triệu" cùng về đúng số 900.000.000. Đó là nguyên
    nhân gốc của bug đã quan sát — hai câu đầu cho ra cùng một trần 900 triệu
    không sàn, rồi phần thưởng "càng rẻ càng tốt" của `domain/scoring` đẩy VF 2
    (188tr), VF 3 (278tr), VF 5 (496tr) lên đầu cả hai.

    Câu gốc thì còn nguyên hướng, và `parse_budget_range` đọc được nó. Nên khi câu
    gốc cho ra một khoảng CÓ SÀN và con số LLM trả nằm gọn trong khoảng đó — tức
    hai nguồn đang nói về cùng một mức tiền — thì khoảng của câu gốc là bản đọc
    đầy đủ hơn và được dùng thay.

    Điều kiện "nằm trong khoảng" là cái chặn việc lấy nhầm một khoảng của con số
    khác trong câu: "Ô tô cho 7 người, ngân sách 500 triệu" mà LLM trả 500 triệu
    thì khoảng suy từ câu vẫn phải chứa 500 triệu mới được nhận.
    """

    if budget.max_vnd is None:
        return budget
    from_message = parse_budget_range(user_message)
    if from_message.min_vnd is None or from_message.max_vnd is None:
        return budget
    if not from_message.min_vnd <= budget.max_vnd <= from_message.max_vnd:
        return budget
    return from_message


def _lock_vehicle_type(
    slots: dict[str, SlotValue], known_type: VehicleType | None, user_message: str
) -> dict[str, SlotValue]:
    if known_type is None:
        return slots
    proposed = coerce_vehicle_type(slots.get(SlotName.VEHICLE_TYPE))
    if proposed is None or not keeps_known_vehicle_type(known=known_type, proposed=proposed, user_message=user_message):
        return slots
    guarded = dict(slots)
    guarded.pop(SlotName.VEHICLE_TYPE, None)
    return guarded


def _applicable_slots(slots: Mapping[str, SlotValue], known_type: VehicleType | None) -> dict[str, SlotValue]:
    effective_type = coerce_vehicle_type(slots.get(SlotName.VEHICLE_TYPE)) or known_type
    if effective_type is None:
        return dict(slots)
    return {name: value for name, value in slots.items() if is_applicable(effective_type, SlotName(name))}


#: Bộ slot tiền — cùng sống, cùng chết. Bỏ mỗi trần mà giữ sàn thì lượt sau lọc
#: bằng một cái sàn không có trần, còn tệ hơn.
_BUDGET_SLOTS: Final[tuple[SlotName, ...]] = (
    SlotName.BUDGET_MAX_VND,
    SlotName.BUDGET_MIN_VND,
    SlotName.BUDGET_STATED_VND,
)


def _drop_unsupported_slots(
    slots: Mapping[str, SlotValue], user_message: str, expected_slot: SlotName | None
) -> dict[str, SlotValue]:
    guarded = dict(slots)
    if _MONTHLY_INSTALLMENT_PATTERN.search(user_message):
        # Cả hai đầu, không chỉ trần: "trả góp khoảng 10 triệu mỗi tháng" nay đọc
        # ra một KHOẢNG (8–12 triệu), nên bỏ mỗi trần sẽ để lại đúng cái sàn 8
        # triệu — vẫn là khoản trả góp bị ghi nhầm thành ngân sách mua xe.
        guarded.pop(SlotName.BUDGET_MAX_VND, None)
        guarded.pop(SlotName.BUDGET_MIN_VND, None)
    # Ngân sách chỉ được ghi khi CHÍNH LƯỢT NÀY khách nói về tiền.
    #
    # Bug thật, đọc từ `turn_traces` prod 2026-08-26:
    #
    #     "1 tỷ, 5 người, đi làm, mỗi ngày 30km" -> budget_max_vnd = 1.000.000.000
    #     "tôi chọn VF 8 All New"                -> budget_max_vnd = 1.100.000.000
    #                                               budget_min_vnd =   900.000.000
    #
    # Lượt thứ hai không có một chữ nào về tiền. LLM nhắc lại ngân sách từ ngữ
    # cảnh và tự thêm chữ "khoảng", nên bộ đọc nới biên ±10% và GHI ĐÈ trần cũ:
    # ngân sách trôi thêm 100 triệu ở một lượt khách chỉ chọn xe. Lượt sau đó lọc
    # rộng hơn ý khách, và không ai thấy vì con số vẫn "hợp lý".
    #
    # Dùng `mentions_money` chứ KHÔNG dùng `parse_budget_range` trên nguyên câu:
    # bộ đọc kia cố ý lỏng (nó chạy trên chuỗi ngân sách LLM đã tách sẵn), nên
    # trên câu đầy đủ thì "VF 8" ra 8 triệu và "xe 5 chỗ" ra 5 triệu — tức chính
    # câu chọn xe lại tự cấp cho mình bằng chứng về tiền.
    #
    # Không có bằng chứng thì GIỮ NGUYÊN ngân sách đang lưu: bỏ một lần cập nhật
    # đáng ngờ rẻ hơn nhiều so với để trần trôi mỗi lượt.
    #
    # `expected_slot` là ngoại lệ: bot vừa hỏi ngân sách thì câu đáp có thể là
    # một dạng mà regex không đọc nổi, và ở đó `_salvaged_slots` mới là đường
    # phục hồi.
    if expected_slot is not SlotName.BUDGET_MAX_VND and any(name in guarded for name in _BUDGET_SLOTS):
        if not mentions_money(user_message):
            for name in _BUDGET_SLOTS:
                guarded.pop(name, None)
    if (
        SlotName.HOME_CHARGING in guarded
        and expected_slot is not SlotName.HOME_CHARGING
        and _CHARGING_SIGNAL_PATTERN.search(user_message) is None
        and _BARE_BOOLEAN_ANSWER_PATTERN.fullmatch(user_message) is None
    ):
        guarded.pop(SlotName.HOME_CHARGING, None)
    return guarded


def _travel_context_slots(
    user_message: str,
    canonical: CanonicalText,
    *,
    extracted: Mapping[str, SlotValue],
) -> dict[str, SlotValue]:
    """Tỉnh đăng ký + quãng đường mỗi ngày, đọc TẤT ĐỊNH từ lời khách.

    BUG THẬT trên prod 2026-08-26. Khách vừa chọn xe xong, gõ:

        "anh ở hồ chí minh và đi khoảng 50km 1 ngày"

    LLM trích về `slots_gained = {}` — RỖNG, dù chính nó gắn nhãn lượt này là
    `SLOT_ANSWER`. Slot rỗng ⇒ `turn_understanding._has_new_task_information`
    trả False ⇒ `reconcile_task_action` chọn `CLARIFY_TASK` ⇒ khách nhận câu
    *"cho em biết ngân sách hoặc số chỗ ngồi mong muốn nhé"* — hỏi lại ngân sách
    đã có từ ba lượt trước, và hỏi số chỗ, thứ luồng này đã bỏ hẳn không hỏi.

    `chain._resolve_registration_province` / `_resolve_daily_distance` ĐÃ đọc
    đúng hai giá trị ấy và ghi vào `known_slots` — nhưng chúng chạy TRƯỚC graph
    và ghi vào *slot đã biết*, còn "lượt này có tin gì mới không" lại chỉ đọc
    `current_slots` do LLM trả. Phép đọc tất định thắng, rồi không ai nghe thấy.

    Đọc lại ở đây bằng CHÍNH hai hàm đó nên không có nguồn sự thật thứ hai; chỗ
    này chỉ nói to kết quả lên đúng lúc bộ định tuyến còn nghe.
    """

    # Khoá là chính THÀNH VIÊN `SlotName`, không phải chuỗi `.value`.
    #
    # BUG THẬT bắt được khi chạy lại kịch bản prod 2026-08-27: vòng ghi slot cuối
    # `extract` gọi `upsert_slot(session_id, slot_name, value)` rồi đọc
    # `slot_name.value` — một chuỗi lọt vào đó làm NỔ cả lượt với
    # `AttributeError: 'str' object has no attribute 'value'`.
    #
    # mypy không cản được: `SlotName` là `StrEnum` nên nó suy kiểu khoá của dict
    # này thành `str`, và một `str` thật trông y hệt một thành viên enum.
    gained: dict[str, SlotValue] = {}
    if SlotName.REGISTRATION_PROVINCE not in extracted:
        province = detect_province(user_message, canonical)
        if province is not None:
            gained[SlotName.REGISTRATION_PROVINCE] = province
    if SlotName.REQUIRED_RANGE_KM not in extracted:
        daily_km = daily_distance_from_message(user_message)
        if daily_km is not None:
            # Qua ĐÚNG luật hợp lý của `normalize_range_km`, không dựng luật thứ
            # hai: "mỗi ngày 500 km" là con số T2 Lớp 3 cố ý KHÔNG ghi, để lượt
            # này phát câu xác nhận đơn vị. Bỏ qua bước này thì phép đọc tất định
            # ghi đè đúng thứ tầng kia vừa từ chối.
            normalized_km, reason = normalize_range_km(daily_km, "day")
            if normalized_km is not None and reason is None:
                gained[SlotName.REQUIRED_RANGE_KM] = normalized_km
    return gained


def _salvaged_slots(
    *,
    payload: LLMExtractionPayload,
    user_message: str,
    vehicle_type: VehicleType | None,
    pending: SlotName | None,
    extracted: Mapping[str, SlotValue],
) -> dict[str, SlotValue]:
    extracted_names = {SlotName(name) for name in extracted}
    if (
        pending is None
        or pending in extracted
        or payload.vehicle_name_mentions
        or (Intent.CATALOG_LOOKUP in payload.intents and Intent.ADVISORY not in payload.intents)
    ):
        return {}
    # A customer may correct or volunteer a different slot instead of answering
    # the pending question. Never reinterpret that same number/text a second time.
    # The one safe exception is the observed LLM mistake of filing purpose text
    # only as a habit tag.
    if extracted_names and not (pending is SlotName.PURPOSE and extracted_names <= {SlotName.HABIT_NEED_TAGS}):
        return {}
    value = salvage_slot(pending, user_message, vehicle_type)
    if value is not None:
        if pending is SlotName.BUDGET_MAX_VND:
            recovered: dict[SlotName, SlotValue] = {pending: value}
            floor = salvaged_budget_floor(user_message)
            if floor is not None:
                recovered[SlotName.BUDGET_MIN_VND] = floor
            stated = salvaged_budget_stated(user_message)
            if stated is not None:
                recovered[SlotName.BUDGET_STATED_VND] = stated
            return recovered
        return {pending: value}
    if pending is SlotName.VEHICLE_TYPE:
        return {}
    if pending is SlotName.HABIT_NEED_TAGS or is_non_answer(user_message):
        return {pending: DECLINED_SLOT_VALUE}
    return {}


def _normalize_mentions(mentions: list[str]) -> list[str]:
    """Gộp khoảng trắng và khử trùng lặp. KHÔNG lọc theo tập nào.

    Dùng chung cho cả tên xe lẫn tính năng, nên đừng nhét phép lọc riêng của một
    loại vào đây: bản đầu của `_feature_mention_codes` sửa thẳng hàm này để lọc
    mã tính năng, và `_vehicle_name_mentions` — vốn gọi cùng hàm — lập tức nuốt
    mất tên xe "Feliz". Bộ eval bắt được, nhưng chỉ vì có đúng một kịch bản phủ.
    """

    normalized = [" ".join(mention.split()) for mention in mentions]
    return list(dict.fromkeys(mention for mention in normalized if mention))


def _feature_mention_codes(mentions: list[str]) -> list[str]:
    """Giữ đúng MÃ thuộc tập đóng; chữ tự do thì thử quy về mã, không được thì bỏ.

    **Bug thật đo trên prod 2026-08-26.** Câu đầu tiên của một khách:

        "Tôi cần một chiếc SUV cho gia đình… xe rộng rãi thoải mái tone màu
         trắng bền bỉ"
        → feature_mentions = ["rộng rãi", "thoải mái", "tone màu trắng", "bền bỉ"]

    Bốn chuỗi đó đi thẳng vào `score`, mà `scoring._feature_mention_reasons` so
    `assertion.feature_code in asked` — chữ tự do không khớp mã nào nên **không
    góp một điểm nào, không log, không lỗi**. Đúng bẫy mục 3.4, ở một chỗ mới.

    Bỏ chúng KHÔNG mất gì: `_customer_wording` lấy ngữ cảnh từ `purpose` và
    `habit_need_tags`, không lấy từ trường này; còn `synthesize` tra nhãn theo mã
    nên chuỗi lạ vốn đã bị loại.

    Thử quy về mã TRƯỚC khi bỏ: "camera 360" LLM trả nguyên văn thì bảng cụm chữ
    đọc ra `CAMERA_360`, không việc gì phải vứt.
    """

    from src.agents.prompts.feature_askable import FEATURE_DISPLAY_LABELS

    resolved: list[str] = []
    for mention in _normalize_mentions(mentions):
        if mention in FEATURE_DISPLAY_LABELS:
            resolved.append(mention)
            continue
        resolved.extend(sorted(feature_codes_mentioned(mention)))
    return list(dict.fromkeys(resolved))


def _vehicle_name_mentions(llm_mentions: list[str], user_message: str) -> list[str]:
    """Keep LLM names and deterministically recover explicit VinFast model names."""

    mentions = [_canonical_vehicle_mention(item) for item in _normalize_mentions(llm_mentions)]
    mentions.extend(f"VF {match.group(1).upper()}" for match in _VF_MODEL_PATTERN.finditer(user_message))
    mentions.extend(
        " ".join(match.group(0).split()).title() for match in _MOTORBIKE_FAMILY_PATTERN.finditer(user_message)
    )
    return list(dict.fromkeys(mentions))


def _canonical_vehicle_mention(mention: str) -> str:
    match = _VF_MODEL_PATTERN.fullmatch(mention)
    return f"VF {match.group(1).upper()}" if match is not None else mention
