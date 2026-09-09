"""[A7-4] Use case của cổng rủi ro báo giá: đánh giá → quyết định → audit.

Thay chính sách cũ ("chạm DB là chặn") bằng chính sách theo rủi ro của nội dung
sắp gửi khách. Quyết định nằm ở `domain/quote_risk.py` và là RULE-BASED thuần;
lớp này chỉ ghép nguồn dữ liệu, đọc config, và đẩy audit đi.

Ba thứ lớp này chịu trách nhiệm mà domain không làm được:
- đọc feature flag (bật/tắt chính sách mới, bật/tắt shadow-mode);
- chạy song song luồng cũ để lấy số liệu so sánh (mục 5 prompt A7-4, KPI A9);
- ghi audit cho MỌI quyết định, kể cả case auto-approve.
"""

from __future__ import annotations

import logging
import os
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from src.agents.services.registry import RiskFlagJudgePort

from src.agents.contracts import QuoteAuditRecord, QuoteGateDecision, VehicleFacts
from src.agents.domain.canonical_text import CanonicalText, build_canonical_text
from src.agents.domain.intent_reconciliation import is_test_drive_request
from src.agents.domain.pricing_intent import PricingIntent, classify_pricing_intent
from src.agents.domain.quote_risk import (
    AUDIT_SAMPLE_RATE,
    CONFIDENCE_THRESHOLD,
    NEAR_THRESHOLD_MARGIN,
    RISK_FLAG_CONFIDENCE_THRESHOLD,
    RISK_FLAG_LLM_SHADOW_MODE,
    RISK_FLAG_SAMPLE_RATE,
    STANDARD_PROMOTIONS,
    DeliveryAction,
    DeliveryDecision,
    OutputKind,
    OutputRiskContext,
    OutputSource,
    QuoteEvaluation,
    QuoteRiskTier,
    classify_delivery,
    classify_tier,
    detect_risk_flags,
    escalation_note,
    evaluate_catalog_lookup,
    evaluate_generated_quote,
    is_near_threshold,
    is_quote_turn,
    legacy_requires_sync_hitl,
    merge_risk_flags,
    requires_sync_hitl,
)
from src.agents.domain.turn_classification import TurnType, classify_turn
from src.agents.domain.turn_understanding import is_restart_task_request
from src.agents.domain.vehicle_type_lock import explicit_vehicle_type
from src.agents.ports import QuoteAuditPort
from src.agents.prompts.next_step import (
    acknowledgment_while_pending_reply,
    next_step_reply,
)
from src.agents.services.intent_heuristics import is_direct_human_request

logger = logging.getLogger(__name__)


def _env_flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


def _env_float(env: Mapping[str, str], name: str, default: float) -> float:
    """Giá trị hỏng thì giữ mặc định — một biến môi trường gõ sai không được
    lặng lẽ đẩy ngưỡng an toàn về 0."""

    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("quote gate: %s=%r không phải số, giữ mặc định %s", name, raw, default)
        return default
    if not 0.0 <= value <= 1.0:
        logger.warning("quote gate: %s=%r ngoài [0,1], giữ mặc định %s", name, raw, default)
        return default
    return value


@dataclass(frozen=True, slots=True)
class QuoteGateConfig:
    """Tham số vận hành của cổng — chỉnh được mà không phải sửa code.

    [GIẢ ĐỊNH] Toàn bộ giá trị mặc định là phỏng đoán khởi đầu. Chúng PHẢI được
    tinh chỉnh bằng số liệu shadow-mode trước khi tắt shadow-mode.
    """

    confidence_threshold: float = CONFIDENCE_THRESHOLD
    near_threshold_margin: float = NEAR_THRESHOLD_MARGIN
    audit_sample_rate: float = AUDIT_SAMPLE_RATE
    standard_promotions: frozenset[str] = STANDARD_PROMOTIONS
    #: `False` → quay lại luồng cũ (chặn mọi lượt chạm dữ liệu). Nút lùi một
    #: bước, dùng khi shadow-mode lộ ra tỷ lệ auto-approve sai.
    risk_policy_enabled: bool = True
    #: `True` → mỗi quyết định ghi kèm kết quả luồng cũ để so sánh. Tắt được sau
    #: khi đã đủ dữ liệu báo cáo (mục 5 prompt A7-4).
    shadow_mode_enabled: bool = True

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> QuoteGateConfig:
        source = os.environ if env is None else env
        return cls(
            confidence_threshold=_env_float(source, "QUOTE_HITL_CONFIDENCE_THRESHOLD", CONFIDENCE_THRESHOLD),
            near_threshold_margin=_env_float(source, "QUOTE_HITL_NEAR_THRESHOLD_MARGIN", NEAR_THRESHOLD_MARGIN),
            audit_sample_rate=_env_float(source, "QUOTE_AUDIT_SAMPLE_RATE", AUDIT_SAMPLE_RATE),
            standard_promotions=frozenset(
                item.strip() for item in (source.get("QUOTE_STANDARD_PROMOTIONS") or "").split(",") if item.strip()
            ),
            risk_policy_enabled=_env_flag(source, "QUOTE_RISK_POLICY_ENABLED", True),
            shadow_mode_enabled=_env_flag(source, "QUOTE_HITL_SHADOW_MODE", True),
        )


