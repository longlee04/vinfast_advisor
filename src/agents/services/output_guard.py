"""Final customer-output cleanup; internal provenance remains in the draft."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Final

from src.agents.contracts import TurnResult

_INTERNAL_CITATION: Final[re.Pattern[str]] = re.compile(
    r"\s*\[(?:evidence_id|source_record):[^\]]+\]",
    re.IGNORECASE,
)
#: Nibble phiên bản để `[1-7]`: UUIDv7 (sinh theo thời gian) đang phổ biến dần và
#: pattern cũ khoá cứng `[1-5]` để nó đi thẳng tới khách. Khoá theo danh sách
#: phiên bản là kiểu rò rỉ tự lặp lại — mỗi lần RFC thêm một phiên bản là một lần
#: rò mới — nên biên ở đây rộng bằng đúng không gian phiên bản đã cấp phát.
_BARE_UUID: Final[re.Pattern[str]] = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-7][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
#: Tên bảng/cột nội bộ lọt vào văn xuôi. Liệt kê TƯỜNG MINH thay vì bắt generic
#: `\w+_\w+`: tiếng Việt không dấu đầy cụm hai từ nối gạch dưới trong tên file,
#: mã xe, mã khuyến mại — một pattern generic sẽ ăn cả nội dung hợp lệ.
_INTERNAL_TOKEN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:"
    r"run_evidence|run_candidates|run_snapshots|review_queue|turn_outcomes|"
    r"conversation_sessions|conversation_messages|conversation_reassignments|"
    r"customer_advisor_assignments|session_offers|offer_adjustment_log|"
    r"out_of_scope_log|quote_audit_log|scoring_result|tco_estimates|"
    r"bottleneck_signals|agent_alembic_version|processed_client_turns"
    r")\b",
    re.IGNORECASE,
)
#: Hotline đã công bố. Danh sách do business sở hữu — số nào không nằm đây thì
#: hoặc là dữ liệu nội bộ rò ra, hoặc là mô hình bịa; cả hai đều không được tới
#: khách. Đối chiếu sau khi bỏ mọi dấu ngăn.
_HOTLINE_ALLOWLIST: Final[frozenset[str]] = frozenset({"1900232389"})
#: Ứng viên "số để gọi". CỐ Ý không bắt cụm 1900/1800 viết liền: `1800123456`
#: không phân biệt được với giá 1,8 tỷ, và xoá nhầm một mức giá là một câu trả
#: lời sai mà khách đọc được. Có dấu ngăn — hoặc có số 0 dẫn đầu, hoặc mã quốc
#: gia — thì ý định là số liên hệ, không phải số tiền.
_CONTACT_NUMBER: Final[re.Pattern[str]] = re.compile(
    r"(?<![\d.,])(?:"
    r"\+?84[\s.\-]?\d(?:[\s.\-]?\d){8,9}"
    r"|0\d(?:[\s.\-]?\d){8,9}"
    r"|1[89]00(?:[\s.\-]+\d){2,6}"
    r")(?![\d])"
)
#: Marker provenance/internal khác ngoài citation — mọi thứ dạng `[tên:giá trị]`
#: với tiền tố nội bộ đã biết. Liệt kê tường minh, không bắt generic `[x:y]`
#: để không nuốt nhầm nội dung hợp lệ của khách.
_PROVENANCE_MARKER: Final[re.Pattern[str]] = re.compile(
    r"\s*\[(?:run_id|session_id|draft|internal|provenance|trace_id|request_id|message_id|turn_id):[^\]]+\]",
    re.IGNORECASE,
)
#: "em" xưng hô KHÁCH (không phải bot tự xưng) → "Quý khách". Chỉ đổi khi "em"
#: đứng trước động từ chỉ ý định của khách; bot tự xưng ("em xin", "em sẽ",
#: "em chuyển", "em muốn giới thiệu"...) giữ nguyên.
_EM_ADDRESS: Final[re.Pattern[str]] = re.compile(
    r"\bem\b(?=\s+(?:"
    r"muốn(?!\s+(?:hỏi|biết|gửi|chuyển|nói|xác\s+nhận|đợi|kiểm\s+tra|tra|đối\s+chiếu|"
    r"xem\s+lại|chia\s+sẻ|báo|làm\s+rõ|hỏi\s+thêm|biết\s+thêm|giới\s+thiệu|hỗ\s+trợ|giúp|"
    r"cung\s+cấp|thông\s+báo|nhắc|lưu\s+ý|đề\s+xuất|gợi\s+ý|khuyên|nêu|trình\s+bày|giải\s+thích))"
    r"|thích|quan\s+tâm|phân\s+vân|cân\s+nhắc|mua|so\s+sánh|đăng\s+ký|trả\s+góp|đổi|bán|"
    r"hẹn|lái\s+thử|dùng\s+thử|đặt\s+cọc|thanh\s+toán|nộp|chọn|đi|đến|liên\s+hệ|tham\s+khảo"
    r"|tìm(?!\s+thấy)"
    r"|cần(?!\s+(?:hỏi|biết|thêm|gửi|chuyển|nói|xác\s+nhận|đợi|kiểm\s+tra|đối\s+chiếu))"
    r"|đang\s+(?:tìm|muốn|phân\s+vân|cân\s+nhắc|so\s+sánh|xem|quan\s+tâm|cần|tìm\s+hiểu|"
    r"tìm\s+mua|thích|chọn|đi|đến|hẹn|liên\s+hệ|tham\s+khảo|đăng\s+ký|trả\s+góp|đổi|bán|"
    r"lái\s+thử|dùng\s+thử|đặt\s+cọc|thanh\s+toán|nộp)"
    # `\b` ĐÓNG nhóm động từ — thiếu nó thì nhánh ngắn nuốt chữ dài hơn bắt đầu
    # bằng chính nó. Bug thật 2026-08-26: "cứ nói em điều mình đang băn khoăn"
    # thành "nói Quý khách điều mình đang băn khoăn", vì "điều" khớp nhánh "đi".
    # Cùng họ với bẫy Sếp tự bắt được: "k" viết tắt của "không" kèm đuôi tự do
    # nuốt mất "khoá chống trộm".
    r")\b)",
    re.IGNORECASE,
)
_QUY_KHACH_CASE: Final[re.Pattern[str]] = re.compile(r"\bquý khách\b", re.IGNORECASE)
#: Token số thập phân hữu hạn đứng độc lập (4+ chữ số phần nguyên, không dính
#: chữ số/dấu phân cách) — ứng viên cần định dạng đọc được. Số đã format
#: ("1.200.000.000"), model name (VF 8, e34), ngày tháng đều bị ranh giới chặn.
_DECIMAL_TOKEN: Final[re.Pattern[str]] = re.compile(r"(?<![\d.,])(-?\d{4,}(?:\.\d+)?)(?![\d.,])")
_YEAR_TOKEN: Final[re.Pattern[str]] = re.compile(r"\d{4}")
#: SĐT VN: mobile 0 + 9-10 chữ số, hotline 1900/1800 + 6 chữ số, quốc tế 84 + 9-10.
_PHONE_TOKEN: Final[re.Pattern[str]] = re.compile(r"(?:0\d{9,10}|1900\d{6}|1800\d{6}|84\d{9,10})")


def customer_safe_answer(internal_answer: str) -> str:
    """Remove implementation provenance and normalize spacing before delivery."""

    cleaned = _INTERNAL_CITATION.sub("", internal_answer)
    cleaned = _BARE_UUID.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    return cleaned.strip()


def normalize_customer_result(result: TurnResult) -> TurnResult:
    """Project mọi trường văn xuôi khách nhìn thấy về dạng an toàn, đọc được.

    Idempotent: áp hai lần cho kết quả y hệt, nên chain có thể project trước
    khi persist và lại ở biên công khai mà không sợ đổi nội dung.

    Chỉ đụng prose: `answer`, `pending_question`, `recommendations[].pitch`,
    `comparison.summary`. Mọi ID có cấu trúc (review_id, vehicle_id, citation,
    evidence, giá card, tên xe...) giữ nguyên.
    """

    answer = _normalize_prose(result.answer)
    pending_question = _normalize_prose(result.pending_question)
    recommendations = [replace(item, pitch=_normalize_prose(item.pitch)) for item in result.recommendations]
    comparison = result.comparison
    if comparison is not None and comparison.summary:
        comparison = replace(comparison, summary=_normalize_prose(comparison.summary))
    return replace(
        result,
        answer=answer,
        pending_question=pending_question,
        recommendations=recommendations,
        comparison=comparison,
    )


def _normalize_prose(text: str | None) -> str | None:
    """Scrub marker nội bộ, chuẩn hoá xưng hô, định dạng số đọc được."""

    if not text:
        return text
    cleaned = customer_safe_answer(text)
    cleaned = _PROVENANCE_MARKER.sub("", cleaned)
    cleaned = _INTERNAL_TOKEN.sub("", cleaned)
    # Số liên hệ dọn TRƯỚC bộ định dạng số: để sau thì chuỗi đã bị nhóm lại
    # ("0912.345.678") và không còn khớp pattern nào nữa.
    cleaned = _CONTACT_NUMBER.sub(_keep_only_allowlisted_hotline, cleaned)
    # Xưng hô thống nhất "anh/chị" (Sếp 2026-08-30). Bộ đổi "em <động từ>" chỉ
    # dành cho văn LLM gọi KHÁCH là "em".
    cleaned = _EM_ADDRESS.sub(lambda match: _em_address_replacement(match, cleaned), cleaned)
    cleaned = _QUY_KHACH_CASE.sub("anh/chị", cleaned)
    cleaned = _DECIMAL_TOKEN.sub(lambda match: _readable_decimal(match.group(1)), cleaned)
    return _tidy_spacing(cleaned)


def _em_address_replacement(match: re.Match[str], text: str) -> str:
    """"em" sau "để " là BOT tự xưng ("để em tìm showroom gần nhất") — giữ nguyên.

    Probe TD-1 (2026-08-30): câu lõi v2 "để em tìm showroom" bị đổi thành "để
    Quý khách tìm showroom" — sai nghĩa hẳn. Còn lại là văn gọi khách bằng "em".
    """

    if text[max(0, match.start() - 3) : match.start()].lower() == "để ":
        return match.group(0)
    return "anh/chị"


def _keep_only_allowlisted_hotline(match: re.Match[str]) -> str:
    """Giữ nguyên hotline đã công bố, xoá mọi số liên hệ khác."""

    token = match.group(0)
    digits = re.sub(r"\D", "", token)
    if digits.startswith("84"):
        digits = "0" + digits[2:]
    return token if digits in _HOTLINE_ALLOWLIST or token.replace(" ", "") in _HOTLINE_ALLOWLIST else ""


def _tidy_spacing(text: str) -> str:
    """Dọn khoảng trắng thừa mà các bước xoá ở trên để lại."""

    tidied = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    tidied = re.sub(r"[ \t]{2,}", " ", tidied)
    return tidied.strip()


def _readable_decimal(token: str) -> str:
    """Định dạng một token số thập phân hữu hạn theo quy ước VN.

    Nghìn tách bằng dấu chấm, phần thập phân bằng dấu phẩy. Năm (1900-2100) và
    số điện thoại không phải giá — giữ nguyên.
    """

    negative = token.startswith("-")
    unsigned = token[1:] if negative else token
    integer_part, _, fraction_part = unsigned.partition(".")
    if _YEAR_TOKEN.fullmatch(integer_part) and 1900 <= int(integer_part) <= 2100:
        return token
    if _PHONE_TOKEN.fullmatch(unsigned):
        return token
    grouped = f"{int(integer_part):,}".replace(",", ".")
    prefix = "-" if negative else ""
    if fraction_part:
        return f"{prefix}{grouped},{fraction_part}"
    return f"{prefix}{grouped}"


#: Mã kết thúc lượt mà khách ĐƯỢC phép thấy. Default-deny: mọi mã ngoài tập này
#: là chi tiết cài đặt (`GUARDRAIL_CONFIGURATION_ERROR` nói thẳng rằng guardrail
#: cấu hình sai) và bị gộp về `UNAVAILABLE`. Allowlist thay vì blocklist để mã
#: nội bộ MỚI mặc định kín — blocklist thì mỗi mã mới là một lần rò.
_PUBLIC_TERMINAL_REASONS: Final[frozenset[str]] = frozenset(
    {"ADVISOR_ACTIVE", "ADVISOR_HANDOFF", "CONTENT_BLOCKED", "OUT_OF_SCOPE", "UNAVAILABLE"}
)
#: Mã nội bộ có nghĩa tương đương một mã công khai — dịch thay vì gộp về
#: `UNAVAILABLE`, để client vẫn phân biệt được "đã chuyển người" với "hệ thống lỗi".
_TERMINAL_REASON_ALIASES: Final[dict[str, str]] = {
    "NO_CANDIDATE_ADVISOR_HANDOFF": "ADVISOR_HANDOFF",
    # Khách cần biết "đã chuyển người", không cần biết đó là do guardrail chặn
    # bản nháp: tên cơ chế nội bộ nằm trong mã này là thứ phải rụng ở cửa ra.
    "GUARDRAIL_FAILED_ADVISOR_HANDOFF": "ADVISOR_HANDOFF",
    "MISSING_DATA": "OUT_OF_SCOPE",
    # Lượt `Silent` khi TVV đang cầm phiên (`run_turn` nhánh Silent). Thiếu dòng
    # này nó gộp về `UNAVAILABLE`, client tưởng bot lỗi và chèn câu fallback
    # "Mình chưa hỗ trợ được..." chen giữa cuộc chat với TVV — lỗi Sếp thấy trên
    # prod 2026-08-31. FE đã im lặng sẵn khi nhận `ADVISOR_ACTIVE`.
    "PENDING_HANDOFF": "ADVISOR_ACTIVE",
}
_GENERIC_TERMINAL_REASON: Final[str] = "UNAVAILABLE"


def public_terminal_reason(reason: str | None) -> str | None:
    """Đổi mã nội bộ sang mã khách đọc được. Idempotent."""

    if reason is None:
        return None
    if reason in _PUBLIC_TERMINAL_REASONS:
        return reason
    return _TERMINAL_REASON_ALIASES.get(reason, _GENERIC_TERMINAL_REASON)


def project_public_result(result: TurnResult) -> TurnResult:
    """Phép chiếu ở BIÊN CÔNG KHAI — chặt hơn `normalize_customer_result`.

    Hai phép chiếu tách nhau vì chúng chạy ở hai thời điểm khác nhau và có hai
    ràng buộc trái ngược: `normalize_customer_result` chạy TRƯỚC khi persist nên
    phải giữ nguyên `terminal_reason` nội bộ cho outcome và cho việc điều tra
    sau; còn hàm này chạy khi trả cho client nên mã đó phải biến mất.

    Gộp hai việc vào một hàm sẽ ghi mã đã làm mờ xuống database — và mất luôn
    thứ duy nhất cho biết vì sao lượt đó hỏng.
    """

    projected = normalize_customer_result(result)
    reason = public_terminal_reason(projected.terminal_reason)
    if reason == projected.terminal_reason:
        return projected
    return replace(projected, terminal_reason=reason)
