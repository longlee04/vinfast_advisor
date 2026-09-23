"""Nơi DUY NHẤT lõi v2 sinh chữ trả khách (spec mục 7). Thuần, tất định.

Cấm ba thứ đã lộ 80 lần trên prod: enum thô (`7_SEATER`), số `.00`, dấu `[1]`.
"""

from __future__ import annotations

import re
from urllib.parse import quote
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.agents.core.actions import (
    FIT_PARTIAL,
    FIT_YES,
    PENDING_SHOWROOM_SLOT,
    TEMPLATE_CANCELLED,
    TEMPLATE_CHOSEN_SUMMARY,
    TEMPLATE_CLARIFY,
    TEMPLATE_NO_BETTER,
    TEMPLATE_SAME_PICK,
    TEMPLATE_STOPPED,
    TEMPLATE_CONCERN,
    TEMPLATE_SOCIAL,
    Ask,
    Reply,
)
from src.agents.core.state import CoreState, Pending, PendingKind
from src.agents.domain.claim_policy import feature_claim_label, plan_claims
from src.agents.domain.need_tags import need_tag_display


class RenderError(ValueError):
    """Chữ sắp trả khách chứa thứ bị cấm."""


FORBIDDEN: tuple[re.Pattern[str], ...] = (
    # `[A-Z]{2,}_[A-Z_]+` (brief mục 7) bỏ sót enum bắt đầu bằng chữ số như
    # "7_SEATER" — mã tính năng thật đã lộ trên prod. Nới thành `[A-Z0-9]+`
    # ở cả hai vế để bắt luôn dạng đó; chữ Việt thường không có "_" nên không
    # sợ bắt nhầm ("VF 8 Plus", "260 lít", "1 tỷ" đều không có underscore).
    re.compile(r"\b[A-Z0-9]+_[A-Z0-9_]+\b"),
    # Mã máy chữ thường (VD "showroom_slot", "toa_do_gps") lọt qua `_label` khi
    # không dịch được (coi như chữ khách nói, giữ nguyên) — `\b` đã đảm bảo
    # token không dính khoảng trắng nên không bắt nhầm cụm tiếng Việt.
    re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b"),
    re.compile(r"\d+\.00\b"),
    re.compile(r"\[\d+\]"),
    # Token nút nội bộ (VD "__lichlaithu__|2026-08-30T09:00:00+07:00|VinFast HTA")
    # từng lộ nguyên văn ra CONFIRM khi lớp act quên nhân-hoá trước khi dựng
    # Ask(CONFIRM). Chặn ở đây để lỗi kêu to thay vì khách nhận token thô.
    re.compile(r"__\w+__"),
    # Toàn lõi v2 xưng anh/chị. "Quý khách" là giọng của nhánh cũ (claim_policy,
    # reaction_policy, standout_facts) — lọt vào đây qua một claim dịch sẵn
    # ("thuộc đúng dòng xe Quý khách đang tìm", prod benchmark2 2026-08-30) là
    # hai giọng trong cùng một bài. Chặn ở cửa để mọi chỗ sinh chữ đều phải dịch
    # lại, không chỗ nào chép nguyên câu của nhánh cũ.
    re.compile(r"Quý khách"),
)


def assert_clean(text: str) -> str:
    for pattern in FORBIDDEN:
        hit = pattern.search(text)
        if hit:
            raise RenderError(f"chữ cấm {hit.group(0)!r} trong: {text[:80]!r}")
    return text


def closing_question(
    state: CoreState,
    *,
    vehicle_name: str,
    has_tco: bool,
    has_booking: bool,
    recommended_names: Sequence[str] = (),
    after_on_road: bool = False,
) -> str:
    """Câu kết CỤ THỂ, ghép từ việc CÒN THIẾU trên checklist (đợt 9).

    Prod đợt 8 kết mọi câu bằng "Anh/chị cần em nói thêm gì không ạ?" — một câu
    hỏi không có việc nào để làm tiếp, khách trả lời "không" và phiên chết ở đó.
    Checklist của một phiên là: chọn xe → xem chi phí → đặt lái thử. Câu kết hỏi
    đúng bước kế tiếp còn thiếu, nên luôn có một việc cụ thể để khách gật.

    `recommended_names`: tên các mẫu đang được đề xuất (theo thứ tự), chỉ dùng khi
    CHƯA chốt xe. Không có tên nào thì lùi về câu xin ngân sách + nhu cầu.
    """

    name = vehicle_name or "mẫu xe này"
    if has_booking:
        return assert_clean(f"Lịch đã xếp; anh/chị cần hỏi thêm gì về {name} trước ngày lái thử không?")
    if not state.chosen_vehicle_id:
        names = [item for item in recommended_names if item] or ([vehicle_name] if vehicle_name else [])
        if len(names) >= 2:
            return assert_clean(f"Anh/chị ưng {names[0]} không, hay để em so với {names[1]} cho dễ quyết?")
        if names:
            return assert_clean(f"Anh/chị ưng {names[0]} không, hay để em so với mẫu khác?")
        return assert_clean("Anh/chị cho em biết ngân sách và nhu cầu để em gợi ý mẫu phù hợp nhất với mình nhé?")
    if after_on_road:
        # Vừa báo giá lăn bánh xong thì không mời "giá lăn bánh" nữa (probe đợt 9).
        if not has_tco:
            return assert_clean(
                f"Đặt lái thử {name} luôn để cảm nhận thật nhé, hay anh/chị muốn xem chi phí 5 năm trước?"
            )
        return assert_clean(f"Đặt lái thử {name} luôn để cảm nhận thật nhé?")
    if not has_tco:
        return assert_clean(
            f"Để rõ tổng tiền trước khi quyết: anh/chị muốn xem chi phí 5 năm, giá lăn bánh, hay đặt lái thử {name}?"
        )
    return assert_clean(f"Đặt lái thử {name} luôn để cảm nhận thật nhé, hay anh/chị muốn xem giá lăn bánh trước?")


def format_number(value: float, unit: str) -> str:
    if unit == "đ":
        if value >= 1_000_000_000 and value % 100_000_000 == 0:
            ty = value / 1_000_000_000
            return f"{ty:g}".replace(".", ",") + " tỷ"
        trieu = round(value / 1_000_000)
        return f"{trieu} triệu"
    if float(value).is_integer():
        return f"{int(value)} {unit}"
    return f"{value:.1f}".replace(".", ",") + f" {unit}"


SLOT_QUESTIONS: dict[str, str] = {
    # MỘT câu duy nhất cho cả luồng tư vấn (Sếp chốt 2026-08-29): hỏi từng slot
    # một là bốn lượt trước khi khách thấy chiếc xe nào — 34 phiên prod đã đo,
    # phần lớn khách rời đi trước lượt thứ ba. Thiếu gì thì SUY, không hỏi thêm.
    "profile": "Để em gợi ý mẫu phù hợp nhất với anh/chị: mình dự tính khoảng bao nhiêu, mua xe để dùng vào việc gì, và thường đi lại/chở người ra sao ạ?",
    "vehicle_type": "Để em bày đúng dòng: anh/chị đang tìm ô tô điện hay xe máy điện ạ?",
    "budget_max_vnd": "Anh/chị dự tính khoảng bao nhiêu cho chiếc xe này ạ?",
    "purpose": "Anh/chị mua xe để dùng vào việc gì là chính ạ?",
    "passenger_count": "Xe thường chở mấy người ạ?",
    "required_range_km": "Mỗi ngày anh/chị đi khoảng bao nhiêu km ạ?",
    "habit_need_tags": "Anh/chị có ưu tiên tính năng nào không ạ?",
    "registration_province": "Anh/chị ở tỉnh/thành nào để em tìm showroom gần nhất ạ?",
}

_CLARIFY: dict[str, str] = {
    "GREETING": "Anh/chị đang tìm ô tô điện hay xe máy điện ạ?",
    "COLLECTING": "Em chưa rõ ý anh/chị, anh/chị nói lại giúp em nhé?",
    "RECOMMENDED": "Anh/chị muốn xem kỹ mẫu nào trong các mẫu em vừa gợi ý ạ?",
    "CHOSEN": "Anh/chị muốn tính chi phí, đặt lái thử hay hỏi thêm về xe ạ?",
    "COSTING": "Anh/chị muốn em tính lại với số km khác, hay chuyển sang đặt lái thử ạ?",
    "SCHEDULING": "Anh/chị chọn giúp em showroom và khung giờ ở trên nhé?",
    "OFFER_REVIEW": "Tư vấn viên đang xem ưu đãi cho anh/chị, anh/chị cần em hỗ trợ gì thêm ạ?",
}


#: Mã máy (VD "7_SEATER", "ADAS") — khác chữ khách tự nói ("đi làm", "giao hàng").
_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_]*$")
#: Id thô lọt ra CHOICE: uuid đủ dấu gạch, hoặc chuỗi hex dài không dấu.
_RAW_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-|^[0-9a-fA-F-]{32,}$", re.IGNORECASE)


def _label(option: str) -> str | None:
    """Dịch một mã (need tag hoặc mã tính năng) sang chữ khách đọc được.

    `need_tag_display` chỉ phủ `NeedTag` (VD "LONG_RANGE"), còn `habit_need_tags`
    thực tế mang cả mã tính năng thô (VD "7_SEATER") — với mã lạ nó trả về
    nguyên input, không phải lỗi. Nên thử `need_tag_display` trước; nếu nó
    không đổi gì (không nhận ra), tra tiếp hàm public
    `claim_policy.feature_claim_label` (mã tính năng → cụm tiếng Việt, VD
    "7_SEATER" → "bảy chỗ") thay vì bịa bảng nhãn mới hoặc đọc thẳng bảng
    private của module khác.

    Mã KHÔNG bảng nào dịch được → `None` (bỏ hẳn khỏi câu hỏi). Đọc nguyên mã
    cho khách là đúng lỗi đã lộ 80 lần trên prod; chữ khách tự nói ("đi làm")
    không phải mã nên vẫn giữ nguyên.
    """

    display = need_tag_display(option)
    if display != option:
        return display
    label = feature_claim_label(option)
    if label is not None:
        return label
    return None if _CODE.match(option) else option