@dataclass(frozen=True, slots=True)
class ShadowComparison:
    """Bộ đếm so sánh hai luồng, đọc được ngay trong process cho test/KPI nhanh."""

    total: int = 0
    legacy_blocked: int = 0
    new_blocked: int = 0
    released_by_new_policy: int = 0

    def with_turn(self, *, legacy: bool, current: bool) -> ShadowComparison:
        return replace(
            self,
            total=self.total + 1,
            legacy_blocked=self.legacy_blocked + int(legacy),
            new_blocked=self.new_blocked + int(current),
            released_by_new_policy=self.released_by_new_policy + int(legacy and not current),
        )

    @property
    def release_rate(self) -> float:
        """Tỷ lệ lượt lẽ ra bị chặn theo luồng cũ nhưng luồng mới cho đi thẳng."""

        return self.released_by_new_policy / self.legacy_blocked if self.legacy_blocked else 0.0


@dataclass(slots=True)
class QuoteGateServiceImpl:
    """Đánh giá một lượt và trả `QuoteGateDecision` cho node.

    `audit=None` nghĩa là chưa nối sink — cổng vẫn quyết định đúng, chỉ mất dòng
    audit. Không tự dựng sink giả để khỏi "có vẻ đang giám sát" trong khi không.
    """

    audit: QuoteAuditPort | None = None
    config: QuoteGateConfig = field(default_factory=QuoteGateConfig)
    sampler: Callable[[], float] = random.random
    shadow: ShadowComparison = field(default_factory=ShadowComparison)
    risk_flag_judge: RiskFlagJudgePort | None = None

    async def evaluate(
        self,
        *,
        session_id: str,
        run_id: UUID | None = None,
        user_message: str,
        canonical: CanonicalText,
        draft_answer: str | None = None,
        lookup_facts: Sequence[VehicleFacts] = (),
        unresolved_mentions: Sequence[str] = (),
        rendered_answer: str | None = None,
        slots_before: Mapping[str, object] | None = None,
        slots_after: Mapping[str, object] | None = None,
        last_quote_evaluation: Mapping[str, Any] | None = None,
        recommendation_count: int = 0,
        facts_verified: bool | None = None,
        active_offers: Sequence[Mapping[str, Any]] = (),
    ) -> QuoteGateDecision:
        """Quyết định lượt này đi thẳng tới khách hay dừng chờ tư vấn viên.

        `canonical` sinh tại chain (ENG REVIEW AMENDMENT 2) — mọi gate con
        (human request, pricing intent, risk flags) đọc nó, không tự normalize.

        `active_offers` (session-scoped, T6) mở rộng allowlist: ưu đãi TVV đã duyệt
        cho chính phiên này không còn bị coi là "ngoài chính sách chuẩn".
        """

        allowlist = self.config.standard_promotions | frozenset(
            _offer_display_name(offer) for offer in active_offers if _offer_display_name(offer)
        )
        if is_direct_human_request(user_message, canonical):
            return self._direct_advisor_handoff(user_message)
        if classify_pricing_intent(user_message, canonical) is PricingIntent.TCO_ESTIMATE_LOOKUP:
            # [A7-9] TCO luôn qua người duyệt. `docs/vinfast-agent-mvp.md` §A7 xếp
            # TCO vào bốn loại câu trả lời bắt buộc có tư vấn viên duyệt hoặc
            # hiệu chỉnh, và tiêu chí hoàn thành 3 ghi cam kết đó "không có ngoại
            # lệ". Chặn ngay tại đây vì nếu để lượt chảy tiếp, câu hỏi TCO không
            # khớp field nào sẽ rơi vào bảng thông số chung và được auto-approve.
            return self._forced_hitl(user_message, "tco_requires_human_review")
        acknowledged = self._acknowledgment(
            user_message=user_message,
            draft_answer=draft_answer,
            slots_before=slots_before,
            slots_after=slots_after,
            last_quote_evaluation=last_quote_evaluation,
        )
        if acknowledged is not None:
            return acknowledged
        evaluation, is_quote = self._build(
            user_message=user_message,
            canonical=canonical,
            draft_answer=draft_answer,
            lookup_facts=lookup_facts,
            unresolved_mentions=unresolved_mentions,
            standard_promotions=allowlist,
        )
        if evaluation is not None:
            evaluation = await self._apply_risk_flag_judge(
                evaluation=evaluation,
                user_message=user_message,
                draft_answer=draft_answer,
            )
        delivery = self._classify_delivery(
            evaluation=evaluation,
            is_quote=is_quote,
            has_draft=bool((draft_answer or "").strip()),
            recommendation_count=recommendation_count,
            facts_verified=facts_verified,
            unresolved_entity_count=len(unresolved_mentions),
        )
        tier = delivery.tier
        # Luồng cũ: chạm dữ liệu catalog hoặc đã có bản nháp → chặn. Tính cả khi
        # shadow-mode tắt, vì nó cũng là giá trị dự phòng khi hạ cờ chính sách.
        legacy = legacy_requires_sync_hitl(touched_catalog=bool(lookup_facts) or draft_answer is not None)
        requires_hitl = delivery.requires_hitl
        reasons = delivery.reasons
        if not self.config.risk_policy_enabled and legacy and not requires_hitl:
            # Cờ hạ xuống → lùi hẳn về luồng cũ. Ghi lý do tường minh để dòng
            # audit không trông giống một cờ rủi ro thật bị bật.
            requires_hitl, tier, reasons = True, QuoteRiskTier.SYNC_HITL, ("legacy_policy_flag",)
            delivery = DeliveryDecision(
                action=DeliveryAction.SYNC_REVIEW,
                tier=tier,
                reasons=reasons,
            )
        # Lượt không phải báo giá VÀ không chạm dữ liệu (khách vừa trả lời một
        # câu hỏi slot) thì cả hai luồng đều cho đi thẳng — đếm và audit nó chỉ
        # làm loãng mẫu số của KPI "giảm bao nhiêu lần cần người duyệt".
        gated = is_quote or legacy
        if gated:
            self.shadow = self.shadow.with_turn(legacy=legacy, current=requires_hitl)
        evaluation_payload = _as_payload(evaluation)
        if evaluation is not None:
            evaluation_payload.update(
                {
                    "delivery_action": delivery.action.value,
                    "risk_tier": tier.value,
                }
            )
        decision = QuoteGateDecision(
            tier=tier.value,
            delivery_action=delivery.action.value,
            requires_hitl=requires_hitl,
            legacy_requires_hitl=legacy,
            evaluation=evaluation_payload,
            reasons=reasons,
            escalation_note=(
                escalation_note(user_message, reasons) if requires_hitl and not (draft_answer or "").strip() else None
            ),
            turn_type=TurnType.NEW_REQUEST.value,
            # Chỉ báo giá THẬT mới đáng nhớ. Lượt không phải báo giá (tra thông
            # số) mà ghi đè bộ nhớ thì lượt "ok" sau đó sẽ xác nhận nhầm thứ khác.
            evaluation_to_remember=evaluation_payload if is_quote else None,
        )
        if not gated:
            return decision
        await self._audit(
            decision,
            session_id=session_id,
            run_id=run_id,
            user_message=user_message,
            output_content=draft_answer or rendered_answer or "",
            confidence=evaluation.confidence_score if evaluation is not None else None,
        )
        return decision

    def _forced_hitl(self, user_message: str, reason: str) -> QuoteGateDecision:
        """Chặn không điều kiện, kèm lý do đọc được cho người duyệt."""

        reasons = (reason,)
        return QuoteGateDecision(
            tier=QuoteRiskTier.SYNC_HITL.value,
            delivery_action=DeliveryAction.SYNC_REVIEW.value,
            requires_hitl=True,
            legacy_requires_hitl=True,
            evaluation=_as_payload(QuoteEvaluation.unknown()),
            reasons=reasons,
            escalation_note=escalation_note(user_message, reasons),
        )

    def _direct_advisor_handoff(self, user_message: str) -> QuoteGateDecision:
        """Escalate an explicit human request before any AI retrieval branch."""

        reasons = ("CUSTOMER_REQUESTED_HUMAN",)
        return QuoteGateDecision(
            tier=QuoteRiskTier.ADVISOR_HANDOFF.value,
            delivery_action=DeliveryAction.ADVISOR_HANDOFF.value,
            requires_hitl=True,
            legacy_requires_hitl=True,
            evaluation=_as_payload(QuoteEvaluation.unknown()),
            reasons=reasons,
            escalation_note=escalation_note(user_message, reasons),
            turn_type=TurnType.NEW_REQUEST.value,
        )

    def _acknowledgment(
        self,
        *,
        user_message: str,
        draft_answer: str | None,
        slots_before: Mapping[str, object] | None,
        slots_after: Mapping[str, object] | None,
        last_quote_evaluation: Mapping[str, Any] | None,
    ) -> QuoteGateDecision | None:
        """[A7-5] Lượt chỉ xác nhận báo giá vừa gửi → tái dùng đánh giá cũ.

        Trả `None` nghĩa là "không phải ca này", lượt đi tiếp vào pipeline đầy đủ.

        Ba điều kiện phải đúng cả ba, và không điều kiện nào suy ra được từ hai
        điều kiện kia:

        - chưa có bản nháp: bản nháp nghĩa là lượt này đã chạy hết chuỗi tư vấn,
          nó là một báo giá mới chứ không phải lời đáp cho báo giá cũ;
        - phiên đã từng gửi một báo giá được đánh giá — không có thì "ok" đang
          xác nhận hư không, cứ để pipeline thường xử lý;
        - `classify_turn` nói lượt này không mang thông tin mới.

        `evaluation_to_remember=None` ở cả hai nhánh dưới đây là phần cốt lõi của
        yêu cầu "không reset bộ nhớ": nhánh này không bao giờ ghi gì vào
        `last_quote_evaluation`, nên xác nhận bao nhiêu lượt liên tiếp cũng không
        làm mất đánh giá gốc.
        """

        if (draft_answer or "").strip() or last_quote_evaluation is None:
            return None
        # Lời XIN VIỆC không phải lời xác nhận.
        #
        # BUG THẬT trên prod 2026-08-28: sau bản đề xuất, khách gõ *"đăng ký lái
        # thử"* và nhận lại `NEXT_STEP_REPLY` — hệ mời họ làm đúng cái việc họ
        # vừa xin. `classify_turn` đọc câu đó thành `ACKNOWLEDGMENT` vì nó không
        # mang slot mới nào, tức trông giống một tiếng "ok".
        #
        # Trả `None` ở đây KHÔNG phải bỏ qua cổng: lượt chảy tiếp xuống `_build`
        # và vẫn được chấm rủi ro đầy đủ. Nhờ vậy câu vừa xin lái thử vừa xin
        # giảm giá vẫn bị bắt lại đúng chỗ nó phải bị bắt.
        if explicit_vehicle_type(user_message) is not None:
            # "xe máy" ngay sau "bắt đầu lại" là câu trả lời loại xe, không phải
            # "ok" cho báo giá cũ còn trong bộ nhớ (đo 2026-08-28).
            return None
        if is_restart_task_request(user_message):
            # "bắt đầu lại" không phải "ok": khách xin làm lại mà nhận câu mời
            # bước kế tiếp (đặt lịch lái thử…) là bị lờ (đo 2026-08-28).
            return None
        if is_test_drive_request(user_message):
            return None
        if (
            classify_turn(form_before=slots_before, form_after=slots_after, user_message=user_message)
            is not TurnType.ACKNOWLEDGMENT
        ):
            return None
        remembered = QuoteEvaluation.from_raw(last_quote_evaluation)
        remembered_action = last_quote_evaluation.get("delivery_action")
        if remembered_action in {
            DeliveryAction.AUTO_DELIVER.value,
            DeliveryAction.DELIVER_WITH_AUDIT.value,
        }:
            still_pending = False
        elif remembered_action in {
            DeliveryAction.SYNC_REVIEW.value,
            DeliveryAction.ADVISOR_HANDOFF.value,
        }:
            still_pending = True
        else:
            still_pending = requires_sync_hitl(remembered, self.config.confidence_threshold)
        return QuoteGateDecision(
            tier=QuoteRiskTier.NON_QUOTE.value,
            delivery_action=DeliveryAction.AUTO_DELIVER.value,
            # `False` ở CẢ HAI nhánh: báo giá cũ đang chờ duyệt thì mục duyệt đã
            # nằm trên bàn tư vấn viên rồi. Đẩy thêm một mục nữa cho một tiếng
            # "ok" chỉ làm hàng đợi dài ra mà không ai cần duyệt hai lần.
            requires_hitl=False,
            legacy_requires_hitl=False,
            evaluation=dict(last_quote_evaluation),
            reasons=("reused_last_quote_evaluation",),
            turn_type=TurnType.ACKNOWLEDGMENT.value,
            reply=(acknowledgment_while_pending_reply() if still_pending else next_step_reply()),
            evaluation_to_remember=None,
        )

    def _classify_delivery(
        self,
        *,
        evaluation: QuoteEvaluation | None,
        is_quote: bool,
        has_draft: bool,
        recommendation_count: int,
        facts_verified: bool | None,
        unresolved_entity_count: int,
    ) -> DeliveryDecision:
        """Build semantic output context, then delegate to the pure policy."""

        if has_draft:
            flags = evaluation.risk_flags() if evaluation is not None else {}
            output_kind = OutputKind.RECOMMENDATION if recommendation_count > 0 else OutputKind.COMMERCIAL_REQUEST
            sources = (
                {OutputSource.SNAPSHOT, OutputSource.CONSTRAINED_LLM}
                if recommendation_count > 0
                else {OutputSource.CONSTRAINED_LLM}
            )
            return classify_delivery(
                OutputRiskContext(
                    output_kind=output_kind,
                    source_kinds=sources,
                    facts_verified=facts_verified,
                    unresolved_entity_count=unresolved_entity_count,
                    **flags,
                )
            )
        if not is_quote:
            return DeliveryDecision(
                action=DeliveryAction.AUTO_DELIVER,
                tier=QuoteRiskTier.NON_QUOTE,
            )
        if evaluation is None:
            return DeliveryDecision(
                action=DeliveryAction.SYNC_REVIEW,
                tier=QuoteRiskTier.SYNC_HITL,
                reasons=("risk_evaluation_missing",),
            )
        tier = classify_tier(
            evaluation,
            is_quote=True,
            threshold=self.config.confidence_threshold,
        )
        if tier is QuoteRiskTier.SYNC_HITL:
            flags = evaluation.risk_flags()
            action = (
                DeliveryAction.ADVISOR_HANDOFF
                if any(value is True for value in flags.values())
                else DeliveryAction.SYNC_REVIEW
            )
            return DeliveryDecision(
                action=action,
                tier=(QuoteRiskTier.ADVISOR_HANDOFF if action is DeliveryAction.ADVISOR_HANDOFF else tier),
                reasons=evaluation.triggered_reasons(self.config.confidence_threshold),
            )
        return DeliveryDecision(
            action=DeliveryAction.AUTO_DELIVER,
            tier=tier,
        )

    def _build(
        self,
        *,
        user_message: str,
        canonical: CanonicalText,
        draft_answer: str | None,
        lookup_facts: Sequence[VehicleFacts],
        unresolved_mentions: Sequence[str],
        standard_promotions: frozenset[str],
    ) -> tuple[QuoteEvaluation | None, bool]:
        """Chọn đúng bộ dựng cho từng nguồn nội dung.

        Có bản nháp → nội dung do LLM soạn, không còn deterministic. Chưa có →
        lượt đang đọc catalog (hoặc chưa đọc gì), đánh giá theo nhánh niêm yết.
        """

        if (draft_answer or "").strip():
            # Chuỗi tổng (câu khách + bản nháp) không có canonical trong state —
            # service dựng canonical riêng cho CHÍNH chuỗi đó, không phải fallback
            # cho chuỗi khách.
            combined = f"{user_message}\n{draft_answer or ''}"
            evaluation = evaluate_generated_quote(
                # Risk belongs to the content about to leave the system, not
                # only to the customer's wording. A safe question cannot make
                # an invented discount promise safe.
                user_message=combined,
                canonical=build_canonical_text(combined),
                # [GIẢ ĐỊNH] Chưa có điểm tin cậy nào đi kèm bản nháp synthesis:
                # `SynthesisService.synthesize` trả chuỗi. Để `None` là đúng
                # chiều an toàn — thiếu dữ liệu thì chặn — và nhánh này vốn luôn
                # chặn vì `is_deterministic_standard=False`.
                confidence_score=None,
                standard_promotions=standard_promotions,
            )
            return evaluation, True
        priced = sum(1 for fact in lookup_facts if fact.starting_price_vnd is not None)
        flags = detect_risk_flags(
            user_message=user_message, canonical=canonical, standard_promotions=standard_promotions
        )
        if not is_quote_turn(priced_fact_count=priced, risk_flags=flags):
            # Không phải báo giá (tra thông số, so sánh xe…) → không đánh giá
            # theo chính sách báo giá, cũng không gọi `requires_sync_hitl`.
            return None, False
        evaluation = evaluate_catalog_lookup(
            user_message=user_message,
            canonical=canonical,
            priced_fact_count=priced,
            unresolved_mention_count=len(unresolved_mentions),
            standard_promotions=standard_promotions,
        )
        return evaluation, True

    async def _apply_risk_flag_judge(
        self,
        *,
        evaluation: QuoteEvaluation,
        user_message: str,
        draft_answer: str | None,
    ) -> QuoteEvaluation:
        """J2: lớp HAI cho bốn cờ rủi ro — bắt cam kết bị diễn đạt lại.

        Bất biến (plan mục 2): judge CHỈ THÊM cờ (OR), không gỡ. SHADOW mặc
        định: chỉ log verdict đo, không đổi evaluation. Lỗi/hết quota → adapter
        fail-open không-cờ-nào, evaluation giữ nguyên.
        """

        if self.risk_flag_judge is None or self.sampler() >= RISK_FLAG_SAMPLE_RATE:
            return evaluation
        prediction = await self.risk_flag_judge.judge(user_message=user_message, draft_answer=draft_answer)
        logger.info(
            "quote_gate.risk_flag_judge shadow=%s judge_flags=%s confidence=%s fallback=%s",
            RISK_FLAG_LLM_SHADOW_MODE,
            prediction.flags,
            prediction.confidence,
            prediction.fallback_reason.value if prediction.fallback_reason is not None else None,
        )
        if RISK_FLAG_LLM_SHADOW_MODE:
            return evaluation
        merged = merge_risk_flags(
            evaluation.risk_flags(),
            prediction,
            shadow_mode=False,
            threshold=RISK_FLAG_CONFIDENCE_THRESHOLD,
        )
        if merged == evaluation.risk_flags():
            return evaluation
        return replace(evaluation, **merged)

    async def _audit(
        self,
        decision: QuoteGateDecision,
        *,
        session_id: str,
        run_id: UUID | None,
        user_message: str,
        output_content: str,
        confidence: float | None,
    ) -> None:
        """Ghi audit; hỏng thì log rồi đi tiếp — audit không được giết lượt của khách."""

        if self.audit is None:
            return
        entry = QuoteAuditRecord(
            session_id=session_id,
            run_id=run_id,
            tier=decision.tier,
            requires_hitl=decision.requires_hitl,
            legacy_requires_hitl=decision.legacy_requires_hitl,
            user_message=user_message,
            output_content=output_content,
            evaluation=decision.evaluation,
            reasons=decision.reasons,
            # Log 100% case auto-approve; cờ `sampled_for_review` chỉ chọn ra
            # phần người phụ trách phải đọc định kỳ.
            sampled_for_review=(not decision.requires_hitl and self.sampler() < self.config.audit_sample_rate),
            # Cận ngưỡng thì log riêng KỂ CẢ khi đã bị chặn: đó chính là tập dữ
            # liệu dùng để biết hạ ngưỡng xuống đâu thì vẫn an toàn.
            near_threshold=is_near_threshold(
                confidence, self.config.confidence_threshold, self.config.near_threshold_margin
            ),
            shadow_mode=self.config.shadow_mode_enabled,
        )
        try:
            await self.audit.record(entry)
        except Exception:  # noqa: BLE001 — audit hỏng không được lộ ra phía khách
            logger.exception("quote gate: ghi audit thất bại cho phiên %s", session_id)


def _as_payload(evaluation: QuoteEvaluation | None) -> dict[str, object]:
    """Phẳng hoá về dict để DTO đi qua `nodes/` mà không kéo theo `domain/`."""

    return {} if evaluation is None else dict(evaluation.model_dump())


def _offer_display_name(offer: Mapping[str, Any]) -> str:
    """`display_name` của offer ACTIVE, dùng cho allowlist containment (T6)."""
    name = offer.get("display_name")
    if isinstance(name, str) and name.strip():
        return name
    code = offer.get("promotion_code")
    return code if isinstance(code, str) and code else ""


__all__ = [
    "QuoteGateConfig",
    "QuoteGateServiceImpl",
    "ShadowComparison",
    "requires_sync_hitl",
]
