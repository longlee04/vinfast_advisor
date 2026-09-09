"""Parse customer budget phrasing into VND without raising on user input.

Một KHOẢNG, không phải một con số. Trước đây module này chỉ trả một trần giá, lấy
bằng `max()` của mọi số tìm thấy trong câu — nên "300-500 triệu" và "500 triệu"
cho ra cùng một kết quả, còn "lớn hơn 500 triệu" thì bị đọc thành trần 500 triệu,
tức NGƯỢC HẲN ý khách. Hướng của câu (trên/dưới/khoảng/từ…đến) là thông tin, và
`max()` bỏ mất toàn bộ thông tin đó.

`parse_budget_vnd` vẫn còn và vẫn trả trần giá — nó là interface hai chỗ gọi đang
dùng — nhưng giờ chỉ là `parse_budget_range(...).max_vnd`, nên không tồn tại hai
bản parse có thể lệch nhau.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.number_word_parser import find_number_word_amounts, parse_number_words

# Sentinel "khách không đặt trần giá": phải đủ lớn để không lọc mất mẫu nào
# (xe đắt nhất trong catalog ~1,5 tỷ) NHƯNG phải nằm gọn trong
# `conversation_slots.slot_value_number` kiểu NUMERIC(14, 3) — cột này chặn ở
# absolute value < 10^11. Giá trị cũ đúng bằng 10^11 nên mọi lượt "bao nhiêu
# cũng được" đều vỡ ở INSERT với `NumericValueOutOfRangeError`, và handler
# `SQLAlchemyError` toàn cục biến nó thành 503 "auth_unavailable".
NO_BUDGET_LIMIT_VND = 10_000_000_000

_BILLION_UNITS = frozenset({"tỷ", "tỉ", "ty", "ti"})
_MILLION_UNITS = frozenset({"triệu", "trieu", "tr", "củ", "cu"})
_THOUSAND_UNITS = frozenset({"nghìn", "nghin", "k"})
#: "5 trăm", "5-6 trăm triệu": khách nói giá xe theo TRĂM TRIỆU. Trước đây "trăm"
#: không phải đơn vị nên "5-6 trăm triệu" đọc thành 5–6 TRIỆU (đo 2026-08-28:
#: "tầm 5 6 trăm" → "ngân sách khoảng 6 triệu"). Đặt trước "triệu" trong bảng
#: alternation nhờ sắp theo độ dài giảm dần.
_HUNDRED_MILLION_UNITS = frozenset({"trăm triệu", "tram trieu", "trăm", "tram"})
_UNIT_ALTERNATION = "|".join(
    sorted(_BILLION_UNITS | _MILLION_UNITS | _THOUSAND_UNITS | _HUNDRED_MILLION_UNITS, key=len, reverse=True)
)
_AMOUNT_TOKEN = re.compile(rf"(\d+(?:[.,]\d+)*)\s*({_UNIT_ALTERNATION})?", re.IGNORECASE)
_HALF_UNIT = re.compile(rf"\b(?:nửa|nua)\s*({_UNIT_ALTERNATION})\b", re.IGNORECASE)
_THOUSAND_GROUPED = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
NO_BUDGET_LIMIT_PATTERN = re.compile(
    r"(?:bao nhiêu cũng được|bao nhieu cung duoc|không giới hạn|khong gioi han|"
    r"thoải mái|thoai mai|không quan trọng|khong quan trong|"
    # Khách nói kiểu "tiền/tài chính không thành vấn đề" hay "giá nào cũng được"
    # rất phổ biến và mang đúng nghĩa không đặt trần. Thiếu các cụm này thì lượt
    # đó không trích được slot nào, agent hỏi lại đúng câu ngân sách vừa hỏi.
    r"(?:tiền|tien|tài chính|tai chinh|giá cả|gia ca|kinh phí|kinh phi|ngân sách|ngan sach)"
    r"\s*(?:thì|thi)?\s*(?:không|khong|ko)\s*(?:thành|thanh)?\s*(?:vấn đề|van de|quan trọng|quan trong)|"
    # Chiều NGƯỢC LẠI của cùng một ý: "KHÔNG quan tâm GIÁ" (phủ định đứng trước
    # danh từ tiền). Nhánh trên đòi danh từ đứng trước nên "không quan tâm giá"
    # — cách nói phổ biến nhất — rơi ra ngoài, và agent hỏi lại đúng câu ngân
    # sách mà khách vừa bảo đừng hỏi. Đo trên câu thật 2026-08-26.
    r"(?:không|khong|ko)\s*(?:cần|can)?\s*(?:quan tâm|quan tam|để ý|de y|đặt nặng|dat nang)"
    r"\s*(?:về|ve|đến|den|tới|toi)?\s*"
    r"(?:tiền|tien|tài chính|tai chinh|giá cả|gia ca|giá|gia|kinh phí|kinh phi|ngân sách|ngan sach)|"
    r"(?:giá|gia|tầm|tam|mức|muc|loại|loai)\s*nào\s*(?:cũng|cung)\s*(?:được|duoc|ok)|"
    r"(?:gia|tam|muc|loai)\s*nao\s*(?:cung)\s*(?:duoc|ok)|"
    r"(?:ngân sách|ngan sach)\s*(?:mở|mo)|"
    r"(?:không|khong|ko)\s*(?:lo|ngại|ngai)\s*(?:về|ve)?\s*(?:tiền|tien|giá|gia))",
    re.IGNORECASE,
)


#: [GIẢ ĐỊNH] "tầm/khoảng/cỡ X" là một ƯỚC LƯỢNG quanh X, và biên của nó là một
#: SỐ TIỀN CỐ ĐỊNH ±100 triệu, KHÔNG phải một tỉ lệ phần trăm.
#:
#: Trước đây biên là ±15%. Nó sai theo cách càng lên cao càng sai: "khoảng 900
#: triệu" thành 765–1.035 triệu, tức mở đáy xuống dưới cả VF 6, trong khi khách
#: nói câu đó đang nhắm đúng nhóm 898–920 triệu. Khách xác nhận bằng ví dụ thật:
#: "khoảng 900 triệu" phải ra VF 7 (920) và VF 8 (898) — đúng ±100 triệu.
#:
#: Cố định (không scale theo X) là có chủ đích: người mua nói "khoảng" là đang nói
#: "xê dịch trong tầm một trăm triệu", không phải "xê dịch 15% giá xe".
APPROX_BAND_VND: Final[Decimal] = Decimal(100_000_000)

#: [GIẢ ĐỊNH] ±100 triệu là biên của người mua Ô TÔ. Với xe máy điện (20–80 triệu)
#: nó vô nghĩa và có hại: "tầm 30 triệu" mà nới trần lên 130 triệu thì gợi ý lọt
#: cả những mẫu đắt gấp bốn lần mức khách nói. Dưới ngưỡng đó, biên quay về tỉ lệ.
#: Chỉ ảnh hưởng số tiền nhỏ hơn chính biên, nên mọi mức giá ô tô giữ đúng ±100
#: triệu như khách đã xác nhận.
_SMALL_AMOUNT_BAND_RATIO: Final[Decimal] = Decimal("0.20")

#: Dấu nối một KHOẢNG. `-` không cần khoảng trắng hai bên ("200-300", "200 -300").
_RANGE_SEPARATOR = re.compile(r"(?:-|–|—|~|=>|->|\bđến\b|\bden\b|\btới\b|\btoi\b)", re.IGNORECASE)
#: Chỉ có SÀN, không có trần: "trên 500", "lớn hơn 500", "từ 500 trở lên".
_LOWER_BOUND_ONLY = re.compile(
    r"(?:trên|tren|lớn hơn|lon hon|cao hơn|cao hon|nhiều hơn|nhieu hon|hơn|hon|"
    r"tối thiểu|toi thieu|ít nhất|it nhat|trở lên|tro len|từ trên|tu tren)",
    re.IGNORECASE,
)
#: "từ 900 triệu" TRẦN TRỤI — không có "đến/tới" nào theo sau, không có "trở lên".
#: Vẫn là một SÀN: khách nói "từ X" là "ít nhất X, trần bao nhiêu tính sau".
#:
#: Bug đã quan sát: câu này rơi xuống tận nhánh cuối và bị đọc thành TRẦN 900
#: triệu — ngược hẳn ý khách — nên "khoảng 900 triệu" và "từ 900 triệu" cùng cho
#: ra một trần 900 triệu, rồi xếp hạng thưởng xe rẻ đẩy VF 2/VF 3/VF 5 lên đầu cả
#: hai câu.
#:
#: Phải đứng ngay trước một CON SỐ, và phải là một từ trọn vẹn: `_LOWER_BOUND_ONLY`
#: không có ranh giới từ nên thêm "tu" vào đó sẽ khớp cả "tuần", "tuổi".
_BARE_FROM_LOWER_BOUND = re.compile(
    r"(?<![a-zà-ỹ0-9])(?:từ|tu)\s+\d",
    re.IGNORECASE,
)
#: Chỉ có TRẦN, không có sàn: "dưới 300", "nhỏ hơn 300", "tối đa 300".
_UPPER_BOUND_ONLY = re.compile(
    r"(?:dưới|duoi|nhỏ hơn|nho hon|thấp hơn|thap hon|ít hơn|it hon|bé hơn|be hon|"
    r"tối đa|toi da|không quá|khong qua|không hơn|khong hon|trở xuống|tro xuong|"
    r"trong vòng|trong vong)",
    re.IGNORECASE,
)
#: Ước lượng quanh một con số.
#:
#: "quãng/tầm" còn là từ chỉ QUÃNG ĐƯỜNG và TẦM CHẠY, nên hai cụm đó bị loại ra:
#: "quang duong 300km, ngan sach 1 ty 2" không phải một ước lượng quanh 1,2 tỷ.
_APPROXIMATE = re.compile(
    r"(?<![a-zà-ỹ0-9])"
    r"(?:tầm|tam|khoảng|khoang|cỡ|xấp xỉ|xap xi|chừng|chung|quãng|quang|~)"
    r"(?!\s*(?:đường|duong|chạy|chay|hoạt động|hoat dong))",
    re.IGNORECASE,
)

#: Từ ước lượng phải đứng NGAY TRƯỚC con số nó nói về, không phải ở đâu đó trong
#: câu. Cửa sổ đủ rộng cho "khoảng chừng", "tài chính khoảng", và đủ hẹp để một
#: mệnh đề khác không với tới được con số ngân sách.
_APPROX_CUE_WINDOW: Final[int] = 24


#: [GIẢ ĐỊNH] Biên "vẫn đáng gợi ý" quanh khoảng khách nêu. Một mẫu lệch trong biên
#: này thì nói rõ là lệch rồi vẫn đưa vào danh sách; lệch quá biên thì nhường chỗ
#: cho mẫu nằm trong khoảng — trừ khi không còn mẫu nào khác.
#:
#: Định nghĩa ở đây, cạnh chính khoảng ngân sách, vì cả xếp hạng (`domain/scoring`)
#: lẫn nhãn hiển thị (`domain/claim_policy`) đều phải dùng CÙNG một biên. Hai biên
#: lệch nhau sẽ đẻ ra thẻ xe bị loại khỏi danh sách nhưng vẫn mang nhãn "nhỉnh hơn
#: một chút", hoặc ngược lại.
BUDGET_TOLERANCE: Final[Decimal] = Decimal("0.20")


def within_budget_band(
    price_vnd: Decimal | None,
    budget_min_vnd: Decimal | None,
    budget_max_vnd: Decimal | None,
    *,
    tolerance: Decimal = BUDGET_TOLERANCE,
) -> bool:
    """Giá này còn đáng gợi ý cho khoảng ngân sách đã nêu không.

    Không có ngân sách, hoặc không có giá → coi là còn đáng gợi ý: thiếu dữ liệu
    không phải là lý do để giấu một mẫu xe khỏi khách.

    Sentinel "không đặt trần" không tạo ra biên trên nào.
    """

    if price_vnd is None:
        return True
    if budget_min_vnd is not None and budget_min_vnd > 0:
        if price_vnd < budget_min_vnd * (Decimal(1) - tolerance):
            return False
    # Trần là TUYỆT ĐỐI (Sếp 2026-08-26): "nếu người dùng cung cấp tài chính thì
    # đề xuất không được vượt quá tài chính".
    #
    # `tolerance` chỉ còn tác dụng ở phía SÀN bên trên. Nới ở phía trần nghĩa là
    # gợi ý một chiếc xe khách đã nói là ngoài tầm — và với dung sai 20% thì
    # "800 triệu" mở tới 960 triệu, đủ để cả VF 8 lọt vào.
    if (
        budget_max_vnd is not None
        and budget_max_vnd > 0
        and budget_max_vnd < NO_BUDGET_LIMIT_VND
        and price_vnd > budget_max_vnd
    ):
        return False
    return True


@dataclass(frozen=True, slots=True)
class BudgetRange:
    """Ngân sách khách nói, dưới dạng một khoảng.

    `min_vnd is None` — khách không nêu sàn. Khác `0`: `0` là "sàn bằng không",
    và không ai nói câu đó.

    `max_vnd` KHÔNG bao giờ là `None` khi câu có nêu ngân sách: câu không có trần
    ("lớn hơn 500 triệu") mang `NO_BUDGET_LIMIT_VND` — sentinel "không đặt trần"
    mà `conversation_slots` và `inquiry_form` đã hiểu từ trước. Dùng `None` ở đây
    sẽ trùng nghĩa với "khách chưa trả lời" và slot ngân sách bị hỏi lại.
    """

    min_vnd: int | None = None
    max_vnd: int | None = None
    #: Con số khách NÓI RA khi câu là một ước lượng ("khoảng 500 triệu"), giữ
    #: nguyên văn. `None` với mọi dạng câu khác — khoảng tự nêu và câu một biên
    #: đã mang sẵn lời khách trong `min_vnd`/`max_vnd`.
    #:
    #: Chỉ dùng để NHẮC LẠI cho khách, không bao giờ dùng để lọc: việc lọc vẫn
    #: theo `min_vnd`/`max_vnd` như trước.
    stated_vnd: int | None = None

    @property
    def is_empty(self) -> bool:
        return self.min_vnd is None and self.max_vnd is None

    @property
    def has_upper_limit(self) -> bool:
        """Có trần THẬT, không phải sentinel "bao nhiêu cũng được"."""

        return self.max_vnd is not None and self.max_vnd < NO_BUDGET_LIMIT_VND


#: Từ chỉ TIỀN, đủ để phân biệt "từ 400 đến 600 triệu" với "nhà em 4 người".
#: `parse_budget_range` một mình quá rộng cho việc đó: nó đọc mọi con số dưới 1.000
#: thành đơn vị triệu, nên "3 con mèo" cũng ra một ngân sách.
_MONEY_CUE = re.compile(
    rf"(?:ngân\s*sách|ngan\s*sach|tài\s*chính|tai\s*chinh|giá|gia|{_UNIT_ALTERNATION})",
    re.IGNORECASE,
)


def mentions_budget(user_message: str) -> bool:
    """Câu này có nói về TIỀN và nêu được một mức tiền cụ thể không."""

    if not user_message or not _MONEY_CUE.search(user_message):
        return False
    return not parse_budget_range(user_message).is_empty


#: Câu này có NÓI VỀ TIỀN không — hỏi trước khi tin bất kỳ con số ngân sách nào.
#:
#: `parse_budget_range` cố ý đọc lỏng: nó nhận cả số TRẦN không đơn vị vì được
#: gọi trên chuỗi ngân sách mà LLM đã tách sẵn ("500", "từ 300 đến 700"). Chạy
#: nó trên nguyên câu của khách thì mọi con số đều thành tiền:
#:
#:     "VF 8"      -> 8.000.000 đồng
#:     "xe 5 chỗ"  -> 5.000.000 đồng
#:
#: Vị từ này là bản đọc CHẶT dùng cho câu hỏi khác hẳn: "khách có đang nói về
#: tiền không". Đòi một ĐƠN VỊ tiền đi kèm, hoặc một con số đủ lớn để không thể
#: là gì khác (bảy chữ số trở lên), hoặc một cụm nói thẳng về ngân sách.
_APPROXIMATE_BARE_NUMBER: Final[re.Pattern[str]] = re.compile(
    r"\b(?:tầm|tam|khoảng|khoang|cỡ|co|chừng|chung|chắc|chac|độ|do|quãng|quang)\s*\d{2,4}(?![\d.,])"
    r"(?!\s*(?:km|cây|cay|chỗ|cho|người|nguoi|kw|kg|tuổi|tuoi|%))",
    re.IGNORECASE,
)
_MONEY_EVIDENCE: Final[re.Pattern[str]] = re.compile(
    # `(?![a-zà-ỹ])` chứ không phải `\b`: khách viết dính số ("tầm 1ty2", "500tr5")
    # nên sau đơn vị có thể là một CHỮ SỐ, mà `\b` giữa "y" và "2" thì không tồn
    # tại. Vẫn phải chặn CHỮ CÁI theo sau, nếu không "tr" nuốt luôn "trong".
    rf"\d\s*(?:{_UNIT_ALTERNATION})(?![a-zà-ỹ])"
    r"|\b\d{7,}\b"
    r"|\b(?:gia|giá|ngan sach|ngân sách|tien|tiền|dong|đồng|vnd|vnđ)\b",
    re.IGNORECASE,
)


def _spoken_amounts(folded: str) -> list[int]:
    """ "bảy trăm" → 700, "một tỷ hai" → 1.2e9: quét cửa sổ ≤ 4 chữ, lấy số đọc được."""

    found = list(find_number_word_amounts(folded))
    if found:
        return found
    tokens = folded.split()
    for start in range(len(tokens)):
        for end in range(min(len(tokens), start + 4), start, -1):
            value = parse_number_words(tokens[start:end])
            if value is not None and value >= 100:
                return [value]
    return []


def mentions_money(user_message: str) -> bool:
    """Câu của khách có bằng chứng nói về TIỀN không.

    Dùng để quyết định có được phép ghi đè ngân sách đang lưu hay không — xem
    `services/slot_extraction._drop_unsupported_slots`.
    """

    text = user_message or ""
    if _MONEY_EVIDENCE.search(text) is not None:
        return True
    # "tầm bảy trăm", "chắc 700 là căng" (golden của Ngọc, 2026-08-28): số viết
    # bằng chữ, hoặc số trần 2–4 chữ số đi sau một cue ước lượng, đều là tiền —
    # miễn không phải quãng đường / số chỗ / số người.
    if _spoken_amounts(build_canonical_text(text).folded):
        return True
    return _APPROXIMATE_BARE_NUMBER.search(text) is not None


def parse_budget_range(value: str | int | float | None) -> BudgetRange:
    """Đọc câu ngân sách thành một khoảng; câu không hiểu được → khoảng rỗng.

    Thứ tự xét là phần quan trọng nhất và không được đảo:

    1. KHOẢNG trước tiên ("từ 300 đến 700", "300-500"). Câu có hai đầu mút thì hai
       đầu mút đó là câu trả lời, kể cả khi câu còn kèm "khoảng" — "khoảng 200 đến
       300" là một khoảng rõ ràng, không phải ước lượng quanh 200.
    2. Rồi mới tới TRẦN/SÀN một phía ("dưới 300", "lớn hơn 500").
    3. Ước lượng ("tầm 400") xét CUỐI, vì mọi dạng trên đều chính xác hơn nó.
    """

    if value is None or isinstance(value, bool):
        return BudgetRange()
    if isinstance(value, (int, float)):
        ceiling = _numeric_ceiling(value)
        return BudgetRange(max_vnd=ceiling)

    text = " ".join(value.casefold().split())
    if not text:
        return BudgetRange()
    amounts = _amounts_with_spans(text)
    if not amounts:
        words = _spoken_amounts(build_canonical_text(text).folded)
        if not words:
            return BudgetRange()
        spoken = Decimal(words[0])
        spoken = spoken * Decimal(1_000_000) if spoken < 1_000 else spoken
        return _approximate_range(spoken) if _APPROXIMATE.search(text) else BudgetRange(max_vnd=int(spoken))

    pair = _range_pair(text, amounts)
    if pair is not None:
        low, high = pair
        return BudgetRange(min_vnd=int(low), max_vnd=int(high))

    amounts = [amount for amount in amounts if amount.value > 0]
    if not amounts:
        return BudgetRange()
    largest_amount = max(amounts, key=lambda amount: amount.value)
    largest = largest_amount.value
    if _UPPER_BOUND_ONLY.search(text):
        return BudgetRange(max_vnd=int(largest))
    if _LOWER_BOUND_ONLY.search(text) or _BARE_FROM_LOWER_BOUND.search(text):
        return BudgetRange(min_vnd=int(largest), max_vnd=NO_BUDGET_LIMIT_VND)
    if _APPROXIMATE.search(text[: largest_amount.span[0]][-_APPROX_CUE_WINDOW:]):
        return _approximate_range(largest)
    # Câu chỉ nêu một con số ("700 triệu") vẫn là TRẦN, đúng như trước: khách nói
    # một số trần trụi thì họ đang nói "đừng vượt quá đây".
    return BudgetRange(max_vnd=int(largest))


def _range_pair(text: str, amounts: list[_Amount]) -> tuple[Decimal, Decimal] | None:
    """Hai đầu mút đầu tiên có dấu nối khoảng nằm GIỮA chúng, hoặc `None`.

    Xét đúng đoạn văn bản giữa hai con số chứ không tìm dấu nối trong cả câu: một
    chữ "đến" ở mệnh đề khác ("đến showroom xem xe, ngân sách 500 triệu") không
    được biến câu một số thành một khoảng.

    Đơn vị lan từ đầu mút SAU sang đầu mút TRƯỚC, và chỉ trong phạm vi một khoảng:
    "1-2 tỷ" là 1 tỷ đến 2 tỷ, không phải 1 triệu đến 2 tỷ. Lan rộng hơn thế thì
    "7 người, tầm 1ty2" biến số 7 thành 7 tỷ và trần giá của câu đó sai hoàn toàn —
    đó là lý do việc lan đơn vị nằm ở đây chứ không nằm trong `_amounts_with_spans`.
    """

    for low, high in zip(amounts, amounts[1:], strict=False):
        between = text[low.span[1] : high.span[0]]
        adjacent_bare = low.multiplier is None and high.multiplier is not None and between.strip() == ""
        if _RANGE_SEPARATOR.search(between) is None and not adjacent_bare:
            continue
        low_value = low.value
        if low.multiplier is None and high.multiplier is not None:
            low_value = low.number * high.multiplier
        if low_value == high.value:
            continue
        return (min(low_value, high.value), max(low_value, high.value))
    return None


def _approximate_range(amount: Decimal) -> BudgetRange:
    """ "khoảng/tầm/cỡ X" → [X − 100 triệu, X + 100 triệu].

    Số tiền nhỏ hơn chính biên dùng biên theo tỉ lệ — xem `_SMALL_AMOUNT_BAND_RATIO`.
    """

    # Nới XUỐNG DƯỚI, KHÔNG nới lên trên (Sếp 2026-08-26): "con số khách cung cấp
    # là trần TUYỆT ĐỐI, đề xuất không được vượt".
    #
    # Bug thật, đọc từ `turn_traces` prod cùng ngày:
    #
    #     khách: "anh dự tính khoảng 800 triệu…"   → nới thành 700–900 triệu
    #     bot  : đề xuất VF 8 All New — 899 triệu, VƯỢT 12,4% mức khách nói
    #
    # Lọc SQL (`catalog_reader`) so thẳng `amount_vnd <= budget_max_vnd` và
    # không nới gì, nên trần bị nâng ở ĐÂY chính là nguồn duy nhất cho xe vượt
    # tầm lọt vào bản đề xuất.
    #
    # Biên dưới thì giữ: "khoảng 800" mà bỏ xe 720 triệu là giấu của khách một
    # mẫu rẻ hơn mà vẫn hợp — chiều đó không tiêu thêm đồng nào của họ.
    band = APPROX_BAND_VND if amount > APPROX_BAND_VND else amount * _SMALL_AMOUNT_BAND_RATIO
    return BudgetRange(
        min_vnd=_round_dong(amount - band),
        max_vnd=_round_dong(amount),
        # Giữ lại con số gốc: biên dưới là suy ra, còn đây mới là lời khách.
        stated_vnd=_round_dong(amount),
    )


def _round_dong(amount: Decimal) -> int:
    """Biên ước lượng, làm tròn về đồng nguyên."""

    return int(amount.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _numeric_ceiling(value: int | float) -> int | None:
    numeric = Decimal(str(value))
    if not numeric.is_finite() or numeric < 0 or numeric != numeric.to_integral_value():
        return None
    return int(numeric)


@dataclass(frozen=True, slots=True)
class _Amount:
    """Một số tiền đã đọc được, kèm đủ dữ liệu để lan đơn vị trong một khoảng."""

    value: Decimal
    span: tuple[int, int]
    #: Số thô như khách viết, trước khi nhân đơn vị.
    number: Decimal
    #: `None` khi khách không viết đơn vị sau số này ("300" trong "300-500 triệu").
    multiplier: Decimal | None


def _amounts_with_spans(text: str) -> list[_Amount]:
    """Mọi số tiền trong câu, kèm vị trí và đơn vị, theo thứ tự xuất hiện.

    Số trần trụi vẫn theo đúng quy ước cũ của `_bare_amount` (dưới 1.000 là đơn vị
    triệu). Việc lan đơn vị chỉ xảy ra khi hai số nằm hai đầu một khoảng — xem
    `_range_pair`.
    """

    amounts: list[_Amount] = []
    half = _HALF_UNIT.search(text)
    if half is not None:
        multiplier = _unit_multiplier(half.group(1))
        if multiplier is not None:
            amounts.append(
                _Amount(
                    value=multiplier / 2,
                    span=half.span(),
                    number=Decimal("0.5"),
                    multiplier=multiplier,
                )
            )

    tokens = [(_to_decimal(match.group(1)), match.group(2), match.span(1)) for match in _AMOUNT_TOKEN.finditer(text)]
    index = 0
    while index < len(tokens):
        number, unit, span = tokens[index]
        if number is None:
            index += 1
            continue
        multiplier = _unit_multiplier(unit)
        if multiplier is None:
            bare = _bare_amount(number)
            if bare is not None:
                amounts.append(_Amount(value=bare, span=span, number=number, multiplier=None))
            elif 0 < number < 10:
                # Một chữ số trần trụi tự nó vô nghĩa, nhưng là ĐẦU MÚT của một
                # khoảng ("5-6 trăm", "5 6 trăm"): giữ lại với value=0 để
                # `_range_pair` lan đơn vị từ đầu mút sau; `parse_budget_range`
                # loại nó nếu không ghép được cặp.
                amounts.append(_Amount(value=Decimal(0), span=span, number=number, multiplier=None))
            index += 1
            continue
        amount = number * multiplier
        if multiplier == Decimal(1_000_000_000) and index + 1 < len(tokens):
            next_number, next_unit, next_span = tokens[index + 1]
            if next_unit is None and next_number is not None and 0 < next_number < 10:
                amount += next_number * Decimal(100_000_000)
                span = (span[0], next_span[1])
                index += 1
        amounts.append(_Amount(value=amount, span=span, number=number, multiplier=multiplier))
        index += 1
    return amounts


def parse_budget_vnd(value: str | int | float | None) -> int | None:
    """Trần giá của câu ngân sách, hoặc `None` khi câu không nêu ngân sách nào.

    Giữ nguyên chữ ký và ý nghĩa cũ cho hai chỗ đang gọi (`slot_extraction`,
    `slot_salvage`), nhưng KHÔNG còn logic riêng: nó đọc đúng khoảng mà
    `parse_budget_range` đã hiểu. Hai bản parse song song là cách chắc chắn nhất
    để cùng một câu của khách bị hai luồng hiểu khác nhau.
    """

    return parse_budget_range(value).max_vnd


def _to_decimal(raw: str) -> Decimal | None:
    if _THOUSAND_GROUPED.fullmatch(raw):
        return Decimal(raw.replace(".", "").replace(",", ""))
    candidate = raw.replace(",", ".")
    if candidate.count(".") > 1:
        candidate = candidate.replace(".", "")
    try:
        value = Decimal(candidate)
    except InvalidOperation:
        return None
    return value if value.is_finite() and value >= 0 else None


def _unit_multiplier(unit: str | None) -> Decimal | None:
    if unit is None:
        return None
    lowered = unit.casefold()
    if lowered in _BILLION_UNITS:
        return Decimal(1_000_000_000)
    if lowered in _HUNDRED_MILLION_UNITS:
        return Decimal(100_000_000)
    if lowered in _MILLION_UNITS:
        return Decimal(1_000_000)
    if lowered in _THOUSAND_UNITS:
        return Decimal(1_000)
    return None


def _bare_amount(value: Decimal) -> Decimal | None:
    if value <= 0:
        return None
    # Một chữ số trần trụi ("2", "1") không đủ nói triệu hay tỷ — đo 2026-08-28:
    # khách gõ "2" sau câu hỏi ngân sách bị ghi "ngân sách khoảng 2 triệu". Trả
    # None để tầng trên hỏi lại đơn vị thay vì đoán sai rồi lặp mãi.
    if value < 10:
        return None
    if value < 1_000:
        return value * Decimal(1_000_000)
    if value >= 1_000_000:
        return value
    return None


__all__ = [
    "APPROX_BAND_VND",
    "BUDGET_TOLERANCE",
    "NO_BUDGET_LIMIT_PATTERN",
    "NO_BUDGET_LIMIT_VND",
    "BudgetRange",
    "parse_budget_range",
    "mentions_budget",
    "parse_budget_vnd",
    "within_budget_band",
]