def render_ask(action: Ask) -> str:
    if action.kind is PendingKind.CONFIRM:
        # `labels[0]` (nhãn khách đọc được, policy chuyển tiếp từ Pending.labels
        # đang treo) được ưu tiên trước — `options[0]` là giá trị máy (VD
        # "__lichlaithu__|...|..."), không phải chữ khách đọc được. Thiếu
        # labels thì rơi về options[0]; `assert_clean` bên dưới vẫn chặn token
        # dạng "__x__" và kêu lỗi to (RenderError) thay vì lộ ra cho khách.
        if not action.labels and any(_RAW_ID.match(option) for option in action.options):
            # Cùng lưới an toàn với nhánh CHOICE: tầng act quên điền `labels` thì
            # câu xác nhận đọc nguyên uuid ("xác nhận giúp em: 3f2504e0-…") —
            # kêu lỗi to còn hơn để khách nhận id thô.
            raise RenderError(f"CONFIRM thiếu nhãn, options là id thô: {action.options[:3]!r}")
        detail = action.labels[0] if action.labels else (action.options[0] if action.options else "việc này")
        return assert_clean(f"Anh/chị xác nhận giúp em: {detail}, đúng không ạ?")
    if action.kind is PendingKind.CHOICE:
        if action.key == PENDING_SHOWROOM_SLOT:
            # Câu treo ở đây là showroom + khung giờ, không phải "chọn mẫu nào".
            return assert_clean("Anh/chị chọn giúp em showroom và khung giờ ở trên nhé?")
        names = action.labels or action.options
        if not action.labels and any(_RAW_ID.match(o) for o in action.options):
            # Tầng act quên điền `labels`: id thô không bao giờ được ra tới khách.
            raise RenderError(f"CHOICE thiếu nhãn, options là id thô: {action.options[:3]!r}")
        if action.job:
            # Câu chọn mẫu mang tên VIỆC — không mượn câu của luồng thông số
            # (log prod 2026-08-31: khách tưởng bot hỏi nơi và gõ "Hà Nội").
            # Sếp cùng ngày: phải mở CẢ HAI lối — chọn mẫu, hoặc kể nhu cầu để
            # em tư vấn rồi quay lại việc.
            if not names:
                return assert_clean(
                    f"Dạ, anh/chị đã chọn được mẫu muốn {action.job} chưa ạ? "
                    "Có rồi thì anh/chị cho em tên mẫu; chưa thì anh/chị cho em ngân sách và nhu cầu sử dụng, "
                    "em tư vấn chọn mẫu phù hợp rồi mình làm tiếp luôn nhé."
                )
            body = "\n".join(f"{i + 1}. {name}" for i, name in enumerate(names[:3]))
            return assert_clean(
                f"Anh/chị muốn {action.job} mẫu nào ạ?\n{body}\n"
                "Chưa ưng mẫu nào thì anh/chị cho em nhu cầu để em tư vấn thêm nhé."
            )
        if not names:
            return assert_clean("Anh/chị muốn xem mẫu nào để em kể đúng phần cần ạ? Cho em tên mẫu nhé.")
        body = "\n".join(f"{i + 1}. {name}" for i, name in enumerate(names[:3]))
        return assert_clean(f"Anh/chị muốn xem kỹ mẫu nào để em kể đúng phần cần ạ?\n{body}")
    question = SLOT_QUESTIONS.get(action.key, "Anh/chị cho em xin thêm thông tin nhé")
    if action.options:
        labels = [x for x in (_label(o) for o in action.options) if x]
        if labels:
            question = question.rstrip("?")
            return assert_clean(f"{question} — ví dụ {', '.join(labels)}?")
    if not question.endswith("?"):
        # Idempotent: nếu chữ đã kết ở "ạ" (thiếu dấu ?), chỉ thêm "?" —
        # tránh lặp "ạ ạ?" như bug thật đã gặp với `SLOT_QUESTIONS["purpose"]`.
        question = question + "?" if question.endswith("ạ") else question + " ạ?"
    return assert_clean(question)


#: Câu trấn an theo chủ đề lo ngại (log prod 2026-08-31). Ràng buộc cứng:
#: KHÔNG chữ số (mọi con số cụ thể ở đây đều là số bịa — chính sách bảo hành,
#: số trạm sạc đổi theo dòng xe và thời điểm), không hứa hẹn tuyệt đối.
_CONCERN_REPLIES: Final[Mapping[str, str]] = {
    "battery": (
        "Dạ, lo về pin là điều em gặp nhiều nhất ạ. Pin xe điện VinFast có chính sách bảo hành riêng dài hạn "
        "và được hãng kiểm tra định kỳ — pin xuống cấp trong thời gian bảo hành là việc của hãng, không phải "
        "của anh/chị. Khi bán lại, xe được đánh giá theo tình trạng pin thực tế nên xe giữ gìn tốt vẫn có giá ạ."
    ),
    "range": (
        "Dạ, đi xa mà lo hết pin là lo rất đúng ạ. Xe luôn hiển thị quãng đường còn lại và trạm sạc gần nhất "
        "ngay trên màn hình, dọc các tuyến lớn có hệ thống trạm sạc VinFast, và hãng có cứu hộ hỗ trợ khi cần. "
        "Trước chuyến dài mình sạc đầy là chủ động được hành trình ạ."
    ),
    "charging": (
        "Dạ, chỗ sạc là điều nên tính trước và thường có lối ra ạ. Chưa sạc được tại nhà thì anh/chị dùng "
        "trạm sạc công cộng của VinFast — ở bãi đỗ, trung tâm thương mại, cây xăng — tranh thủ sạc trong lúc "
        "đỗ xe sinh hoạt bình thường. Anh/chị cho em khu vực mình ở, em tìm trạm sạc gần nhất cho mình nhé."
    ),
    "service": (
        "Dạ anh/chị yên tâm khoản này ạ: VinFast có cứu hộ hỗ trợ dọc đường và hệ thống xưởng dịch vụ chính "
        "hãng ở các tỉnh thành — gặp sự cố mình gọi tổng đài là có người lo, không phải tự xử lý ạ."
    ),
    "usability": (
        "Dạ, xe điện nhìn nhiều màn hình vậy thôi chứ thao tác hằng ngày chỉ là lên xe, đi và cắm sạc như sạc "
        "điện thoại ạ. Khi nhận xe, nhân viên showroom hướng dẫn tận tay từng chức năng — anh/chị lái thử một "
        "lần là quen ngay ạ."
    ),
    "general": (
        "Dạ, mua xe điện lần đầu ai cũng có chỗ lấn cấn, anh/chị cứ hỏi thẳng ạ. Điều anh/chị đang băn khoăn "
        "nhất là pin, chỗ sạc, chi phí hay cách sử dụng — em giải thích từng điểm, rồi mình lái thử thực tế "
        "là rõ nhất ạ."
    ),
}


def render_reply(action: Reply, *, vehicle_name: str | None = None, closing: str | None = None) -> str:
    """`closing`: câu kết theo checklist (`closing_question`) — act truyền vào để
    mẫu SAME_PICK không kết bằng menu mở như cũ."""

    if action.template == TEMPLATE_SOCIAL:
        if action.resume_pending or action.args.get("stage") not in {"", "GREETING"}:
            # Đang giữa việc: khách "cảm ơn em" thì đáp ngắn rồi quay lại câu
            # đang hỏi — đọc lại cả lời chào là bắt họ đọc thứ vừa đọc.
            return assert_clean("Dạ em nghe anh/chị ạ.")
        return assert_clean(GREETING_TEXT)
    if action.template == TEMPLATE_CONCERN:
        # Câu trấn an theo chủ đề lo ngại — KHÔNG một con số nào (số ở đây là số
        # bịa: chính sách đổi theo dòng xe và thời điểm; chi tiết để tư vấn viên
        # hoặc tài liệu chính thức nói). Đang treo câu hỏi (`resume_pending`)
        # thì không kết bằng câu hỏi mở — act sẽ nối lại câu đang treo.
        body = _CONCERN_REPLIES.get(action.args.get("topic", ""), _CONCERN_REPLIES["general"])
        if action.resume_pending:
            return assert_clean(body)
        return assert_clean(f"{body} Anh/chị còn điểm nào lấn cấn nữa không, hay để em tư vấn tiếp ạ?")
    if action.template == TEMPLATE_CANCELLED:
        return assert_clean("Dạ, em đã huỷ việc đó. Anh/chị cần em hỗ trợ gì tiếp ạ?")
    if action.template == TEMPLATE_STOPPED:
        # Khách nói THÔI: dừng đẩy hàng, không hỏi thêm một câu nào, để ngỏ lối
        # quay lại. Đo trên máy 2026-09-23: "t ko muốn tư vấn nữa" nhận lại đúng
        # hai thẻ xe cũ kèm câu mời chọn mẫu — đọc như bot không nghe thấy gì.
        return assert_clean(
            "Dạ vâng, em dừng ở đây ạ. Khi nào anh/chị cần xem lại hay cần em hỗ trợ gì, "
            "anh/chị nhắn em một câu là được ạ."
        )
    if action.template == TEMPLATE_CLARIFY:
        return assert_clean(_CLARIFY.get(action.args.get("stage", ""), _CLARIFY["COLLECTING"]))
    if action.template == TEMPLATE_SAME_PICK:
        # Đề xuất lại mà không có mẫu nào MỚI: nói NGẮN, không đọc lại nguyên
        # bài (khách vừa đọc xong), và không nói dối "chưa tìm được mẫu nào".
        name = action.args.get("vehicle_name") or vehicle_name or "mẫu xe này"
        tail = closing or "Anh/chị muốn em tính chi phí, so sánh với mẫu khác, hay đặt lái thử ạ?"
        return assert_clean(f"Với tiêu chí anh/chị vừa nêu, em vẫn thấy {name} hợp nhất. {tail}")
    if action.template == TEMPLATE_NO_BETTER:
        # KHÔNG nhắc lại nguyên văn lời khách: chữ khách gõ có thể chứa mã máy,
        # mà mọi thứ ra khỏi đây đều phải qua `assert_clean`.
        name = action.args.get("vehicle_name") or vehicle_name or "mẫu em vừa gợi ý"
        return assert_clean(
            f"Với yêu cầu anh/chị vừa nêu, em chưa có mẫu nào khác hợp hơn ạ — gần nhất vẫn là {name}. "
            "Anh/chị nới thêm một chút để em tìm rộng hơn nhé?"
        )
    if action.template == TEMPLATE_CHOSEN_SUMMARY:
        # FALLBACK khi act không lấy được thông số xe (catalog lỗi): câu ngắn,
        # KHÔNG bịa "hợp nhu cầu anh/chị" (khách chưa kể nhu cầu ở nhánh này —
        # Sếp 2026-08-31). Câu giới thiệu xe đầy đủ do `chosen_intro` dựng ở act.
        name = vehicle_name or "mẫu xe này"
        return assert_clean(
            f"Dạ, {name} là một mẫu rất đáng cân nhắc trong dải xe điện VinFast — em rất vui được đồng hành cùng anh/chị! "
            "Anh/chị cho em biết thêm mình hay dùng xe vào việc gì, đi lại tầm bao nhiêu để em tư vấn sát hơn nhé "
            "— hoặc em tính luôn chi phí sử dụng, giá lăn bánh cho anh/chị ạ."
        )
    # Không có lối thoát êm: template lạ nghĩa là policy và render đã lệch nhau,
    # trả bừa câu xã giao chỉ giấu lỗi cho tới khi khách nhận câu vô nghĩa.
    raise RenderError(f"template lạ: {action.template!r}")


