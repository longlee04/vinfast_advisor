"""Ưu đãi theo CƠ HỘI: gợi ý phù hợp (DSL), đề xuất, duyệt, gửi, chốt (plan Customer 360 Phase 5B).

Luật hợp lệ đánh giá TẤT ĐỊNH (`products.domain.eligibility_rules`), không qua LLM. Mọi
con số gửi khách đi qua `session_offers` → `offer_reply.offer_announcement` như đường cũ; ở đây
chỉ quyết định ĐƯỢC gửi hay không và ghi vết.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from src.agents.domain.agent_flag import AgentFlagState
from src.agents.domain.customer360_flags import FLAG_OFFER_LIFECYCLE, FLAG_OFFER_RULES, is_globally_on
from src.agents.domain.offer_lifecycle import (
    OfferStatus,
    PromotionGate,
    SendBlocked,
    check_transition,
    initial_status,
    needs_manager_approval,
    promotion_blocker,
    send_blocker,
)
from src.products.domain.eligibility_rules import Eligibility, evaluate


@dataclass(frozen=True, slots=True)
class PromotionCandidate:
    promotion_code: str
    title: str
    promotion_type: str
    discount_amount_vnd: int | None
    discount_percent: float | None
    eligibility_rules: Mapping[str, Any]
    priority: int
    stackable: bool
    requires_advisor_approval: bool
    advisor_max_discount_vnd: int | None
    #: Tên mẫu xe áp dụng (rỗng = mọi xe).
    vehicle_models: tuple[str, ...]
    gate: PromotionGate


@dataclass(frozen=True, slots=True)
class OfferView:
    offer_id: str
    opportunity_id: str
    customer_id: str
    promotion_code: str
    status: OfferStatus
    discount_vnd: int | None
    needs_manager_approval: bool
    proposed_value: Mapping[str, Any] = field(default_factory=dict)


class OfferBlockedError(Exception):
    def __init__(self, reason: SendBlocked | str) -> None:
        super().__init__(str(reason))
        self.reason = str(reason)


class OffersDisabledError(Exception):
    """Cờ ưu đãi đang TẮT."""


class PromotionCatalog(Protocol):
    async def candidates(self, at: datetime) -> list[PromotionCandidate]: ...
    async def gate(self, promotion_code: str) -> PromotionGate | None: ...
    async def consume_use(self, promotion_code: str) -> bool: ...


class OpportunityOfferRepository(Protocol):
    async def opportunity_context(self, opportunity_id: str) -> tuple[str, dict[str, Any]] | None: ...
    async def create(
        self,
        *,
        opportunity_id: str,
        customer_id: str,
        candidate: PromotionCandidate,
        eligibility: str,
        reasons: Sequence[str],
        status: OfferStatus,
        proposed_value: Mapping[str, Any],
        discount_vnd: int | None,
        needs_manager: bool,
        actor: str,
        at: datetime,
    ) -> OfferView: ...
    async def get(self, offer_id: str) -> OfferView | None: ...
    async def transition(
        self,
        offer_id: str,
        current: OfferStatus,
        target: OfferStatus,
        actor: str,
        at: datetime,
        meta: Mapping[str, Any],
    ) -> OfferView | None: ...
    async def deliver(self, offer: OfferView, candidate_title: str, actor: str, at: datetime) -> str | None: ...
    async def list_for_customer(self, customer_id: str) -> list[dict[str, Any]]: ...
    async def expire_due(self, at: datetime) -> int: ...
    async def stats(self, promotion_code: str | None) -> list[dict[str, Any]]: ...


class FlagReader(Protocol):
    async def load(self, name: str) -> AgentFlagState | None: ...


def _norm(text: str) -> str:
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _vehicle_verdict(candidate: PromotionCandidate, context: Mapping[str, Any]) -> Eligibility | None:
    if not candidate.vehicle_models:
        return None
    wanted = context.get("vehicle_model")
    if not wanted:
        return Eligibility.NEED_INFO
    target = _norm(str(wanted))
    return (
        Eligibility.ELIGIBLE
        if any(_norm(model) in target or target in _norm(model) for model in candidate.vehicle_models)
        else Eligibility.INELIGIBLE
    )


def _discount_vnd(candidate: PromotionCandidate, proposed: Mapping[str, Any]) -> int | None:
    amount = proposed.get("amount_vnd")
    if isinstance(amount, int | float) and amount > 0:
        return int(amount)
    return candidate.discount_amount_vnd


class OpportunityOfferOperations:
    def __init__(
        self,
        repository: OpportunityOfferRepository,
        catalog: PromotionCatalog,
        *,
        clock: Callable[[], datetime],
        flags: FlagReader | None = None,
    ) -> None:
        self._repository = repository
        self._catalog = catalog
        self._clock = clock
        self._flags = flags

    async def _require(self, name: str) -> None:
        if self._flags is None or not is_globally_on(await self._flags.load(name)):
            raise OffersDisabledError

    async def eligible(self, opportunity_id: str) -> dict[str, Any] | None:
        """Ưu đãi phù hợp (ELIGIBLE, kèm lý do) và cần hỏi thêm (NEED_INFO, kèm câu hỏi)."""

        await self._require(FLAG_OFFER_RULES)
        found = await self._repository.opportunity_context(opportunity_id)
        if found is None:
            return None
        _customer_id, context = found
        at = self._clock()
        eligible: list[dict[str, Any]] = []
        need_info: list[dict[str, Any]] = []
        for candidate in sorted(await self._catalog.candidates(at), key=lambda item: item.priority):
            if promotion_blocker(candidate.gate, at) is not None:
                continue
            result = evaluate(candidate.eligibility_rules, context)
            vehicle = _vehicle_verdict(candidate, context)
            if result.status in {Eligibility.INELIGIBLE, Eligibility.INVALID_RULE} or vehicle is Eligibility.INELIGIBLE:
                continue
            base = {
                "promotion_code": candidate.promotion_code,
                "title": candidate.title,
                "promotion_type": candidate.promotion_type,
                "discount_amount_vnd": candidate.discount_amount_vnd,
                "discount_percent": candidate.discount_percent,
                "stackable": candidate.stackable,
                "advisor_max_discount_vnd": candidate.advisor_max_discount_vnd,
            }
            missing = list(result.missing_fields) + (["vehicle_model"] if vehicle is Eligibility.NEED_INFO else [])
            if missing:
                hints = list(result.question_hints) + (
                    ["Anh/chị đang quan tâm mẫu xe nào ạ?"] if vehicle is Eligibility.NEED_INFO else []
                )
                need_info.append({**base, "missing_fields": missing, "question_hints": hints})
            else:
                eligible.append({**base, "reasons": list(result.reasons)})
        return {"eligible": eligible, "need_info": need_info}

    async def create(
        self, opportunity_id: str, promotion_code: str, proposed_value: Mapping[str, Any], actor: str
    ) -> OfferView:
        """TVV đề xuất một ưu đãi đang hợp lệ cho cơ hội. Vượt ngưỡng → chờ quản lý (SUGGESTED)."""

        await self._require(FLAG_OFFER_LIFECYCLE)
        found = await self._repository.opportunity_context(opportunity_id)
        if found is None:
            raise OfferBlockedError("OPPORTUNITY_NOT_FOUND")
        customer_id, context = found
        at = self._clock()
        candidate = next(
            (item for item in await self._catalog.candidates(at) if item.promotion_code == promotion_code), None
        )
        if candidate is None:
            raise OfferBlockedError(SendBlocked.PROMOTION_NOT_ACTIVE)
        blocker = promotion_blocker(candidate.gate, at)
        if blocker is not None:
            raise OfferBlockedError(blocker)
        result = evaluate(candidate.eligibility_rules, context)
        vehicle = _vehicle_verdict(candidate, context)
        if result.status in {Eligibility.INELIGIBLE, Eligibility.INVALID_RULE} or vehicle is Eligibility.INELIGIBLE:
            raise OfferBlockedError("INELIGIBLE")
        eligibility = (
            "NEED_INFO" if result.status is Eligibility.NEED_INFO or vehicle is Eligibility.NEED_INFO else "ELIGIBLE"
        )
        discount = _discount_vnd(candidate, proposed_value)
        manager = needs_manager_approval(discount, candidate.advisor_max_discount_vnd)
        return await self._repository.create(
            opportunity_id=opportunity_id,
            customer_id=customer_id,
            candidate=candidate,
            eligibility=eligibility,
            reasons=list(result.reasons) or list(result.missing_fields),
            status=initial_status(manager),
            proposed_value=dict(proposed_value),
            discount_vnd=discount,
            needs_manager=manager,
            actor=actor,
            at=at,
        )

    async def _move(
        self, offer_id: str, target: OfferStatus, actor: str, meta: Mapping[str, Any] | None = None
    ) -> OfferView:
        offer = await self._repository.get(offer_id)
        if offer is None:
            raise OfferBlockedError("OFFER_NOT_FOUND")
        check_transition(offer.status, target)
        moved = await self._repository.transition(offer_id, offer.status, target, actor, self._clock(), meta or {})
        if moved is None:
            raise OfferBlockedError("CONFLICT")
        return moved

    async def approve(self, offer_id: str, manager: str) -> OfferView:
        """Quản lý (Admin) duyệt đề xuất vượt ngưỡng."""

        await self._require(FLAG_OFFER_LIFECYCLE)
        return await self._move(offer_id, OfferStatus.APPROVED, manager, {"approved_by": manager})

    async def send(self, offer_id: str, actor: str) -> OfferView:
        """Gửi cho khách — hàng rào kiểm NGAY LÚC GỬI, rồi ghi `session_offers` cho agent."""

        await self._require(FLAG_OFFER_LIFECYCLE)
        offer = await self._repository.get(offer_id)
        if offer is None:
            raise OfferBlockedError("OFFER_NOT_FOUND")
        at = self._clock()
        blocker = send_blocker(offer.status, await self._catalog.gate(offer.promotion_code), at)
        if blocker is not None:
            raise OfferBlockedError(blocker)
        if not await self._catalog.consume_use(offer.promotion_code):
            raise OfferBlockedError(SendBlocked.NO_USES_LEFT)
        candidate = next(
            (item for item in await self._catalog.candidates(at) if item.promotion_code == offer.promotion_code), None
        )
        session_offer_id = await self._repository.deliver(
            offer, candidate.title if candidate else offer.promotion_code, actor, at
        )
        if session_offer_id is None:
            raise OfferBlockedError(SendBlocked.NO_OPEN_SESSION)
        return await self._move(offer_id, OfferStatus.SENT, actor, {"session_offer_id": session_offer_id})

    async def mark(self, offer_id: str, target: OfferStatus, actor: str) -> OfferView:
        """ENGAGED / CONVERTED / DISMISSED do TVV bấm."""

        await self._require(FLAG_OFFER_LIFECYCLE)
        return await self._move(offer_id, target, actor)

    async def list_for_customer(self, customer_id: str) -> list[dict[str, Any]]:
        return await self._repository.list_for_customer(customer_id)

    async def expire_due(self) -> int:
        return await self._repository.expire_due(self._clock())

    async def stats(self, promotion_code: str | None = None) -> list[dict[str, Any]]:
        return await self._repository.stats(promotion_code)


class ActivePromotionGuard:
    """Hàng rào lúc AGENT TRẢ LỜI (plan §2.4): chỉ được nhắc ưu đãi còn ACTIVE và còn hạn.

    `session_offers` có thể còn ACTIVE trong khi admin đã huỷ/hết hạn ưu đãi gốc. Cờ
    `offer_lifecycle` TẮT → cho qua tất cả (hành vi cũ).
    """

    def __init__(self, catalog: PromotionCatalog, flags: FlagReader | None, clock: Callable[[], datetime]) -> None:
        self._catalog = catalog
        self._flags = flags
        self._clock = clock

    async def allowed(self, promotion_codes: Sequence[str]) -> set[str]:
        codes = set(promotion_codes)
        if self._flags is None or not is_globally_on(await self._flags.load(FLAG_OFFER_LIFECYCLE)):
            return codes
        at = self._clock()
        allowed = set()
        for code in codes:
            gate = await self._catalog.gate(code)
            # Hết suất không chặn NHẮC LẠI ưu đãi đã cấp — suất đã tính lúc gửi.
            if (
                gate is not None
                and gate.status == "ACTIVE"
                and gate.valid_from <= at
                and (gate.valid_to is None or gate.valid_to >= at)
            ):
                allowed.add(code)
        return allowed


__all__ = [
    "ActivePromotionGuard",
    "OfferBlockedError",
    "OfferView",
    "OffersDisabledError",
    "OpportunityOfferOperations",
    "PromotionCandidate",
]
