"""[A3-2] Render natural slot questions without LLM calls."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from src.agents.contracts import FilterCriteria
from src.agents.domain.slot_mapping import to_filter_criteria
from src.agents.domain.slot_policy import missing_required, next_slot
from src.agents.domain.slot_salvage import is_non_answer, is_vague_answer
from src.agents.domain.slot_tree import opening_group_for
from src.agents.domain.values import DECLINED_SLOT_VALUE, SlotName, SlotValue, VehicleType
from src.agents.domain.vehicle_type_inference import CAR_MIN_PRICE_VND, infer_vehicle_type
from src.agents.prompts.closed_clarify import closed_clarify_question
from src.agents.prompts.combined_intake import (
    INTAKE_TOPICS,
    build_combined_intake_question,
)
from src.agents.prompts.persona import CUSTOMER_ADDRESS
from src.agents.prompts.question_variants import get_question_variant
from src.agents.services.slot_codec import coerce_slots, coerce_vehicle_type

# Hỏi lại tối đa 1 lần (tổng 2 lượt) rồi bỏ qua field — quy tắc 1 của spec (T6).
# [GIẢ ĐỊNH] Đếm là "số lần ĐÃ hỏi", nên bỏ qua khi count > MAX, tức lần hỏi thứ 3.
MAX_ASK_ATTEMPTS: Final[int] = 1

#: Giá trị `SlotName` hợp lệ — để phân biệt slot thật với key không phải slot
#: (như `ROUTING_FIELD`) khi xét slot bị hỏi quá quota.
_SLOT_VALUES: Final[frozenset[str]] = frozenset(member.value for member in SlotName.__members__.values())

_ADDRESS = CUSTOMER_ADDRESS.capitalize()

_REJECTION_BEFORE = r"(?:không\s+(?:chọn|lấy|xem)|khong\s+(?:chon|lay|xem)|loại|loai|bỏ|bo)"
_REJECTION_AFTER = r"(?:không\s+(?:chọn|lấy)|khong\s+(?:chon|lay)|loại|loai|bỏ|bo)"

#: Câu hỏi CHỈ về số người — dùng khi PURPOSE đã có (Sếp 2026-08-21: khách đã
#: cho biết mục đích thì hỏi lại/hỏi thêm số người không được lặp lại vế mục
#: đích trong dòng ghép `_QUESTION_TEMPLATES[PASSENGER_COUNT]`/`QUESTION_VARIANTS`
#: nữa — đọc như bot không nghe khách vừa trả lời).
_PASSENGER_COUNT_ONLY_VARIANTS: Final[tuple[str, ...]] = (
    f"Xe nhà {CUSTOMER_ADDRESS} thường đi mấy người ạ?",
    f"Dạ {CUSTOMER_ADDRESS} cho em biết cụ thể xe hay chở khoảng bao nhiêu người ạ?",
)


def _millions_vnd(amount: object) -> str | None:
    """VND → "500 triệu" / "1,5 tỷ" cho câu ghi nhận lại (Sếp 2026-08-21).

    Không dùng `format_vnd` (đồng đầy đủ) vì câu ghi nhận cần ngắn gọn, đúng
    cách khách vừa nói ("500 triệu"), không phải số dài "500.000.000 đồng".
    """

    if not isinstance(amount, (int, float)):
        return None
    millions = amount / 1_000_000
    if millions >= 1000:
        billions = millions / 1000
        text = f"{billions:.1f}".replace(".", ",").removesuffix(",0")
        return f"{text} tỷ"
    return f"{int(millions):,}".replace(",", ".") + " triệu"


def _budget_recap_part(known_slots: Mapping[SlotName, SlotValue]) -> str | None:
    """Nhắc lại ngân sách bằng ĐÚNG con số khách nói (Sếp 2026-08-25).

    Khách gõ "khoảng 500 triệu" mà bot đáp "ngân sách khoảng 600 triệu" là nói
    lại một con số họ không hề nói — chỗ mất lòng tin nhanh nhất trong cả cuộc
    tư vấn. Nguyên nhân nằm ở `budget_parsing._approximate_range`: nó nới sẵn
    thành 400–600 rồi ghi 600 vào `budget_max_vnd`, và câu này in trần đó ra.

    Nay `_approximate_range` giữ nguyên con số khách nói ở CẢ HAI biên, nên:

    - hai biên BẰNG NHAU  → khách nói "khoảng X" → nhắc lại "khoảng X";
    - hai biên KHÁC NHAU  → khách tự nêu một khoảng → nhắc lại nguyên khoảng đó,
      vì gọi nó là "khoảng (X+Y)/2" cũng là bịa ra một con số khách không nói;
    - chỉ có trần         → "dưới X triệu" và các câu tương đương.

    Việc LỌC vẫn theo dải rộng hơn: `within_budget_band` nới ±`BUDGET_TOLERANCE`
    quanh các biên này. Dải và câu chữ là hai việc khác nhau — dải để không bỏ sót
    xe, câu chữ để khách nhận ra lời mình vừa nói.
    """

    # Con số khách NÓI RA thắng mọi thứ suy ra từ nó.
    stated_text = _millions_vnd(known_slots.get(SlotName.BUDGET_STATED_VND))
    if stated_text is not None:
        return f"ngân sách khoảng {stated_text}"
    min_text = _millions_vnd(known_slots.get(SlotName.BUDGET_MIN_VND))
    max_text = _millions_vnd(known_slots.get(SlotName.BUDGET_MAX_VND))
    if min_text is not None and max_text is not None:
        # Khách tự nêu một khoảng: nhắc lại nguyên khoảng đó. Gọi nó là "khoảng
        # (X+Y)/2" cũng là bịa ra một con số khách không nói.
        return f"ngân sách từ {min_text} đến {max_text}"
    if max_text is not None:
        return f"ngân sách khoảng {max_text}"
    if min_text is not None:
        return f"ngân sách từ {min_text} trở lên"
    return None


def _captured_recap(known_slots: Mapping[SlotName, SlotValue]) -> str:
    """Câu mở đầu "đã ghi nhận..." cho MỌI lượt hỏi sau lượt 1 (Sếp 2026-08-21).

    Chỉ nêu lại BUDGET_MAX_VND/PURPOSE/PASSENGER_COUNT — ba trường lượt 1 —
    và CHỈ trường đã có giá trị; trường đang được hỏi ở CHÍNH lượt này chưa
    có trong `known_slots` nên tự động không lọt vào câu ghi nhận, không cần
    loại trừ thủ công. Rỗng (chưa có gì) thì trả `""` — lượt hỏi đầu tiên
    không cần câu này.
    """

    parts: list[str] = []
    budget_part = _budget_recap_part(known_slots)
    if budget_part is not None:
        parts.append(budget_part)
    purpose = known_slots.get(SlotName.PURPOSE)
    if isinstance(purpose, str) and purpose.strip() and not purpose.startswith("__"):
        # "__declined__" là cờ nội bộ (khách không muốn nói) — không in ra thành
        # "mục đích __declined__" (đo 2026-08-28).
        parts.append(f"mục đích {purpose.strip()}")
    passenger = known_slots.get(SlotName.PASSENGER_COUNT)
    if isinstance(passenger, int):
        parts.append(f"{passenger} người sử dụng")
    interest = known_slots.get(SlotName.INTEREST_VEHICLE)
    if isinstance(interest, str) and interest.strip():
        parts.append(f"đang quan tâm {interest.strip()}")
    if not parts:
        return ""
    if len(parts) == 1:
        joined = parts[0]
    else:
        joined = ", ".join(parts[:-1]) + f" và {parts[-1]}"
    return f"Em đã ghi nhận thông tin của {CUSTOMER_ADDRESS} là {joined}.\n\n"


_QUESTION_TEMPLATES: Final[Mapping[SlotName, str]] = {
    SlotName.VEHICLE_TYPE: f"{_ADDRESS} đang tìm ô tô điện hay xe máy điện ạ?",
    # Câu ghép PASSENGER_COUNT + PURPOSE (thiết kế `docs/designs/luong-hoi-nhu-cau-
    # 3-luot.md` mục "Lượt 1"): PASSENGER_COUNT chỉ áp ô tô, PURPOSE áp cả hai nhánh,
    # nên gộp vào một câu để bộ trích xuất điền được một trong hai hoặc cả hai —
    # thiếu vế PURPOSE thì suy loại xe (giao hàng → xe máy) không có tín hiệu ở lượt 1.
    SlotName.PASSENGER_COUNT: (
        f"Xe thường chở mấy người, hoặc {CUSTOMER_ADDRESS} dùng để đi làm, giao hàng hay đi cá nhân ạ?"
    ),
    SlotName.REQUIRED_RANGE_KM: f"Một ngày {CUSTOMER_ADDRESS} đi khoảng bao nhiêu ki-lô-mét ạ?",
    SlotName.HOME_CHARGING: f"Ở nhà {CUSTOMER_ADDRESS} có chỗ sạc qua đêm không ạ?",
    SlotName.BUDGET_MAX_VND: f"{_ADDRESS} dự tính khoảng bao nhiêu cho chiếc xe này ạ?",
    SlotName.PURPOSE: (f"{_ADDRESS} mua xe để dùng vào mục đích gì ạ — đi làm, giao hàng hay đi cá nhân?"),
    SlotName.MAX_LOAD_KG: f"Mỗi chuyến {CUSTOMER_ADDRESS} thường chở nặng khoảng bao nhiêu ạ?",
    SlotName.HABIT_NEED_TAGS: f"{_ADDRESS} thường dùng xe thế nào, có gì đặc biệt cần lưu ý không ạ?",
}


@dataclass(frozen=True, slots=True)
class MissingRequiredSlotsError(Exception):
    """Report required slots missing before recommendation."""

    missing: tuple[SlotName, ...]

    def __str__(self) -> str:
        return f"thiếu slot bắt buộc: {', '.join(slot.value for slot in self.missing)}"


@dataclass(frozen=True, slots=True)
class SlotPlanningServiceImpl:
    """Return at most one rendered slot question per turn."""

    def next_field(
        self,
        *,
        vehicle_type: str | None,
        known_slots: Mapping[str, SlotValue],
        ask_counts: Mapping[str, int] | None = None,
    ) -> SlotName | None:
        """Slot kế tiếp cần hỏi — thuần logic, KHÔNG gọi LLM (prompt mục 3).

        Slot đã hỏi quá `MAX_ASK_ATTEMPTS` lần bị bỏ qua: khách không trả lời
        được thì hỏi thêm lần nữa cũng vậy, mà hội thoại thì đứng im mãi.
        `chain.run_turn` chịu trách nhiệm ghi giá trị "mở" cho slot bị bỏ qua để
        downstream vẫn thấy nó đã điền.
        """

        resolved = coerce_vehicle_type(vehicle_type)
        slots = dict(coerce_slots(known_slots))
        counts = {name: count for name, count in (ask_counts or {}).items()}
        while True:
            slot = next_slot(resolved, slots)
            if slot is None or counts.get(slot.value, 0) <= MAX_ASK_ATTEMPTS:
                return slot
            # Coi như đã điền để `next_slot` đi tiếp sang slot sau, KHÔNG sửa
            # `known_slots` của người gọi.
            slots[slot] = DECLINED_SLOT_VALUE

    def question_for(self, *, slot: SlotName, retry_count: int = 0, seed: str = "") -> str:
        """Câu hỏi cho một slot, đổi cách nói khi phải hỏi lại (prompt mục 3.1).

        `seed` là danh tính phiên: nó dời ĐIỂM XUẤT PHÁT của vòng biến thể, để hai
        hội thoại khác nhau không cùng mở đầu bằng một câu. Không có nó thì mọi
        phiên đều bắt đầu ở `retry_count = 0` — đo trên prod, câu hỏi loại xe lặp
        y nguyên 80 lần.
        """
        return get_question_variant(slot, retry_count, seed)

    def should_close_group_retry(self, user_message: str) -> bool:
        """Decide whether vague group answer needs closed clarification."""
        return is_non_answer(user_message) or is_vague_answer(user_message)

    def exhausted_notice(self, *, ask_counts: Mapping[str, int] | None = None) -> str | None:
        """Câu báo khi có slot bị bỏ vì hỏi quá quota — thay cho im lặng (B mục 3).

        `chain._open_exhausted_slots` đã đánh dấu "mở" slot quá quota rồi đi tiếp;
        câu này chỉ báo khách biết bot dừng hỏi, không phải lỗi. Loại
        `VEHICLE_TYPE` (lọc bắt buộc, không bỏ) và mọi key không phải slot thật
        (như `ROUTING_FIELD`) — cùng quy ước `_open_exhausted_slots`.
        """
        counts = {name: count for name, count in (ask_counts or {}).items()}
        exhausted = any(
            count > MAX_ASK_ATTEMPTS
            for name, count in counts.items()
            if name in _SLOT_VALUES and name != SlotName.VEHICLE_TYPE.value
        )
        if not exhausted:
            return None
        return f"Dạ em sẽ tư vấn với những thông tin {CUSTOMER_ADDRESS} đã cung cấp ạ."

    def vehicle_type_signals_conflict(self, *, passenger_count: object, budget_max_vnd: object) -> bool:
        """Detect passenger and budget signals that cannot support inferred car type."""
        return (
            isinstance(passenger_count, int)
            and passenger_count >= 3
            and isinstance(budget_max_vnd, (int, float))
            and budget_max_vnd < CAR_MIN_PRICE_VND
        )

    def next_group(
        self,
        *,
        vehicle_type: str | None,
        known_slots: Mapping[str, SlotValue],
        ask_counts: Mapping[str, int] | None = None,
    ) -> tuple[SlotName, ...]:
        """Nhóm slot mở đầu chưa có giá trị, chưa vượt quota (T5).

        Nhóm theo nhánh qua `opening_group_for` (ô tô giữ dòng ghép chỗ ngồi +
        mục đích; xe máy và lượt chưa biết loại xe hỏi PURPOSE riêng) và loại
        slot đã điền / đã hỏi quá `MAX_ASK_ATTEMPTS`. Khách trả lời thiếu một
        phần (vd chỉ ngân sách) → lượt sau hỏi lại ĐÚNG phần thiếu trong một
        tin nhắn; từng slot chỉ được hỏi lại một lần, quá quota thì nhóm xong
        (trả rỗng) → đi đề xuất bằng dữ liệu còn lại.
        """

        resolved = coerce_vehicle_type(vehicle_type)
        slots = dict(coerce_slots(known_slots))
        counts = {name: count for name, count in (ask_counts or {}).items()}
        # Chưa biết loại xe thì nhóm rỗng và câu hỏi LOẠI XE đi trước (Sếp
        # 2026-08-25) — trừ khi đã hỏi cạn quota mà khách vẫn không nói rõ,
        # lúc đó mới rơi về nhóm cũ để suy loại xe từ mục đích.
        exhausted = counts.get(SlotName.VEHICLE_TYPE.value, 0) > MAX_ASK_ATTEMPTS
        return tuple(
            slot
            for slot in opening_group_for(resolved, vehicle_type_exhausted=exhausted)
            if slots.get(slot) is None and counts.get(slot.value, 0) <= MAX_ASK_ATTEMPTS
        )

    def question_for_group(
        self,
        *,
        slots: Sequence[SlotName],
        retry: bool,
        closed: bool = False,
        known_slots: Mapping[str, SlotValue] | None = None,
    ) -> str:
        """Render một tin nhắn nhiều gạch đầu dòng cho nhóm slot (T5).

        `retry=False` dùng lời mở đầu đầy đủ; `retry=True` chỉ hỏi phần thiếu,
        gộp một tin nhắn, đúng một lần, và MỖI DÒNG đổi sang biến thể thứ hai —
        lặp nguyên văn câu vừa hỏi đọc như bot không nghe. `closed=True` (chỉ
        có ý nghĩa cùng `retry=True`) đổi từng dòng sang câu đóng thay vì câu
        mở — khách vừa trả lời mơ hồ cho cả nhóm ("tuỳ em", "không biết").
        Lời mở của lượt hỏi lại (Sếp 2026-08-21) nêu rõ đây là xin lại thông
        tin còn thiếu — khách mơ hồ/cố tình lảng tránh vẫn biết vì sao bị hỏi
        thêm, không phải bot lặp lại vô cớ.

        `known_slots` (Sếp 2026-08-21): PURPOSE đã có thì dòng PASSENGER_COUNT
        đổi sang câu CHỈ hỏi số người — dòng ghép "hoặc dùng để đi làm, giao
        hàng..." mặc định giả định PURPOSE chưa biết, lặp lại phần khách vừa
        trả lời đọc như bot không nghe.
        """

        purpose_known = known_slots is not None and known_slots.get(SlotName.PURPOSE.value) is not None
        lines: list[str] = []
        for slot in slots:
            if slot is SlotName.PASSENGER_COUNT and purpose_known:
                variants = _PASSENGER_COUNT_ONLY_VARIANTS
                variant = variants[min(1 if retry else 0, len(variants) - 1)]
                lines.append(f"- {variant}")
                continue
            text = closed_clarify_question(slot) if closed else None
            variant = get_question_variant(slot, 1 if retry else 0)
            lines.append(f"- {text if text is not None else variant}")
        body = "\n".join(lines)
        if retry:
            return (
                f"Mời {CUSTOMER_ADDRESS} vui lòng cung cấp thêm thông tin để em "
                f"tư vấn đúng nhu cầu của mình hơn nhé:\n{body}"
            )
        return f"Để em lọc đúng xe, {CUSTOMER_ADDRESS} cho em xin vài thông tin nhé:\n{body}"

    def inferred_vehicle_type(self, known_slots: Mapping[str, SlotValue]) -> tuple[VehicleType | None, bool]:
        """Suy loại xe từ slot (T3) — node gọi qua service, không import domain."""
        return infer_vehicle_type(coerce_slots(known_slots))

    def clarify_question(self, *, slot: SlotName) -> str | None:
        """Câu đóng khi khách trả lời mơ hồ (T4); `None` nếu slot không có."""
        return closed_clarify_question(slot)

    def captured_recap(self, known_slots: Mapping[str, SlotValue]) -> str:
        """Câu "đã ghi nhận..." đặt trước MỌI câu hỏi sau lượt 1 (Sếp 2026-08-21)."""
        return _captured_recap(coerce_slots(known_slots))

    def question_for_turn(
        self,
        *,
        slot: SlotName,
        retry_count: int,
        user_message: str,
        vehicle_mentions: Sequence[str],
        vehicle_type: str | None = None,
        known_slots: Mapping[str, SlotValue] | None = None,
        rejected_mention: str | None = None,
        rejection_reason: str | None = None,
        seed: str = "",
    ) -> str:
        """Câu hỏi của lượt này — GỘP nhiều tiêu chí khi đã biết loại xe.

        Ba nhánh, theo đúng thứ tự ưu tiên:

        1. Khách vừa loại một mẫu xe → xác nhận điều đó trước rồi mới hỏi ngân
           sách. Cụ thể hơn cả câu gộp, và chỉ xảy ra ở một lượt hiếm.
        2. Đã biết loại xe, đang ở LẦN HỎI ĐẦU, và còn từ hai tiêu chí thiếu →
           một tin nhắn hỏi hết, dạng danh sách đánh số.
        3. Còn lại → câu hỏi đơn như cũ. Bao gồm cả lượt HỎI LẠI
           (`retry_count > 0`): khách vừa trả lời hụt một phần thì hỏi lại đúng
           phần đó, dội lại cả danh sách là bắt họ đọc lại những câu đã trả lời.

        Chưa biết loại xe (`vehicle_type is None`) không bao giờ vào nhánh 2 —
        đó là bước một của luồng và nó phải đứng riêng.
        """

        if slot is SlotName.BUDGET_MAX_VND and retry_count == 0:
            acknowledgment = _vehicle_elimination_budget_question(
                user_message,
                vehicle_mentions,
                rejected_mention=rejected_mention,
                rejection_reason=rejection_reason,
            )
            if acknowledgment is not None:
                return acknowledgment
        combined = self._combined_question(
            slot=slot,
            retry_count=retry_count,
            vehicle_type=vehicle_type,
            known_slots=known_slots,
        )
        return combined or self.question_for(slot=slot, retry_count=retry_count, seed=seed)

    def _combined_question(
        self,
        *,
        slot: SlotName,
        retry_count: int,
        vehicle_type: str | None,
        known_slots: Mapping[str, SlotValue] | None,
    ) -> str | None:
        """Tin nhắn gộp, hoặc `None` khi lượt này không đủ điều kiện gộp."""

        resolved = coerce_vehicle_type(vehicle_type)
        if resolved is None or retry_count > 0:
            return None
        answered = coerce_slots(known_slots or {})
        unanswered = [topic for topic in INTAKE_TOPICS if answered.get(topic) is None or topic is slot]
        return build_combined_intake_question(vehicle_type=resolved, unanswered=unanswered)

    def next_question(
        self,
        *,
        vehicle_type: str | None,
        known_slots: Mapping[str, SlotValue],
        ask_counts: Mapping[str, int] | None = None,
        seed: str = "",
    ) -> str | None:
        """Return next rendered question, or None when slot capture is complete."""
        slot = self.next_field(vehicle_type=vehicle_type, known_slots=known_slots, ask_counts=ask_counts)
        if slot is None:
            return None
        return self.question_for(slot=slot, retry_count=(ask_counts or {}).get(slot.value, 0), seed=seed)

    def build_criteria(self, *, vehicle_type: str, known_slots: Mapping[str, SlotValue]) -> FilterCriteria:
        """Build Layer 1 criteria from confirmed slots through domain mapping."""
        resolved = coerce_vehicle_type(vehicle_type)
        if resolved is None:
            raise ValueError(f"loại phương tiện không hợp lệ: {vehicle_type!r}")
        return to_filter_criteria(resolved, coerce_slots(known_slots))

    def require_complete(self, *, vehicle_type: str | None, known_slots: Mapping[str, SlotValue]) -> None:
        """Reject recommendation when required slots remain unanswered."""
        missing = missing_required(coerce_vehicle_type(vehicle_type), coerce_slots(known_slots))
        if missing:
            raise MissingRequiredSlotsError(missing)


def _vehicle_elimination_budget_question(
    user_message: str,
    vehicle_mentions: Sequence[str],
    *,
    rejected_mention: str | None = None,
    rejection_reason: str | None = None,
) -> str | None:
    mentions = list(dict.fromkeys(mention.strip() for mention in vehicle_mentions if mention.strip()))
    if len(mentions) != 2:
        return None
    rejected = (
        rejected_mention
        if rejected_mention is not None and rejected_mention in mentions
        else next(
            (mention for mention in mentions if _is_rejected(user_message, mention)),
            None,
        )
    )
    if rejected is None:
        return None
    remaining = next(mention for mention in mentions if mention != rejected)
    reason = (
        rejection_reason
        if rejected_mention == rejected and rejection_reason
        else _rejection_reason(user_message, rejected)
    )
    reason_text = f" vì {reason}" if reason else ""
    return (
        f"Em đã ghi nhận anh/chị loại {rejected}{reason_text} và đang cân nhắc "
        f"{remaining}. Anh/chị dự tính ngân sách khoảng bao nhiêu ạ?"
    )


def _is_rejected(user_message: str, mention: str) -> bool:
    mention_pattern = _flexible_mention_pattern(mention)
    before = re.compile(
        rf"\b{_REJECTION_BEFORE}\s+(?:(?:mẫu|mau|xe|con)\s+)?{mention_pattern}\b",
        re.IGNORECASE,
    )
    after = re.compile(
        rf"\b{mention_pattern}\b\s*(?:(?:thì|thi|này|nay)\s+)?{_REJECTION_AFTER}\b",
        re.IGNORECASE,
    )
    return before.search(user_message) is not None or after.search(user_message) is not None


def _rejection_reason(user_message: str, rejected: str) -> str | None:
    mention_pattern = _flexible_mention_pattern(rejected)
    match = re.search(
        rf"\b{mention_pattern}\b\s+(?:vì|vi|do)\s+([^,.!?;]+)",
        user_message,
        re.IGNORECASE,
    )
    if match is None:
        return None
    reason = re.sub(r"\s+", " ", match.group(1)).strip()
    reason = re.split(
        r"\s+(?:và|va|nhưng|nhung|còn|con)\s+"
        r"(?=(?:đang|dang|giữ|giu|chốt|chot|chọn|chon|loại|loai|bỏ|bo)\b)",
        reason,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    return reason if 0 < len(reason) <= 80 else None


def _flexible_mention_pattern(mention: str) -> str:
    parts = [re.escape(part) for part in re.split(r"[\s-]+", mention.strip()) if part]
    return r"[\s-]*".join(parts)