#: Lời chào mở đầu — cùng nội dung với `prompts/reply_variants.SOCIAL_VARIANTS`
#: (Sếp 2026-08-26: "dài hơn 1 chút thì tốt"), rút về MỘT bản tất định vì lõi v2
#: không xoay biến thể. Bản cũ của lõi v2 ("Dạ em nghe anh/chị ạ.") trả lời câu
#: "chào em" đầu tiên bằng một dòng trạng thái: khách không biết bot làm được
#: gì, phải tự nghĩ ra câu hỏi — và đó là lúc hội thoại chết. Đúng MỘT dấu "?".
GREETING_TEXT: str = (
    "Dạ em chào anh/chị ạ. Em là trợ lý tư vấn xe điện VinFast, có thể giúp anh/chị "
    "chọn xe theo nhu cầu, tra giá và thông số từng mẫu, hoặc ước tính chi phí sử dụng. "
    "Anh/chị đang quan tâm tới điều gì để em hỗ trợ ngay ạ?"
)

#: Chữ nối câu hỏi đang treo vào sau câu trả lời của lượt chen ngang.
RESUME_PREFIX = "Quay lại câu lúc nãy: "


def render_resume(main: str, pending: Pending | None) -> str:
    """Nối câu hỏi treo SAU `main`. Chỉ phần render sinh ra mới bị soi.

    `main` thường là `answer` của service cũ (`catalog_browse`, `compare_vehicles`,
    `vehicle_overview`…) — nhóm được MIỄN `assert_clean` theo global constraints
    vì nó có guardrail riêng và hợp lệ khi chứa `[1]`, `260.00`, `lfp_battery`.
    Soi cả `main` ở đây từng làm `RenderError` bắn lên `act` và khách mất CẢ câu
    trả lời LẪN câu hỏi đang treo — đúng chỉ số 2 của spec mục 8.
    """

    if pending is None:
        return main
    # `job` đi theo: câu treo của việc lái thử nối lại phải vẫn là câu lái thử
    # (prod 2026-08-31 — "Quay lại câu lúc nãy" từng đọc lại câu luồng thông số).
    question = render_ask(
        Ask(key=pending.key, kind=pending.kind, options=pending.options, labels=pending.labels, job=pending.job)
    )
    return f"{main}\n\n{assert_clean(RESUME_PREFIX + question)}"


@dataclass(frozen=True, slots=True)
class FallbackVehicle:
    """Một mẫu xe cho đường dự phòng khi synthesis/verify hỏng.

    `facts` là cặp (nhãn tiếng Việt, giá trị đã có đơn vị) lấy từ SNAPSHOT của
    chính run này (`recommendation.compare`), không phải chữ do LLM viết.
    """

    name: str
    facts: tuple[tuple[str, str], ...] = ()
    reasons: tuple[str, ...] = ()


#: Số trong `value_text` của snapshot hay ra dạng "260.00" — đúng thứ đã lộ 80
#: lần trên prod. Cắt phần thập phân bằng 0 TRƯỚC khi `assert_clean` chạy, thay
#: vì để `assert_clean` ném lỗi và giết luôn đường dự phòng.
_TRAILING_ZEROS = re.compile(r"(\d+)\.0+\b")


def tidy_number(text: str) -> str:
    return _TRAILING_ZEROS.sub(r"\1", text)


#: Bốn dạng dấu vết claim CHƯA dịch được (brief mục 7, bug prod 2026-08-29):
#: `[slot=...]` — chuỗi thô `ScoringReason.render()`; `{CLAIM...}` — placeholder
#: chưa được `plan_claims`/`feature_claim_label` thay bằng chữ; mã máy hoa
#: (`VEHICLE_TYPE`, `BLIND_SPOT`); và `[n]` chỉ số trích dẫn của synthesis.
#: Không dùng chung `FORBIDDEN`: nó còn bắt `\d+\.00`/`__x__`, không liên quan
#: claim, và bắt luôn mã máy CHỮ THƯỜNG ("vehicle_type") — thứ mà `_claim_text`
#: cố tình dịch chứ không phải thứ cần lọc bỏ ở đây.
_UNTRANSLATED_CLAIM_FRAGMENT: re.Pattern[str] = re.compile(r"\[slot=|\{CLAIM|\b[A-Z]{2,}_[A-Z_]+\b|\[\d+\]")
#: Một reason/claim đôi khi ĐÃ RỜI khỏi `ScoringReason.render()` và chỉ còn lại
#: nguyên placeholder trần ("{CLAIM_BLIND_SPOT}") — không có vế `[slot=...]`
#: cho `plan_claims` bắt. Bắt riêng dạng này để còn thử `feature_claim_label`
#: trên hậu tố, thay vì bỏ thẳng.
_INLINE_CLAIM_PLACEHOLDER: re.Pattern[str] = re.compile(r"\{CLAIM_([A-Z][A-Z0-9_]*)\}")
#: Claim KHÔNG mang thông tin: "đúng loại xe" đúng với MỌI mẫu trong danh sách
#: (bộ lọc đã khoá loại xe từ đầu), nên in nó ra là in một câu độn — và bản
#: dịch của nó ở `claim_policy` còn xưng "Quý khách". Bỏ hẳn, để chỗ gọi rơi về
#: số thật của xe (`need_lead(facts=…)`).
_FILLER_CLAIM: re.Pattern[str] = re.compile(r"^\[slot=vehicle_type\]")


def _sanitize_reason(reason: str) -> str | None:
    """Một lý do chấm điểm thô → chữ tiếng Việt sạch, hoặc `None` nếu bó tay.

    Bug thật trên prod (2026-08-29, xem traceback `act.py:684 _pitch_text` →
    `render.py:284 recommend_fallback`): đường dự phòng khi `synthesis` hỏng
    từng nối THẲNG `Recommendation.reasons` (chuỗi `ScoringReason.render()`,
    VD `"[slot=vehicle_type] Đúng loại phương tiện đã chọn"`) vào câu trả
    khách. `assert_clean` đúng khi chặn token `vehicle_type` — cái sai là câu
    đó được DỰNG bằng chuỗi nội bộ thay vì chữ khách đọc được, nên cả lượt rơi
    về câu an toàn.

    Sửa bằng cách dịch TRƯỚC khi dựng câu, dùng lại ĐÚNG bộ từ vựng claim đã
    duyệt mà `synthesis` dùng (`claim_policy.plan_claims`) — không bịa bảng
    dịch riêng cho đường dự phòng. `reason` truyền vào đây chính là một phần
    tử của input `plan_claims` vẫn nhận (một danh sách reason), chỉ khác là
    gọi với đúng MỘT phần tử.
    """

    reason = reason.strip()
    if not reason or _FILLER_CLAIM.match(reason):
        return None
    planned = plan_claims((reason,))
    if planned:
        text = planned[0].text
    else:
        inline = _INLINE_CLAIM_PLACEHOLDER.fullmatch(reason)
        text = feature_claim_label(inline.group(1)) if inline else reason
    if not text or _UNTRANSLATED_CLAIM_FRAGMENT.search(text):
        # Không dịch được (slot lạ, mã tính năng lạ) hoặc bản dịch vẫn còn sót
        # dấu vết claim: BỎ hẳn thay vì đọc nguyên cho khách — đúng nguyên tắc
        # `_label` đã chốt ở bước 1 cho mã tính năng trong câu hỏi.
        return None
    # Bảng claim của nhánh cũ xưng "Quý khách" ("có giá nằm trong ngân sách Quý
    # khách dự tính"); nội dung thì đúng, chỉ sai giọng. Dịch lại giọng ở đây —
    # bỏ cả lý do là mất một câu có nội dung, còn để nguyên là nổ `assert_clean`.
    return text.replace("Quý khách", "anh/chị")


def reason_text(reason: str) -> str | None:
    """Lý do chấm điểm thô → chữ đọc được, hoặc `None` khi không có gì đáng nói.

    Cửa công khai cho tầng act: nó cần biết TRƯỚC khi dựng câu dẫn là lý do này
    có dùng được không, để chỉ tốn một lần đọc số xe khi thật sự phải nói bằng số.
    """

    return _sanitize_reason(reason)


def _sanitize_reasons(reasons: Sequence[str]) -> tuple[str, ...]:
    cleaned = (_sanitize_reason(reason) for reason in reasons)
    return tuple(text for text in cleaned if text is not None)


