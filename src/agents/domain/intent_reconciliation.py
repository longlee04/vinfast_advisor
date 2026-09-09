"""Pure, deterministic reconciliation of raw LLM intent labels."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Final

from src.agents.domain.canonical_text import CanonicalText, build_canonical_text
from src.agents.domain.comparative_revision import detect_comparative_revision
from src.agents.domain.nearby_location import is_nearby_location_request
from src.agents.domain.pricing_intent import PricingIntent, classify_pricing_intent
from src.agents.domain.values import Intent, SlotName, SlotValue, is_declined
from src.agents.domain.vehicle_comparison import plan_comparison

_NEED_CUE = re.compile(
    r"\b(?:cần|can|muốn|muon|tìm|tim|ưu\s*tiên|uu\s*tien|tư\s*vấn|tu\s*van|"
    r"phù\s*hợp|phu\s*hop|có\s*nên\s*mua|co\s*nen\s*mua|có\s*hợp|co\s*hop)\b",
    re.IGNORECASE,
)
_CATALOG_CUE = re.compile(
    r"(?:\?|\b(?:giá|gia|bao\s*nhiêu|bao\s*nhieu|khác|khac|so\s*sánh|so\s*sanh|"
    r"thông\s*số|thong\s*so|lỗi|loi|bị\s*sao|bi\s*sao)\b)",
    re.IGNORECASE,
)
_TECHNICAL_OR_COMPARISON = re.compile(
    r"\b(?:pin\s+tụt|pin\s+tut|lỗi|loi|bị\s+sao|bi\s+sao|khác\s+nhau|khac\s+nhau|"
    r"so\s*sánh|so\s*sanh)\b",
    re.IGNORECASE,
)
_PASSENGER_EVIDENCE = re.compile(
    r"\b(?:\d+|một|mot|hai|ba|bốn|bon|năm|nam|sáu|sau|bảy|bay|tám|tam|chín|chin)"
    r"\s*(?:người|nguoi|chỗ|cho|thành\s*viên|thanh\s*vien)\b",
    re.IGNORECASE,
)
_BUDGET_EVIDENCE = re.compile(
    r"\b(?:ngân\s*sách|ngan\s*sach|tài\s*chính|tai\s*chinh|triệu|trieu|tr|tỷ|ty)\b",
    re.IGNORECASE,
)
_DAILY_RANGE_EVIDENCE = re.compile(
    r"(?:\b(?:mỗi\s*ngày|moi\s*ngay|hàng\s*ngày|hang\s*ngay|quãng\s*đường|"
    r"quang\s*duong|đi\s*lại|di\s*lai)\b.*\bkm\b|\bkm\b.*\b(?:mỗi\s*ngày|"
    r"moi\s*ngay|hàng\s*ngày|hang\s*ngay)\b)",
    re.IGNORECASE,
)
_CHARGING_EVIDENCE = re.compile(r"\bsạc\b|\bsac\b", re.IGNORECASE)
_LOAD_EVIDENCE = re.compile(r"\b(?:kg|tải\s*trọng|tai\s*trong)\b", re.IGNORECASE)
_ALL_MODELS_CUE = re.compile(
    r"\b(?:tất\s*cả|tat\s*ca|mọi|moi|bất\s*kỳ|bat\s*ky)\b.*"
    r"\b(?:xe|mẫu|mau)\b|\b(?:xe|mẫu|mau)\b.*"
    r"\b(?:tất\s*cả|tat\s*ca|mọi|moi|bất\s*kỳ|bat\s*ky)\b",
    re.IGNORECASE,
)
_GENERIC_VEHICLE_DISCOVERY_CUE = re.compile(
    r"\b(?:tư\s*vấn|tu\s*van|mua|xem|chọn|chon|tìm|tim|gợi\s*ý|goi\s*y)\b.*"
    r"\b(?:xe|mẫu|mau|ô\s*tô|o\s*to|oto|xe\s*hơi|xe\s*hoi)\b|"
    r"\b(?:xe|mẫu|mau)\s+khác\b",
    re.IGNORECASE,
)
_BARE_ADVISORY_CUE = re.compile(
    r"^\s*(?:(?:tôi|toi|mình|minh)\s+muốn\s+|(?:tôi|toi|mình|minh)\s+muon\s+)?"
    r"tư\s*vấn(?:\s+giúp\s+(?:tôi|toi|mình|minh))?\s*[.!?]*\s*$|"
    r"^\s*tu\s*van(?:\s+giup\s+(?:toi|minh))?\s*[.!?]*\s*$",
    re.IGNORECASE,
)
#: Khách xin xem CÁC MẪU ("mẫu ô tô phù hợp") hoặc xin xe KHÁC với cái vừa xem.
#: Đây là chỗ duy nhất tách được hai câu đó khỏi "tôi cần tư vấn xe ô tô" — câu
#: mới chỉ nêu một LOẠI xe và còn thiếu tiêu chí để lọc, nên phải hỏi gộp trước.
_MODEL_NOUN_CUE = re.compile(r"\b(?:mẫu|mau)\b|\b(?:xe|mẫu|mau)\s+(?:khác|khac)\b", re.IGNORECASE)
_PERSONAL_CRITERION_CUE = re.compile(
    r"\b(?:gia\s*đình|gia\s*dinh|thành\s*viên|thanh\s*vien|trả\s*góp|tra\s*gop|"
    r"mỗi\s*tháng|moi\s*thang|trạm\s*sạc|tram\s*sac|sạc|sac)\b",
    re.IGNORECASE,
)
_NAMED_MODEL_LISTING_CUE = re.compile(
    r"\b(?:(?:tất\s*cả|tat\s*ca|toàn\s*bộ|toan\s*bo|mọi|moi)\s+"
    r"(?:các\s+|cac\s+)?(?:mẫu|mau|phiên\s+bản|phien\s+ban|xe)|"
    r"danh\s*sách|danh\s*sach|liệt\s*kê|liet\s*ke|show|"
    r"các\s+mẫu|cac\s+mau|các\s+phiên\s+bản|cac\s+phien\s+ban)\b",
    re.IGNORECASE,
)
#: Câu TRẦN chỉ nói loại xe — "Ô tô điện", "xe máy điện ạ", "oto".
#:
#: Đây đúng là chuỗi mà nút chọn loại xe gửi đi, nên nó là CÂU TRẢ LỜI, không
#: phải lời xin danh mục. Chạy thật trên prod 2026-08-26:
#:
#:     bot : "Anh/chị cho em xin loại xe nhé — ô tô điện hay xe máy điện ạ?"
#:     khách: "Ô tô điện"
#:     bot : "VinFast hiện có dải sản phẩm… Dưới đây là 7 dòng ô tô điện…"
#:
#: Khách bấm đúng nút bot vừa đưa ra và nhận về một bảng danh mục.
#:
#: Vì sao không dựa vào `expected_slot`: chain suy `inferred_vehicle_type` TRƯỚC
#: bước trích, nên `expected_slot` đã nhảy sang slot kế tiếp và vế "đang chờ loại
#: xe" không còn đúng ở đúng cái lượt cần nó.
#:
#: Khớp TOÀN CHUỖI, nên "ô tô điện gồm những xe nào" không lọt vào đây — câu đó
#: vẫn là lời xin danh mục thật.
_BARE_VEHICLE_TYPE_REPLY: Final[re.Pattern[str]] = re.compile(
    r"(?:da\s*|vang\s*|em\s*chon\s*|toi\s*chon\s*|chon\s*)?"
    r"(?:xe\s*)?(?:o\s*to|oto|xe\s*hoi|xe\s*con|xe\s*may|xe\s*gan\s*may|xe\s*tay\s*ga)"
    r"(?:\s*dien)?"
    r"(?:\s*(?:a|ah|nhe|nha|di|thoi|nay|ok))*\s*[.!]?"
)


def _fold_reply(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", (value or "").casefold())
    plain = "".join(character for character in decomposed if unicodedata.category(character) != "Mn")
    return re.sub(r"\s+", " ", plain.replace("d\u0111", "d").replace("đ", "d")).strip()


_BARE_VEHICLE_TYPE_CUE = re.compile(
    r"^\s*(?:CAR|MOTORBIKE|ELECTRIC_MOTORBIKE|"
    r"ô\s*tô|o\s*to|oto|xe\s*máy|xe\s*may|"
    r"ô\s*tô\s*điện|o\s*to\s*dien|oto\s*dien|"
    r"xe\s*máy\s*điện|xe\s*may\s*dien|"
    r"xe\s*hơi|xe\s*hoi|xe\s*điện|xe\s*dien|"
    r"tất\s*cả\s*(?:các\s+)?(?:mẫu\s*)?xe|tat\s*ca\s*(?:cac\s+)?(?:mau\s*)?xe|"
    r"danh\s*sách\s*xe|danh\s*sach\s*xe|"
    r"các\s*mẫu\s*xe|cac\s*mau\s*xe|"
    r"toàn\s*bộ\s*xe|toan\s*bo\s*xe)\s*[.!?]*\s*$",
    re.IGNORECASE,
)
_REFERENCE_LOOKUP_CUE = re.compile(
    r"\bmẫu\s+(?:còn\s+lại|thứ\s+hai|(?:tôi\s+)?vừa\s+(?:loại|bỏ)|vừa\s+nói)\b|"
    r"\bmau\s+(?:con\s+lai|thu\s+hai|(?:toi\s+)?vua\s+(?:loai|bo)|vua\s+noi)\b",
    re.IGNORECASE,
)
_VEHICLE_CONSIDERATION_CUE = re.compile(
    r"\b(?:cân\s*nhắc|can\s*nhac|phân\s*vân|phan\s*van|"
    r"đang\s+(?:xem|ngắm)|dang\s+(?:xem|ngam)|quan\s*tâm|quan\s*tam)\b",
    re.IGNORECASE,
)
_REFERENTIAL_SELECTION_ACTION = re.compile(
    r"\b(?:loại|loai|bỏ|bo|giữ\s*lại|giu\s*lai|chốt|chot)\s+"
    r"(?:mẫu|mau|xe|con)\b",
    re.IGNORECASE,
)
#: Khách QUYẾT ĐỊNH mua một mẫu xe đích danh ("chốt mẫu X", "chốt con X"). Khác
#: `_REFERENTIAL_SELECTION_ACTION` ở ngữ nghĩa: "loại/giữ lại" là thao tác LỌC
#: danh sách đang chọn hộ, còn "chốt" là lời CHỐT cuối cùng cho ĐÚNG một xe — phải
#: đi nhánh tra cứu đúng xe đó, không được chảy vào xếp hạng cả danh mục.
_COMMIT_ACTION = re.compile(
    r"\b(?:chốt|chot)\s+(?:mẫu|mau|xe|con)\b",
    re.IGNORECASE,
)
#: "lái thử" đủ các biến thể gõ thật: có/không dấu, "thử" viết nhầm thành "thứ".
#: Xin đặt lịch lái thử.
#:
#: Nhánh `l[áa]i\s*h(?:ử|u)` bắt lỗi gõ THIẾU chữ — "lái hử", "lai hu". Đọc từ
#: `turn_traces` prod 2026-08-26: "tôi muốn đặt lịch lái hử" bị đóng lượt vì lạc
#: đề. Khách đang xin đúng cái việc cả luồng dẫn tới, mà mất vì một chữ "t".
#: Cụm đó không mang nghĩa nào khác trong tiếng Việt nên nhận nó là an toàn.
#: Xin LÁI THỬ. "đặt lịch"/"đặt hẹn"/"xếp lịch" phải có mặt (Sếp 2026-08-27,
#: đọc từ log thật): khách gõ *"cho anh đặt lịch"* và lượt rơi xuống
#: `CLARIFY_TASK` — bot hỏi lại ngân sách khách đã nói và số chỗ vốn đã bỏ
#: không hỏi. Trong sản phẩm này chỉ có MỘT thứ để đặt lịch, nên cụm đó
#: không mơ hồ.
#:
#: "đặt cọc" KHÔNG nằm đây, cố ý: đó là giao dịch tiền, có đường riêng đi
#: tới tư vấn viên. Hai cụm khác chuỗi nên không đụng nhau.
_TEST_DRIVE_CUE = re.compile(
    r"\b(?:lái\s*th(?:ử|ứ|u)|lai\s*thu|l[áa]i\s*h(?:ử|u)|test\s*drive|"
    r"đặt\s*lịch|dat\s*lich|đặt\s*hẹn|dat\s*hen|xếp\s*lịch|xep\s*lich|book\s*lịch)\b",
    re.IGNORECASE,
)
_SELECTION_ACTION_BEFORE = (
    r"(?:không\s+(?:chọn|lấy|xem)|khong\s+(?:chon|lay|xem)|"
    r"loại|loai|bỏ|bo|giữ\s*lại|giu\s*lai|chốt|chot|ưu\s*tiên|uu\s*tien)"
)
_SELECTION_ACTION_AFTER = (
    r"(?:không\s+(?:chọn|lấy)|khong\s+(?:chon|lay)|"
    r"loại|loai|bỏ|bo|giữ\s*lại|giu\s*lai|chốt|chot)"
)


def reconcile_intents(
    *,
    user_message: str,
    raw_intents: Sequence[Intent],
    normalized_slots: Mapping[SlotName | str, SlotValue],
    vehicle_mentions: Sequence[str],
    known_slots: Mapping[SlotName | str, SlotValue] | None = None,
    expected_slot: SlotName | None = None,
    canonical: CanonicalText | None = None,
) -> list[Intent]:
    """Return stable intent labels from this turn and the active session context.

    Raw labels remain useful evidence, but the graph consumes this normalized list.
    This protects short slot answers from LLM omissions without making another model call.
    """

    intents = set(raw_intents)
    if is_nearby_location_request(user_message):
        return [Intent.FIND_NEARBY_LOCATION]
    slot_names = _slot_names(normalized_slots)
    known_slot_names = _slot_names(known_slots or {})
    vehicle_selection_action = _has_vehicle_selection_action(user_message, vehicle_mentions)
    vehicle_selection = vehicle_selection_action or (
        bool(vehicle_mentions) and _VEHICLE_CONSIDERATION_CUE.search(user_message) is not None
    )
    has_need_cue = _NEED_CUE.search(user_message) is not None
    supported_need = _has_supported_need_slot(user_message, slot_names)
    has_catalog_cue = _CATALOG_CUE.search(user_message) is not None
    has_reference_lookup_cue = _REFERENCE_LOOKUP_CUE.search(user_message) is not None
    has_named_model_listing_cue = bool(vehicle_mentions and is_named_model_listing_request(user_message))
    has_lookup_cue = has_catalog_cue or has_reference_lookup_cue or has_named_model_listing_cue
    information_only = bool(vehicle_mentions) and has_lookup_cue and not has_need_cue and not vehicle_selection_action
    targeted_model_consultation = (
        bool(vehicle_mentions) and has_need_cue and not supported_need and not vehicle_selection_action
    )
    implicit_named_model_lookup = bool(vehicle_mentions) and not supported_need and not vehicle_selection_action
    has_active_advisory = _has_active_advisory_context(known_slot_names)
    # Lời xin ĐỔI ĐỀ XUẤT nói theo lối so sánh ("nhỏ hơn", "rẻ hơn").
    #
    # Bug thật trên prod 2026-08-26: cùng một câu *"nếu anh muốn 1 chiếc nhỏ hơn
    # thì sao"*, mô hình trả `intents: []` ở cả hai phiên gặp nó, rồi bịa nhãn
    # phạm vi khác nhau — một lần `OUT_OF_SCOPE` (lượt chết), một lần `IN_SCOPE`
    # (đề xuất lại chính chiếc xe khách vừa chê là to). Xem
    # `domain/comparative_revision`.
    #
    # Đòi `has_active_advisory`: chưa có hồ sơ nào thì "rẻ hơn" không có gì để so
    # với, và câu đó thuộc về bước khai nhu cầu chứ không phải bước đổi kết quả.
    wants_revised_results = (
        detect_comparative_revision(
            canonical or build_canonical_text(user_message),
            vehicle_mentions=bool(vehicle_mentions),
        )
        is not None
        and has_active_advisory
    )
    commit_to_named_model = _is_commit_action(user_message) and bool(vehicle_mentions)
    answers_active_slot = has_active_advisory and expected_slot is not None and expected_slot in slot_names
    continues_active_vehicle_branch = (
        has_active_advisory
        and SlotName.VEHICLE_TYPE in slot_names
        and not information_only
        and not targeted_model_consultation
        # Xin LÁI THỬ không phải "đi tiếp nhánh tư vấn".
        #
        # Gốc của một chỗ chập chờn 1/4 lần trong lưới E2E, đo bằng bản in tại
        # chỗ trên hai lần chạy cùng một kịch bản:
        #
        #     XANH:  RAW=[]  SLOTS={}                    -> intents []
        #     ĐỎ:    RAW=[]  SLOTS={vehicle_type: CAR}   -> intents [ADVISORY]
        #
        # LLM không gắn intent nào ở CẢ HAI lần. Khác nhau ở chỗ lần đỏ,
        # `vehicle_type` — thứ đã khoá từ đầu phiên, KHÔNG phải tiêu chí khách
        # vừa nói — làm bật cờ này, `ADVISORY` được thêm vào, luồng chấm điểm
        # chạy lại, và khách nhận đè lên đúng bản đề xuất họ vừa đọc.
        #
        # Theo định nghĩa của chính enum: `ADVISORY` là khách đưa TIÊU CHÍ CÁ
        # NHÂN. Loại xe đã biết từ trước không phải tiêu chí mới, và câu xin lái
        # thử không mang tiêu chí nào.
        and not is_test_drive_request(user_message)
    )
    # Lượt này là CÂU TRẢ LỜI cho câu hỏi loại xe mà bot vừa đặt.
    #
    # Bug thật, đọc từ `turn_traces` prod 2026-08-26 — lặp ở MỌI phiên tư vấn:
    #
    #     "tôi cần tư vấn xe"  -> bot hỏi "ô tô điện hay xe máy điện ạ?"
    #     "Ô tô điện"          -> intents=["CATALOG_BROWSE"], slots_gained={}
    #
    # Khách BẤM ĐÚNG cái nút bot vừa đưa ra, mà lượt đó bị đọc thành "cho tôi xem
    # danh mục ô tô điện" và `vehicle_type` KHÔNG được ghi nhận. Luồng chỉ chạy
    # tiếp nhờ `inferred_vehicle_type` đoán lại từ ngân sách ở lượt sau — tức nó
    # sống bằng một phép đoán, chứ không bằng câu trả lời khách vừa đưa.
    #
    # `answers_active_slot` không cứu được: nó đòi `has_active_advisory`, mà ở
    # lượt thứ hai của phiên thì hồ sơ còn rỗng nên cờ đó chưa bật. Điều kiện
    # đúng hẹp hơn và không phụ thuộc hồ sơ: bot ĐANG chờ đúng slot này, và lượt
    # này trích được đúng slot đó.
    #
    # `not vehicle_mentions` là vế thứ ba, và nó bắt buộc: "tất cả các mẫu vf8
    # hiện tại" cũng trích ra `vehicle_type` khi phiên chưa biết loại xe, nên hai
    # vế đầu khớp — nhưng câu đó nêu TÊN MỘT MẪU, tức là tra cứu, không phải lời
    # đáp cho câu hỏi "ô tô hay xe máy". Một câu trả lời loại xe không bao giờ
    # kèm tên mẫu.
    answers_vehicle_type_question = not vehicle_mentions and (
        _BARE_VEHICLE_TYPE_REPLY.fullmatch(_fold_reply(user_message)) is not None
        or (expected_slot is SlotName.VEHICLE_TYPE and SlotName.VEHICLE_TYPE in slot_names)
    )
    catalog_browse_request = (
        not answers_vehicle_type_question
        and not vehicle_mentions
        and (
            _BARE_VEHICLE_TYPE_CUE.search(user_message) is not None
            or _ALL_MODELS_CUE.search(user_message) is not None
            or is_named_model_listing_request(user_message)
            or (has_active_advisory and is_catalog_browse_request(user_message))
            or (SlotName.VEHICLE_TYPE in slot_names and _MODEL_NOUN_CUE.search(user_message) is not None)
        )
        and not supported_need
        and _PERSONAL_CRITERION_CUE.search(user_message) is None
    )
    # [COMPARE_VEHICLES] Nhãn được gắn TẤT ĐỊNH ở đây, không do LLM phát: prompt
    # trích slot không nhắc tới nhãn này nên bộ trích không bao giờ trả nó về, và
    # đó là chủ ý — một lượt so sánh vẫn chỉ tốn đúng một lần gọi LLM ở bước hiểu
    # ý (A4-2).
    #
    # Điều kiện dùng CHUNG `has_comparison_cue`/`plan_comparison` với Lớp 3 và
    # với `nodes/route_intent`: ba chỗ hỏi cùng một câu, nên phải cùng một câu
    # trả lời. `plan_comparison` cũng là chỗ duy nhất biết luật trùng xe và trần
    # ba xe, nên "so sánh vf3 và vf3" không bao giờ được gắn nhãn so sánh.
    comparison_request = plan_comparison(user_message=user_message, vehicle_names=vehicle_mentions).should_call_tool

    if comparison_request:
        # Câu so sánh KHÔNG còn là một lượt tra cứu: để `CATALOG_LOOKUP` ở lại,
        # `nodes/route_intent` sẽ render hai bảng thông số nối đuôi nhau và
        # `ask_or_retrieve` coi lượt đã xong — đúng hành vi cũ mà tính năng này
        # sinh ra để thay.
        intents.discard(Intent.CATALOG_LOOKUP)
        intents.discard(Intent.CATALOG_BROWSE)
        intents.add(Intent.COMPARE_VEHICLES)
        if not supported_need:
            # Khách chỉ nêu đích danh hai mẫu xe, không đưa tiêu chí cá nhân nào
            # → không phải lượt nhờ chọn hộ từ cả danh mục.
            intents.discard(Intent.ADVISORY)
        else:
            # "nên mua vf3 hay vf5 cho nhà 5 người, ngân sách 700 triệu" mang CẢ
            # HAI: một câu hỏi so sánh và một hồ sơ nhu cầu thật. Gỡ `ADVISORY` ở
            # đây sẽ kéo theo `services/slot_extraction` xoá sạch slot của lượt
            # (nhánh "lượt tra cứu thuần"), tức vứt đúng ngân sách và số người mà
            # khách vừa khai. Lượt này vẫn ĐÁP bằng bảng so sánh —
            # `nodes/ask_or_retrieve` short-circuit trên `compare_answered` — còn
            # slot thì được giữ lại cho lượt tư vấn kế tiếp.
            intents.add(Intent.ADVISORY)
        return [intent for intent in Intent if intent in intents]

    if answers_vehicle_type_question:
        # Nhãn của LLM phải bị BỎ, không chỉ bị bỏ qua. `intents` khởi tạo từ
        # `raw_intents`, nên để nguyên thì "Ô tô điện" vẫn rời hàm này mang nhãn
        # `CATALOG_BROWSE` do LLM gắn — và graph vẫn đi liệt kê danh mục.
        intents.discard(Intent.CATALOG_BROWSE)
        intents.discard(Intent.CATALOG_LOOKUP)
    if catalog_browse_request:
        intents.discard(Intent.ADVISORY)
        intents.discard(Intent.CATALOG_LOOKUP)
        intents.add(Intent.CATALOG_BROWSE)
    if information_only and not supported_need:
        intents.discard(Intent.ADVISORY)
    if targeted_model_consultation:
        # "Tư vấn xe VF5" targets VF5.  Without a current-turn budget,
        # passenger count, purpose, or other suitability criterion it is not
        # permission to rank the whole catalog using stale advisory slots.
        intents.discard(Intent.ADVISORY)
        intents.add(Intent.CATALOG_LOOKUP)
    if implicit_named_model_lookup:
        # A concrete model is already a complete lookup target. Short natural
        # follow-ups such as "VF9 đi" or "VF 9 nhé" do not need an extra verb,
        # and must not depend on the LLM assigning an intent to a discourse
        # particle. Personal criteria and explicit choose/reject actions are
        # excluded above, so they continue through advisory reconciliation.
        intents.discard(Intent.ADVISORY)
        intents.add(Intent.CATALOG_LOOKUP)
    if vehicle_mentions:
        # CATALOG_BROWSE is only valid when the customer names a vehicle TYPE,
        # never when a concrete model has already been recovered. Keeping the
        # raw browse label here makes the graph ignore the model and list the
        # whole catalog when the LLM focuses on words such as "tất cả các mẫu".
        intents.discard(Intent.CATALOG_BROWSE)
    # "anh đang quan tâm vf8" (Sếp 2026-08-29): chỉ nêu xe đang để ý, KHÔNG nêu nhu
    # cầu, chưa có cuộc tư vấn nào đang chạy → là một lượt TRA CỨU mẫu đó (hệ ghi
    # `interest_vehicle`, câu kết mời tư vấn), không phải mở cuộc tư vấn rồi hỏi
    # ngân sách/mục đích như thể chưa nghe tên xe. Còn "phân vân VF 8 có hợp
    # không" (có cue nhu cầu) hay đang giữa cuộc tư vấn thì vẫn là tư vấn.
    bare_interest = (
        vehicle_selection
        and not vehicle_selection_action
        and not has_need_cue
        and not supported_need
        and not has_active_advisory
        and not commit_to_named_model
    )
    if vehicle_selection and not has_lookup_cue and not commit_to_named_model and not bare_interest:
        intents.discard(Intent.CATALOG_LOOKUP)

    if not catalog_browse_request and (
        (supported_need and not information_only)
        or (has_need_cue and SlotName.VEHICLE_TYPE in slot_names and not targeted_model_consultation)
        or (
            answers_active_slot
            # Trả lời câu hỏi loại xe LÀ một lượt tư vấn, kể cả khi hồ sơ còn
            # rỗng — đây thường là lượt thứ hai của cả phiên. Thiếu vế này thì
            # lượt đó rời hàm với `intents` RỖNG, và `vehicle_type` khách vừa
            # chọn không đi tới đâu cả.
            or answers_vehicle_type_question
            or continues_active_vehicle_branch
            or wants_revised_results
            or (vehicle_selection and not information_only and not commit_to_named_model and not bare_interest)
        )
    ):
        intents.add(Intent.ADVISORY)
    if bare_interest:
        intents.add(Intent.CATALOG_LOOKUP)
        intents.discard(Intent.ADVISORY)
    if vehicle_mentions and has_catalog_cue:
        intents.add(Intent.CATALOG_LOOKUP)
    if vehicle_mentions and has_reference_lookup_cue:
        intents.add(Intent.CATALOG_LOOKUP)
    if has_named_model_listing_cue:
        intents.add(Intent.CATALOG_LOOKUP)
    if commit_to_named_model:
        intents.discard(Intent.ADVISORY)
        intents.add(Intent.CATALOG_LOOKUP)

    pricing_intent = classify_pricing_intent(user_message, canonical or build_canonical_text(user_message))
    if pricing_intent is not PricingIntent.NONE:
        # Pricing branch owns clear pricing requests; catalog browse must not win
        # because generic cue "giá" also matches these messages.
        intents.discard(Intent.CATALOG_BROWSE)
        # KHÔNG bỏ luôn `CATALOG_LOOKUP` khi khách ĐÃ nêu tên xe.
        #
        # BUG THẬT do chính bản vá trước sinh ra: bỏ cả hai nhãn mà không thêm
        # nhãn nào thay nghĩa là `intents` rỗng, và `nodes/route_intent` trả `{}`
        # ngay — nên *"giá lăn bánh VF 5"* chết im, dù `_on_road_answer` nằm sẵn
        # trong nhánh tra cứu và được xét TRƯỚC renderer giá niêm yết.
        #
        # Có tên xe thì nhánh tra cứu là ĐƯỜNG DUY NHẤT tới câu giá lăn bánh.
        # Không tên xe thì để chặng sau đề xuất (`chain._advance_post_pitch`,
        # nhánh `WANTS_COST`) trả lời — ở đó mới biết khách đang hỏi giá chiếc nào.
        if vehicle_mentions:
            intents.add(Intent.CATALOG_LOOKUP)
        else:
            intents.discard(Intent.CATALOG_LOOKUP)

    return [intent for intent in Intent if intent in intents]


def is_named_model_listing_request(user_message: str) -> bool:
    """Return whether the customer explicitly asks for a current model-family listing."""

    return _NAMED_MODEL_LISTING_CUE.search(user_message) is not None


def is_test_drive_request(user_message: str) -> bool:
    """Return whether the customer asks to book a test drive."""

    return _TEST_DRIVE_CUE.search(user_message) is not None


def is_catalog_browse_request(user_message: str) -> bool:
    """Return whether the turn asks to discover products without personal criteria.

    This recognizes both explicit enumeration (``tất cả các mẫu``) and broad
    shopping language (``tư vấn xe``, ``xem xe khác``).  Suitability criteria
    are checked separately by :func:`reconcile_intents`; when they are present,
    the same words stay in the advisory/scoring flow.
    """

    return (
        _ALL_MODELS_CUE.search(user_message) is not None
        or _GENERIC_VEHICLE_DISCOVERY_CUE.search(user_message) is not None
        or _BARE_ADVISORY_CUE.search(user_message) is not None
        or _BARE_VEHICLE_TYPE_CUE.search(user_message) is not None
    )


def _has_vehicle_selection_action(user_message: str, vehicle_mentions: Sequence[str]) -> bool:
    """Detect choosing/rejecting named vehicles without matching attributes such as `loại pin`."""

    if not vehicle_mentions:
        return False
    if _REFERENTIAL_SELECTION_ACTION.search(user_message):
        return True
    for mention in vehicle_mentions:
        mention_pattern = _flexible_mention_pattern(mention)
        action_before = re.compile(
            rf"\b{_SELECTION_ACTION_BEFORE}\s+"
            rf"(?:(?:mẫu|mau|xe|con)\s+)?{mention_pattern}\b",
            re.IGNORECASE,
        )
        action_after = re.compile(
            rf"\b{mention_pattern}\b\s*(?:(?:thì|thi|này|nay)\s+)?"
            rf"{_SELECTION_ACTION_AFTER}\b",
            re.IGNORECASE,
        )
        if action_before.search(user_message) or action_after.search(user_message):
            return True
    return False


def _is_commit_action(user_message: str) -> bool:
    return _COMMIT_ACTION.search(user_message) is not None


def _flexible_mention_pattern(mention: str) -> str:
    parts = [re.escape(part) for part in re.split(r"[\s-]+", mention.strip()) if part]
    return r"[\s-]*".join(parts)


def _slot_names(slots: Mapping[SlotName | str, SlotValue]) -> set[SlotName]:
    names: set[SlotName] = set()
    for name in slots:
        if is_declined(slots[name]):
            continue
        try:
            names.add(SlotName(name))
        except ValueError:
            continue
    return names


def _has_supported_need_slot(user_message: str, slots: set[SlotName]) -> bool:
    checks = {
        SlotName.PASSENGER_COUNT: _PASSENGER_EVIDENCE,
        SlotName.BUDGET_MAX_VND: _BUDGET_EVIDENCE,
        SlotName.REQUIRED_RANGE_KM: _DAILY_RANGE_EVIDENCE,
        SlotName.HOME_CHARGING: _CHARGING_EVIDENCE,
        SlotName.MAX_LOAD_KG: _LOAD_EVIDENCE,
    }
    if SlotName.PURPOSE in slots or SlotName.HABIT_NEED_TAGS in slots:
        return True
    return any(name in slots and pattern.search(user_message) for name, pattern in checks.items())


def _has_active_advisory_context(slots: set[SlotName]) -> bool:
    return bool(
        slots
        & {
            SlotName.BUDGET_MAX_VND,
            SlotName.PASSENGER_COUNT,
            SlotName.REQUIRED_RANGE_KM,
            SlotName.HOME_CHARGING,
            SlotName.PURPOSE,
            SlotName.MAX_LOAD_KG,
            SlotName.HABIT_NEED_TAGS,
        }
    )
