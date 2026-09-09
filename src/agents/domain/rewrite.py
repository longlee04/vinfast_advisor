"""[Lớp 1] Kết quả rewrite và các guard thuần — phần KHÔNG gọi LLM.

Việc gọi mô hình nằm ở `services/rewrite.py`. Ở đây chỉ có hai thứ, và cả hai
đều phải test được mà không cần LLM:

1. **Cổng quyết định có nên gọi LLM không.** `docs/vinfast-agent-mvp.md` §A4-2
   chốt ngân sách "lượt hỏi slot ≤ 1 lần gọi LLM" và có test spy canh đúng con
   số đó. Một bước rewrite gọi mô hình ở MỌI lượt sẽ đội mọi lượt lên gấp đôi và
   phá cả ngân sách lẫn p95 ≤ 6s (PRD 8.5). Nên câu đã sạch phải đi qua với 0
   lần gọi thêm, và việc phân loại "sạch/nhiễu" bắt buộc phải rẻ và tất định.

2. **Guard chặn mô hình sáng tác.** Yêu cầu của Lớp 1 là "chỉ sửa chính tả,
   KHÔNG suy luận thêm nội dung". Không thể tin prompt một mình giữ được cam kết
   đó — prompt là lời dặn, guard mới là ràng buộc. Đổi quá `MAX_TOKEN_CHANGE_RATIO`
   phần token nghĩa là mô hình đã viết một câu khác, không phải sửa câu này.

Câu gốc KHÔNG bao giờ bị ghi đè: `RewriteResult` giữ cả hai bản, và khi guard từ
chối thì `text_for_matching` trả về đúng câu khách đã viết.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from rapidfuzz import fuzz

from src.agents.domain.text_normalization import (
    changed_tokens,
    digits_from_words,
    normalize,
    tokenize,
)

#: Tỷ lệ token BỊA được phép có. Vượt ngưỡng → mô hình đã sáng tác, huỷ rewrite.
#:
#: Đo token BỊA chứ không phải token ĐỔI, và khác biệt đó quyết định guard này
#: có dùng được không. Một bản sửa chính tả nặng đổi gần hết token của câu:
#: "tho ti x vf năm" → "thông tin xe VF 5" đổi 4/5 token = 80%. Đếm token đổi thì
#: guard từ chối đúng cái ca mà cả tính năng này sinh ra để xử lý.
#:
#: Token BỊA là token không truy được về BẤT KỲ token nào của câu gốc: "thong"
#: truy về "tho", "xe" truy về "x", nhưng "hà nội" trong một câu không hề nhắc
#: tới địa điểm thì không truy về đâu cả — và đó mới đúng là "suy luận thêm nội
#: dung không có trong câu gốc".
#:
#: [GIẢ ĐỊNH] 50% là phỏng đoán khởi đầu, cần tinh chỉnh bằng log thật.
#:
#: Nới hơn con số trực giác vì một GIỚI HẠN THẬT của phép đo: mở rộng viết tắt
#: là việc Lớp 1 ĐƯỢC YÊU CẦU làm ("gd" → "gia đình"), nhưng khoảng cách ký tự
#: không phân biệt được nó với bịa — "gd" so với "gia" chỉ được 40 điểm. Siết
#: ngưỡng này sẽ chặn đúng nhóm ca mà tính năng sinh ra để xử lý.
#:
#: Rào chắn thật với việc bịa nội dung là `MAX_TOKEN_GROWTH` ngay dưới (cấu
#: trúc, không phải ký tự) cộng với ba lớp bảo vệ ngoài module này: confidence
#: sàn của mô hình, việc bản rewrite CHỈ đi vào `extract_slots` (guardrail A6-1
#: và audit A7-4 vẫn đọc câu gốc), và Lớp 2 vẫn phải khớp entity với catalog
#: thật. Xem `docs/docs_buildagent_long/rewiter/06_assumptions_and_risks.md`.
MAX_TOKEN_CHANGE_RATIO: Final[float] = 0.5

#: Điểm tối thiểu để coi một token của bản rewrite là "truy được" về câu gốc.
#: [GIẢ ĐỊNH] 60 đủ rộng cho các bản mở rộng thật ("x" → "xe" được 67, "tho" →
#: "thong" được 75) và đủ chặt để chặn từ mới hoàn toàn.
MIN_TOKEN_TRACE_SCORE: Final[float] = 60.0

#: Bản rewrite được phép dài hơn câu gốc bao nhiêu lần. Tách một từ dính
#: ("thongtinxe" → "thông tin xe") làm số token tăng thật, nên không thể cấm
#: tăng; nhưng gấp đôi số từ thì không còn là tách từ nữa.
MAX_TOKEN_GROWTH: Final[float] = 2.0

#: Dưới ngưỡng này thì chính mô hình cũng không chắc — dùng lại câu gốc.
MIN_REWRITE_CONFIDENCE: Final[float] = 0.7

#: Câu dài hơn ngưỡng này không rewrite: chi phí tăng theo độ dài, mà một tin
#: nhắn dài đã có đủ ngữ cảnh để các lớp sau bám vào.
MAX_REWRITE_TOKENS: Final[int] = 40

#: Token bị coi là "cụt" khi ngắn hơn ngưỡng này mà không giải thích được.
SHORT_TOKEN_LENGTH: Final[int] = 3

#: Tỷ lệ token không giải thích được đủ để coi cả câu là nhiễu.
NOISE_TOKEN_RATIO: Final[float] = 0.4

#: Hư từ tiếng Việt hay gặp trong câu chat. Có mặt ở đây nghĩa là "token này
#: bình thường", không phải dấu hiệu câu bị gõ hỏng.
#: [GIẢ ĐỊNH] Danh sách gom từ cách hỏi thường gặp, chưa phủ hết tiếng Việt đời
#: thường. Thiếu một từ chỉ khiến một câu sạch bị đưa đi rewrite (tốn một lần gọi
#: LLM, kết quả vẫn đúng); thừa một từ mới là bỏ sót câu cần sửa.
COMMON_WORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "ah",
        "ak",
        "anh",
        "chi",
        "em",
        "minh",
        "toi",
        "ban",
        "quy",
        "khach",
        "cho",
        "voi",
        "va",
        "hay",
        "hoac",
        "la",
        "co",
        "khong",
        "ko",
        "k",
        "chua",
        "cua",
        "o",
        "tai",
        "tu",
        "den",
        "ve",
        "theo",
        "nhu",
        "bang",
        "muon",
        "can",
        "tim",
        "xem",
        "hoi",
        "biet",
        "duoc",
        "the",
        "nao",
        "gi",
        "bao",
        "nhieu",
        "may",
        "sao",
        "vay",
        "ne",
        "nhe",
        "nha",
        "ma",
        "thi",
        "nay",
        "do",
        "kia",
        "day",
        "roi",
        "dang",
        "se",
        "da",
        "van",
        "con",
        "xe",
        "oto",
        "moto",
        "gia",
        "tien",
        "trieu",
        "ty",
        "km",
        "vnd",
        "mua",
        "ban",
        "tra",
        "gop",
        "lai",
        "di",
        "chay",
        "sac",
        "pin",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "0",
        # Chào hỏi/xã giao. Có mặt ở đây là BẮT BUỘC, không phải cho đầy đủ:
        # "chào em" chỉ có hai token, nên thiếu "chao" thì tỷ lệ chưa-giải-thích
        # là 1/2 và câu chào đầu tiên của MỌI cuộc hội thoại bị gắn là nhiễu.
        # `classify_scope` (A6-2) đã có nhãn `SOCIAL` xử lý đúng nhóm này rồi.
        "chao",
        "alo",
        "hello",
        "hi",
        "xin",
        "cam",
        "on",
        "tam",
        "biet",
        "oke",
        "ok",
        "vang",
        "dung",
        "sang",
        "trua",
        "chieu",
        "toi",
        "nay",
    }
)


@dataclass(frozen=True, slots=True)
class RewriteTrigger:
    """Kết luận của cổng "có nên gọi LLM rewrite không", kèm lý do đọc được."""

    should_attempt: bool
    reason: str
    noise_ratio: float = 0.0
    suspicious_tokens: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RewriteResult:
    """Câu gốc và câu đã sửa, đi SONG SONG xuống các lớp sau.

    `applied=False` nghĩa là có bản rewrite nhưng bị guard từ chối (hoặc chưa
    từng gọi mô hình). Khi đó `rewritten` vẫn được giữ lại để audit đọc được mô
    hình đã định viết gì, nhưng `text_for_matching` không dùng nó.
    """

    original: str
    rewritten: str = ""
    confidence: float = 0.0
    changed_tokens: tuple[str, ...] = ()
    applied: bool = False
    #: Vì sao không áp dụng: `clean`, `too_short`, `low_confidence`,
    #: `rewrote_too_much`, `invented_content`, `llm_unavailable`, ...
    reason: str = "not_attempted"
    #: Cổng Lớp 1 có coi câu này là gõ hỏng không. Lớp 4 dùng cờ này để CHỈ kích
    #: hoạt hai nhánh hỏi lại cho input thật sự nhiễu — xem `route_confidence`.
    input_looks_noisy: bool = False

    @property
    def text_for_matching(self) -> str:
        """Chuỗi mà Lớp 2/3 nên dùng làm bản 'đã sửa'.

        Không áp dụng được thì trả CÂU GỐC, không trả chuỗi rỗng: lớp sau luôn có
        một chuỗi hợp lệ để làm việc, nên không lớp nào phải tự xử lý ca rỗng.
        """

        return self.rewritten if self.applied else self.original

    @property
    def trust(self) -> float:
        """Độ tin cậy để Lớp 3 nhân vào confidence.

        Không rewrite (câu vốn đã sạch) là 1.0 — cao nhất, vì không có bước suy
        đoán nào chen vào giữa khách và hệ thống. Có rewrite thì trần là chính
        confidence của mô hình.
        """

        return 1.0 if not self.applied else self.confidence

    @classmethod
    def unchanged(cls, original: str, reason: str, *, input_looks_noisy: bool = False) -> RewriteResult:
        """Bản 'giữ nguyên câu gốc' kèm lý do."""

        return cls(original=original, reason=reason, input_looks_noisy=input_looks_noisy)


def rewrite_trigger(text: str, known_tokens: frozenset[str] = frozenset()) -> RewriteTrigger:
    """Câu này có đáng gọi LLM để sửa không — quyết định RULE-BASED, không LLM.

    `known_tokens` là tập token xuất hiện trong danh mục thực thể (tên xe, từ
    khoá thuộc tính, từ khoá intent). Token nào không nằm trong đó, cũng không
    phải hư từ, thì là token chưa giải thích được — và một câu gồm phần lớn token
    chưa giải thích được chính là định nghĩa của "gõ hỏng".

    Thiếu dấu KHÔNG phải tín hiệu nhiễu: mọi so khớp về sau đều chạy trên dạng đã
    bỏ dấu, nên "gia bao nhieu" và "giá bao nhiêu" là cùng một câu. Coi thiếu dấu
    là nhiễu sẽ đốt một lần gọi LLM cho phần lớn tin nhắn tiếng Việt gõ nhanh.
    """

    tokens = tokenize(text)
    if len(tokens) < 2:
        # Một token thì không có ngữ cảnh nào để mô hình bám vào mà sửa cho đúng;
        # đoán một từ đứng riêng chính là "suy luận thêm nội dung".
        return RewriteTrigger(False, "too_short")
    if len(tokens) > MAX_REWRITE_TOKENS:
        return RewriteTrigger(False, "too_long")

    explained = known_tokens | COMMON_WORDS
    unexplained = tuple(
        token
        for token in tokens
        # Token thuần số luôn được coi là giải thích được: "700" trong "700
        # triệu" không phải một từ gõ sai, và không có bản sửa chính tả nào cho
        # một con số. Bỏ luật này thì mọi câu trả lời về ngân sách hay quãng
        # đường đều bị gắn là nhiễu và bị đem đi rewrite vô ích.
        if not token.isdigit() and token not in explained
    )
    suspicious = tuple(token for token in unexplained if len(token) < SHORT_TOKEN_LENGTH)
    ratio = len(unexplained) / len(tokens)
    if suspicious:
        # Token cụt (một–hai ký tự) không giải thích được là dấu hiệu chắc chắn
        # nhất của gõ tắt/gõ sót: tiếng Việt không có nhiều từ như vậy.
        return RewriteTrigger(True, "truncated_tokens", ratio, suspicious)
    if ratio >= NOISE_TOKEN_RATIO:
        return RewriteTrigger(True, "unexplained_tokens", ratio, unexplained)
    return RewriteTrigger(False, "clean", ratio)


def invented_tokens(original: str, rewritten: str) -> tuple[str, ...]:
    """Token của bản rewrite không truy được về token nào của câu gốc.

    So sau khi đổi số đếm tiếng Việt thành chữ số: "năm" → "5" là một bản sửa
    hợp lệ (đúng thứ prompt Lớp 1 được yêu cầu làm cho tên xe), nhưng đo trên
    chuỗi thô thì "5" không giống "nam" chút nào và sẽ bị chấm là bịa.
    """

    source = digits_from_words(original).split()
    target = digits_from_words(rewritten).split()
    if not target:
        return ()
    if not source:
        return tuple(target)
    return tuple(token for token in target if max(fuzz.ratio(token, item) for item in source) < MIN_TOKEN_TRACE_SCORE)


def invented_token_ratio(original: str, rewritten: str) -> float:
    """Tỷ lệ token bịa trong bản rewrite, trong [0, 1]. Bản rỗng → 0.0."""

    target = digits_from_words(rewritten).split()
    if not target:
        return 0.0
    return len(invented_tokens(original, rewritten)) / len(target)


def evaluate_rewrite(
    *,
    original: str,
    rewritten: str,
    confidence: float,
    max_change_ratio: float = MAX_TOKEN_CHANGE_RATIO,
    min_confidence: float = MIN_REWRITE_CONFIDENCE,
    input_looks_noisy: bool = True,
) -> RewriteResult:
    """Áp guard lên bản rewrite mô hình vừa trả về.

    Bốn cửa, theo đúng thứ tự — cửa nào đóng thì dừng ở đó và dùng lại câu gốc:
    rewrite rỗng hoặc y hệt câu gốc → không có gì để áp dụng; confidence dưới
    ngưỡng → chính mô hình cũng không chắc; câu dài ra gấp bội → không còn là
    tách từ; quá nhiều token bịa → đã sáng tác thêm nội dung.
    """

    cleaned = " ".join((rewritten or "").split())
    if not cleaned or normalize(cleaned) == normalize(original):
        return RewriteResult(
            original=original,
            rewritten=cleaned,
            confidence=confidence,
            reason="no_change",
            input_looks_noisy=input_looks_noisy,
        )
    if confidence < min_confidence:
        return RewriteResult(
            original=original,
            rewritten=cleaned,
            confidence=confidence,
            changed_tokens=changed_tokens(original, cleaned),
            reason="low_confidence",
            input_looks_noisy=input_looks_noisy,
        )
    source_count = len(tokenize(original))
    target_count = len(tokenize(cleaned))
    if source_count and target_count > source_count * MAX_TOKEN_GROWTH:
        return RewriteResult(
            original=original,
            rewritten=cleaned,
            confidence=confidence,
            changed_tokens=changed_tokens(original, cleaned),
            reason="rewrote_too_much",
            input_looks_noisy=input_looks_noisy,
        )
    if invented_token_ratio(original, cleaned) > max_change_ratio:
        return RewriteResult(
            original=original,
            rewritten=cleaned,
            confidence=confidence,
            changed_tokens=changed_tokens(original, cleaned),
            reason="invented_content",
            input_looks_noisy=input_looks_noisy,
        )
    return RewriteResult(
        original=original,
        rewritten=cleaned,
        confidence=confidence,
        changed_tokens=changed_tokens(original, cleaned),
        applied=True,
        reason="applied",
        input_looks_noisy=input_looks_noisy,
    )


__all__ = [
    "COMMON_WORDS",
    "MAX_REWRITE_TOKENS",
    "MAX_TOKEN_CHANGE_RATIO",
    "MAX_TOKEN_GROWTH",
    "MIN_REWRITE_CONFIDENCE",
    "MIN_TOKEN_TRACE_SCORE",
    "NOISE_TOKEN_RATIO",
    "RewriteResult",
    "RewriteTrigger",
    "evaluate_rewrite",
    "invented_token_ratio",
    "invented_tokens",
    "rewrite_trigger",
]
