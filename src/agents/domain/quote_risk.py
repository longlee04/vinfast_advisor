"""[A7-4] Chính sách giao nội dung theo rủi ro đầu ra, không theo công nghệ tạo nó.

Luồng cũ chặn mọi lượt chạm database để chờ tư vấn viên duyệt. Phần lớn lượt đó
là đọc giá niêm yết/thông số công khai — không mang rủi ro, nhưng vẫn bắt khách
chờ người. Module này thay điều kiện "có chạm DB không" bằng "nội dung gửi khách
có phải một BÁO GIÁ RỦI RO không".

Các điều kiện thương mại bắt buộc dừng lại chờ người (đủ 1 là chặn):
1. cá nhân hoá — giá điều chỉnh riêng theo hồ sơ khách, không phải giá niêm yết;
2. thương lượng — khách mặc cả, agent phản hồi mức khác bảng giá;
3. ưu đãi ngoài chính sách chuẩn — khuyến mãi/quà tặng ngoài danh sách đã duyệt;
4. cam kết tài chính — giá cuối, điều khoản thanh toán, bảo hành mở rộng;
5. độ tin cậy dưới ngưỡng với báo giá catalog.

Recommendation/comparison là một nhánh riêng: câu chữ có thể do LLM viết nhưng
được đi thẳng khi chỉ diễn đạt từ snapshot tin cậy và đã qua guardrail. Việc
"có dùng LLM" không còn là cờ rủi ro; provenance và verification mới là cờ.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK. Quyết định
là RULE-BASED — không gọi LLM ở bước quyết định, vì một quyết định an toàn không
được phụ thuộc vào thứ có thể bịa.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, ValidationError

from src.agents.domain.canonical_text import (
    CanonicalText,
    MatchTier,
    compile_keyword_variants,
    match_tier,
)

# ── Tham số chính sách (config, KHÔNG phải hằng số nghiệp vụ bất biến) ─────────
# [GIẢ ĐỊNH] Cả ba số dưới đây là phỏng đoán khởi đầu, PHẢI tinh chỉnh bằng số
# liệu shadow-mode (mục 5 của prompt A7-4) trước khi coi là chốt.
CONFIDENCE_THRESHOLD: Final[float] = 0.85
# Dải cận ngưỡng `[THRESHOLD - MARGIN, THRESHOLD)`: vẫn vào HITL, nhưng log riêng
# để sau này biết hạ ngưỡng xuống bao nhiêu thì an toàn.
NEAR_THRESHOLD_MARGIN: Final[float] = 0.10
# Tỷ lệ case auto-approve được gắn cờ cho người review định kỳ (log thì 100%).
AUDIT_SAMPLE_RATE: Final[float] = 0.10

# Bảng ưu đãi đã duyệt. Hằng số này là MẶC ĐỊNH KHI KHÔNG CẤU HÌNH, không phải
# nơi khai báo danh sách — nguồn sự thật là biến môi trường
# `QUOTE_STANDARD_PROMOTIONS` (chuỗi tên chương trình, ngăn bằng dấu phẩy), đọc ở
# `services/quote_gate.QuoteGateConfig.from_env` và nối vào cổng tại
# `composition.py`. CHỦ SỞ HỮU danh sách: phòng kinh doanh.
#
# Đừng đổ tên chương trình vào đây. Làm vậy dựng một nguồn sự thật thứ hai, và nó
# thắng im lặng ở mọi đường không đi qua `from_env` — gồm cả test và script.
#
# RỖNG nghĩa là mọi lời nhắc tới khuyến mãi bị coi là "ngoài chính sách chuẩn" →
# chặn. Đó là chiều an toàn: thà chặn nhầm một ưu đãi hợp lệ còn hơn để agent tự
# hứa một ưu đãi không tồn tại.
STANDARD_PROMOTIONS: Final[frozenset[str]] = frozenset()


class QuoteRiskTier(StrEnum):
    """Risk tier retained in audit storage for each delivery decision."""

    #: Không phải báo giá (tra thông số, tồn kho, so sánh xe) — không áp chính
    #: sách 5 điều kiện, đi thẳng như Tier tự động.
    NON_QUOTE = "NON_QUOTE"
    #: Báo giá sinh deterministic từ catalog, mọi cờ rủi ro tắt → tự động.
    DETERMINISTIC_AUTO = "DETERMINISTIC_AUTO"
    #: LLM chỉ diễn đạt từ snapshot/evidence đã được guardrail xác minh. Nội
    #: dung đi thẳng tới khách nhưng vẫn được audit và lấy mẫu hậu kiểm.
    EVIDENCE_BACKED_AUTO = "EVIDENCE_BACKED_AUTO"
    #: Nội dung đã có nhưng chưa đủ điều kiện tự động → chờ duyệt đồng bộ.
    SYNC_HITL = "SYNC_HITL"
    #: Khách đang yêu cầu một quyết định thương mại của con người, không phải
    #: yêu cầu duyệt câu chữ mà bot đã soạn.
    ADVISOR_HANDOFF = "ADVISOR_HANDOFF"


class DeliveryAction(StrEnum):
    """How the application should handle one candidate customer output."""

    AUTO_DELIVER = "AUTO_DELIVER"
    DELIVER_WITH_AUDIT = "DELIVER_WITH_AUDIT"
    SYNC_REVIEW = "SYNC_REVIEW"
    ADVISOR_HANDOFF = "ADVISOR_HANDOFF"


class OutputKind(StrEnum):
    """Semantic kind of output; independent from which renderer wrote it."""

    INFORMATION = "INFORMATION"
    CATALOG_QUOTE = "CATALOG_QUOTE"
    RECOMMENDATION = "RECOMMENDATION"
    COMPARISON = "COMPARISON"
    TCO_ESTIMATE = "TCO_ESTIMATE"
    COMMERCIAL_REQUEST = "COMMERCIAL_REQUEST"


class OutputSource(StrEnum):
    """Trusted provenance participating in the candidate output."""

    CATALOG = "CATALOG"
    SNAPSHOT = "SNAPSHOT"
    APPROVED_RAG = "APPROVED_RAG"
    DETERMINISTIC_TOOL = "DETERMINISTIC_TOOL"
    CONSTRAINED_LLM = "CONSTRAINED_LLM"


class OutputRiskContext(BaseModel):
    """Structured facts used to decide delivery without judging LLM usage alone."""

    model_config = ConfigDict(frozen=True)

    output_kind: OutputKind
    source_kinds: frozenset[OutputSource] = frozenset()
    facts_verified: bool | None = None
    unresolved_entity_count: int = 0
    is_personalized: bool | None = None
    is_negotiated: bool | None = None
    has_non_standard_offer: bool | None = None
    has_financial_commitment: bool | None = None

    def risk_flags(self) -> dict[str, bool | None]:
        """Return the commercial risk flags in audit-friendly shape."""

        return {
            "is_personalized": self.is_personalized,
            "is_negotiated": self.is_negotiated,
            "has_non_standard_offer": self.has_non_standard_offer,
            "has_financial_commitment": self.has_financial_commitment,
        }


@dataclass(frozen=True, slots=True)
class DeliveryDecision:
    """Pure policy result before graph routing and persistence concerns."""

    action: DeliveryAction
    tier: QuoteRiskTier
    reasons: tuple[str, ...] = ()

    @property
    def requires_hitl(self) -> bool:
        """Return whether delivery must wait for a person."""

        return self.action in {DeliveryAction.SYNC_REVIEW, DeliveryAction.ADVISOR_HANDOFF}


def classify_delivery(context: OutputRiskContext) -> DeliveryDecision:
    """Classify semantic risk from provenance, verification and business impact."""

    flags = context.risk_flags()
    commercial_reasons = tuple(name for name, value in flags.items() if value is True)
    if commercial_reasons:
        return DeliveryDecision(
            action=DeliveryAction.ADVISOR_HANDOFF,
            tier=QuoteRiskTier.ADVISOR_HANDOFF,
            reasons=commercial_reasons,
        )
    unknown_flags = tuple(name for name, value in flags.items() if value is None)
    if unknown_flags:
        return DeliveryDecision(
            action=DeliveryAction.SYNC_REVIEW,
            tier=QuoteRiskTier.SYNC_HITL,
            reasons=tuple(f"{name}_unknown" for name in unknown_flags),
        )
    if context.unresolved_entity_count > 0:
        return DeliveryDecision(
            action=DeliveryAction.SYNC_REVIEW,
            tier=QuoteRiskTier.SYNC_HITL,
            reasons=("unresolved_entities",),
        )
    if context.output_kind is OutputKind.TCO_ESTIMATE:
        return DeliveryDecision(
            action=DeliveryAction.SYNC_REVIEW,
            tier=QuoteRiskTier.SYNC_HITL,
            reasons=("tco_requires_human_review",),
        )
    if context.output_kind in {OutputKind.RECOMMENDATION, OutputKind.COMPARISON}:
        required_sources = {OutputSource.SNAPSHOT, OutputSource.CONSTRAINED_LLM}
        reasons: list[str] = []
        if context.facts_verified is not True:
            reasons.append("facts_not_verified")
        if not required_sources.issubset(context.source_kinds):
            reasons.append("untrusted_output_provenance")
        if reasons:
            return DeliveryDecision(
                action=DeliveryAction.SYNC_REVIEW,
                tier=QuoteRiskTier.SYNC_HITL,
                reasons=tuple(reasons),
            )
        return DeliveryDecision(
            action=DeliveryAction.DELIVER_WITH_AUDIT,
            tier=QuoteRiskTier.EVIDENCE_BACKED_AUTO,
        )
    if context.output_kind is OutputKind.COMMERCIAL_REQUEST:
        return DeliveryDecision(
            action=DeliveryAction.ADVISOR_HANDOFF,
            tier=QuoteRiskTier.ADVISOR_HANDOFF,
            reasons=("commercial_request",),
        )
    if context.facts_verified is False:
        return DeliveryDecision(
            action=DeliveryAction.SYNC_REVIEW,
            tier=QuoteRiskTier.SYNC_HITL,
            reasons=("facts_not_verified",),
        )
    return DeliveryDecision(
        action=DeliveryAction.AUTO_DELIVER,
        tier=(
            QuoteRiskTier.DETERMINISTIC_AUTO
            if context.output_kind is OutputKind.CATALOG_QUOTE
            else QuoteRiskTier.NON_QUOTE
        ),
    )


class QuoteEvaluation(BaseModel):
    """Sáu cờ quyết định số phận một báo giá.

    Mọi field mặc định `None` chứ không phải `False`: `None` nghĩa là "không xác
    định được", và default-deny bắt buộc coi không-xác-định là RỦI RO. Nếu mặc
    định là `False`, một lỗi dựng thiếu field sẽ lặng lẽ biến thành auto-approve
    — đúng thứ chính sách này sinh ra để chặn.
    """

    model_config = ConfigDict(frozen=True)

    is_personalized: bool | None = None
    is_negotiated: bool | None = None
    has_non_standard_offer: bool | None = None
    has_financial_commitment: bool | None = None
    confidence_score: float | None = None
    is_deterministic_standard: bool | None = None

    @classmethod
    def unknown(cls) -> QuoteEvaluation:
        """Bản đánh giá "không biết gì" — mọi field `None`, luôn dẫn tới HITL."""

        return cls()

    @classmethod
    def from_raw(cls, payload: Mapping[str, Any] | None) -> QuoteEvaluation:
        """Dựng từ dict thô; payload hỏng → bản `unknown()` chứ không raise.

        Một `ValidationError` lọt lên graph sẽ làm chết lượt của khách. Nhưng nuốt
        lỗi rồi coi như an toàn thì còn tệ hơn: ở đây nuốt lỗi và trả về bản đánh
        giá rủi ro tối đa, nên hỏng dữ liệu luôn rơi về phía chặn.
        """

        if payload is None:
            return cls.unknown()
        try:
            return cls.model_validate(dict(payload))
        except ValidationError:
            return cls.unknown()

    def risk_flags(self) -> dict[str, bool | None]:
        """Bốn cờ rủi ro nội dung (không gồm confidence/deterministic)."""

        return {
            "is_personalized": self.is_personalized,
            "is_negotiated": self.is_negotiated,
            "has_non_standard_offer": self.has_non_standard_offer,
            "has_financial_commitment": self.has_financial_commitment,
        }

    def triggered_reasons(self, threshold: float = CONFIDENCE_THRESHOLD) -> tuple[str, ...]:
        """Liệt kê lý do khiến lượt này bị chặn — để audit đọc được, không đoán."""

        reasons = [name for name, value in self.risk_flags().items() if value is not False]
        if not _is_usable_score(self.confidence_score):
            reasons.append("confidence_missing")
        elif self.confidence_score is not None and self.confidence_score < threshold:
            reasons.append("confidence_below_threshold")
        if self.is_deterministic_standard is not True:
            reasons.append("not_deterministic_standard")
        return tuple(reasons)


def _is_usable_score(score: object) -> bool:
    """Số dùng được là số thực hữu hạn trong [0, 1] — `None`/NaN/bool thì không.

    Chặn `bool` tường minh vì `isinstance(True, int)` là `True` trong Python, và
    một cờ boolean lọt vào ô confidence sẽ được đọc thành 1.0 → auto-approve.
    """

    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return False
    return math.isfinite(float(score)) and 0.0 <= float(score) <= 1.0


def requires_sync_hitl(
    evaluation: QuoteEvaluation | None,
    threshold: float = CONFIDENCE_THRESHOLD,
) -> bool:
    """`True` nghĩa là CHẶN lượt, chờ tư vấn viên duyệt (synchronous HITL).

    Default-deny: chỉ đúng một đường dẫn tới `False`, và nó đòi TẤT CẢ điều kiện
    an toàn được thoả mãn tường minh — sinh deterministic từ catalog, confidence
    đủ cao, và bốn cờ rủi ro đều `False` (không phải "khác True": `None` là chưa
    biết, mà chưa biết thì không được đi qua).
    """

    if evaluation is None:
        return True
    if evaluation.is_deterministic_standard is not True:
        return True
    score = evaluation.confidence_score
    if not _is_usable_score(score) or float(score) < threshold:  # type: ignore[arg-type]
        return True
    if any(flag is not False for flag in evaluation.risk_flags().values()):
        return True
    return False


def legacy_requires_sync_hitl(*, touched_catalog: bool) -> bool:
    """Luồng CŨ để so sánh shadow-mode: cứ chạm dữ liệu là chặn.

    Giữ lại nguyên văn quy tắc cũ thay vì hard-code `True` ở chỗ gọi, để phần
    báo cáo A9 đọc được đúng thứ đang bị so sánh.
    """

    return touched_catalog


def is_near_threshold(
    score: float | None,
    threshold: float = CONFIDENCE_THRESHOLD,
    margin: float = NEAR_THRESHOLD_MARGIN,
) -> bool:
    """Confidence nằm trong `[threshold - margin, threshold)` — dữ liệu tune ngưỡng."""

    if not _is_usable_score(score):
        return False
    return threshold - margin <= float(score) < threshold  # type: ignore[arg-type]


# ── Nhận diện rủi ro từ lời khách — rule-based, không LLM ──────────────────────
#
# [GIẢ ĐỊNH] Bộ mẫu dưới đây bắt theo TỪ KHOÁ tiếng Việt có dấu, khớp trên chuỗi
# đã hạ chữ thường. Nó ưu tiên bắt nhầm (false positive → chặn thừa) hơn bỏ sót
# (false negative → agent tự hứa giá). Số liệu shadow-mode là căn cứ để siết lại.

_NEGOTIATION_PATTERNS: Final[tuple[str, ...]] = (
    r"giảm\s+(giá|cho|được|thêm|nữa)",
    # Xin giảm một SỐ TIỀN cụ thể — dạng mặc cả trực tiếp nhất, và tốn tiền
    # thật nhất nếu agent tự gật. Mẫu ngay trên đòi một TỪ theo sau nên
    # "giảm 20 triệu" lọt sạch. Tìm ra 2026-08-28 khi dựng lưới cửa lái thử.
    #
    # Buộc phải có ĐƠN VỊ TIỀN đi kèm, không nhận số trần: "tầm chạy giảm 30
    # km" là câu hỏi kỹ thuật, không phải một lời trả giá.
    r"(giảm|bớt|hạ)\s+\d+\s*(triệu|trieu|tr\b|củ|cu\b|k\b|nghìn|nghin|đồng|dong)",
    r"xin\s+giảm",
    r"bớt\s+(giá|cho|được|chút|tí)",
    r"hạ\s+giá",
    r"mặc\s+cả",
    r"thương\s+lượng",
    r"thư[oơ]ng\s+l[uư][oơ]ng",
    r"giá\s+(tốt|mềm|cuối|chốt|thấp)",
    r"chốt\s+giá",
    r"fix\s+giá",
    r"rẻ\s+hơn",
    r"discount",
    r"\bdeal\b",
)
_NON_STANDARD_OFFER_PATTERNS: Final[tuple[str, ...]] = (
    r"khuyến\s*mãi",
    r"ưu\s+đãi",
    r"quà\s+tặng",
    r"tặng\s+kèm",
    r"tặng\s+thêm",
    r"voucher",
    r"trợ\s+giá",
    r"chương\s+trình\s+(khuyến|ưu)",
)
_FINANCIAL_COMMITMENT_PATTERNS: Final[tuple[str, ...]] = (
    r"trả\s+góp",
    r"trả\s+trước",
    r"lãi\s+suất",
    r"đặt\s+cọc",
    r"tiền\s+cọc",
    r"hợp\s+đồng",
    r"cam\s+kết",
    r"thanh\s+toán",
    r"gia\s+hạn\s+bảo\s+hành",
    r"bảo\s+hành\s+thêm",
    r"vay\s+(ngân\s+hàng|vốn|tiền)",
)
_PERSONALIZED_PATTERNS: Final[tuple[str, ...]] = (
    # "giá lăn bánh" TỪNG nằm ở đây và bị chặn chờ duyệt. Đã gỡ ở A7-9: nó được
    # tính bằng một công thức cố định trên biểu phí đã công bố
    # (`tools/on_road_price.py`), tức deterministic đúng như giá niêm yết — không
    # phải một con số ai đó thương lượng riêng cho khách này. Điều kiện đổi lại
    # là phải đủ slot: thiếu tỉnh thì HỎI, không phải đoán rồi chặn.
    r"báo\s+giá\s+riêng",
    r"riêng\s+cho\s+(em|anh|chị|mình|tôi)",
    r"trường\s+hợp\s+của",
    r"tính\s+(giúp|hộ)\s+.*(tổng|chi\s+phí)",
    r"gói\s+riêng",
)

#: Chính cụm "rẻ hơn"/"giá thấp", để bóc ra khi cần hỏi "bỏ nó đi thì câu này còn
#: dấu hiệu mặc cả nào không".
_CHEAPER_COMPARATIVE: Final[re.Pattern[str]] = re.compile(r"rẻ\s+hơn|giá\s+thấp")
_CHEAPER_COMPARATIVE_FOLDED: Final[re.Pattern[str]] = re.compile(r"re hon|gia thap")

_COMPILED: Final[dict[str, tuple[re.Pattern[str], ...]]] = {
    "is_negotiated": tuple(re.compile(p) for p in _NEGOTIATION_PATTERNS),
    "has_non_standard_offer": tuple(re.compile(p) for p in _NON_STANDARD_OFFER_PATTERNS),
    "has_financial_commitment": tuple(re.compile(p) for p in _FINANCIAL_COMMITMENT_PATTERNS),
    "is_personalized": tuple(re.compile(p) for p in _PERSONALIZED_PATTERNS),
}

#: Keyword KHÔNG DẤU + leet cho cùng bốn nhóm rủi ro — bắt "giam gia", "tra
#: gop", "bao hanh them" mà regex có dấu ở trên không thấy (ENG REVIEW
#: AMENDMENT 1). Compile variants MỘT lần ở module-load (AMENDMENT 3).
_FOLDED_RISK_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "is_negotiated": (
        "giam gia",
        "giam cho",
        "giam duoc",
        "giam them",
        "giam nua",
        "xin giam",
        "bot gia",
        "bot cho",
        "bot duoc",
        "bot chut",
        "bot ti",
        "ha gia",
        "mac ca",
        "thuong luong",
        "gia tot",
        "gia mem",
        "gia cuoi",
        "gia chot",
        "gia thap",
        "chot gia",
        "fix gia",
        "re hon",
        "discount",
        "deal",
    ),
    "has_non_standard_offer": (
        "khuyen mai",
        "uu dai",
        "qua tang",
        "tang kem",
        "tang them",
        "voucher",
        "tro gia",
        "chuong trinh khuyen",
        "chuong trinh uu",
    ),
    "has_financial_commitment": (
        "tra gop",
        "tra truoc",
        "lai suat",
        "dat coc",
        "tien coc",
        "hop dong",
        "cam ket",
        "thanh toan",
        "gia han bao hanh",
        "bao hanh them",
        "vay ngan hang",
        "vay von",
        "vay tien",
    ),
    "is_personalized": (
        "bao gia rieng",
        "rieng cho em",
        "rieng cho anh",
        "rieng cho chi",
        "rieng cho minh",
        "rieng cho toi",
        "truong hop cua",
        "goi rieng",
    ),
}

_FOLDED_RISK_NEEDLES: Final[dict[str, tuple[str, ...]]] = {
    name: compile_keyword_variants(keywords) for name, keywords in _FOLDED_RISK_KEYWORDS.items()
}


#: Câu đang xin một MẪU XE khác rẻ hơn, không xin giảm giá mẫu đang xem.
#:
#: BUG THẬT trên prod 2026-08-27: *"có mẫu nào rẻ hơn không em"* bị `rẻ hơn` xếp
#: vào nhóm mặc cả → `is_negotiated` → chuyển tư vấn viên. Nhưng đó là hai việc
#: khác hẳn nhau:
#:
#: - *"bớt cho anh 100 triệu được không"* — xin hạ giá CHIẾC NÀY. Người thật phải
#:   duyệt, và cờ mặc cả đúng ở đây.
#: - *"có mẫu nào rẻ hơn không"* — xin một CHIẾC KHÁC. Đây là việc của bộ đề xuất,
#:   và đẩy nó sang hàng duyệt là bỏ rơi khách ngay lúc họ còn muốn mua.
#:
#: Dấu hiệu phân biệt là DANH TỪ CHỈ XE đứng cùng một từ hỏi tồn tại/lựa chọn:
#: khách hỏi "mẫu nào", "còn xe", "chiếc khác". Lời mặc cả không bao giờ hỏi
#: "mẫu nào" — nó nói thẳng vào giá của chiếc đang bàn.
_CHEAPER_MODEL_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(pattern)
    for pattern in (
        r"(?:mẫu|xe|chiếc|dòng|phiên\s+bản|bản)\s+(?:nào|khác|kh[aá]c)",
        # Chỉ định TRỎ VÀO CHIẾC ĐANG XEM thì không phải xin mẫu khác: "muốn xe
        # này rẻ hơn" là mặc cả, "muốn xe rẻ hơn" là xin mẫu khác. Một chữ "này"
        # đảo hẳn nghĩa, nên nó phải nằm trong luật chứ không nằm trong bụng.
        r"(?:có|còn|c[óo]n|muốn|cần|tìm|xem|giới\s+thiệu)\s+"
        r"(?:mẫu|xe|chiếc|dòng|phiên\s+bản|bản)(?!\s*(?:này|đó|kia|ấy|đấy))",
    )
)
_FOLDED_CHEAPER_MODEL_NEEDLES: Final[tuple[str, ...]] = (
    "mau nao",
    "xe nao",
    "chiec nao",
    "dong nao",
    "mau khac",
    "xe khac",
    "chiec khac",
    "co mau",
    "con mau",
    "co xe",
    "con xe",
)


def _asks_for_a_cheaper_model(canonical: CanonicalText) -> bool:
    """Câu này xin một mẫu khác, không xin hạ giá mẫu đang xem."""

    if any(pattern.search(canonical.original) for pattern in _CHEAPER_MODEL_PATTERNS):
        return True
    folded = canonical.folded
    return any(needle in folded for needle in _FOLDED_CHEAPER_MODEL_NEEDLES)


def detect_risk_flags(
    *,
    user_message: str,
    canonical: CanonicalText,
    standard_promotions: frozenset[str] = STANDARD_PROMOTIONS,
) -> dict[str, bool]:
    """Bốn cờ rủi ro nội dung, đọc từ lời khách.

    Ưu đãi được đối chiếu với `standard_promotions`: nhắc tới một chương trình đã
    nằm trong bảng đã duyệt thì KHÔNG phải "ngoài chính sách chuẩn".

    So khớp chạy trên `canonical` sinh tại chain (ENG REVIEW AMENDMENT 2) —
    gate KHÔNG tự normalize: regex có dấu trên `original`, keyword không dấu +
    leet trên `folded`/`leet_decoded`. `canonical` là BẮT BUỘC; thiếu là lỗi
    caller, không fallback im lặng.
    """

    text = canonical.original
    flags = {name: any(pattern.search(text) for pattern in patterns) for name, patterns in _COMPILED.items()}
    for name, needles in _FOLDED_RISK_NEEDLES.items():
        if any(match_tier(canonical, needle) is not MatchTier.NONE for needle in needles):
            flags[name] = True
    # Xin MẪU KHÁC rẻ hơn thì gỡ cờ mặc cả — trừ khi câu còn mang một dấu hiệu
    # mặc cả THẬT ("bớt", "giảm giá"). Câu vừa xin mẫu khác vừa mặc cả vẫn phải
    # tới người: gỡ cờ theo kiểu tất-cả-hoặc-không là mở một đường lách.
    if flags["is_negotiated"] and _asks_for_a_cheaper_model(canonical):
        text_without_cheaper = _CHEAPER_COMPARATIVE.sub(" ", text)
        folded_without_cheaper = _CHEAPER_COMPARATIVE_FOLDED.sub(" ", canonical.folded)
        still_negotiating = any(pattern.search(text_without_cheaper) for pattern in _COMPILED["is_negotiated"]) or any(
            needle in folded_without_cheaper for needle in ("giam", "bot ", "ha gia", "mac ca", "discount")
        )
        flags["is_negotiated"] = still_negotiating
    if flags["has_non_standard_offer"] and standard_promotions:
        flags["has_non_standard_offer"] = not any(promotion.casefold() in text for promotion in standard_promotions)
    return flags


def is_quote_turn(*, priced_fact_count: int, risk_flags: Mapping[str, bool]) -> bool:
    """Lượt này có phải một BÁO GIÁ không.

    Hai dấu hiệu, đủ một là có: nội dung sắp gửi có ít nhất một con số giá đọc từ
    catalog, hoặc lời khách chạm vào một trong bốn chủ đề rủi ro (mặc cả, ưu đãi,
    cam kết tài chính, yêu cầu giá riêng).

    Tra thông số kỹ thuật/tồn kho/so sánh xe không rơi vào cả hai → `NON_QUOTE`,
    và chính sách 5 điều kiện KHÔNG áp lên nó [GIẢ ĐỊNH: prompt mục 3 gạch đầu
    dòng 3 — bản chất khác nhau, không phải báo giá thì không đánh giá như báo giá].
    """

    return priced_fact_count > 0 or any(risk_flags.values())


def evaluate_catalog_lookup(
    *,
    user_message: str,
    canonical: CanonicalText,
    priced_fact_count: int,
    unresolved_mention_count: int,
    standard_promotions: frozenset[str] = STANDARD_PROMOTIONS,
) -> QuoteEvaluation:
    """Đánh giá một lượt đọc giá niêm yết từ catalog.

    `is_deterministic_standard=True` vì câu trả lời được render thẳng từ
    `VehicleFacts` (`domain/catalog_reply.py`) — không có bước suy luận hay điều
    chỉnh nào của LLM chen vào giữa bảng giá và chữ gửi khách.

    [GIẢ ĐỊNH] Nguồn `confidence_score`: pipeline hiện chưa có điểm tin cậy nào ở
    bước trích slot (`ExtractedSlots` không mang field đó), nên với nhánh
    deterministic này confidence được suy ra từ ĐỘ TRỌN VẸN CỦA VIỆC RESOLVE tên
    xe: resolve sạch → 1.0; còn tên mập mờ/không khớp lẫn trong một câu có giá →
    0.70, dưới ngưỡng, vì báo giá kèm một mẫu xe chưa xác định là báo nhầm giá.
    """

    flags = detect_risk_flags(user_message=user_message, canonical=canonical, standard_promotions=standard_promotions)
    return QuoteEvaluation(
        **flags,
        confidence_score=0.70 if unresolved_mention_count > 0 else 1.0,
        is_deterministic_standard=True,
    )


def evaluate_generated_quote(
    *,
    user_message: str,
    canonical: CanonicalText,
    confidence_score: float | None,
    standard_promotions: frozenset[str] = STANDARD_PROMOTIONS,
) -> QuoteEvaluation:
    """Đánh giá một bản nháp do LLM soạn (nhánh advisory, sau `synthesize`).

    `is_deterministic_standard=False` vẫn mô tả đúng nguồn tạo câu chữ, nhưng
    không còn tự nó quyết định HITL. `classify_delivery` xét thêm output kind,
    provenance và kết quả guardrail để thả recommendation an toàn có audit.
    """

    flags = detect_risk_flags(user_message=user_message, canonical=canonical, standard_promotions=standard_promotions)
    return QuoteEvaluation(
        **flags,
        confidence_score=confidence_score,
        is_deterministic_standard=False,
    )


def classify_tier(
    evaluation: QuoteEvaluation | None,
    *,
    is_quote: bool,
    threshold: float = CONFIDENCE_THRESHOLD,
) -> QuoteRiskTier:
    """Gộp hai câu hỏi ("có phải báo giá không", "có rủi ro không") thành một tier."""

    if not is_quote:
        return QuoteRiskTier.NON_QUOTE
    if requires_sync_hitl(evaluation, threshold):
        return QuoteRiskTier.SYNC_HITL
    return QuoteRiskTier.DETERMINISTIC_AUTO


# ── J2: LLM judge risk flag — lớp HAI sau regex (plan chống-crack) ─────────────
# Cùng bất biến với J1: judge CHỈ THÊM cờ (OR), không bao giờ gỡ. Regex là đáy,
# quyết định vẫn thuần rule-based (`classify_delivery` không đổi). Judge lỗi →
# không thêm gì. SHADOW mặc định: chỉ đo, không đổi cờ.
RISK_FLAG_LLM_SHADOW_MODE: Final[bool] = True
RISK_FLAG_CONFIDENCE_THRESHOLD: Final[float] = 0.90
RISK_FLAG_SAMPLE_RATE: Final[float] = 0.20


class RiskFlagFallbackReason(StrEnum):
    """Lý do judge risk flag fail-open về "không thêm cờ nào"."""

    OPTIONAL_BUDGET_EXHAUSTED = "optional_budget_exhausted"
    MISSING_API_KEY = "missing_api_key"
    TIMEOUT = "timeout"
    EMPTY_TOOL_CALL = "empty_tool_call"
    INVALID_PAYLOAD = "invalid_payload"
    PROVIDER_API_ERROR = "provider_api_error"
    UNEXPECTED_KNOWN_FAILURE = "unexpected_known_failure"


@dataclass(frozen=True, slots=True)
class RiskFlagPrediction:
    """Bốn cờ rủi ro judge LLM quan sát trên nội dung sắp gửi khách."""

    flags: Mapping[str, bool]
    confidence: float
    fallback_reason: RiskFlagFallbackReason | None = None


def merge_risk_flags(
    regex_flags: Mapping[str, bool | None],
    prediction: RiskFlagPrediction | None,
    *,
    shadow_mode: bool = RISK_FLAG_LLM_SHADOW_MODE,
    threshold: float = RISK_FLAG_CONFIDENCE_THRESHOLD,
) -> dict[str, bool | None]:
    """Gộp cờ regex + cờ judge theo chiều AN TOÀN: chỉ OR, không AND-gỡ.

    Regex cờ `True` → giữ `True`. Judge báo `True` đủ ngưỡng (live mode) →
    thêm. Shadow / judge lỗi → trả nguyên cờ regex. Không đường nào gỡ cờ đã bật.
    """

    merged = dict(regex_flags)
    if shadow_mode or prediction is None or prediction.confidence < threshold:
        return merged
    for name, value in prediction.flags.items():
        if value:
            merged[name] = True
    return merged


def escalation_note(user_message: str, reasons: Sequence[str]) -> str:
    """Nội dung đẩy vào hàng đợi khi chặn một lượt CHƯA có bản nháp.

    Tư vấn viên cần thấy khách hỏi gì và vì sao hệ thống không tự trả lời; một
    mục rỗng thì không duyệt được (`SqlAlchemyReviewQueueRepository.enqueue` từ
    chối thẳng chuỗi rỗng).
    """

    listed = ", ".join(reasons) if reasons else "unknown"
    return f"[CẦN TƯ VẤN VIÊN BÁO GIÁ] Khách hỏi: “{user_message.strip()}”. Lý do chuyển: {listed}."


__all__ = [
    "AUDIT_SAMPLE_RATE",
    "CONFIDENCE_THRESHOLD",
    "DeliveryAction",
    "DeliveryDecision",
    "NEAR_THRESHOLD_MARGIN",
    "OutputKind",
    "OutputRiskContext",
    "OutputSource",
    "RISK_FLAG_CONFIDENCE_THRESHOLD",
    "RISK_FLAG_LLM_SHADOW_MODE",
    "RISK_FLAG_SAMPLE_RATE",
    "STANDARD_PROMOTIONS",
    "QuoteEvaluation",
    "QuoteRiskTier",
    "RiskFlagFallbackReason",
    "RiskFlagPrediction",
    "classify_delivery",
    "classify_tier",
    "detect_risk_flags",
    "escalation_note",
    "evaluate_catalog_lookup",
    "evaluate_generated_quote",
    "is_near_threshold",
    "is_quote_turn",
    "legacy_requires_sync_hitl",
    "merge_risk_flags",
    "requires_sync_hitl",
]
