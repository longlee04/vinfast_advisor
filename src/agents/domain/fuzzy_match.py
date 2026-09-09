"""[Lớp 2] Khớp mờ câu của khách với danh mục thực thể tĩnh.

Bộ khớp hiện có (`adapters/catalog_reader.resolve_vehicle_names`) là khớp CHÍNH
XÁC sau khi bỏ khoảng trắng — "vf5" ra "VF 5", nhưng "vf 5" gõ thiếu một ký tự
thì không ra gì. Module này lấp đúng khoảng đó, và CHỈ khoảng đó: nó trả về ứng
viên kèm điểm, không tự ý quyết định danh tính xe.

Hai quy tắc an toàn, cả hai đều để giữ cam kết "không suy đoán danh tính xe"
(A4-1) chứ không phải để tối ưu tốc độ:

1. **Alias ngắn dưới `MIN_FUZZY_LENGTH` ký tự chỉ khớp CHÍNH XÁC.** Với chuỗi ba
   ký tự, một thao tác sửa đã là một phần ba chuỗi, nên mọi ngưỡng phần trăm đều
   vô nghĩa: "mua" sẽ khớp "màu", "chi" sẽ khớp "cho". Đây là nhóm alias đông
   nhất trong bảng thuộc tính, nên nới nó ra là mở cửa cho hàng loạt khớp sai.
2. **Khớp theo CỬA SỔ TOKEN, không phải theo chuỗi con.** Một alias hai từ được
   so với đúng các cụm hai từ trong câu. So chuỗi con sẽ cho "o to" khớp vào
   "cho toi" — đúng con bug mà `domain/catalog_browse._mentions` đã phải xử lý
   bằng ranh giới từ.

THUẦN Python + `rapidfuzz` (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from rapidfuzz import fuzz, process

from src.agents.domain.entity_catalog import EntityAlias, EntityCatalog, EntityCategory
from src.agents.domain.text_normalization import tokenize

#: Alias ngắn hơn ngưỡng này chỉ chấp nhận khớp tuyệt đối. Xem quy tắc 1 ở docstring.
MIN_FUZZY_LENGTH: Final[int] = 4

#: Trần độ dài cửa sổ. Danh mục hiện tại có alias dài nhất ~4 từ; chặn trên để
#: một tin nhắn dài bất thường không biến bước này thành O(n²) trên đường chạy thật.
MAX_WINDOW_TOKENS: Final[int] = 5

SourceLabel = Literal["original", "rewritten"]


#: [GIẢ ĐỊNH] Ba số này là phỏng đoán khởi đầu, cùng tinh thần với
#: `domain/quote_risk.py`: phải tinh chỉnh bằng log hội thoại thật trước khi coi
#: là chốt. Chúng được đọc từ biến môi trường ở `services/nlu_pipeline.py`.
#:
#: Hằng số MODULE chứ không chỉ là default của dataclass — xem lý do ở
#: `domain/nlu_confidence.DEFAULT_AUTO_THRESHOLD` (bẫy `slots=True`).
#:
#: Alias một token (tên xe viết liền, từ khoá đơn).
DEFAULT_SINGLE_TOKEN_SCORE: Final[float] = 85.0
#: Alias nhiều token — nới hơn vì cụm dài chịu được nhiều lỗi gõ hơn mà vẫn
#: không mơ hồ: một cụm bốn từ sai hai ký tự vẫn chỉ có thể là chính nó.
DEFAULT_MULTI_TOKEN_SCORE: Final[float] = 80.0
#: Sàn "ứng viên yếu": không được coi là đã khớp, chỉ dùng làm chứng cứ phụ để
#: Lớp 3 hạ confidence thay vì im lặng bỏ qua.
DEFAULT_WEAK_FLOOR: Final[float] = 70.0


@dataclass(frozen=True, slots=True)
class MatchThresholds:
    """Ngưỡng chấp nhận một khớp mờ, thang 0–100 của `rapidfuzz`."""

    single_token: float = DEFAULT_SINGLE_TOKEN_SCORE
    multi_token: float = DEFAULT_MULTI_TOKEN_SCORE
    weak_floor: float = DEFAULT_WEAK_FLOOR

    def accepted_for(self, token_count: int) -> float:
        return self.single_token if token_count <= 1 else self.multi_token


@dataclass(frozen=True, slots=True)
class EntityMatch:
    """Một thực thể Lớp 2 nhận ra, kèm bằng chứng để lớp sau kiểm lại được."""

    category: EntityCategory
    #: Giá trị chuẩn: tên xe như catalog ghi, hoặc `VehicleAttribute`/`Intent`.
    canonical: str
    #: Alias đã khớp, dạng chuẩn hoá.
    matched_alias: str
    #: Điểm `rapidfuzz`, thang 0–100.
    score: float
    #: Cụm từ trong câu khách đã viết — mọi ký tự đều lấy từ input, không bịa.
    source_span: str
    #: Khớp trên câu gốc hay câu đã rewrite. Cần cho audit: một entity chỉ khớp
    #: được sau khi rewrite thì độ tin cậy của nó phụ thuộc độ tin cậy của Lớp 1.
    matched_on: SourceLabel
    #: `True` khi điểm nằm giữa `weak_floor` và ngưỡng chấp nhận.
    is_weak: bool = False


def _windows(tokens: Sequence[str], size: int) -> list[str]:
    """Mọi cụm `size` token liên tiếp, đã nối lại thành chuỗi chuẩn hoá."""

    if size <= 0 or size > len(tokens):
        return []
    return [" ".join(tokens[start : start + size]) for start in range(len(tokens) - size + 1)]


def _best_for_aliases(windows: Sequence[str], aliases: Sequence[EntityAlias]) -> list[tuple[EntityAlias, str, float]]:
    """Với mỗi cửa sổ, tìm alias giống nhất trong nhóm cùng độ dài token."""

    if not windows or not aliases:
        return []
    choices = [alias.alias for alias in aliases]
    found: list[tuple[EntityAlias, str, float]] = []
    for window in windows:
        result = process.extractOne(window, choices, scorer=fuzz.ratio)
        if result is None:
            continue
        _matched, score, index = result
        found.append((aliases[index], window, float(score)))
    return found


def _short_tokens_match(alias: str, window: str) -> bool:
    """Mọi token NGẮN của alias phải khớp tuyệt đối, đúng vị trí.

    Đây là quy tắc 1 áp ở mức token thay vì mức cả chuỗi, và nó cần thiết vì
    điểm phần trăm tính trên cả cụm che mất lỗi nằm trong một từ ngắn: "cac xe"
    so với "can xe" được 83 điểm — đủ qua ngưỡng cụm nhiều từ — trong khi "cac"
    và "can" là hai từ khác hẳn nhau. Đo trên cả cụm thì một ký tự sai trong sáu
    ký tự trông như nhiễu nhỏ; đo trên đúng từ chứa nó thì đó là một phần ba từ.

    Hệ quả có chủ đích: "vf nem" KHÔNG còn khớp "vf nam". Đó là chiều đúng —
    A4-1 cấm suy đoán danh tính xe, và một ký tự sai giữa "năm" với "nem" không
    đủ để khẳng định khách muốn VF 5. Ca đó thuộc về Lớp 1: sửa chính tả xong
    thì "VF 5" khớp tuyệt đối.
    """

    alias_tokens, window_tokens = alias.split(), window.split()
    if len(alias_tokens) != len(window_tokens):
        return False
    return all(
        left == right for left, right in zip(alias_tokens, window_tokens, strict=True) if len(left) < MIN_FUZZY_LENGTH
    )


def _passes(alias: EntityAlias, window: str, score: float, thresholds: MatchThresholds) -> bool:
    """Khớp này có được chấp nhận không (chưa xét nhánh 'ứng viên yếu')."""

    if len(alias.alias) < MIN_FUZZY_LENGTH or len(window) < MIN_FUZZY_LENGTH:
        # Quy tắc 1: chuỗi quá ngắn thì phần trăm giống nhau không còn ý nghĩa.
        return alias.alias == window
    if score < thresholds.accepted_for(alias.token_count):
        return False
    return alias.token_count <= 1 or _short_tokens_match(alias.alias, window)


def _scan(text: str, catalog: EntityCatalog, thresholds: MatchThresholds, source: SourceLabel) -> list[EntityMatch]:
    """Quét một chuỗi, trả mọi khớp đạt ít nhất `weak_floor`."""

    tokens = tokenize(text)
    if not tokens:
        return []
    by_size: dict[int, list[EntityAlias]] = {}
    for alias in catalog.aliases:
        by_size.setdefault(alias.token_count, []).append(alias)

    matches: list[EntityMatch] = []
    for size, aliases in by_size.items():
        if size > MAX_WINDOW_TOKENS:
            continue
        for alias, window, score in _best_for_aliases(_windows(tokens, size), aliases):
            accepted = _passes(alias, window, score, thresholds)
            if not accepted and score < thresholds.weak_floor:
                continue
            if not accepted and len(alias.alias) < MIN_FUZZY_LENGTH:
                # Alias ngắn không có nhánh "ứng viên yếu": nó vốn đã chỉ được
                # khớp tuyệt đối, cho nó vào diện yếu là mở lại đúng cửa vừa đóng.
                continue
            matches.append(
                EntityMatch(
                    category=alias.category,
                    canonical=alias.canonical,
                    matched_alias=alias.alias,
                    score=score,
                    source_span=window,
                    matched_on=source,
                    is_weak=not accepted,
                )
            )
    return matches


def match_entities(
    *,
    original_text: str,
    rewritten_text: str = "",
    catalog: EntityCatalog,
    thresholds: MatchThresholds | None = None,
) -> tuple[EntityMatch, ...]:
    """Khớp CẢ câu gốc lẫn câu đã rewrite, giữ bản tốt nhất cho mỗi thực thể.

    Quét cả hai là có chủ đích, không phải quét thừa: rewrite có thể sửa đúng
    ("tho ti" → "thông tin") nhưng cũng có thể làm hỏng một tên xe mà câu gốc
    viết đúng. Giữ điểm cao nhất giữa hai đường nghĩa là Lớp 1 chỉ có thể GIÚP
    Lớp 2, không bao giờ làm nó tệ đi.

    Câu gốc được ưu tiên khi hoà điểm: nó là thứ khách thật sự đã viết.
    """

    limits = thresholds or MatchThresholds()
    found = _scan(original_text, catalog, limits, "original")
    if rewritten_text and rewritten_text != original_text:
        found.extend(_scan(rewritten_text, catalog, limits, "rewritten"))

    best: dict[tuple[EntityCategory, str], EntityMatch] = {}
    for match in found:
        key = (match.category, match.canonical)
        current = best.get(key)
        if current is None or match.score > current.score:
            best[key] = match
    return tuple(sorted(best.values(), key=lambda item: (-item.score, item.canonical)))


def accepted_only(matches: Sequence[EntityMatch]) -> tuple[EntityMatch, ...]:
    """Bỏ các ứng viên yếu — dùng khi cần danh sách entity để hành động."""

    return tuple(match for match in matches if not match.is_weak)


def all_of(matches: Sequence[EntityMatch], category: EntityCategory) -> tuple[EntityMatch, ...]:
    """MỌI khớp mạnh của một loại, theo điểm giảm dần. Bỏ qua ứng viên yếu.

    `best_of` trả một khớp vì phần lớn nhánh chỉ hỏi "khách nhắc xe nào". Nhánh
    so sánh hỏi một câu khác hẳn — "khách nhắc NHỮNG xe nào" — và trả lời câu đó
    bằng `best_of` là luôn so sánh một xe với chính nó.
    """

    return tuple(
        sorted(
            (match for match in matches if match.category is category and not match.is_weak),
            key=lambda item: -item.score,
        )
    )


def best_of(matches: Sequence[EntityMatch], category: EntityCategory) -> EntityMatch | None:
    """Khớp mạnh nhất của một loại, hoặc `None`. Bỏ qua ứng viên yếu."""

    candidates = [match for match in matches if match.category is category and not match.is_weak]
    return max(candidates, key=lambda item: item.score, default=None)


__all__ = [
    "DEFAULT_MULTI_TOKEN_SCORE",
    "DEFAULT_SINGLE_TOKEN_SCORE",
    "DEFAULT_WEAK_FLOOR",
    "MAX_WINDOW_TOKENS",
    "MIN_FUZZY_LENGTH",
    "EntityMatch",
    "MatchThresholds",
    "accepted_only",
    "all_of",
    "best_of",
    "match_entities",
]
