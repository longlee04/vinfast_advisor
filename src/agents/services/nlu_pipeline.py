"""Điều phối bốn lớp nhận diện ý định thành một use case duy nhất.

    câu gốc → [1] rewrite → [2] fuzzy entity → [3] phân loại → [4] định tuyến

Node chỉ gọi vào đây và map kết quả vào state; toàn bộ nghiệp vụ nằm ở
`domain/`. Đó là lý do lớp này mỏng: nó đọc config, ghép nguồn, ghi log, và
KHÔNG tự quyết định điều gì mà `domain/` chưa quyết định.

Ba bảo đảm mà lớp này chịu trách nhiệm giữ, cả ba đều là ràng buộc tương thích
ngược chứ không phải tính năng:

- **Câu gốc không bao giờ bị ghi đè.** `NluDecision` giữ cả hai bản; bản rewrite
  chỉ được dùng khi guard của Lớp 1 chấp nhận nó.
- **Slot đang chờ (A7-10) chiếm quyền tuyệt đối.** Có `pending_slot` thì tier
  luôn là `AUTO`, không lớp nào được chen câu hỏi vào giữa.
- **`PENDING_HANDOFF` chiếm quyền tuyệt đối.** Xem `route_confidence`.

`routing_enabled=False` là nút lùi một bước: bốn lớp vẫn chạy và vẫn ghi log đầy
đủ, nhưng tier luôn `AUTO` nên hành vi hệ thống y hệt trước khi có tính năng này.
Đây là chế độ shadow-mode để thu số liệu tinh chỉnh ngưỡng, cùng khuôn với
`QuoteGateConfig.shadow_mode_enabled` (A7-4).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from src.agents.domain.entity_catalog import (
    POPULAR_MODEL_SUGGESTIONS,
    EntityCatalog,
    EntityCategory,
    default_catalog,
)
from src.agents.domain.fuzzy_match import (
    DEFAULT_MULTI_TOKEN_SCORE,
    DEFAULT_SINGLE_TOKEN_SCORE,
    DEFAULT_WEAK_FLOOR,
    EntityMatch,
    MatchThresholds,
    match_entities,
)
from src.agents.domain.nlu_confidence import (
    DEFAULT_AUTO_THRESHOLD,
    DEFAULT_CONFIRM_THRESHOLD,
    ConfidenceThresholds,
    NluClassification,
    NluTier,
    QuickReplyOption,
    advisory_flow_active,
    classify_intent,
    route_confidence,
)
from src.agents.domain.pending_intent_confirmation import PendingIntentConfirmation
from src.agents.domain.pricing_intent import PROVINCES
from src.agents.domain.rewrite import (
    MAX_TOKEN_CHANGE_RATIO,
    MIN_REWRITE_CONFIDENCE,
    RewriteResult,
    rewrite_trigger,
)
from src.agents.domain.text_normalization import normalize
from src.agents.domain.values import SlotValue
from src.agents.logging import get_agent_logger
from src.agents.prompts.nlu_replies import (
    CONFIRM_NO_LABEL,
    CONFIRM_NO_VALUE,
    CONFIRM_YES_LABEL,
    CONFIRM_YES_VALUE,
    clarify_message,
    confirm_text_question,
    confirm_vehicle_question,
)
from src.agents.services.rewrite import RewriteServiceImpl

logger = get_agent_logger("agent.nlu.pipeline")


def _env_float(env: Mapping[str, str], name: str, default: float, ceiling: float) -> float:
    """Giá trị hỏng hoặc ngoài dải thì giữ mặc định.

    Cùng khuôn với `services/quote_gate._env_float`: một biến môi trường gõ sai
    không được lặng lẽ đẩy ngưỡng nhận diện về 0 — ở mức đó mọi câu đều "đủ tin
    cậy" và cả bốn lớp trở thành trang trí.
    """

    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("nlu: %s=%r khong phai so, giu mac dinh %s", name, raw, default)
        return default
    if not 0.0 <= value <= ceiling:
        logger.warning("nlu: %s=%r ngoai [0,%s], giu mac dinh %s", name, raw, ceiling, default)
        return default
    return value


def _env_flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class NluPipelineConfig:
    """Tham số vận hành của bốn lớp — chỉnh được mà không phải sửa code.

    [GIẢ ĐỊNH] Mọi giá trị mặc định là phỏng đoán khởi đầu và PHẢI được tinh
    chỉnh bằng số liệu thật (chạy `routing_enabled=False` để thu log trước).
    """

    thresholds: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    match_thresholds: MatchThresholds = field(default_factory=MatchThresholds)
    rewrite_enabled: bool = True
    max_change_ratio: float = MAX_TOKEN_CHANGE_RATIO
    min_rewrite_confidence: float = MIN_REWRITE_CONFIDENCE
    #: `False` → bốn lớp vẫn chạy và vẫn log, nhưng không lớp nào đổi hành vi.
    routing_enabled: bool = True

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> NluPipelineConfig:
        source = os.environ if env is None else env
        auto = _env_float(source, "NLU_AUTO_THRESHOLD", DEFAULT_AUTO_THRESHOLD, 1.0)
        confirm = _env_float(source, "NLU_CONFIRM_THRESHOLD", DEFAULT_CONFIRM_THRESHOLD, 1.0)
        if confirm > auto:
            # Đảo ngưỡng thì dải "xác nhận" biến mất và mọi câu lửng lơ rơi thẳng
            # xuống nhánh hỏi làm rõ. Giữ mặc định còn hơn chạy với một cấu hình
            # vô nghĩa mà không ai nhận ra.
            logger.warning(
                "nlu: NLU_CONFIRM_THRESHOLD=%s > NLU_AUTO_THRESHOLD=%s, giu mac dinh",
                confirm,
                auto,
            )
            auto, confirm = DEFAULT_AUTO_THRESHOLD, DEFAULT_CONFIRM_THRESHOLD
        return cls(
            thresholds=ConfidenceThresholds(auto=auto, confirm=confirm),
            match_thresholds=MatchThresholds(
                single_token=_env_float(source, "NLU_FUZZY_SINGLE_TOKEN_SCORE", DEFAULT_SINGLE_TOKEN_SCORE, 100.0),
                multi_token=_env_float(source, "NLU_FUZZY_MULTI_TOKEN_SCORE", DEFAULT_MULTI_TOKEN_SCORE, 100.0),
                weak_floor=_env_float(source, "NLU_FUZZY_WEAK_FLOOR", DEFAULT_WEAK_FLOOR, 100.0),
            ),
            rewrite_enabled=_env_flag(source, "NLU_REWRITE_ENABLED", True),
            max_change_ratio=_env_float(source, "NLU_MAX_TOKEN_CHANGE_RATIO", MAX_TOKEN_CHANGE_RATIO, 1.0),
            min_rewrite_confidence=_env_float(source, "NLU_MIN_REWRITE_CONFIDENCE", MIN_REWRITE_CONFIDENCE, 1.0),
            routing_enabled=_env_flag(source, "NLU_ROUTING_ENABLED", True),
        )


@dataclass(frozen=True, slots=True)
class NluDecision:
    """Kết quả đầy đủ của bốn lớp — đủ để node ghi state và để audit đọc lại."""

    tier: NluTier
    rewrite: RewriteResult
    classification: NluClassification
    entities: tuple[EntityMatch, ...] = ()
    #: Câu trả khách cho nhánh `CONFIRM`/`CLARIFY`; `None` ở nhánh `AUTO`.
    reply: str | None = None
    quick_replies: tuple[QuickReplyOption, ...] = ()
    #: Bản ghi cần lưu để lượt sau hiểu được câu "đúng rồi" của khách.
    pending_confirmation: PendingIntentConfirmation | None = None

    @property
    def message_for_extraction(self) -> str:
        """Chuỗi đưa xuống `extract_slots`. Luôn là một chuỗi dùng được."""

        return self.rewrite.text_for_matching

    #: Lớp 3 có nhận ra một ý định ĐỦ CHẮC không (>= ngưỡng xác nhận).
    #:
    #: Tính ở đây vì đây là nơi DUY NHẤT biết ngưỡng. `nodes/classify_scope` cần
    #: câu trả lời này để bản đọc tất định thắng nhãn `OUT_OF_SCOPE` của LLM,
    #: nhưng node không được import `domain/` (mục 6.5b) — và chép ngưỡng sang
    #: node là dựng bản thứ hai sẽ lệch.
    intent_confident: bool = False


@dataclass(slots=True)
class NluPipelineServiceImpl:
    """Chạy bốn lớp cho một tin nhắn.

    `rewrite_service=None` → Lớp 1 tắt, ba lớp còn lại chạy bình thường trên câu
    gốc. Không dựng một bộ rewrite giả để khỏi "có vẻ đang sửa lỗi" trong khi
    không — cùng nguyên tắc với `composition.py` để service chưa nối là `None`.
    """

    rewrite_service: RewriteServiceImpl | None = None
    catalog: EntityCatalog = field(default_factory=default_catalog)
    config: NluPipelineConfig = field(default_factory=NluPipelineConfig)

    async def recognize(
        self,
        *,
        user_message: str,
        pending_slot: str | None = None,
        pending_intent: str | None = None,
        handoff_active: bool = False,
        known_slots: Mapping[str, SlotValue] | None = None,
    ) -> NluDecision:
        """Nhận diện một tin nhắn, trả quyết định định tuyến kèm bằng chứng.

        `known_slots` là slot của phiên TẠI ĐẦU LƯỢT. Truyền vào để Lớp 4 biết
        phiên có đang giữa một cuộc tư vấn không — xem `advisory_flow_active`.
        """

        original = user_message or ""

        # ── Lớp 1 ─────────────────────────────────────────────────────────────
        if self.rewrite_service is None or not self.config.rewrite_enabled:
            # Lớp 1 tắt, nhưng cổng phát hiện nhiễu của nó vẫn phải chạy: Lớp 4
            # dùng cờ đó để biết có được phép hỏi lại không, và cổng này là rule-
            # based thuần nên không tốn lần gọi LLM nào. Tắt Lớp 1 mà mất luôn cờ
            # sẽ khiến mọi câu bị coi là sạch và hai nhánh hỏi lại chết âm thầm.
            trigger = rewrite_trigger(original, self._known_tokens())
            rewrite = RewriteResult.unchanged(original, "disabled", input_looks_noisy=trigger.should_attempt)
        else:
            rewrite = await self.rewrite_service.rewrite(original)

        # ── Lớp 2 ─────────────────────────────────────────────────────────────
        entities = match_entities(
            original_text=original,
            rewritten_text=rewrite.text_for_matching,
            catalog=self.catalog,
            thresholds=self.config.match_thresholds,
        )
        logger.info(
            "layer2: input=%r rewritten=%r entities=%s",
            original[:120],
            rewrite.text_for_matching[:120],
            [
                f"{item.category.value}:{item.canonical}@{item.score:.0f}{'(weak)' if item.is_weak else ''}"
                for item in entities
            ],
        )

        # ── Lớp 3 ─────────────────────────────────────────────────────────────
        classification = classify_intent(
            entities=entities,
            rewrite_trust=rewrite.trust,
            pending_slot=pending_slot,
            pending_intent=pending_intent,
            # Câu GỐC, không phải bản rewrite: cue so sánh ("so sánh", "hay",
            # "khác gì") là chữ khách tự viết và Lớp 1 không có lý do gì để sửa
            # chúng. Đưa bản rewrite vào đây sẽ để một lần sửa chính tả hỏng cướp
            # mất ý định của cả lượt.
            user_message=original,
        )
        logger.info(
            "layer3: intent=%s confidence=%.4f candidates=%s pending_slot=%s",
            classification.intent_hint,
            classification.confidence,
            [f"{item.intent}@{item.score:.2f}" for item in classification.candidates],
            pending_slot,
        )

        # ── Lớp 4 ─────────────────────────────────────────────────────────────
        slot_flow_active = advisory_flow_active(known_slots)
        tier = route_confidence(
            classification,
            self.config.thresholds,
            handoff_active=handoff_active,
            slot_flow_active=slot_flow_active,
            input_looks_noisy=rewrite.input_looks_noisy,
        )
        if not self.config.routing_enabled and tier is not NluTier.AUTO:
            logger.info("layer4: shadow-mode, ha %s ve AUTO", tier.value)
            tier = NluTier.AUTO
        logger.info(
            "layer4: tier=%s confidence=%.4f noisy=%s handoff_active=%s slot_flow_active=%s routing_enabled=%s",
            tier.value,
            classification.confidence,
            rewrite.input_looks_noisy,
            handoff_active,
            slot_flow_active,
            self.config.routing_enabled,
        )

        confident = (
            classification.intent_hint is not None and classification.confidence >= self.config.thresholds.confirm
        )
        if tier is NluTier.CONFIRM:
            return replace(self._confirm_decision(rewrite, classification, entities), intent_confident=confident)
        if tier is NluTier.CLARIFY:
            return replace(self._clarify_decision(rewrite, classification, entities), intent_confident=confident)
        return NluDecision(
            tier=NluTier.AUTO,
            rewrite=rewrite,
            classification=classification,
            entities=entities,
            intent_confident=confident,
        )

    def _confirm_decision(
        self,
        rewrite: RewriteResult,
        classification: NluClassification,
        entities: tuple[EntityMatch, ...],
    ) -> NluDecision:
        """Nhánh xác nhận: nêu ĐÚNG thứ vừa hiểu, không hỏi chung chung."""

        vehicles = classification.vehicle_names
        proposed = rewrite.text_for_matching
        reply = confirm_vehicle_question(vehicles[0]) if vehicles else confirm_text_question(proposed)
        return NluDecision(
            tier=NluTier.CONFIRM,
            rewrite=rewrite,
            classification=classification,
            entities=entities,
            reply=reply,
            quick_replies=(
                QuickReplyOption(label=CONFIRM_YES_LABEL, value=CONFIRM_YES_VALUE),
                QuickReplyOption(label=CONFIRM_NO_LABEL, value=CONFIRM_NO_VALUE),
            ),
            pending_confirmation=PendingIntentConfirmation(
                proposed_text=proposed,
                intent_hint=classification.intent_hint,
                vehicle_names=vehicles,
                confidence=classification.confidence,
            ),
        )

    def _clarify_decision(
        self,
        rewrite: RewriteResult,
        classification: NluClassification,
        entities: tuple[EntityMatch, ...],
    ) -> NluDecision:
        """Nhánh hỏi làm rõ: luôn kèm lối thoát dạng nút bấm (PRD 5.9)."""

        suggestions = self.suggested_models()
        return NluDecision(
            tier=NluTier.CLARIFY,
            rewrite=rewrite,
            classification=classification,
            entities=entities,
            reply=clarify_message(suggestions),
            quick_replies=tuple(QuickReplyOption(label=name, value=name) for name in suggestions),
        )

    def _known_tokens(self) -> frozenset[str]:
        """Token của danh mục, dùng cho cổng phát hiện nhiễu khi Lớp 1 tắt.

        Tính lại mỗi lần gọi là chấp nhận được: nhánh này chỉ chạy khi Lớp 1
        TẮT — tức ở test và ở môi trường chưa nối LLM, không phải đường chạy
        thật. Đường chạy thật đã có `build_known_tokens` tính sẵn một lần ở
        `composition.py` và truyền vào `RewriteServiceImpl`.
        """

        return build_known_tokens(self.catalog)

    def suggested_models(self) -> tuple[str, ...]:
        """Mẫu xe gợi ý, đã lọc theo danh mục đang có.

        Lọc chứ không trả thẳng hằng số: gợi ý một mẫu xe không còn trong catalog
        thì khách bấm vào sẽ nhận "chưa tìm thấy mẫu này" — một lối thoát dẫn vào
        ngõ cụt còn tệ hơn không có lối thoát nào.
        """

        known = set(self.catalog.canonical_names(EntityCategory.VEHICLE))
        available = tuple(name for name in POPULAR_MODEL_SUGGESTIONS if name in known)
        return available or POPULAR_MODEL_SUGGESTIONS


def build_known_tokens(catalog: EntityCatalog) -> frozenset[str]:
    """Tập token hệ thống "giải thích được" — đầu vào của cổng Lớp 1.

    Một câu toàn token như vậy không cần đem đi sửa chính tả.

    Gồm cả tên tỉnh/thành dù chúng KHÔNG phải một danh mục thực thể của Lớp 2:
    đây là từ vựng để phát hiện nhiễu, không phải bảng để khớp entity. Thiếu
    chúng thì "hà nội" (hai token ngắn, không khớp danh mục nào) bị chấm là gõ
    hỏng và bị đẩy qua LLM ở mỗi lần khách trả lời câu hỏi tỉnh của luồng giá
    lăn bánh (A7-9) — vừa tốn tiền vừa không sửa được gì.
    """

    catalog_tokens = (token for alias in catalog.aliases for token in alias.alias.split())
    province_tokens = (token for alias in PROVINCES for token in normalize(alias).split())
    return frozenset((*catalog_tokens, *province_tokens))


__all__ = [
    "NluDecision",
    "NluPipelineConfig",
    "NluPipelineServiceImpl",
    "build_known_tokens",
]
