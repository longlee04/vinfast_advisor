"""Integration tests for OfferSuggestionService against real PostgreSQL."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.agents.domain.customer_profile import (
    Bottleneck,
    BottleneckEvidence,
    OfferState,
    ProfileSnapshot,
)
from src.products.application.offer_suggestion_service import OfferSuggestionService
from src.products.domain.values import PromotionType, RecordLifecycleStatus
from src.products.infrastructure.models import PromotionRow
from src.products.infrastructure.promotion_repository import SqlAlchemyPromotionRepository

NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


def _price_snapshot() -> ProfileSnapshot:
    return ProfileSnapshot(
        needs=["budget"],
        considered_vehicles=[],
        bottlenecks=[BottleneckEvidence(bottleneck=Bottleneck.PRICE, verbatim_quote="giá cao")],
        offer_state=OfferState.BOTTLENECK_NO_OFFER,
        unmet_demand_flag=True,
        unmet_bottleneck="PRICE",
        color_preference=None,
    )


async def _insert_promotion(session_factory, **overrides) -> None:
    async with session_factory() as session, session.begin():
        row = PromotionRow(
            promotion_id=str(uuid4()),
            promotion_code=overrides.get("promotion_code", "FINANCING-1"),
            title=overrides.get("title", "Hỗ trợ tài chính"),
            promotion_type=overrides.get("promotion_type", PromotionType.FINANCING.value),
            region_code="VN",
            eligibility_rules={},
            status=overrides.get("status", RecordLifecycleStatus.ACTIVE.value),
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            valid_to=overrides.get("valid_to"),
            created_at=NOW,
            updated_at=NOW,
            gift_group=overrides.get("gift_group"),
        )
        session.add(row)


@pytest.mark.asyncio
async def test_suggest_returns_offer_available_with_match(product_session_factory) -> None:
    # Given: DB có 1 promotion ACTIVE FINANCING.
    await _insert_promotion(product_session_factory)

    service = OfferSuggestionService(SqlAlchemyPromotionRepository(product_session_factory))

    # When
    suggestion = await service.suggest(_price_snapshot(), NOW)

    # Then
    assert suggestion.offer_state is OfferState.BOTTLENECK_OFFER_AVAILABLE
    assert len(suggestion.matched) == 1
    assert suggestion.matched[0].promotion.promotion_type is PromotionType.FINANCING
    assert suggestion.unmet_demand_flag is False


@pytest.mark.asyncio
async def test_suggest_returns_no_offer_when_db_empty(product_session_factory) -> None:
    # Given: DB rỗng promotions.
    service = OfferSuggestionService(SqlAlchemyPromotionRepository(product_session_factory))

    # When
    suggestion = await service.suggest(_price_snapshot(), NOW)

    # Then
    assert suggestion.offer_state is OfferState.BOTTLENECK_NO_OFFER
    assert suggestion.matched == []
    assert suggestion.unmet_demand_flag is True
    assert suggestion.unmet_bottleneck == "PRICE"


@pytest.mark.asyncio
async def test_suggest_skips_expired_promotion(product_session_factory) -> None:
    # Given: promotion EXPIRED.
    await _insert_promotion(product_session_factory, status=RecordLifecycleStatus.EXPIRED.value)

    service = OfferSuggestionService(SqlAlchemyPromotionRepository(product_session_factory))

    # When
    suggestion = await service.suggest(_price_snapshot(), NOW)

    # Then
    assert suggestion.offer_state is OfferState.BOTTLENECK_NO_OFFER
    assert suggestion.matched == []


@pytest.mark.asyncio
async def test_suggest_skips_promotion_past_valid_to(product_session_factory) -> None:
    # Given: promotion valid_to trong quá khứ.
    await _insert_promotion(product_session_factory, valid_to=datetime(2026, 5, 1, tzinfo=UTC))

    service = OfferSuggestionService(SqlAlchemyPromotionRepository(product_session_factory))

    # When
    suggestion = await service.suggest(_price_snapshot(), NOW)

    # Then
    assert suggestion.offer_state is OfferState.BOTTLENECK_NO_OFFER
    assert suggestion.matched == []


@pytest.mark.asyncio
async def test_suggest_none_bottleneck_yields_none_state(product_session_factory) -> None:
    # Given: snapshot không nút thắt + DB có promotion.
    await _insert_promotion(product_session_factory)
    snapshot = ProfileSnapshot(
        needs=[],
        considered_vehicles=[],
        bottlenecks=[],
        offer_state=OfferState.NONE_BOTTLENECK,
        unmet_demand_flag=False,
        unmet_bottleneck=None,
        color_preference=None,
    )
    service = OfferSuggestionService(SqlAlchemyPromotionRepository(product_session_factory))

    # When
    suggestion = await service.suggest(snapshot, NOW)

    # Then
    assert suggestion.offer_state is OfferState.NONE_BOTTLENECK
    assert suggestion.matched == []
    assert suggestion.unmet_demand_flag is False
