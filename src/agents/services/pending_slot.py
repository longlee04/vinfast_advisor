"""[A7-10] Nối câu trả lời ngắn của khách vào câu hỏi slot bot vừa đặt.

Chạy TRƯỚC `classify_scope` và trước cả bước trích slot bằng LLM. Hai lý do, cả
hai đều là lý do đúng đắn chứ không phải tối ưu tốc độ:

- "hà nội" đứng riêng bị `classify_scope` gắn OUT_OF_SCOPE rồi kết thúc lượt.
  Guardrail đó đúng cho một tin nhắn rời, nhưng đây không phải tin nhắn rời.
- Đã biết đang chờ slot nào thì trích bằng luật rẻ và chắc hơn gọi LLM.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from src.agents.domain.canonical_text import CanonicalText
from src.agents.domain.intent_reconciliation import is_test_drive_request
from src.agents.domain.on_road_pending import ON_ROAD_VEHICLE_SLOT
from src.agents.domain.pending_slot import PendingSlotRequest
from src.agents.domain.pricing_intent import PricingIntent, detect_province
from src.agents.domain.purpose_answer import purpose_from_answer
from src.agents.domain.slot_salvage import salvage_slot, salvaged_vehicle_type
from src.agents.domain.task_frame import is_suspendable, question_for
from src.agents.domain.test_drive import TEST_DRIVE_VEHICLE_SLOT
from src.agents.domain.values import SlotName
from src.agents.domain.vehicle_type_lock import explicit_vehicle_type

logger = logging.getLogger(__name__)

#: Bộ trích cho từng slot, RULE-BASED. Không gọi LLM: đã biết đang chờ gì thì
#: một hàm khớp mẫu vừa rẻ vừa chắc hơn, và không thêm một chỗ có thể bịa.
#: Nhận `canonical` sinh tại chain — gate không tự normalize (AMENDMENT 2).
SlotExtractor = Callable[[str, CanonicalText], object | None]


def message_only_extractor(extractor: Callable[[str], object | None]) -> SlotExtractor:
    """Bọc một bộ trích CHỈ nhận câu khách cho khớp hợp đồng `SlotExtractor`.

    BUG THẬT, sập trên prod 2026-08-26:

        TypeError: location_text_from() takes 1 positional argument but 2 were given

    `composition` cắm thẳng `location_text_from` / `location_kind_from` (một tham
    số) vào bảng `extractors` (hai tham số). Lỗi chỉ nổ ĐÚNG lúc khách gõ địa
    danh trả lời câu "cho em biết vị trí" — tức đúng bước đổi một cuộc tư vấn
    thành một lịch lái thử, và không lượt nào khác chạm tới nhánh đó.

    mypy không bắt được: `{**DEFAULT_EXTRACTORS, SLOT: ham_mot_tham_so}` bị suy
    kiểu nới ra thành `dict[str, object]` nên phép gán không còn gì để kiểm.

    Vì vậy bọc, chứ không đổi chữ ký hàm gốc: `services/nearby_location` gọi
    chúng với ĐÚNG một tham số, và thêm một tham số thừa ở đó là bắt một chỗ
    đang đúng phải mang theo thứ nó không dùng.
    """

    def adapted(user_message: str, _canonical: CanonicalText) -> object | None:
        return extractor(user_message)

    return adapted


def _vehicle_type_value(user_message: str, canonical: CanonicalText) -> object | None:
    """Nhánh xe khách vừa chọn, dưới dạng chuỗi enum như `conversation_slots` lưu."""

    del canonical
    resolved = salvaged_vehicle_type(user_message)
    return None if resolved is None else resolved.value


DEFAULT_EXTRACTORS: dict[str, SlotExtractor] = {
    "province": detect_province,
    # Câu hỏi làm rõ "ô tô điện hay xe máy điện ạ?" (A3-2) là câu hỏi slot đầu
    # tiên của MỌI cuộc tư vấn, nên câu trả lời cho nó là lượt hay bị đọc sai
    # nhất: "xe ô tô điện" đứng riêng là một cụm danh từ không có hành động nào,
    # và `classify_scope` gắn OUT_OF_SCOPE rồi kết thúc lượt.
    SlotName.VEHICLE_TYPE.value: _vehicle_type_value,
    # Ngân sách đọc tất định ("2 tỉ", "tài chính khoảng 500 triệu…"): câu hỏi
    # nhóm (ngân sách + mục đích) sau bảng catalog giữ pending ở slot ngân sách,
    # không có bộ đọc này thì câu trả lời đúng cũng bị "xin lại thông tin"
    # (đo 2026-08-28).
    SlotName.BUDGET_MAX_VND.value: lambda message, canonical: salvage_slot(SlotName.BUDGET_MAX_VND, message, None),
    # Câu hỏi MỤC ĐÍCH. Đo trên prod 2026-08-28 (phiên `456c34e1`): bot hỏi mục
    # đích, khách đáp *"đi làm thôi"*, bot HỎI LẠI đúng câu đó bằng lời khác,
    # khách phải nói lần hai là *"đi làm"* mới đi tiếp.
    #
    # Thiếu dòng này thì `can_resolve("purpose")` trả `False`, `_advisory_pending`
    # không mở bản ghi chờ, và lượt sau không còn dấu vết nào cho biết câu của
    # khách đang trả lời cái gì — trông cả vào LLM, LLM trượt là mất lượt.
    SlotName.PURPOSE.value: purpose_from_answer,
}

#: Slot mà LUỒNG CHỦ của nó tự hỏi lại, nên trích thất bại ở đây phải THẢ lượt về
#: pipeline thường thay vì hỏi lại tại chỗ.
#:
#: Khác `province`: câu hỏi tỉnh chỉ tồn tại bên trong tool giá lăn bánh, thả lượt
#: đi là mất luôn phép tính khách đang chờ, nên ở đó hỏi lại là đúng. Còn
#: `vehicle_type` thuộc cây slot A3-2 và `ask_or_retrieve` sẽ hỏi lại đúng câu đó
#: ở cuối lượt nếu slot vẫn thiếu — hỏi lại ở đây vừa lặp câu, vừa chặn mất
#: guardrail/router xử lý một câu khách đã đổi hẳn sang chủ đề khác.
#: Khoá trong `partial_form` chở CẢ NHÓM slot mà một câu hỏi gộp đang chờ.
#: Xem `chain._advisory_pending` về lý do không thể chỉ giữ một slot.
PENDING_GROUP_KEY: Final[str] = "pending_group"

DEFAULT_RELEASE_ON_FAILURE: frozenset[str] = frozenset(
    {
        SlotName.VEHICLE_TYPE.value,
        SlotName.PURPOSE.value,
        # Không đọc được ngân sách tất định thì thả về pipeline cho LLM đọc, không
        # giam khách ở câu "xin lại thông tin budget_max_vnd".
        SlotName.BUDGET_MAX_VND.value,
        TEST_DRIVE_VEHICLE_SLOT,
        ON_ROAD_VEHICLE_SLOT,
    }
)

#: Nói ra rằng câu hỏi đang chờ vừa bị bỏ. Ngắn, không xin lỗi dài dòng: khách
#: vừa chủ động đổi việc, họ cần biết chuyện gì xảy ra chứ không cần được dỗ.
DROPPED_FOR_TEST_DRIVE: Final[str] = "Dạ em tạm để lại câu hỏi lúc nãy để sắp xếp lái thử cho anh/chị trước ạ."


@dataclass(frozen=True, slots=True)
class PendingResolution:
    """Kết quả xử lý một lượt khi đang có pending.

    `handled=False` nghĩa là lượt đi tiếp vào pipeline thường — hoặc vì không có
    pending, hoặc vì đã bỏ cuộc và coi khách đổi chủ đề.
    """

    handled: bool = False
    filled_form: Mapping[str, object] | None = None
    intent: str | None = None
    #: Slot vừa được điền. `filled_form` đã chứa giá trị đó, nhưng người gọi không
    #: có cách nào biết khoá NÀO trong form là khoá mới nếu không nói ra ở đây.
    missing_slot: str | None = None
    reply: str | None = None
    #: Bản ghi pending cần lưu lại. `None` + `clear_pending=True` là xoá.
    pending: PendingSlotRequest | None = None
    clear_pending: bool = False
    #: Câu nói ra rằng câu hỏi đang chờ vừa bị BỎ để nhường cho việc khách vừa
    #: xin. Mỗi phiên chỉ giữ ĐÚNG MỘT `pending_slot_request`, nên nhường là mất
    #: — mất trong im lặng thì khách tưởng hệ vẫn đang giữ câu hỏi cũ.
    dropped_notice: str | None = None
    #: Việc công cụ vừa bị THẢ vì khách chen một câu khác. Chain treo nó lại
    #: (`domain/task_frame`) và quay lại sau khi trả lời câu chen ngang — thả
    #: trong im lặng là mất luôn việc khách đã xin (Sếp 2026-08-29).
    suspended: PendingSlotRequest | None = None


@dataclass(slots=True)
class PendingSlotServiceImpl:
    """Đọc pending, thử điền, quyết định lượt này đi đâu."""

    extractors: Mapping[str, SlotExtractor] = field(default_factory=lambda: dict(DEFAULT_EXTRACTORS))
    clarify_questions: Mapping[str, str] = field(default_factory=dict)
    #: Bộ trích DỰ PHÒNG, chạy khi bộ rule-based ở trên không lấy được gì. Đây là
    #: điểm nối thứ hai của tầng nhận diện bốn lớp, và nó BẮT BUỘC phải ở đây
    #: chứ không phải trong graph: `chain._resume_pending_slot` chạy trước
    #: `graph.ainvoke` và kết thúc lượt ngay khi giải được, nên node
    #: `recognize_intent` không bao giờ nhìn thấy lượt đang trả lời một slot.
    #: Cắm bốn lớp vào mỗi graph là để tính năng "ưu tiên diễn giải theo slot
    #: đang chờ" không bao giờ chạy.
    fallback_extractors: Mapping[str, SlotExtractor] = field(default_factory=dict)
    #: Xem `DEFAULT_RELEASE_ON_FAILURE`.
    release_on_failure: frozenset[str] = DEFAULT_RELEASE_ON_FAILURE
    #: Câu chốt khi đã hỏi lại đủ số lần mà vẫn không trích được, theo từng slot.
    #:
    #: Mặc định RỖNG nên hành vi cũ không đổi một chút nào: slot không có mục ở
    #: đây vẫn thả lượt về pipeline thường (`handled=False`), đúng như `province`
    #: đang làm. Chỉ slot nào mà việc thả lượt để lại một câu hỏi treo — nhánh so
    #: sánh vừa hỏi "Quý khách muốn so sánh xe nào" hai lần — mới cần nói ra một
    #: câu kết thúc, thay vì im lặng chuyển chủ đề.
    exhausted_replies: Mapping[str, str] = field(default_factory=dict)

    def can_resolve(self, slot_name: str) -> bool:
        """Slot này có bộ trích nào không.

        `chain.run_turn` hỏi trước khi ghi lại một câu hỏi slot thành pending: ghi
        pending cho một slot không ai trích được thì lượt sau chỉ nhận lại đúng
        câu hỏi cũ, tức là biến cơ chế cứu ngữ cảnh thành một vòng lặp.
        """

        return slot_name in self.extractors or slot_name in self.fallback_extractors

    def resolve(
        self,
        *,
        payload: Mapping[str, object] | None,
        user_message: str,
        canonical: CanonicalText,
        now: datetime | None = None,
    ) -> PendingResolution:
        """Quyết định lượt này có phải câu trả lời cho câu hỏi vừa đặt không."""

        pending = PendingSlotRequest.from_payload(payload)
        moment = now or datetime.now(UTC)
        if pending is None:
            return PendingResolution()
        if pending.is_expired(moment):
            # Hết hạn dọn NGAY LÚC ĐỌC, không cần cron. Khách quay lại sau nửa
            # tiếng thì tin nhắn mới của họ là tin nhắn mới, không phải câu trả
            # lời cho câu hỏi họ đã quên.
            logger.info("pending slot %s hết hạn, đã xoá", pending.missing_slot)
            return PendingResolution(clear_pending=True)

        # Thử slot đang chờ TRƯỚC, rồi tới các slot còn lại trong cùng câu hỏi
        # nhóm. Khách trả lời slot NÀO trong nhóm cũng là một câu trả lời hợp lệ.
        filled_slot, value = pending.missing_slot, None
        if str(pending.intent).upper() == "ADVISORY" and pending.missing_slot != "vehicle_type":
            # Đổi LOẠI XE phải xét TRƯỚC bộ trích slot đang chờ: "thôi xe máy đi"
            # mà đưa vào bộ trích mục đích thì chữ "thôi" bị đọc thành từ chối
            # (đo 2026-08-28: purpose = __declined__, còn loại xe thì lỡ).
            folded = canonical.folded
            plain_switch = (
                len(folded.split()) <= 6 and re.search(r"\d|\bvf\b|evo|klara|feliz|vento|theon", folded) is None
            )
            explicit = explicit_vehicle_type(user_message) if plain_switch else None
            if explicit is not None:
                filled_slot, value = "vehicle_type", explicit.value
        if value is None:
            value = self._extract(pending.missing_slot, user_message, canonical)
        if value is None or value == "__declined__":
            # Từ chối ("sao cũng được") chỉ được nhận khi KHÔNG slot nào trong nhóm
            # đọc ra giá trị thật: "500" trả lời nhóm (ngân sách, mục đích) là 500
            # triệu, không phải "từ chối nói mục đích" (đo 2026-08-28).
            for name in dict(pending.partial_form).get(PENDING_GROUP_KEY) or []:
                if not isinstance(name, str) or name == pending.missing_slot:
                    continue
                recovered = self._extract(name, user_message, canonical)
                if recovered is not None:
                    filled_slot, value = name, recovered
                    break
        if value is not None:
            # Quyết định "đây là câu TRẢ LỜI cho slot đang chờ, không phải ý định
            # mới". Log lại vì bug gốc là một bug IM LẶNG: không dòng nào cho biết
            # router đã đọc câu của khách theo nghĩa nào.
            logger.info(
                "pending slot %s duoc dien tu cau tra loi %r (intent %s)",
                pending.missing_slot,
                user_message[:120],
                pending.intent,
            )
            return PendingResolution(
                handled=True,
                # Bỏ khoá nhóm khỏi form trả ra: nó là ghi chú nội bộ của bản
                # ghi chờ, không phải một slot khách vừa nói.
                filled_form={
                    **{k: v for k, v in dict(pending.partial_form).items() if k != PENDING_GROUP_KEY},
                    filled_slot: value,
                },
                intent=pending.intent,
                missing_slot=filled_slot,
                clear_pending=True,
            )
        # Lời xin lái thử CẮT NGANG câu hỏi đang chờ.
        #
        # BUG THẬT: `province` không nằm trong `release_on_failure`, nên khách
        # đang được hỏi "tỉnh nào" mà gõ *"đăng ký lái thử"* thì trích không ra,
        # hệ hỏi lại tỉnh, và lượt DỪNG ngay đó — nhánh lái thử ở `route_intent`
        # không bao giờ chạy tới. Bộ đọc tất định nhận ra đúng ý khách, đường vào
        # bị chặn: đúng họ lỗi đang phải dọn.
        #
        # Nhường là MẤT câu hỏi cũ (một pending mỗi phiên), nên phải nói ra.
        if pending.missing_slot == "budget_max_vnd" and re.fullmatch(r"\d", canonical.folded.strip()):
            # "2" trả lời câu ngân sách: 2 triệu hay 2 tỷ? Không đoán (Sếp chốt
            # 2026-08-28) — hỏi lại đơn vị, giữ pending.
            digit = canonical.folded.strip()
            return PendingResolution(
                handled=True,
                reply=f"Dạ anh/chị nói {digit} triệu hay {digit} tỷ ạ? Anh/chị cho em con số kèm đơn vị nhé.",
                pending=pending.clarified(),
            )
        if is_test_drive_request(user_message) and pending.missing_slot != TEST_DRIVE_VEHICLE_SLOT:
            logger.info(
                "pending slot %s bi loi xin lai thu cat ngang, tha luot: %r",
                pending.missing_slot,
                user_message[:120],
            )
            return PendingResolution(
                clear_pending=True, dropped_notice=DROPPED_FOR_TEST_DRIVE, suspended=_suspendable(pending)
            )
        if pending.missing_slot in self.release_on_failure:
            logger.info(
                "pending slot %s: khong trich duoc tu %r, tha luot ve pipeline thuong",
                pending.missing_slot,
                user_message[:120],
            )
            return PendingResolution(clear_pending=True, suspended=_suspendable(pending))
        if pending.exhausted():
            # Hỏi lại đủ số lần mà vẫn không trích được → coi là đổi chủ đề.
            # Log để về sau soi lại template câu hỏi có gây hiểu lầm không.
            logger.info(
                "pending slot %s bị bỏ sau %d lượt hỏi lại; câu cuối: %r",
                pending.missing_slot,
                pending.turn_count + 1,
                user_message[:120],
            )
            closing = self.exhausted_replies.get(pending.missing_slot)
            if closing is None:
                return PendingResolution(clear_pending=True)
            return PendingResolution(handled=True, reply=closing, clear_pending=True)
        return PendingResolution(
            handled=True,
            reply=self.clarify_questions.get(pending.missing_slot) or _fallback_clarify(pending),
            pending=pending.clarified(),
        )

    def _extract(self, slot_name: str, user_message: str, canonical: CanonicalText) -> object | None:
        """Bộ chính trước, bộ dự phòng sau — thứ tự này là điều kiện an toàn.

        Bộ rule-based chính (`detect_province`) khớp chính xác và không bao giờ
        đoán. Bộ dự phòng khớp MỜ, nên chỉ được chạy khi bộ chính đã bó tay: đảo
        thứ tự thì một câu khách viết đúng vẫn có thể bị bộ mờ đọc thành một giá
        trị gần đúng, và ta đánh đổi độ chính xác để lấy đúng những ca không cần.
        """

        extractor = self.extractors.get(slot_name)
        value = extractor(user_message, canonical) if extractor is not None else None
        if value is not None:
            return value
        fallback = self.fallback_extractors.get(slot_name)
        if fallback is None:
            return None
        recovered = fallback(user_message, canonical)
        if recovered is not None:
            logger.info(
                "pending slot %s duoc cuu boi bo tri xuat du phong: %r",
                slot_name,
                user_message[:80],
            )
        return recovered


def _fallback_clarify(pending: PendingSlotRequest) -> str:
    """Câu hỏi lại theo khung việc; chỉ khi intent không khai báo mới rơi về câu chung.

    Trước đây in thẳng tên slot kỹ thuật ("xin lại thông tin test_drive_vehicle")
    ra màn chat.
    """

    declared = question_for(pending.intent, pending.missing_slot)
    if declared:
        return f"Dạ, {declared[0].lower()}{declared[1:]}"
    return "Dạ, anh/chị cho em xin thêm thông tin để em làm tiếp giúp ạ?"


def _suspendable(pending: PendingSlotRequest) -> PendingSlotRequest | None:
    return pending if is_suspendable(pending) else None


def pending_for_province(vehicle_variant: object, vehicle_name: str, asked_at: datetime) -> PendingSlotRequest:
    """Bản ghi pending cho câu hỏi tỉnh của luồng giá lăn bánh.

    Lưu kèm TÊN xe chứ không chỉ id: lượt sau tính xong phải xưng đúng tên mẫu
    xe, mà tra lại tên chỉ để in một dòng là một lần chạm database thừa.
    """

    return PendingSlotRequest(
        intent=PricingIntent.ON_ROAD_PRICE_LOOKUP.value,
        missing_slot="province",
        partial_form={"vehicle_variant": str(vehicle_variant), "vehicle_name": vehicle_name},
        asked_at=asked_at,
    )


__all__ = [
    "DEFAULT_EXTRACTORS",
    "DEFAULT_RELEASE_ON_FAILURE",
    "PendingResolution",
    "PendingSlotServiceImpl",
    "message_only_extractor",
    "pending_for_province",
]