def recommend_fallback(vehicles: Sequence[FallbackVehicle], *, needs: Sequence[str] = ()) -> str:
    """Đường dự phòng: tên xe + số thật + vì sao khớp slot. KHÔNG boilerplate.

    Spec mục 7: synthesis hoặc verify hỏng thì khách vẫn phải nhận một câu có
    nội dung — 282 lần synthesis hỏng/tuần trên prod đang thành câu rỗng.
    """

    if not vehicles:
        return assert_clean(
            "Em chưa tìm được mẫu nào khớp tiêu chí anh/chị vừa nêu. Anh/chị nới ngân sách một chút giúp em nhé?"
        )
    opening = "Em gợi ý anh/chị mấy mẫu sau ạ:"
    if needs:
        # Đường dự phòng vẫn phải nói được VÌ NHU CẦU NÀO — khách đọc một danh
        # sách thông số không biết nó liên quan gì tới việc mình vừa kể. Chữ ở
        # đây là chữ khách tự nói (purpose) và nhãn tiếng Việt của tính năng họ
        # nêu (`feature_label`), không phải mã máy.
        opening = f"Theo nhu cầu anh/chị nêu ({', '.join(needs[:3])}), em gợi ý mấy mẫu sau ạ:"
    lines: list[str] = [opening]
    for index, vehicle in enumerate(vehicles, start=1):
        parts = [f"{index}. {vehicle.name}"]
        if vehicle.facts:
            parts.append(", ".join(f"{label} {value}" for label, value in vehicle.facts[:3]))
        reasons = _sanitize_reasons(vehicle.reasons)
        if reasons:
            # Nối THẲNG lý do vào nhu cầu khách vừa kể: "hợp vì đủ 5 chỗ" là một
            # thông số, còn "hợp với đưa đón con nhờ đủ 5 chỗ" là một câu trả lời
            # cho người đang hỏi. Cùng dữ liệu, khác chỗ khách nhận ra mình.
            why = "; ".join(reasons[:2])
            parts.append(f"hợp với {needs[0]} nhờ {why}" if needs else f"hợp vì {why}")
        lines.append(" — ".join(parts))
    return assert_clean(tidy_number("\n".join(lines)))


#: Loại xe → chữ khách đọc được. Cùng hai giá trị `policy._KNOWN_VEHICLE_TYPES`;
#: mã lạ thì KHÔNG có câu dẫn (chứ không đọc mã thô cho khách).
_VEHICLE_TYPE_WORDS: dict[str, str] = {"CAR": "ô tô điện", "ELECTRIC_MOTORBIKE": "xe máy điện"}


def type_switch_lead(vehicle_type: str) -> str:
    """Câu dẫn cho lượt khách ĐỔI loại xe giữa chừng. Rỗng nếu loại lạ.

    Lượt prod LP03: ở chặng đề xuất (ô tô), khách gõ "thôi xe máy đi" và nhận
    lại đúng chiếc ô tô cũ. Sau khi policy làm lại đề xuất cho đúng loại, bài
    mới vẫn phải NÓI RA việc chuyển — không nói thì khách không có cách nào biết
    lõi đã nghe câu vừa rồi.
    """

    word = _VEHICLE_TYPE_WORDS.get((vehicle_type or "").upper())
    if not word:
        return ""
    return assert_clean(f"Dạ, em chuyển sang {word} theo yêu cầu của anh/chị ạ.")


#: Mã bậc nới tiêu chí — `act` chọn bậc, `render` viết câu. Hai chỗ dùng chung
#: một bảng mã để không ai phải đoán chữ của bên kia.
RELAX_BUDGET = "budget"
RELAX_SEATS = "seats"
RELAX_RANGE = "range"
RELAX_OTHER = "other"


#: Số mẫu tối đa cho MỘT bậc giá. Khách xin "đắt hơn" muốn bước lên một nấc,
#: không muốn đọc cả danh mục: đổ 8 thẻ một lượt là khách hết chỗ để hỏi tiếp
#: (Sếp 2026-09-23 — "để họ có nhiều khoảng để hỏi đắt hơn rẻ hơn").
PRICE_STEP_LIMIT: int = 3


def price_step_lead(*, pricier: bool) -> str:
    """Câu dẫn cho lượt bước MỘT nấc giá, đứng trước danh sách.

    KHÔNG kết bằng dấu hai chấm: ngay sau nó là câu mở danh sách của bài
    (`recommend_fallback`: "Em gợi ý anh/chị mấy mẫu sau ạ:"), hai câu cùng vai
    trò mở danh sách đứng cạnh nhau đọc như bot lắp.
    """

    if pricier:
        return assert_clean("Dạ, em bước lên tầm giá cao hơn một bậc cho anh/chị ạ.")
    return assert_clean("Dạ, em lùi xuống tầm giá thấp hơn một bậc cho anh/chị ạ.")


def price_step_tail(*, pricier: bool, more: bool) -> str:
    """Câu mời đi tiếp, đứng CUỐI bài — chỗ khách đọc xong danh sách.

    `more=False` nghĩa là hết mẫu ở hướng đó: nói thật, đừng mời khách hỏi thêm
    một thứ không còn.
    """

    if not more:
        return assert_clean(
            "Đây đã là tầm cao nhất em có ạ." if pricier else "Đây đã là tầm thấp nhất em có ạ."
        )
    if pricier:
        return assert_clean("Anh/chị muốn xem tầm cao hơn nữa thì nói em nhé, hoặc quay lại tầm cũ cũng được ạ.")
    return assert_clean("Anh/chị cần rẻ hơn nữa thì nói em nhé, hoặc quay lại tầm cũ cũng được ạ.")


def relax_lead(
    relaxed: Sequence[str],
    *,
    budget_vnd: object = None,
    widened_vnd: object = None,
    passenger_count: object = None,
    required_range_km: object = None,
) -> str:
    """MỘT câu mở đầu nói ra lõi đã tự nới tiêu chí nào. Rỗng khi không nới gì.

    Luật của Sếp (2026-08-29): không khớp thì LUÔN đề xuất, đừng bảo khách tự
    nới ngân sách (lượt prod LP18/LP03 kết thúc ngay ở câu "anh/chị nới ngân
    sách giúp em"). Nhưng nới trong im lặng còn tệ hơn: khách 300 triệu nhận về
    mẫu 420 triệu mà không hiểu vì sao. Nên câu này bắt buộc đi kèm mọi lượt có
    nới, và nó nói bằng chính con số khách đã nêu.
    """

    steps = [code for code in dict.fromkeys(relaxed) if code in {RELAX_BUDGET, RELAX_SEATS, RELAX_RANGE, RELAX_OTHER}]
    if not steps:
        return ""
    budget = _amount(budget_vnd)
    widened = _amount(widened_vnd)
    seats = passenger_count if isinstance(passenger_count, int) and passenger_count > 0 else None
    range_km = _amount(required_range_km)
    parts: list[str] = []
    for code in steps:
        if code == RELAX_BUDGET and widened is not None:
            parts.append(f"nới ngân sách lên khoảng {format_number(widened, 'đ')}")
        elif code == RELAX_SEATS:
            parts.append(f"bỏ điều kiện đủ {seats} chỗ" if seats is not None else "bỏ điều kiện số chỗ")
        elif code == RELAX_RANGE:
            # Nói THẲNG cái bị gác lại (Sếp 2026-08-31): "bỏ bớt các tiêu chí
            # phụ" giấu khách sự thật là xe sắp bày ra KHÔNG đủ tầm cho chuyến
            # đi dài họ vừa kể — đúng khe hở làm pitch VF 2 "hợp đi xa" lọt prod.
            parts.append(
                f"tạm gác tiêu chí tầm chạy (đi đường dài thoải mái cần khoảng {format_number(range_km, 'km')} "
                "mỗi lần sạc trở lên)"
                if range_km is not None
                else "tạm gác tiêu chí tầm chạy cho chuyến đi dài"
            )
        elif code == RELAX_OTHER:
            parts.append("bỏ bớt các tiêu chí phụ")
    if not parts:
        return ""
    head = (
        f"Dạ trong đúng tầm {format_number(budget, 'đ')} hiện chưa có mẫu nào khớp đủ tiêu chí"
        if budget is not None
        else "Dạ chưa có mẫu nào khớp đủ tiêu chí anh/chị nêu"
    )
    done = ", ".join(parts)
    tail = (
        " Anh/chị nới thêm ngân sách thì em chọn được mẫu đủ tầm đi xa ạ."
        if RELAX_RANGE in steps and budget is not None
        else ""
    )
    return assert_clean(f"{head}, nên em {done} để anh/chị tham khảo các mẫu gần nhất ạ.{tail}")


