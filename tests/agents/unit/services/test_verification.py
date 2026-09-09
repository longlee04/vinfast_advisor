"""Contract tests for the A6-1 numeric evidence guardrail."""

from uuid import UUID

import pytest

from src.agents.services.verification import (
    DefaultVerificationService,
    VerificationEvidence,
)

RUN_ID = UUID("10000000-0000-0000-0000-000000000101")
RANGE_EVIDENCE_ID = UUID("30000000-0000-0000-0000-000000000101")
PRICE_EVIDENCE_ID = UUID("30000000-0000-0000-0000-000000000102")


class FakeVerificationSource:
    def __init__(self) -> None:
        self.calls: list[UUID] = []

    async def load_evidence(self, run_id: UUID) -> tuple[VerificationEvidence, ...]:
        self.calls.append(run_id)
        return (
            VerificationEvidence(
                evidence_id=RANGE_EVIDENCE_ID,
                fact_code="CAR_RANGE_KM",
                value_text="399",
            ),
            VerificationEvidence(
                evidence_id=PRICE_EVIDENCE_ID,
                fact_code="STARTING_PRICE_VND",
                value_text="690000000",
            ),
        )

    async def load_vehicle_names(self, run_id: UUID) -> tuple[str, ...]:
        return ()


class SemanticVerificationSource(FakeVerificationSource):
    def __init__(self, excerpt: str) -> None:
        super().__init__()
        self._excerpt = excerpt

    async def load_evidence(self, run_id: UUID) -> tuple[VerificationEvidence, ...]:
        return (
            *(await super().load_evidence(run_id)),
            VerificationEvidence(
                evidence_id=UUID("30000000-0000-0000-0000-000000000103"),
                fact_code="DOC_EXCERPT",
                value_text=self._excerpt,
            ),
        )


@pytest.mark.asyncio
async def test_accepts_every_exact_number_with_matching_evidence() -> None:
    source = FakeVerificationSource()
    service = DefaultVerificationService(source=source)
    answer = (
        f"Tầm hoạt động 399 km [evidence_id:{RANGE_EVIDENCE_ID}], giá 690000000 VND [evidence_id:{PRICE_EVIDENCE_ID}]."
    )

    assert await service.verify(run_id=RUN_ID, draft_answer=answer) is True
    assert source.calls == [RUN_ID]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer",
    [
        f"Tầm hoạt động 400 km [evidence_id:{RANGE_EVIDENCE_ID}].",
        "Tầm hoạt động 399 km.",
        f"Tầm hoạt động 399 km [evidence_id:{PRICE_EVIDENCE_ID}].",
        f"Tầm hoạt động 399 km. [evidence_id:{RANGE_EVIDENCE_ID}]",
        f"Không có số liệu [evidence_id:{RANGE_EVIDENCE_ID}].",
        f"Mức 399 km [evidence_id:{RANGE_EVIDENCE_ID}] và thêm 7 chỗ.",
        "Giá dạng khoa học 1e9 VND.",
    ],
)
async def test_rejects_wrong_uncited_mismatched_or_unpaired_numbers(answer: str) -> None:
    service = DefaultVerificationService(source=FakeVerificationSource())

    assert await service.verify(run_id=RUN_ID, draft_answer=answer) is False


@pytest.mark.asyncio
async def test_text_without_numeric_claims_is_valid() -> None:
    service = DefaultVerificationService(source=FakeVerificationSource())

    assert await service.verify(run_id=RUN_ID, draft_answer="Mẫu này phù hợp với nhu cầu của bạn.")


@pytest.mark.asyncio
async def test_rejects_index_footnotes_that_were_not_rewritten() -> None:
    service = DefaultVerificationService(source=FakeVerificationSource())

    assert (
        await service.verify(
            run_id=RUN_ID,
            draft_answer="Tầm hoạt động 399 km [1] và giá 690000000 VND [2].",
        )
        is False
    )


@pytest.mark.asyncio
async def test_rejects_long_distance_claim_when_document_is_urban_only() -> None:
    quote_id = UUID("30000000-0000-0000-0000-000000000103")
    excerpt = "Mẫu xe phù hợp với nhu cầu di chuyển trong đô thị và các chuyến đi ngắn."
    service = DefaultVerificationService(source=SemanticVerificationSource(excerpt))
    answer = (
        f'Tài liệu ghi: "{excerpt}" [evidence_id:{quote_id}] '
        f"Tầm hoạt động 399 km [evidence_id:{RANGE_EVIDENCE_ID}], "
        "rất lý tưởng cho những chuyến đi xa."
    )

    assert await service.verify(run_id=RUN_ID, draft_answer=answer) is False


@pytest.mark.asyncio
async def test_rejects_go_home_suitability_claim_when_document_is_urban_only() -> None:
    quote_id = UUID("30000000-0000-0000-0000-000000000103")
    excerpt = "Mẫu xe phù hợp di chuyển trong đô thị và các chuyến đi ngắn."
    service = DefaultVerificationService(source=SemanticVerificationSource(excerpt))
    answer = (
        f'Tài liệu ghi: "{excerpt}" [evidence_id:{quote_id}] Mẫu xe này rất phù hợp với nhu cầu thường xuyên đi về quê.'
    )

    assert await service.verify(run_id=RUN_ID, draft_answer=answer) is False


@pytest.mark.asyncio
async def test_accepts_long_distance_claim_only_with_supporting_document() -> None:
    quote_id = UUID("30000000-0000-0000-0000-000000000103")
    excerpt = "Tầm hoạt động và khả năng sạc nhanh phù hợp cho các chuyến đi xa, đường dài."
    service = DefaultVerificationService(source=SemanticVerificationSource(excerpt))
    answer = (
        f'Tài liệu ghi: "{excerpt}" [evidence_id:{quote_id}] '
        f"Tầm hoạt động 399 km [evidence_id:{RANGE_EVIDENCE_ID}], "
        "phù hợp cho những chuyến đi xa."
    )

    assert await service.verify(run_id=RUN_ID, draft_answer=answer) is True


@pytest.mark.asyncio
async def test_uncited_document_cannot_support_semantic_claim() -> None:
    service = DefaultVerificationService(source=SemanticVerificationSource("Mẫu xe phù hợp cho những chuyến đi xa."))
    answer = f"Tầm hoạt động 399 km [evidence_id:{RANGE_EVIDENCE_ID}], phù hợp cho những chuyến đi xa."

    assert await service.verify(run_id=RUN_ID, draft_answer=answer) is False


@pytest.mark.asyncio
async def test_number_words_require_a_matching_cited_evidence() -> None:
    """Số viết chữ không được lọt guardrail nếu không có evidence khớp."""
    service = DefaultVerificationService(source=FakeVerificationSource())
    answer = "Giá của mẫu này là ba trăm triệu đồng."

    assert await service.verify(run_id=RUN_ID, draft_answer=answer) is False


@pytest.mark.asyncio
async def test_number_words_pass_when_cited_evidence_matches() -> None:
    """Số viết chữ có evidence khớp giá trị thì pass như số digit."""
    service = DefaultVerificationService(source=FakeVerificationSource())
    answer = (
        "Giá của mẫu này là sáu trăm chín mươi triệu đồng "
        f"[evidence_id:{PRICE_EVIDENCE_ID}]."
    )

    assert await service.verify(run_id=RUN_ID, draft_answer=answer) is True
