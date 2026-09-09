"""Chuẩn hoá tiếng Việt cho tầng nhận diện ý định (Lớp 1 + Lớp 2).

Tách thành module riêng vì cả bốn lớp đều cần đúng MỘT định nghĩa "hai chuỗi
này là một": nếu Lớp 2 bỏ dấu theo một cách và Lớp 3 theo cách khác thì một
entity khớp được ở lớp này lại không khớp ở lớp kia, và lỗi đó không nhìn thấy
được từ log.

Bỏ dấu phải đi qua NFD rồi lọc dấu tổ hợp, KHÔNG dùng bảng ánh xạ tay: cùng một
chữ "ế" có hai cách mã hoá Unicode (một code point, hoặc "e" + hai dấu tổ hợp),
mà bàn phím tiếng Việt sinh ra cả hai. Bảng tay chỉ bắt được một dạng, nên
"vf5 màu ế" gõ từ hai máy khác nhau sẽ cho hai kết quả chuẩn hoá khác nhau.

`đ`/`Đ` là ngoại lệ bắt buộc xử lý riêng: nó là một CHỮ CÁI độc lập trong bảng
chữ cái tiếng Việt, không phải "d" kèm dấu, nên NFD không tách nó ra.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

#: Ký tự giữ lại sau khi bỏ dấu. Chữ và số giữ nguyên; mọi thứ khác thành
#: khoảng trắng — dấu câu không mang thông tin phân biệt entity, mà giữ lại thì
#: "vf5," và "vf5" thành hai token khác nhau ở bước fuzzy match.
_NON_WORD_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")

#: Dấu vết của dữ liệu có cấu trúc lọt ra chữ gửi khách: tên trường gán giá trị
#: (`slot=`, `feature_code=`), mã dạng `SNAKE_CASE`, và toán tử so sánh. LLM mà
#: để lọt mấy dấu này vào câu trả lời là nó đang chép nguyên văn một cấu trúc nội
#: bộ, không còn là một câu tiếng Việt tự nhiên.
RAW_STRUCTURED_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:\b(?:slot|feature_code|need_tag|source|evidence)\s*=|"
    r"[A-Za-z]+_[A-Za-z0-9_]+|>=|<=|==|!=)",
    re.IGNORECASE,
)

#: Bảng số đếm tiếng Việt → chữ số. Dùng để sinh alias "vf năm" cho "VF 5":
#: khách gõ tiếng Việt có dấu lẫn không dấu, và cả hai đều là cách viết hợp lệ
#: của cùng một mẫu xe. Chỉ tới 9 vì tên xe VinFast chỉ có một chữ số.
VIETNAMESE_DIGIT_WORDS: Final[dict[str, str]] = {
    "khong": "0",
    "mot": "1",
    "hai": "2",
    "ba": "3",
    "bon": "4",
    "tu": "4",
    "nam": "5",
    "lam": "5",
    "sau": "6",
    "bay": "7",
    "tam": "8",
    "chin": "9",
}


def strip_diacritics(text: str) -> str:
    """Bỏ toàn bộ dấu tiếng Việt, giữ nguyên chữ cái nền.

    "Thông tin xe" → "Thong tin xe". "Đà Nẵng" → "Da Nang".
    """

    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    # `đ` không phân rã dưới NFD — nó là chữ cái riêng, không phải d + dấu.
    return without_marks.replace("đ", "d").replace("Đ", "D")


def normalize(text: str) -> str:
    """Dạng so khớp chuẩn: không dấu, thường, chỉ chữ và số, một khoảng trắng.

    Đây là dạng DUY NHẤT được đưa vào `rapidfuzz`. Đưa chuỗi thô vào sẽ khiến
    "hà nội" và "ha noi" có edit-distance 2 trong khi chúng là cùng một chữ —
    tức thư viện đo đúng khoảng cách ký tự nhưng trả lời sai câu hỏi ta đang hỏi.
    """

    if not text:
        return ""
    folded = strip_diacritics(unicodedata.normalize("NFC", text)).casefold()
    return _NON_WORD_PATTERN.sub(" ", folded).strip()


def tokenize(text: str) -> list[str]:
    """Token của câu ở dạng đã chuẩn hoá."""

    normalized = normalize(text)
    return normalized.split() if normalized else []


def digits_from_words(text: str) -> str:
    """Đổi số đếm tiếng Việt đứng riêng thành chữ số, giữ nguyên phần còn lại.

    "vf nam" → "vf 5". Chỉ đổi token ĐỨNG RIÊNG, không đổi chuỗi con: "nam" nằm
    trong "nam gioi" và "chin" nằm trong "chinh sach", nên thay theo chuỗi con sẽ
    biến "chính sách pin" thành "9h sách pin".
    """

    tokens = tokenize(text)
    if not tokens:
        return ""
    return " ".join(VIETNAMESE_DIGIT_WORDS.get(token, token) for token in tokens)


def squash(text: str) -> str:
    """Dạng đã chuẩn hoá và bỏ hẳn khoảng trắng — dùng để so tên mẫu xe.

    Cùng quy ước với `adapters/catalog_reader._squash`: catalog ghi "VF 3" còn
    khách gõ "vf3", và dấu cách giữa dòng xe với số hiệu không phân biệt xe nào
    với xe nào.
    """

    return normalize(text).replace(" ", "")


def has_diacritics(text: str) -> bool:
    """Câu có dùng dấu tiếng Việt không."""

    composed = unicodedata.normalize("NFC", text or "")
    return strip_diacritics(composed) != composed


def contains_keyword(text: str, keyword: str) -> bool:
    """Từ khoá có xuất hiện trong câu không — CHỈ bỏ dấu khi câu không có dấu.

    Đây là điểm tinh tế nhất của cả module, và làm sai thì hỏng theo hướng khó
    thấy. Bỏ dấu vô điều kiện nghe có vẻ đúng, nhưng tiếng Việt có những cặp từ
    chỉ khác nhau ở dấu mà **đều là từ rất thông dụng**:

    - "chỗ" (ghế ngồi) ↔ "cho" (giới từ) — "giá bao nhiêu **cho** gia đình tôi"
      bị đọc thành câu hỏi số **chỗ** ngồi.
    - "giá" (tiền) ↔ "gia" (trong "gia đình") — "hợp với **gia** đình không" bị
      đọc thành câu hỏi **giá**.
    - "màu" ↔ "mau", "sạc" ↔ "sac", ...

    Nên quy tắc là: **khách gõ có dấu thì tin dấu họ gõ.** Người ta gõ tiếng
    Việt theo một trong hai kiểu nhất quán — có dấu hết, hoặc không dấu hết. Câu
    có dấu mà một từ không mang dấu thì đó là chủ ý, không phải gõ sót.

    - Câu **CÓ** dấu → khớp chặt, giữ nguyên dấu (đúng hành vi cũ của mọi bảng
      từ khoá trong hệ thống, nên không lượt nào đang chạy bị đổi kết quả).
    - Câu **KHÔNG** dấu → khớp trên dạng đã bỏ dấu, theo RANH GIỚI TỪ. Ranh giới
      là bắt buộc: bỏ dấu làm không gian từ hẹp lại nên chuỗi con trở nên nguy
      hiểm hơn hẳn ("o to" nằm trong "cho toi"). Cùng khuôn với
      `domain/catalog_browse._mentions` và `pricing_intent.detect_province`.
    """

    if not text or not keyword:
        return False
    if has_diacritics(text):
        return keyword.casefold() in " ".join(text.casefold().split())
    normalized_text = normalize(text)
    normalized_keyword = normalize(keyword)
    if not normalized_text or not normalized_keyword:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(normalized_keyword)}(?![a-z0-9])"
    return re.search(pattern, normalized_text) is not None


def changed_tokens(before: str, after: str) -> tuple[str, ...]:
    """Token có trong `after` mà không có trong `before`, so ở dạng chuẩn hoá.

    Dùng để đo Lớp 1 đã sửa những gì. So ở dạng CHUẨN HOÁ chứ không phải chuỗi
    thô: thêm dấu vào "thong tin" thành "thông tin" là sửa chính tả (hợp lệ),
    còn thêm hẳn một từ mới là suy luận thêm nội dung (bị cấm) — đếm trên chuỗi
    thô thì cả hai đều hiện ra là "đã đổi" và không phân biệt được.
    """

    before_tokens = set(tokenize(before))
    return tuple(token for token in tokenize(after) if token not in before_tokens)


def token_change_ratio(before: str, after: str) -> float:
    """Tỷ lệ token bị đổi, trong [0, 1]. Câu gốc rỗng → 0.0.

    Đây là thước đo của guard "rewrite không được viết lại cả câu": vượt ngưỡng
    nghĩa là mô hình đã sáng tác thêm chứ không còn sửa chính tả.
    """

    before_tokens = tokenize(before)
    if not before_tokens:
        return 0.0
    return len(changed_tokens(before, after)) / len(before_tokens)


__all__ = [
    "RAW_STRUCTURED_PATTERN",
    "VIETNAMESE_DIGIT_WORDS",
    "changed_tokens",
    "contains_keyword",
    "digits_from_words",
    "normalize",
    "squash",
    "strip_diacritics",
    "token_change_ratio",
    "tokenize",
]
