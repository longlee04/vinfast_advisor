"""Khách xin đổi đề xuất bằng lối SO SÁNH ("nhỏ hơn", "cốp rộng hơn", "gầm cao hơn").

THUẦN Python — không import FastAPI/SQLAlchemy/LangGraph/LLM SDK.

**Vì sao phải đọc tất định.** Đo trên `turn_traces` prod 2026-08-26, ĐÚNG một câu
*"nếu anh muốn 1 chiếc nhỏ hơn thì sao"* xuất hiện hai lần ở hai phiên, và mô hình
trả `intents: []`, `slots_gained: {}` ở CẢ HAI — không hiểu gì. Khác nhau chỗ nhãn
phạm vi nó bịa ra: một lần `OUT_OF_SCOPE` (lượt chết, khách nhận *"câu này nằm
ngoài phần em phụ trách"*), một lần `IN_SCOPE` rồi đề xuất lại **VF 8** — chính
chiếc khách vừa chê là to. Một câu, hai kết cục, cả hai sai.

**Vì sao KHÔNG liệt kê trục** (Sếp 2026-08-27: *"khách có thể yêu cầu rất nhiều
trường hợp, chẳng hạn cốp rộng hơn, gầm cao hơn, đi lại tiện lợi hơn"*). Bản đầu
của file này liệt kê bốn trục cứng (nhỏ/to/xa/rẻ) — sai về nguyên tắc: mỗi lần
catalog thêm một tính năng là danh sách ấy lại thiếu, và thiếu trong im lặng.

Bản này tách làm hai tầng, và chỉ tầng dưới cần bảo trì:

1. **KHUNG** — thuần ngữ pháp: có `hơn`/`nhất` là có lời xin đổi. Khung không
   biết gì về ô tô nên không bao giờ lạc hậu, và nó bảo đảm điều quan trọng
   nhất: **lượt không bao giờ chết**, kể cả khi không hiểu khách muốn gì hơn.
2. **THUỘC TÍNH** — tra bằng CHÍNH các bảng từ vựng đã có và đang được dùng ở
   chiều ngược lại: `claim_policy._FEATURE_CLAIM_CUES` (28 mã tính năng) và
   `perceptual_traits._TRAIT_CUES` (4 cảm quan). Thêm một tính năng vào catalog
   là tự động thêm một lối nói so sánh, không phải sửa file này.

Nhờ vậy "cốp rộng hơn" → `TRAIT_LARGE_CARGO`, "gầm cao hơn" → `TRAIT_SUV_STANCE`,
"cửa sổ trời rộng hơn" → `PANORAMIC_ROOF` — cả ba đều chạy mà không có dòng nào
viết riêng cho chúng.

**Cầu nối tính từ trần** là phần duy nhất phải liệt kê, và nó nhỏ vì lý do ngôn
ngữ chứ không phải vì lười: hai bảng trên chép lời khách dạng CỤM (danh từ + tính
từ), nên chúng phủ hết "cốp rộng", "gầm cao", "chở nặng". Chỉ những tính từ ĐỨNG
MỘT MÌNH — "nhỏ hơn", "xa hơn" — mới không có cụm nào để khớp.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final

from src.agents.domain.canonical_text import CanonicalText
from src.agents.domain.claim_policy import feature_codes_mentioned
from src.agents.domain.perceptual_traits import trait_codes_mentioned

#: Khung so sánh. `nhất` đi cùng `hơn` vì "xe nào nhỏ nhất" cũng là lời xin đổi.
#:
#: Bắt buộc phải có một trong hai chữ này. Thiếu ràng buộc đó thì "anh cần 1
#: chiếc nhỏ gọn thôi" — lời khai nhu cầu ở lượt đầu — bị đọc thành lệnh đổi kết
#: quả, và cuộc tư vấn nhảy cóc qua bước khách còn chưa nói xong.
_COMPARATIVE_FRAME: Final[re.Pattern[str]] = re.compile(r"\b(?:hon|nhat)\b")

#: Số TỪ nhìn ngược lại trước chữ so sánh để tìm thuộc tính.
#:
#: Bốn là đủ cho cụm dài nhất trong hai bảng ("khoang hành lý rộng" = 4 từ) và
#: đủ ngắn để không vơ luôn một mệnh đề khác của cùng câu.
_ATTRIBUTE_WINDOW_WORDS: Final[int] = 4

#: Tính từ ĐỨNG MỘT MÌNH → mã đã có trong bảng chấm điểm.
#:
#: Chỉ nhận tính từ mà hai bảng từ vựng kia không thể phủ, và chỉ ánh xạ tới mã
#: CÓ THẬT, đã có xe mang cờ — mã không xe nào mang thì cộng 0 điểm trong im
#: lặng, đúng cái bẫy `HIGH_PAYLOAD` đã dính ở `claim_policy`.
#:
#: `cao` KHÔNG có mặt, cố ý: "giá cao hơn" là chuyện tiền, còn "gầm cao hơn" đã
#: được `_TRAIT_CUES` bắt trọn cụm. Cho `cao` vào đây là biến một câu về giá
#: thành một yêu cầu về gầm xe.
_BARE_ADJECTIVE_CODES: Final[dict[str, tuple[str, ...]]] = {
    "nho": ("COMPACT_SIZE",),
    "be": ("COMPACT_SIZE",),
    "gon": ("COMPACT_SIZE",),
    "to": ("7_SEATER",),
    "lon": ("7_SEATER",),
    "rong": ("7_SEATER",),
    "xa": ("HIGH_RANGE_BATTERY",),
    "manh": ("HIGH_RANGE_BATTERY",),
    "sang": ("PANORAMIC_ROOF", "LEATHER_SEATS"),
    "cao cap": ("PANORAMIC_ROOF", "LEATHER_SEATS"),
    "tien nghi": ("PANORAMIC_ROOF", "LEATHER_SEATS"),
}

#: Cụm nói về TIỀN. Tách riêng vì giá không phải một mã tính năng: gán cho nó một
#: mã trang bị là đặt vào miệng khách một yêu cầu họ không nêu.
_CHEAPER_CUES: Final[tuple[str, ...]] = (
    "re",
    "gia thap",
    "thap",
    "it tien",
    "tiet kiem",
    "kinh te",
)


@dataclass(frozen=True, slots=True)
class ComparativeRevision:
    """Lời xin đổi đề xuất, kèm những gì đọc được về hướng khách muốn."""

    #: Mã tính năng đẩy vào bảng chấm điểm. RỖNG là chuyện bình thường: khung
    #: nhận ra lời xin đổi kể cả khi thuộc tính không quy về mã nào.
    feature_codes: tuple[str, ...] = ()
    #: Mã cảm quan đọc được ("cốp rộng", "gầm cao"). Hiện CHƯA có cần chấm điểm
    #: nào theo trục số, nên chúng chỉ dùng để biết khách nói về cái gì — nhưng
    #: giữ lại ở đây để lượt sau nói lại đúng thứ khách vừa nêu.
    trait_codes: tuple[str, ...] = ()
    #: Khách muốn RẺ hơn. Không kèm mã nào — xem `_CHEAPER_CUES`.
    cheaper: bool = False

    @property
    def attribute_known(self) -> bool:
        """Có đọc được khách muốn hơn ở ĐIỂM NÀO không.

        `False` vẫn là một lời xin đổi hợp lệ ("đi lại tiện lợi hơn"): lượt phải
        chạy tiếp và loại những xe đã xem, chỉ là không có hướng để đẩy điểm.
        """

        return bool(self.feature_codes or self.trait_codes or self.cheaper)


def detect_comparative_revision(
    canonical: CanonicalText,
    *,
    vehicle_mentions: bool = False,
) -> ComparativeRevision | None:
    """Lời xin đổi đề xuất của lượt này, hoặc `None` khi câu không có khung so sánh.

    `vehicle_mentions=True` thì trả `None` LUÔN: câu có gọi tên xe là câu SO SÁNH
    hai mẫu ("VF 8 rộng hơn VF 7 không ạ"), không phải lời xin đổi đề xuất. Đọc
    nhầm chiều đó sẽ thay một bảng so sánh khách hỏi bằng một danh sách khách
    không hỏi.
    """

    if vehicle_mentions:
        return None
    folded = canonical.folded
    windows = _attribute_windows(folded)
    if not windows:
        return None

    features: list[str] = []
    traits: list[str] = []
    cheaper = False
    for window in windows:
        window_features = sorted(feature_codes_mentioned(window))
        window_traits = sorted(trait_codes_mentioned(window))
        # Cầu nối tính từ trần chỉ chạy khi hai bảng CỤM đã bó tay. Cụm cụ thể
        # hơn nên phải thắng: "cốp rộng hơn" là `TRAIT_LARGE_CARGO`, và để chữ
        # "rộng" chạy tiếp qua cầu nối sẽ gán thêm `7_SEATER` — biến một câu về
        # cốp thành một câu đòi thêm hàng ghế.
        if not window_features and not window_traits:
            for adjective, codes in _BARE_ADJECTIVE_CODES.items():
                if _mentions(window, adjective):
                    window_features.extend(codes)
        for code in window_features:
            if code not in features:
                features.append(code)
        for trait in window_traits:
            if trait not in traits:
                traits.append(trait)
        cheaper = cheaper or any(_mentions(window, cue) for cue in _CHEAPER_CUES)

    return ComparativeRevision(
        feature_codes=tuple(features),
        trait_codes=tuple(traits),
        cheaper=cheaper,
    )


def _attribute_windows(folded: str) -> tuple[str, ...]:
    """Các đoạn chữ đứng NGAY TRƯỚC mỗi chữ so sánh.

    Cắt cửa sổ thay vì tra cả câu là để giữ đúng quan hệ "thuộc tính nào hơn":
    câu "anh có xe cốp rộng rồi, giờ muốn chiếc rẻ hơn" tra cả câu sẽ ra CẢ cốp
    rộng — một yêu cầu khách vừa nói là đã có, không phải thứ họ đang tìm.
    """

    words = folded.split()
    windows: list[str] = []
    for index, word in enumerate(words):
        if not _COMPARATIVE_FRAME.fullmatch(word):
            continue
        start = max(0, index - _ATTRIBUTE_WINDOW_WORDS)
        window = " ".join(words[start:index])
        if window:
            windows.append(window)
        elif index == 0:
            # "hơn nữa" mở đầu câu: khung có mà không có thuộc tính nào phía
            # trước. Vẫn tính là một cửa sổ rỗng để lượt không bị bỏ qua.
            windows.append("")
    return tuple(windows)


def _mentions(window: str, phrase: str) -> bool:
    """Cụm xuất hiện như TỪ TRỌN VẸN trong cửa sổ.

    Khớp chuỗi con trần là bẫy đã dính nhiều lần ở kho này ("vinh" nằm trong
    "vinh long", "k" nuốt "khoá chống trộm"): ở đây "re" sẽ khớp bên trong "trẻ
    em" và biến một câu về ghế trẻ em thành một câu đòi giá rẻ.
    """

    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", window) is not None


__all__ = [
    "SEEN_LOWEST_PRICE_KEY",
    "ComparativeRevision",
    "budget_ceiling_below_seen",
    "detect_comparative_revision",
]


#: Khoá trong `ActiveTask.form` giữ GIÁ THẤP NHẤT của bản đề xuất vừa gửi.
#:
#: Đặt ở module này vì nó tồn tại cho đúng một việc: xử lý "rẻ hơn". `chain` ghi
#: nó ngay sau khi giao thẻ xe — chỗ duy nhất biết khách THẤY giá nào, vì
#: `pitches` còn cả phần dư đã bị cắt khỏi màn hình.
SEEN_LOWEST_PRICE_KEY: Final[str] = "seen_lowest_price_vnd"


def budget_ceiling_below_seen(form: Mapping[str, object] | None) -> Decimal | None:
    """Trần ngân sách mới cho lượt "rẻ hơn", hoặc `None` khi chưa có gì để so.

    **Ngay dưới một đồng**, không phải một tỉ lệ phần trăm nào: mọi con số kiểu
    "hạ 10%" đều là số bịa, còn "dưới chiếc rẻ nhất khách vừa xem" là đúng nghĩa
    đen của điều khách vừa nói. Trần cứng (Sếp 2026-08-26) làm nốt phần còn lại —
    nó đã chặn mọi xe trên trần, nên chiếc vừa bị chê đắt rơi ra theo đúng luật
    đang chạy chứ không cần một luật riêng.

    Hết xe dưới mức đó là một kết cục HỢP LỆ: khách nghe "không còn mẫu nào rẻ
    hơn" là một câu trả lời thật, còn đưa lại đúng mấy chiếc cũ thì không.
    """

    if not form:
        return None
    raw = form.get(SEEN_LOWEST_PRICE_KEY)
    if raw is None:
        return None
    try:
        lowest = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    return lowest - 1 if lowest > 1 else None
