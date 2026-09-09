"""A6-1 mo rong: trich dan van ban phai khop nguyen van evidence cung run."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest

from src.agents.services.verification import (
    DefaultVerificationService,
    VerificationEvidence,
)


class _Source:
    def __init__(
        self,
        evidence: Sequence[VerificationEvidence],
        vehicle_names: Sequence[str] = (),
    ) -> None:
        self._evidence = evidence
        self._vehicle_names = vehicle_names

    async def load_evidence(self, run_id: UUID) -> Sequence[VerificationEvidence]:
        return self._evidence

    async def load_vehicle_names(self, run_id: UUID) -> Sequence[str]:
        return self._vehicle_names


@pytest.mark.asyncio
async def test_quote_matching_evidence_passes() -> None:
    evidence_id = uuid4()
    service = DefaultVerificationService(
        source=_Source(
            [
                VerificationEvidence(
                    evidence_id=evidence_id,
                    fact_code="DOC_EXCERPT",
                    value_text="Cửa sổ trời toàn cảnh chống tia UV",
                )
            ]
        )
    )

    draft = f'Theo tài liệu: "Cửa sổ trời toàn cảnh chống tia UV" [evidence_id:{evidence_id}]'

    assert await service.verify(run_id=uuid4(), draft_answer=draft) is True


@pytest.mark.asyncio
async def test_quote_altered_by_one_word_is_rejected() -> None:
    evidence_id = uuid4()
    service = DefaultVerificationService(
        source=_Source(
            [
                VerificationEvidence(
                    evidence_id=evidence_id,
                    fact_code="DOC_EXCERPT",
                    value_text="Cửa sổ trời toàn cảnh chống tia UV",
                )
            ]
        )
    )

    draft = f'Theo tài liệu: "Cửa sổ trời toàn cảnh chống tia cực tím" [evidence_id:{evidence_id}]'

    assert await service.verify(run_id=uuid4(), draft_answer=draft) is False


@pytest.mark.asyncio
async def test_quote_without_any_evidence_is_rejected() -> None:
    service = DefaultVerificationService(source=_Source(()))

    draft = f'Theo tài liệu: "Xe co cua so troi" [evidence_id:{uuid4()}]'

    assert await service.verify(run_id=uuid4(), draft_answer=draft) is False


@pytest.mark.asyncio
async def test_model_name_digits_are_allowed_only_when_name_is_in_the_run_snapshot() -> None:
    evidence_id = uuid4()
    service = DefaultVerificationService(
        source=_Source(
            [
                VerificationEvidence(
                    evidence_id=evidence_id,
                    fact_code="STARTING_PRICE_VND",
                    value_text="436000000",
                )
            ],
            vehicle_names=["VinFast VF 5 Plus"],
        )
    )
    answer = f"Em gợi ý VinFast VF 5 Plus, giá từ 436000000 VND [evidence_id:{evidence_id}]."

    assert await service.verify(run_id=uuid4(), draft_answer=answer)


@pytest.mark.asyncio
async def test_invented_model_name_digits_are_still_rejected() -> None:
    service = DefaultVerificationService(source=_Source([], vehicle_names=["VinFast VF 5 Plus"]))

    assert not await service.verify(run_id=uuid4(), draft_answer="Em gợi ý VF 12.")


@pytest.mark.asyncio
async def test_exact_quote_with_vehicle_name_is_checked_before_name_masking() -> None:
    evidence_id = uuid4()
    service = DefaultVerificationService(
        source=_Source(
            [
                VerificationEvidence(
                    evidence_id=evidence_id,
                    fact_code="DOC_EXCERPT",
                    value_text="VF 8 có cửa sổ trời",
                )
            ],
            vehicle_names=["VF 8"],
        )
    )
    answer = f'Theo tài liệu: "VF 8 có cửa sổ trời" [evidence_id:{evidence_id}]'

    assert await service.verify(run_id=uuid4(), draft_answer=answer)


@pytest.mark.asyncio
async def test_full_retrieval_excerpt_longer_than_four_hundred_chars_is_verified() -> None:
    evidence_id = uuid4()
    excerpt = "Nội dung tài liệu đã xác minh. " * 18
    service = DefaultVerificationService(
        source=_Source(
            [
                VerificationEvidence(
                    evidence_id=evidence_id,
                    fact_code="DOC_EXCERPT",
                    value_text=excerpt,
                )
            ]
        )
    )

    answer = f'Theo tài liệu: "{excerpt}" [evidence_id:{evidence_id}]'

    assert await service.verify(run_id=uuid4(), draft_answer=answer)