def _amount(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        return None
    number = float(value)
    return number if number > 0 else None


def budget_below_any_floor(
    *, budget_vnd: object, motorbike_floor_vnd: object = None, car_floor_vnd: object = None
) -> str:
    """Ngân sách dưới hẳn giá sàn MỌI loại xe: nói thật sàn + hỏi lại một câu gộp.

    Bug prod 2026-08-31 11:52: "anh có 5 củ mua xe để đi" (phiên khoá Ô TÔ) nhận
    gợi ý VF 2 "gần giá nhất" 188 triệu — gấp 37 lần túi tiền, đọc như trêu
    khách. Ở vùng này "gần nhất" không cứu được ai; câu đúng là giá sàn thật
    của từng loại (đọc từ catalog, không bịa) + hỏi lại loại xe và ngân sách
    trong MỘT câu — vẫn giữ luật không từ chối cụt.
    """

    budget = _amount(budget_vnd)
    floors: list[str] = []
    bike = _amount(motorbike_floor_vnd)
    if bike is not None:
        floors.append(f"xe máy điện từ khoảng {format_number(bike, 'đ')}")
    car = _amount(car_floor_vnd)
    if car is not None:
        floors.append(f"ô tô điện từ {format_number(car, 'đ')}")
    head = (
        f"Dạ với {format_number(budget, 'đ')} thì hiện chưa có mẫu VinFast nào trong tầm ạ"
        if budget is not None
        else "Dạ mức này hiện chưa có mẫu VinFast nào trong tầm ạ"
    )
    detail = f" — {', '.join(floors)}" if floors else ""
    return assert_clean(
        tidy_number(
            f"{head}{detail}. Anh/chị định mua xe máy điện hay ô tô, "
            "và dự tính tầm bao nhiêu để em chọn đúng ạ?"
        )
    )


def nearest_by_price(vehicles: Sequence[tuple[str, str]]) -> str:
    """Bậc CUỐI: nới hết bậc vẫn không mẫu nào khớp → mẫu gần giá nhất.

    Vẫn phải có xe trong câu trả lời: một danh sách rỗng kèm lời mời khách tự
    nới ngân sách là đúng chỗ hội thoại chết trên prod. Tên và giá đọc từ catalog
    tất định, không phải từ LLM.
    """

    lines = ["Dạ chưa có mẫu nào khớp hết tiêu chí anh/chị nêu, em gợi ý hai mẫu gần nhất về giá ạ:"]
    lines += [f"{index}. {name} — giá từ {price}" for index, (name, price) in enumerate(vehicles, start=1)]
    lines.append("Anh/chị muốn em xem kỹ mẫu nào ạ?")
    return assert_clean(tidy_number("\n".join(lines)))


def spec_facts(*, price_vnd: object = None, seats: object = None, range_km: object = None) -> tuple[str, ...]:
    """Ba con số khách hỏi nhiều nhất của một xe, ở dạng đọc được. Thiếu số nào bỏ số đó.

    Dùng cho câu dẫn bài đề xuất khi không có lý do chấm điểm nào đáng nói
    (`need_lead(facts=…)`): "từ 278 triệu, 4 chỗ, ~215 km mỗi lần sạc" là một
    câu có nội dung, còn "thuộc đúng dòng xe đang tìm" thì không.
    """

    facts: list[str] = []
    price = _amount(price_vnd)
    if price is not None:
        facts.append(f"từ {format_number(price, 'đ')}")
    if isinstance(seats, int) and not isinstance(seats, bool) and seats > 0:
        facts.append(f"{seats} chỗ")
    reach = _amount(range_km)
    if reach is not None:
        facts.append(f"~{format_number(reach, 'km')} mỗi lần sạc")
    return tuple(facts)


def need_lead(
    *, purpose: str, passenger_count: object, vehicle_name: str, reason: str, facts: Sequence[str] = ()
) -> str:
    """MỘT câu dẫn cho mỗi xe, viết bằng chữ KHÁCH vừa dùng. Rỗng nếu chưa đủ dữ liệu.

    Bài prod đọc "có công suất động cơ lớn nhất trong nhóm em vừa chọn… hợp với
    mục đích sử dụng Quý khách chia sẻ": đúng ngữ pháp, nhưng "mục đích sử dụng
    Quý khách chia sẻ" là chỗ đáng ra phải in ĐÚNG việc khách vừa kể. Bộ viết
    bài đã nhận `customer_wording` và `feature_mention_codes` (xem
    `act.customer_wording`) mà vẫn nói chung chung, nên câu này được dựng TẤT
    ĐỊNH ở đây — không nhờ mô hình, không có gì để quên.

    Chỉ chữ khách tự nói và lý do đã có sẵn trong `Recommendation.reasons` (trỏ
    về slot, không do LLM viết) mới được vào đây.

    Không có lý do nào đáng nói (khách gõ "đi rạo" — lỗi chính tả, không khớp
    need-tag nào — nên lý do duy nhất là claim loại xe, prod benchmark2) thì câu
    dẫn nói bằng SỐ THẬT của chính chiếc xe (`facts`, xem `spec_facts`): "VF 3:
    từ 278 triệu, 4 chỗ, ~215 km mỗi lần sạc". Cùng một câu độn lặp cho ba xe
    là thứ khách đọc ra ngay là máy viết.
    """

    need = (purpose or "").strip().rstrip(".")
    count = passenger_count if isinstance(passenger_count, int) and passenger_count > 0 else None
    if count is not None:
        need = f"{need} cho {count} người" if need else f"chở {count} người"
    if not need or not vehicle_name:
        return ""
    why = (_sanitize_reason(reason) or "").strip().rstrip(".") if reason else ""
    numbers = [item.strip() for item in facts if item and item.strip()]
    if why:
        tail = f" hợp vì {why}"
    elif numbers:
        tail = f": {', '.join(numbers)}"
    else:
        tail = " là mẫu sát nhất"
    return assert_clean(tidy_number(f"Với nhu cầu {need}, {vehicle_name}{tail}."))


def ask_province_for_price() -> str:
    """Câu hỏi tỉnh của lượt GIÁ LĂN BÁNH — không phải câu của lượt lái thử.

    `SLOT_QUESTIONS["registration_province"]` nói "để em tìm showroom gần nhất":
    đúng cho lượt đặt lịch, nhưng khách vừa hỏi TIỀN. Phí trước bạ và biển số
    khác nhau theo tỉnh nên đây mới là lý do thật của câu hỏi, và nói đúng lý do
    là cách duy nhất để khách chịu trả lời thêm một câu.
    """

    return assert_clean("Anh/chị đăng ký xe ở tỉnh/thành nào để em tính đúng phí lăn bánh ạ?")


def vnd_full(value: object) -> str:
    """Số tiền đủ chữ số kiểu niêm yết: 899000000 → "899.000.000đ".

    Khác `format_number(…, "đ")` (làm tròn về triệu cho câu văn): giá niêm yết
    là con số khách đem đi so với bảng giá đại lý, phải khớp từng chữ số.
    """

    amount = _amount(value)
    if amount is None:
        return ""
    return f"{int(round(amount)):,}".replace(",", ".") + "đ"


def short_vehicle_name(vehicle_name: str) -> str:
    """Tên xe bỏ tiền tố hãng cho nhãn nút ("VinFast VF 8" → "VF 8"). Rỗng giữ rỗng."""

    name = (vehicle_name or "").strip()
    for prefix in ("VinFast ", "Vinfast ", "vinfast "):
        if name.startswith(prefix):
            return name[len(prefix) :].strip()
    return name


def price_lookup(*, vehicle_name: str, price_vnd: object) -> str:
    """Câu trả lời cho "giá <mẫu> bao nhiêu": giá niêm yết TRƯỚC, rồi hai lối đi tiếp.

    Prod benchmark2: câu hỏi giá nhận nguyên bảng thông số dài. Khách hỏi một
    con số thì con số phải đứng ở câu đầu; thông số khác họ hỏi sau nếu cần.
    """

    name = vehicle_name or "Mẫu xe này"
    return assert_clean(
        f"{name}: giá niêm yết từ {vnd_full(price_vnd)} (đã VAT). "
        "Anh/chị muốn em tính giá lăn bánh theo tỉnh hay chi phí sử dụng 5 năm không ạ?"
    )


#: Nhãn nút sau câu trả lời giá — viết đúng như KHÁCH sẽ gõ (luật `suggest.py`),
#: có tên xe để cửa hiểu ý trỏ đúng mẫu ở lượt sau.
def price_lookup_replies(vehicle_name: str) -> tuple[str, ...]:
    short = short_vehicle_name(vehicle_name)
    if not short:
        return ()
    return tuple(
        assert_clean(item) for item in (f"Giá lăn bánh {short}", f"Tính chi phí {short}", f"Đặt lái thử {short}")
    )


#: Trần số tên xe đọc trong câu "hiện có: …" — dài hơn thì khách đọc thẻ, không đọc chữ.
MAX_CATALOG_NAMES_IN_TEXT = 8


def not_in_catalog(*, mention: str, vehicle_names: Sequence[str]) -> str:
    """Khách nêu tên xe không có trong danh mục — nói thật, bày danh mục, mở hai lối.

    Prod benchmark2: "anh muốn mua mẫu vf10" nhận "Anh/chị muốn xem mẫu nào ạ?
    Anh/chị cho em tên mẫu nhé." — hỏi lại đúng thứ khách vừa nói. Câu này nói ra
    tên khách dùng (để họ biết bot đã nghe), tên các mẫu THẬT (từ catalog, đã bỏ
    tiền tố hãng cho gọn), rồi mời chọn mẫu HOẶC kể nhu cầu.
    """

    shown = [short_vehicle_name(name) for name in vehicle_names if name]
    shown = list(dict.fromkeys(name for name in shown if name))[:MAX_CATALOG_NAMES_IN_TEXT]
    head = f"Em chưa thấy '{mention}' trong danh mục VinFast hiện hành ạ."
    if not shown:
        return assert_clean(f"{head} Anh/chị cho em ngân sách + nhu cầu để em chọn giúp nhé?")
    return assert_clean(
        f"{head} Hiện có: {', '.join(shown)}. Anh/chị xem mẫu nào, hay cho em ngân sách + nhu cầu để em chọn giúp?"
    )


def no_fact(vehicle_name: str) -> str:
    """Không có dữ liệu trả lời câu hỏi về xe — nói thật, rồi đề nghị TVV."""

    name = vehicle_name or "mẫu xe này"
    return assert_clean(
        f"Thông tin này của {name} em chưa có trong dữ liệu đã kiểm chứng ạ. "
        "Em nhờ tư vấn viên trả lời chính xác cho anh/chị nhé?"
    )


def fit_assessment(
    *,
    vehicle_name: str,
    verdict: str,
    reasons: Sequence[str],
    alternative_name: str = "",
    just_chosen: bool = False,
    closing: str | None = None,
) -> str:
    """Câu trả lời cho "xe này có hợp với nhu cầu của tôi không".

    `closing`: câu kết theo checklist cho nhánh HỢP — thay câu menu mở cũ.

    Nhận CHUỖI chứ không nhận `fit.FitAssessment`: `fit` đã import module này để
    dùng chung một bộ định dạng tiền, nên nhận kiểu của nó ở đây là dựng một
    vòng import giữa hai file thuần. `verdict` là một trong ba hằng `FIT_*` của
    `actions` — chính nó là chữ đọc cho khách, nên không có bảng dịch thứ hai.

    Lượt vừa CHỌN vừa HỎI được trả lời trong MỘT tin nhắn: bỏ lời ghi nhận thì
    khách không biết lõi đã chốt xe; bỏ phần đánh giá thì đúng lỗi prod vòng 9.
    """

    name = vehicle_name or "mẫu xe này"
    opening = f"Dạ, em ghi nhận anh/chị chọn {name}. " if just_chosen else "Dạ, "
    lines = [f"{opening}đối chiếu với nhu cầu anh/chị đã kể thì {name} {verdict or FIT_PARTIAL} ạ:"]
    lines.extend(f"- {reason}" for reason in reasons if reason)
    if verdict == FIT_YES:
        lines.append(closing or "Anh/chị muốn em tính chi phí sử dụng hay đặt lịch lái thử ạ?")
    elif alternative_name:
        lines.append(f"Hợp hơn với ý anh/chị vừa nói thì có {alternative_name} — em so hai mẫu này giúp anh/chị nhé?")
    else:
        lines.append("Anh/chị muốn em tìm mẫu khác bám sát nhu cầu này hơn không ạ?")
    return assert_clean("\n".join(lines))


def compare_fit_lead(*, better_name: str, better_reasons: Sequence[str], other_name: str, tie: bool = False) -> str:
    """Dòng KẾT LUẬN đặt TRƯỚC bảng so sánh: mẫu nào hợp nhu cầu hơn, vì sao.

    Bảng so sánh đặt hai cột số cạnh nhau rồi để khách tự xếp hạng — nhưng câu
    khách hỏi ("cái nào hợp với nhu cầu của tôi hơn") là một câu XẾP HẠNG. Dòng
    này trả lời đúng câu đó, bảng ở dưới là bằng chứng.
    """

    left = better_name or "mẫu thứ nhất"
    right = other_name or "mẫu còn lại"
    if tie:
        return assert_clean(
            f"Dạ, theo nhu cầu anh/chị đã kể thì {left} và {right} bám sát ngang nhau ạ — "
            "anh/chị xem bảng dưới rồi cho em biết tiêu chí nào quan trọng nhất nhé?"
        )
    why = "; ".join(reason for reason in list(better_reasons)[:2] if reason)
    detail = f": {why}" if why else ""
    return assert_clean(f"Dạ, theo nhu cầu anh/chị đã kể thì {left} hợp hơn {right} ạ{detail}.")


#: Nhãn nút của lượt "các bước đi tiếp". Viết đúng như KHÁCH sẽ gõ (luật của
#: `suggest.py`): nút gửi lại nguyên văn vào cùng cửa hiểu ý.
NEXT_STEP_REPLIES: tuple[str, ...] = ("Đặt lịch lái thử", "Có ưu đãi gì không?")


def next_steps(vehicle_name: str) -> str:
    """Các BƯỚC để chốt một chiếc xe — nói thật việc nào bot làm, việc nào người làm.

    Lượt prod vòng 9: "làm sao để tôi chốt vf3" nhận về "em vẫn thấy VF 3 hợp
    nhất. Anh/chị muốn em tính chi phí, so sánh với mẫu khác, hay đặt lái thử
    ạ?" — khách đang ở bước cuối và bị đẩy về bước đầu.

    Ba bước dưới đây là ĐÚNG những gì hệ đang làm được: đặt lịch lái thử có
    đường chạy thật (`ShowroomOptions` → `Book`), ưu đãi đi qua tư vấn viên
    (`EnqueueHitl`), còn cọc và hợp đồng thì showroom lo — hứa bot chốt cọc
    online là hứa một việc không có thật.
    """

    name = vehicle_name or "mẫu xe này"
    return assert_clean(
        f"Dạ, để chốt {name} thì mình đi ba bước ạ:\n"
        f"1. Đặt lịch lái thử tại showroom gần anh/chị — em xếp lịch ngay trong cuộc trò chuyện này.\n"
        f"2. Hỏi ưu đãi đang áp dụng cho {name} — em chuyển tư vấn viên báo lại chính sách mới nhất.\n"
        "3. Đặt cọc và ký hợp đồng tại showroom, bên đó lo tiếp hồ sơ và bàn giao xe.\n"
        "Anh/chị muốn bắt đầu từ bước nào ạ?"
    )


def scope_note(*, vehicle_name: str, range_km: object = None) -> str:
    """Câu hỏi NGOÀI phạm vi — nói thật, rồi kéo về đúng thứ giúp được.

    Lượt prod vòng 9: "VF3 thì nên đi du lịch ở Việt Nam, ở đâu" rơi vào đường
    xin CHỈNH đề xuất và khách nhận "em chưa có mẫu nào khác hợp hơn ạ". Vừa
    không trả lời được câu hỏi, vừa nói một câu chẳng liên quan.

    Có `range_km` thì nói ra con số THẬT của chính chiếc xe đó: đó là phần duy
    nhất của câu hỏi du lịch mà lõi có dữ liệu để trả lời.
    """

    name = vehicle_name or "mẫu xe này"
    amount = _amount(range_km)
    if amount:
        reach = format_number(amount, "km")
        return assert_clean(
            f"Dạ, chỗ đi chơi thì em chưa tư vấn được, em chỉ rành về xe thôi ạ. "
            f"Nhưng về {name}: tầm chạy {reach} mỗi lần sạc, nên các chuyến trong khoảng đó là đi thẳng một mạch, "
            "xa hơn thì mình tính thêm một điểm sạc giữa đường. "
            "Anh/chị cho em biết quãng đường hay đi để em xem xe có đủ không nhé?"
        )
    return assert_clean(
        f"Dạ, việc này em chưa tư vấn được, em chỉ rành về xe thôi ạ. "
        f"Anh/chị muốn em nói thêm về {name} — chi phí sử dụng, tầm chạy, hay đặt lịch lái thử ạ?"
    )


def policy_handoff_note() -> str:
    """Báo khách: câu chính sách đã sang TVV, và MỜI HỎI TIẾP — không bỏ rơi."""

    return assert_clean(
        "Dạ, câu về chính sách này em đã chuyển tư vấn viên để trả lời cho thật chính xác — "
        "câu trả lời sẽ hiện ngay tại đây ạ. Trong lúc chờ, anh/chị cứ hỏi tiếp về xe thoải mái."
    )


def policy_vehicle_clarification() -> str:
    """Ask for an exact model before searching vehicle-bound policy scopes."""

    return assert_clean("Anh/chị muốn hỏi chính sách cho mẫu xe nào ạ?")


def policy_review_draft(*, user_message: str) -> str:
    """Nháp TRẢ KHÁCH cho mục duyệt chính sách — TVV điền nội dung rồi duyệt."""

    return assert_clean(
        "Dạ, về câu hỏi chính sách của anh/chị, tư vấn viên xin trả lời như sau: "
        "(tư vấn viên bổ sung nội dung đã kiểm chứng rồi gửi giúp em ạ)"
    )


def policy_no_source() -> str:
    """Hỏi chính sách mà không có tài liệu nào để dựa vào — nói thật, mời TVV.

    Câu chính sách là câu SAI ĐẮT nhất (bảo hành mấy năm, trả góp bao nhiêu phần
    trăm): trả lời bằng trí nhớ mô hình là hứa thay công ty. Không nguồn thì
    không câu trả lời, đúng cách `no_fact` xử câu hỏi về xe.
    """

    return assert_clean(
        "Chính sách này em chưa có tài liệu chính thức để trả lời chính xác ạ. "
        "Em nhờ tư vấn viên xác nhận lại cho anh/chị nhé?"
    )


def test_drive_needs_location() -> str:
    """Chữ đi kèm thẻ lái thử `needs_location=True` — mời chọn vị trí TRÊN THẺ.

    Đợt 8 (contract mục 1): không hỏi tỉnh bằng chữ nữa. Câu hỏi tỉnh bắt khách
    gõ, rồi lượt sau mới có thẻ; thẻ có sẵn nút vị trí thì một lượt là xong.
    """

    return assert_clean(
        "Anh/chị bấm *Dùng vị trí của tôi* hoặc gõ quận/huyện ngay trong thẻ "
        "để em tìm showroom gần nhất và giờ lái thử nhé."
    )


def booking_summary(*, vehicle_name: str, showroom: str, scheduled_at: datetime) -> str:
    """Câu xác nhận lịch — THAY bài đề xuất, không nối sau (bẫy spec mục 12).

    Đây cũng là chỗ DUY NHẤT nút `__lichlaithu__` được nhân-hoá thành chữ: mọi
    `Ask(kind=CONFIRM)` về đặt lịch phải lấy chuỗi từ đây, vì `assert_clean`
    chặn token `__x__` và sẽ ném `RenderError` nếu token thô lọt vào.
    """

    when = scheduled_at.strftime("%H:%M ngày %d/%m")
    return assert_clean(f"lái thử {vehicle_name or 'xe'} lúc {when} tại {showroom}")


def feature_label(code: str) -> str | None:
    """Mã tính năng → nhãn tiếng Việt, hoặc `None` khi không bảng nào dịch được.

    Trả `None` chứ không echo mã: `_label` đã chốt như vậy ở bước 1 vì đọc
    nguyên `7_SEATER` cho khách chính là lỗi đã lộ 80 lần trên prod. Tầng act
    phải LOẠI mã không dịch được khỏi `options`, không được giữ mã rồi gán nhãn
    bằng chính nó.
    """

    return _label(code)


def tco_summary(
    *,
    vehicle_name: str,
    total_text: str,
    assumed_daily_km: int | None = None,
    daily_km: int | None = None,
    closing: str | None = None,
) -> str:
    """`assumed_daily_km` khác `None` = khách CHƯA nói số km, lõi tự tạm tính.

    `closing` (đợt 9): câu kết theo checklist thay "tính lại với số km khác không
    ạ?" — khách sửa km bằng ô trên thẻ chi phí, câu kết phải mời việc KẾ TIẾP.

    Phải nói ra con số đã tạm tính: một tổng năm năm dựa trên giả định giấu kín
    là con số khách mang đi so với báo giá đại lý mà không biết nó tính theo
    quãng đường nào. Nói ra thì họ sửa được ngay ở câu sau.
    """

    name = vehicle_name or "mẫu xe này"
    # Sếp 2026-08-31: THẺ là nơi khách tự chỉnh khu vực + km — chữ không giả
    # định, không hỏi km nữa; chỉ giới thiệu bảng rồi (nếu có) dẫn bước kế.
    lead = f"Bảng chi phí 5 năm của {name} khoảng {total_text} đây ạ — anh/chị chỉnh khu vực và số km mỗi ngày ngay trên bảng."
    return assert_clean(f"{lead} {closing}" if closing else lead)


def on_road_card_lead(*, vehicle_name: str, closing: str | None = None) -> str:
    """Câu dẫn của lượt GIÁ LĂN BÁNH — thẻ nói số, chữ chỉ trỏ vào thẻ.

    Sếp 2026-08-31: "giá lăn bánh với TCO là MỘT" — lượt này trả đúng thẻ chi
    phí, không đọc con số trong chat và KHÔNG hỏi tỉnh (thẻ có ô chọn, mặc định
    Khu vực II như thẻ vẫn làm); khoản lăn bánh nằm ở nhóm đầu bảng.
    """

    name = vehicle_name or "mẫu xe này"
    lead = (
        f"Bảng chi phí của {name} đây ạ — phần *giá lăn bánh* nằm ngay các khoản đầu bảng, "
        "anh/chị chọn tỉnh trên bảng để đúng lệ phí biển số."
    )
    return assert_clean(f"{lead} {closing}" if closing else lead)


def tco_updated(*, vehicle_name: str, km: int | None = None, province_name: str | None = None) -> str:
    """Khách nhắc lại km/tỉnh SAU khi đã có thẻ → xác nhận ĐÃ cập nhật thẻ cũ.

    Sếp 2026-08-31: thẻ chi phí giữ xuyên suốt phiên và đổi số TẠI CHỖ — chữ mà
    đọc lại một bài dẫn mới thì khách tưởng vừa có thẻ thứ hai. Câu chỉ nói đúng
    thứ vừa đổi (km / tỉnh), không đọc lại con số: số nằm trên thẻ.
    """

    name = vehicle_name or "mẫu xe này"
    changes: list[str] = []
    if km is not None:
        changes.append(f"quãng đường {km} km mỗi ngày")
    if province_name:
        changes.append(f"tỉnh đăng ký {province_name}")
    detail = " và ".join(changes) or "thông tin mới"
    return assert_clean(f"Dạ, em đã cập nhật lại bảng chi phí của {name} theo {detail} giúp anh/chị ạ.")


def booking_confirmed(summary: str, *, showroom: str = "") -> str:
    """Câu chốt sau khi đặt lịch: CẢM ƠN + BẢNG thông tin + lối chỉ đường.

    Sếp 2026-08-31 (hai đợt): "đặt lịch xong phải cảm ơn chứ", rồi "gửi lại
    thông tin lịch của khách dưới dạng bảng và vị trí showroom, khách chỉ cần
    click". `summary` vẫn là chuỗi của `booking_summary` ("lái thử X lúc H
    ngày D tại S") — tách lại thành dòng ở đây thay vì đổi chữ ký cả chuỗi gọi.
    Link chỉ đường theo TÊN showroom (không bịa toạ độ); client chỉ render link
    tuyệt đối cho đúng tiền tố Google Maps này.
    """

    head = "Dạ, em đã đặt lịch thành công — em cảm ơn anh/chị đã tin tưởng ạ!"
    tail = "Tư vấn viên sẽ liên hệ xác nhận với anh/chị trước buổi hẹn ạ."
    lines = [head]
    marker = " tại "
    when_part, _, place_part = summary.rpartition(marker)
    if when_part and place_part:
        vehicle_part, _, when = when_part.partition(" lúc ")
        vehicle_name = vehicle_part.removeprefix("lái thử").strip()
        lines.append(f"1. **Xe lái thử**: {vehicle_name}")
        if when.strip():
            lines.append(f"2. **Thời gian**: {when.strip()}")
        lines.append(f"3. **Showroom**: {place_part.strip()}")
    else:
        lines.append(f"1. **Lịch hẹn**: {summary}")
    if showroom.strip():
        # Trỏ về trang bản đồ CỦA MÌNH với ô tìm điền sẵn tên showroom (Sếp
        # 2026-08-31): khách thấy đúng điểm hẹn trên bản đồ nhà, bấm điểm đó là
        # có nút Chỉ đường mở Google Maps theo TOẠ ĐỘ THẬT — chính xác hơn link
        # maps theo tên, và khách không bị bứng thẳng ra ngoài web.
        target = quote(showroom.strip())
        lines.append(f"4. **Vị trí**: [Xem showroom trên bản đồ để bấm chỉ đường](/locations?q={target})")
    lines.append(tail)
    return assert_clean("\n".join(lines))


def slot_expired() -> str:
    """Mã khung giờ không đọc được (hết hạn, sai chữ ký, của phiên khác).

    Khác `booking_invalid`: câu kia mời khách "chọn lại một khung ở trên", đúng
    khi các nút vẫn còn trên màn hình. Lượt prod LP21 là nút của một lượt CŨ —
    không còn khung nào "ở trên" để chọn, nên lõi phải bày lại khung mới.
    """

    return assert_clean("Khung giờ này đã hết hiệu lực rồi ạ, em gợi ý lại các khung giờ mới nhé.")


def booking_invalid() -> str:
    return assert_clean("Khung giờ này không còn hiệu lực ạ. Anh/chị chọn lại giúp em một khung ở trên nhé?")


def offer_pending(vehicle_name: str) -> str:
    name = vehicle_name or "mẫu xe anh/chị chọn"
    return assert_clean(f"Em đã chuyển yêu cầu ưu đãi cho {name} tới tư vấn viên ạ. Anh/chị chờ em ít phút nhé.")


def confirm_offer_label(vehicle_name: str) -> str:
    """Nhãn khách đọc được cho `Ask(kind=CONFIRM, key=offer)`.

    Policy chỉ treo `vehicle_id` (nó không biết catalog), nên không có hàm này
    thì `render_ask` đọc nguyên uuid cho khách. Tên tra không ra → cụm chữ chung,
    KHÔNG bao giờ là id thô.
    """

    return assert_clean(f"xin ưu đãi cho {vehicle_name or 'mẫu xe anh/chị chọn'}")


def offer_review_summary(snapshot: object) -> str:
    """Dòng tổng hợp cho TVV đọc ngay trong `content` của mục duyệt."""

    needs = list(getattr(snapshot, "needs", ()) or ())
    considered = list(getattr(snapshot, "considered_vehicles", ()) or ())
    bottlenecks = list(getattr(snapshot, "bottlenecks", ()) or ())
    parts = []
    if considered:
        parts.append("Quan tâm: " + ", ".join(considered[:3]))
    if needs:
        parts.append("Nhu cầu: " + "; ".join(needs[:5]))
    if bottlenecks:
        labels = {"PRICE": "giá", "CHARGING": "sạc", "BATTERY": "pin", "RANGE": "tầm chạy"}
        parts.append(
            "Lăn tăn: "
            + "; ".join(
                f'{labels.get(str(getattr(item, "bottleneck", "")).split(".")[-1], "khác")} ("{getattr(item, "verbatim_quote", "")[:60]}")'
                for item in bottlenecks[:3]
            )
        )
    if not parts:
        parts.append("Chưa ghi nhận nhu cầu hay điểm lăn tăn cụ thể.")
    return "Tổng hợp khách — " + " | ".join(parts)


def offer_review_content(*, vehicle_name: str, user_message: str) -> str:
    """(Cũ) mô tả nội bộ — GIỮ cho tương thích test cũ, không còn gửi đi đâu."""

    return f"Khách hỏi ưu đãi cho {vehicle_name or 'xe chưa xác định'}. Nguyên văn: {user_message.strip()[:400]}"


def offer_review_draft(*, vehicle_name: str, promo_count: int) -> str:
    """BẢN NHÁP TRẢ KHÁCH của mục ưu đãi — thứ TVV sửa/duyệt và hệ GỬI THẲNG khách.

    Bài học prod 2026-08-31: `content` từng là dòng nội bộ ("Khách hỏi ưu đãi…
    Tổng hợp khách —…"), TVV bấm duyệt nguyên trạng là khách nhận nguyên dòng đó.
    Nháp không chứa SỐ (guard 1A cấm số ngoài danh sách verify) — con số ưu đãi
    do TVV điền, đối chiếu bảng chính sách điều chỉnh đã duyệt.
    """

    name = vehicle_name or "mẫu xe anh/chị chọn"
    if promo_count > 0:
        # KHÔNG in con số đếm: guard 1A đếm MỌI chữ số trong content, "3 chương
        # trình" cũng thành số chưa verify và chặn luôn nút duyệt nguyên trạng.
        return assert_clean(
            f"Dạ, {name} đang có chương trình ưu đãi áp dụng ạ. "
            "Tư vấn viên xin phép gửi mức ưu đãi cụ thể ngay trong tin này."
        )
    return assert_clean(
        f"Dạ, về ưu đãi cho {name}: tư vấn viên đang kiểm tra chương trình đang chạy và sẽ báo anh/chị ngay ạ."
    )


#: Từ khoá trong câu hỏi → (mã spec, nhãn, đơn vị). Thứ tự = thứ tự ưu tiên khi
#: câu chạm nhiều nhóm. Chỉ đọc cột catalog đã có — không suy diễn, không LLM.
#: Khoá nhóm theo THỨ TỰ các hàng `_SPEC_QA` — hợp đồng với tool `tra_thong_so`
#: (`domain/spec_tool.SPEC_GROUPS`); test chốt hai bản không trôi nhau.
SPEC_GROUP_KEYS: tuple[str, ...] = (
    # tam_di TRƯỚC sac: câu "đi được bao xa mỗi lần sạc" chứa cả "bao xa" và
    # "sạc"; first-match-wins nên nhóm tầm-đi phải đứng trước, không thì khách
    # hỏi TẦM ĐI lại nhận THỜI GIAN SẠC (bug ACC-07, benchmark 2026-08-31).
    "tam_di", "sac", "pin", "cho_ngoi", "cop", "cong_suat",
    "tang_toc", "toc_do", "tai_trong", "yen", "bang_lai", "kieu_dang",
)

_SPEC_QA: tuple[tuple[tuple[str, ...], tuple[tuple[str, str, str], ...]], ...] = (
    (
        ("bao xa", "quãng đường", "đi được", "tầm hoạt động", "tầm chạy"),
        (("range_km", "tầm hoạt động khoảng", "km"), ("range_max_km", "tầm hoạt động tối đa khoảng", "km")),
    ),
    (
        ("sạc",),
        (
            ("fast_charge_time_minutes", "sạc nhanh khoảng", "phút"),
            ("charging_time_minutes", "thời gian sạc khoảng", "phút"),
            ("battery_capacity_kwh", "pin", "kWh"),
        ),
    ),
    (("pin",), (("battery_capacity_kwh", "dung lượng pin", "kWh"), ("battery_type", "loại pin", ""))),
    (("chỗ", "ngồi", "mấy người", "bao nhiêu người"), (("seat_count", "", "chỗ ngồi"),)),
    (("cốp", "hành lý", "khoang"), (("cargo_volume_standard_l", "khoang hành lý", "lít"),)),
    (
        ("công suất", "mạnh", "mã lực", "động cơ"),
        (
            ("motor_power_kw", "công suất", "kW"),
            ("motor_power_w", "công suất", "W"),
            ("torque_nm", "mô-men xoắn", "Nm"),
        ),
    ),
    (("tăng tốc",), (("acceleration_0_100_seconds", "tăng tốc 0–100 km/h", "giây"),)),
    (("tốc độ", "nhanh nhất", "tối đa"), (("max_speed_kmh", "tốc độ tối đa", "km/h"),)),
    (("tải", "chở nặng", "chở được"), (("max_load_kg", "tải trọng tối đa", "kg"),)),
    (("yên",), (("seat_height_mm", "chiều cao yên", "mm"),)),
    (("bằng lái", "bằng"), (("license_requirement", "yêu cầu bằng lái", ""),)),
    (("kiểu dáng", "dáng", "loại xe gì"), (("body_type", "kiểu dáng", ""),)),
)


def _spec_value(value: object) -> str:
    if isinstance(value, Decimal):
        normalized = value.normalize()
        text = (
            format(normalized, "f")
            if normalized == normalized.to_integral()
            else format(normalized, "f").rstrip("0").rstrip(".")
        )
        return text.replace(".", ",")
    if isinstance(value, float):
        return _spec_value(Decimal(str(value)))
    text = str(value).strip()
    try:
        return _spec_value(Decimal(text))
    except (ArithmeticError, ValueError):
        return text


def spec_answer(
    *, vehicle_name: str, question: str, specs: Mapping[str, object], closing: str | None = None
) -> str | None:
    """Trả lời MỘT câu hỏi thông số bằng đúng cột catalog — không đổ cả bảng.

    Probe H-7 (2026-08-30): "VF 5 sạc bao lâu" nhận về nguyên bảng tổng quan
    (động cơ, ADAS, giá...). Khách hỏi một con số thì trả một con số; câu không
    chạm nhóm nào (bảo hành, màu...) → `None`, act rơi về tổng quan như cũ.
    """

    text = (question or "").casefold()
    for keywords, columns in _SPEC_QA:
        if not any(keyword in text for keyword in keywords):
            continue
        spoken = _render_spec_columns(vehicle_name=vehicle_name, columns=columns, specs=specs, closing=closing)
        if spoken:
            return spoken
    return None


def spec_answer_by_group(
    *, vehicle_name: str, group: str, specs: Mapping[str, object], closing: str | None = None
) -> str | None:
    """Trả lời theo NHÓM đã biết — lối vào của tool `tra_thong_so`.

    Tool chỉ trỏ nhóm; con số và lời đánh giá vẫn tất định từ catalog, cùng một
    bộ render với đường từ khoá — hai lối vào, MỘT cách nói.
    """
    try:
        index = SPEC_GROUP_KEYS.index(group)
    except ValueError:
        return None
    _, columns = _SPEC_QA[index]
    return _render_spec_columns(vehicle_name=vehicle_name, columns=columns, specs=specs, closing=closing)


def _render_spec_columns(
    *, vehicle_name: str, columns: tuple[tuple[str, str, str], ...], specs: Mapping[str, object], closing: str | None
) -> str | None:
    parts = []
    verdict = ""
    for code, label, unit in columns:
        value = specs.get(code)
        if value is None or str(value).strip() == "":
            continue
        parts.append(" ".join(part for part in (label, _spec_value(value), unit) if part))
        if not verdict:
            verdict = _spec_verdict(code, value)
    if not parts:
        return None
    name = vehicle_name or "mẫu xe này"
    tail = closing or "Anh/chị cần em nói thêm gì về xe không ạ?"
    body = "; ".join(parts)
    # Con số PHẢI đi kèm lời đánh giá (Sếp 2026-08-31: "446 lít" trần
    # trụi không giúp khách biết cốp đó rộng hay hẹp so với việc chở đồ).
    spoken = f"Dạ, {name}: {body} — {verdict} ạ. {tail}" if verdict else f"Dạ, {name}: {body} ạ. {tail}"
    return assert_clean(spoken)


def _chosen_segment(body_type: str, seat_count: int | None) -> str:
    """Nhóm người ĐIỂN HÌNH của một mẫu — ánh xạ TẤT ĐỊNH từ kiểu thân xe + số
    chỗ. Không phải nhu cầu của khách (khách chưa kể), mà là phân khúc mà chính
    mẫu xe đó hướng tới. Bảo thủ: câu chung đúng cho mọi mẫu cùng dạng.
    """
    body = (body_type or "").casefold()
    seats = seat_count or 0
    if seats >= 7:
        return "hợp với gia đình đông người hoặc anh/chị cần chở nhiều"
    if "suv" in body or "cuv" in body or "gầm cao" in body:
        return "hợp với gia đình nhỏ, đi phố hằng ngày lẫn đi xa cuối tuần"
    if "hatchback" in body or "mini" in body or "đô thị" in body or (0 < seats <= 4):
        return "hợp với anh/chị đi lại trong phố, chỗ đỗ hẹp và đường đông"
    if "sedan" in body:
        return "hợp với anh/chị cần một chiếc lịch sự, êm ái đi làm và tiếp khách"
    return "hợp với nhiều nhu cầu đi lại hằng ngày"


def chosen_intro(*, vehicle_name: str, specs: Mapping[str, object]) -> str | None:
    """Giới thiệu NGẮN về mẫu khách vừa chọn — dòng xe, thông số nổi bật, nhóm
    người điển hình. Số liệu từ catalog; nhóm người ánh xạ từ thân xe + số chỗ.
    KHÔNG nói "hợp nhu cầu anh/chị" (khách chưa kể nhu cầu ở nhánh chọn khan —
    Sếp 2026-08-31). Thiếu dữ liệu cốt lõi thì trả `None` để act rơi về fallback.
    """
    name = vehicle_name or "mẫu xe này"
    body = str(specs.get("body_type") or "").strip()
    seat = specs.get("seat_count")
    seat_int = int(seat) if isinstance(seat, int | float) and not isinstance(seat, bool) else None
    range_val = specs.get("range_km") or specs.get("range_max_km")
    facts: list[str] = []
    if body:
        facts.append(f"là dòng {body}" + (f" {seat_int} chỗ" if seat_int else ""))
    elif seat_int:
        facts.append(f"là mẫu {seat_int} chỗ")
    if range_val is not None and str(range_val).strip():
        facts.append(f"tầm chạy khoảng {_spec_value(range_val)} km mỗi lần sạc")
    if not facts:
        return None
    segment = _chosen_segment(body, seat_int)
    body_text = f"Dạ, {name} {', '.join(facts)} — {segment} ạ. "
    # Chủ động MỜI khách kể nhu cầu để tư vấn sát hơn — nhưng KHÔNG khẳng định
    # "rất hợp với yêu cầu anh/chị" khi chưa biết nhu cầu (Sếp 2026-08-31).
    tail = (
        "Anh/chị cho em biết thêm mình hay dùng xe vào việc gì, đi lại tầm bao nhiêu để em tư vấn "
        "sát hơn nhé — hoặc em tính luôn chi phí sử dụng, giá lăn bánh cho anh/chị ạ."
    )
    return assert_clean(body_text + tail)


def _spec_verdict(code: str, value: object) -> str:
    """Lời ĐÁNH GIÁ tất định cho một con số thông số — ngưỡng theo mặt bằng dải xe VinFast.

    Không LLM, không bịa: chỉ xếp con số vào khung rộng/vừa/gọn với hệ quả sử
    dụng cụ thể, để khách hỏi "cốp có rộng không" nhận được câu trả lời CÓ/KHÔNG
    kèm lý do chứ không phải một con số tự tra nghĩa.
    """

    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return ""
    if code == "cargo_volume_standard_l":
        if number >= 420:
            return "cốp thuộc loại rộng rãi, chở nhiều đồ hay vali cho cả nhà đều thoải mái"
        if number >= 300:
            return "cốp mức khá, đủ cho đồ đạc đi lại hằng ngày; chở cồng kềnh thì gập thêm hàng ghế sau"
        return "cốp gọn, hợp đồ nhẹ; chở nhiều đồ anh/chị sẽ cần gập hàng ghế sau"
    if code in ("range_km", "range_max_km"):
        if number >= 350:
            return "tầm chạy dư dả cho cả những chuyến đi tỉnh"
        if number >= 250:
            return "tầm chạy thoải mái cho đi lại hằng ngày và chuyến gần"
        return "tầm chạy hợp đi phố; đi xa nên tính trước điểm sạc dọc đường"
    if code in ("fast_charge_time_minutes", "charging_time_minutes"):
        if number <= 35:
            return "sạc nhanh thuộc nhóm tốt — nghỉ một ly cà phê là đủ pin đi tiếp"
        if number <= 60:
            return "thời gian sạc ở mức trung bình"
        return "sạc hơi lâu, hợp cắm qua đêm hơn là sạc dọc đường"
    if code == "seat_count":
        if number >= 7:
            return "đủ chỗ cho gia đình đông người"
        if number >= 5:
            return "vừa vặn cho gia đình 4–5 người"
        return "hợp đi một mình hoặc hai người"
    if code == "max_load_kg":
        return "tải trọng đáp ứng tốt việc chở hàng hằng ngày" if number >= 140 else "tải trọng hợp chở người và đồ nhẹ"
    return ""


def qa_follow_up(vehicle_name: str) -> str:
    """Câu kết SAU một thắc mắc về xe: mời soi tiếp về xe, KHÔNG lái sang tiền.

    Sếp 2026-08-31: khách đang hỏi đặc tính mà bot chốt hạ "xem chi phí 5 năm
    hay giá lăn bánh?" là bỏ rơi mạch quan tâm của họ.
    """

    name = vehicle_name or "mẫu xe này"
    return assert_clean(f"Anh/chị còn băn khoăn điểm nào của {name} nữa không ạ? Hỏi em thoải mái.")
