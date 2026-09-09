"""Bộ trích slot khớp MỜ — bản dự phòng cho A7-10 khi bộ chính bó tay.

Đây là chỗ tầng nhận diện bốn lớp thật sự giữ lời hứa "ưu tiên diễn giải theo
slot đang chờ". Cắm nó vào graph là vô ích: `chain._resume_pending_slot` chạy
TRƯỚC `graph.ainvoke` và kết thúc lượt ngay khi giải được, nên node
`recognize_intent` không bao giờ nhìn thấy một lượt đang trả lời câu hỏi slot.

Chỉ chạy khi bộ khớp chính xác đã thất bại (`PendingSlotServiceImpl._extract`).
Nhờ vậy độ chính xác của đường thường không đổi một chút nào: bot hỏi tỉnh, khách
gõ đúng "hà nội" thì `detect_province` bắt được như cũ, còn "hà nôi" hay "ha nol"
— trước đây rơi thẳng vào nhánh hỏi lại — giờ mới tới lượt bộ này.

Ngưỡng ở đây CAO hơn ngưỡng chung của Lớp 2: đã biết đang chờ slot nào thì không
gian đáp án hẹp lại còn vài chục giá trị, nên một khớp mờ ở đây có sức nặng hơn
nhiều — và đoán sai tỉnh nghĩa là báo sai phí trước bạ hàng chục triệu đồng.

THUẦN Python + `rapidfuzz` (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Final

from rapidfuzz import fuzz, process

from src.agents.domain.canonical_text import CanonicalText
from src.agents.domain.entity_catalog import EntityCatalog, EntityCategory
from src.agents.domain.fuzzy_match import all_of, match_entities
from src.agents.domain.pricing_intent import PROVINCES
from src.agents.domain.text_normalization import normalize, tokenize

#: Ngưỡng riêng, cao hơn `MatchThresholds` của Lớp 2 — xem docstring module.
#: [GIẢ ĐỊNH] 88 là phỏng đoán khởi đầu, cần tinh chỉnh bằng log thật.
SLOT_MATCH_THRESHOLD: Final[float] = 88.0

#: Alias ngắn hơn ngưỡng này chỉ khớp chính xác. Cùng lý do với
#: `domain/fuzzy_match.MIN_FUZZY_LENGTH`, nhưng ở đây hậu quả nặng hơn: "hn",
#: "ct", "kh" đều là mã tỉnh hai ký tự, và nới lỏng chúng thì mọi từ hai chữ cái
#: trong câu đều có thể biến thành một tỉnh.
MIN_SLOT_FUZZY_LENGTH: Final[int] = 4


def _windows(tokens: list[str], max_size: int) -> list[str]:
    found: list[str] = []
    for size in range(1, max_size + 1):
        found.extend(" ".join(tokens[start : start + size]) for start in range(len(tokens) - size + 1))
    return found


def fuzzy_lookup(
    user_message: str,
    aliases: Mapping[str, str],
    *,
    threshold: float = SLOT_MATCH_THRESHOLD,
) -> str | None:
    """Giá trị chuẩn khớp mờ nhất trong `aliases`, hoặc `None`.

    `aliases` ánh xạ cách viết → mã chuẩn (ví dụ `PROVINCES`). Khớp theo CỬA SỔ
    TOKEN chứ không theo chuỗi con, cùng lý do với `domain/fuzzy_match`.

    Trả `None` khi có TỪ HAI mã chuẩn cùng đạt điểm cao nhất: khách viết một
    chuỗi nằm giữa hai tỉnh thì hỏi lại là câu trả lời đúng, chọn bừa một tỉnh
    là bịa ra một con số phí trước bạ.
    """

    normalized_aliases = {normalized: code for alias, code in aliases.items() if (normalized := normalize(alias))}
    if not normalized_aliases:
        return None
    tokens = tokenize(user_message)
    if not tokens:
        return None
    max_alias_tokens = max(len(alias.split()) for alias in normalized_aliases)
    choices = list(normalized_aliases)

    best_score = 0.0
    best_codes: set[str] = set()
    for window in _windows(tokens, max_alias_tokens):
        result = process.extractOne(window, choices, scorer=fuzz.ratio)
        if result is None:
            continue
        matched, score, _index = result
        if len(matched) < MIN_SLOT_FUZZY_LENGTH or len(window) < MIN_SLOT_FUZZY_LENGTH:
            if matched != window:
                continue
            score = 100.0
        if score < threshold:
            continue
        code = normalized_aliases[matched]
        if score > best_score:
            best_score, best_codes = float(score), {code}
        elif score == best_score:
            best_codes.add(code)
    if len(best_codes) != 1:
        return None
    return next(iter(best_codes))


def fuzzy_detect_province(user_message: str, canonical: CanonicalText | None = None) -> str | None:
    """Mã tỉnh khách vừa nêu, chấp nhận gõ sai dấu hoặc sai một ký tự.

    `canonical` giữ cho khớp chữ ký `SlotExtractor` (pending_slot) — bộ mờ tự
    chuẩn hoá nội bộ bằng `normalize` (fuzzy match cần dạng bỏ dấu), không dùng
    canonical từ state.
    """

    del canonical
    return fuzzy_lookup(user_message, PROVINCES)


#: Bộ dự phòng theo tên slot, để `composition.py` nối vào `PendingSlotServiceImpl`.
#:
#: [GIẢ ĐỊNH] Chỉ có `province` ở đây vì `DEFAULT_EXTRACTORS` của A7-10 cũng chỉ
#: có `province` — không slot nào khác từng được dựng thành pending. Thêm slot
#: mới vào pending thì thêm một dòng ở đây, không phải sửa logic nào.
FUZZY_FALLBACK_EXTRACTORS: Final[dict[str, Callable[[str], object | None]]] = {
    "province": fuzzy_detect_province,
}


def compare_targets_extractor(
    catalog: EntityCatalog,
) -> Callable[[str, CanonicalText], object | None]:
    """[COMPARE_VEHICLES] Bộ trích cho slot `compare_targets`.

    Trả về DANH SÁCH tên xe chuẩn (theo thứ tự điểm khớp giảm dần), hoặc `None`
    khi câu không nêu được mẫu nào — đúng hợp đồng `SlotExtractor` của A7-10,
    nơi `None` nghĩa là "chưa điền được".

    Dùng thẳng `match_entities` của Lớp 2 chứ không viết một bộ khớp thứ hai: đó
    là cam kết "chuẩn hoá tên xe là trách nhiệm của Lớp 2" — mọi biến thể `vf3`,
    `vf 3`, `VF  3`, `vinfast vf3`, `evo200` đã được xử lý ở đó và có test riêng.
    Một bộ khớp riêng cho nhánh so sánh sẽ lệch khỏi Lớp 2 ngay lần sửa sau.

    Đây là bộ DỰ PHÒNG chứ không phải bộ chính (`fallback_extractors` ở
    `PendingSlotServiceImpl`) vì cùng lý do với `fuzzy_detect_province`: nó khớp
    MỜ, nên chỉ được chạy sau khi bộ khớp chính xác đã bó tay. Slot này chưa có
    bộ chính nào, nên trên thực tế nó chạy ngay — nhưng vị trí đúng vẫn là ở đây,
    để ngày có bộ chính thì thứ tự ưu tiên đã sẵn đúng.

    Nhận `catalog` qua tham số thay vì đọc `default_catalog()` tại chỗ:
    `composition.py` đã dựng danh mục MỘT LẦN lúc khởi động, và dựng lại nó ở mỗi
    tin nhắn sẽ cộng vài nghìn phép chuẩn hoá chuỗi vào đúng đường chạy mà p95 ≤
    6s đang đo (PRD 8.5).
    """

    def extract(user_message: str, canonical: CanonicalText | None = None) -> object | None:
        del canonical
        matches = match_entities(original_text=user_message, catalog=catalog)
        names = [item.canonical for item in all_of(matches, EntityCategory.VEHICLE)]
        return names or None

    return extract


__all__ = [
    "FUZZY_FALLBACK_EXTRACTORS",
    "compare_targets_extractor",
    "MIN_SLOT_FUZZY_LENGTH",
    "SLOT_MATCH_THRESHOLD",
    "fuzzy_detect_province",
    "fuzzy_lookup",
]


def test_drive_vehicle_extractor(
    catalog: EntityCatalog,
) -> Callable[[str, CanonicalText], object | None]:
    """[TEST_DRIVE] Bộ trích cho slot `test_drive_vehicle` — MỘT tên xe, hoặc `None`.

    Dùng lại `match_entities` của Lớp 2 vì đúng lý do đã ghi ở
    `compare_targets_extractor`: chuẩn hoá tên xe là việc của Lớp 2, và bộ khớp
    thứ hai sẽ lệch khỏi nó ngay lần sửa sau.

    Lấy tên khớp mạnh nhất chứ không trả cả danh sách: câu trả lời cho "muốn lái
    thử mẫu nào" là MỘT chiếc. Khách nêu hai tên thì lấy chiếc khớp mạnh nhất và
    bước đặt lịch sẽ xưng rõ tên đó, nên nếu đoán trượt thì khách thấy ngay ở
    câu kế tiếp — thay vì im lặng bỏ cả lượt.
    """

    def extract(user_message: str, canonical: CanonicalText | None = None) -> object | None:
        del canonical
        matches = match_entities(original_text=user_message, catalog=catalog)
        names = [item.canonical for item in all_of(matches, EntityCategory.VEHICLE)]
        return names[0] if names else None

    return extract
