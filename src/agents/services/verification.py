"""Snapshot-backed numeric evidence verification for A6-1."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final, Protocol
from uuid import UUID

from src.agents.domain.number_word_parser import replace_number_words
from src.agents.domain.semantic_validation import semantic_claims_are_supported
from src.agents.logging import get_agent_logger

logger = get_agent_logger("agent.services.verification")

CITATION_PATTERN: Final[re.Pattern[str]] = re.compile(r"\[evidence_id:(?P<evidence_id>[0-9a-fA-F-]{36})\]")
QUOTE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[\"“](?P<quote>[^\"”]{1,1000})[\"”]\s*"
    r"\[evidence_id:(?P<evidence_id>[0-9a-fA-F-]{36})\]"
)
CLAIM_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?P<number>(?<![\w])[-+]?\d+(?:[.,]\d+)*(?![\w]))"
    r"(?P<context>[^\d.;!?\n\[\]]{0,40})"
    r"\[evidence_id:(?P<evidence_id>[0-9a-fA-F-]{36})\]"
)


@dataclass(frozen=True, slots=True)
class VerificationEvidence:
    """Numeric value that one run is allowed to cite."""

    evidence_id: UUID
    fact_code: str
    value_text: str


class VerificationDataSource(Protocol):
    """Load immutable evidence rows belonging to one run."""

    async def load_evidence(self, run_id: UUID) -> Sequence[VerificationEvidence]: ...

    async def load_vehicle_names(self, run_id: UUID) -> Sequence[str]: ...


class DefaultVerificationService:
    """Reject any numeric claim lacking an exact same-run evidence citation."""

    def __init__(self, *, source: VerificationDataSource) -> None:
        self._source = source

    async def verify(self, *, run_id: UUID, draft_answer: str) -> bool:
        """Return true only when all numbers are paired with exact evidence values."""

        def _reject(reason: str) -> bool:
            # Chẩn đoán tạm (Sếp yêu cầu 2026-08-23): guardrail chặn draft nhưng
            # không để lại dấu vết lý do, khiến mọi lần fail đều phải đoán mù.
            # Log rút gọn draft để soi case thật, gỡ sau khi hết cần debug.
            logger.warning(
                "verify tu choi draft (run_id=%s, ly do=%s): %r",
                run_id,
                reason,
                draft_answer[:800],
            )
            return False

        evidence = tuple(await self._source.load_evidence(run_id))
        evidence_by_id = {item.evidence_id: item for item in evidence}
        if len(evidence_by_id) != len(evidence):
            return _reject("evidence_id trung lap trong run_evidence")
        quotes = tuple(QUOTE_PATTERN.finditer(draft_answer))
        cited_document_evidence: list[str] = []
        for quote in quotes:
            try:
                quote_evidence_id = UUID(quote.group("evidence_id"))
            except ValueError:
                return _reject("quote evidence_id khong parse duoc UUID")
            quoted_source = evidence_by_id.get(quote_evidence_id)
            if quoted_source is None:
                return _reject("quote evidence_id khong co trong run_evidence")
            if quote.group("quote") != quoted_source.value_text:
                return _reject(
                    f"quote text lech evidence: draft={quote.group('quote')!r} evidence={quoted_source.value_text!r}"
                )
            if quoted_source.fact_code == "DOC_EXCERPT":
                cited_document_evidence.append(quoted_source.value_text)
        if not semantic_claims_are_supported(draft_answer, cited_document_evidence):
            return _reject("semantic_claims_are_supported tra False")
        draft_answer_masked = QUOTE_PATTERN.sub(" ", draft_answer)
        names = tuple(await self._source.load_vehicle_names(run_id))
        draft_answer_masked = _mask_vehicle_names(draft_answer_masked, names)
        # T2: số viết chữ ("ba trăm triệu") cũng là con số. Đổi số chữ thành digit
        # ĐỂ claim/digit check bên dưới xử lý nó y hệt số digit — chưa cite thì rơi
        # vào nhánh "còn chữ số ngoài citation".
        draft_answer_masked = replace_number_words(draft_answer_masked)
        claims = tuple(CLAIM_PATTERN.finditer(draft_answer_masked))
        citation_count = len(tuple(CITATION_PATTERN.finditer(draft_answer_masked)))
        if len(claims) != citation_count:
            return _reject(f"so claim ({len(claims)}) khac so citation ({citation_count}) sau khi mask quote/ten xe")
        cited_digit_positions: set[int] = set()
        for claim in claims:
            try:
                evidence_id = UUID(claim.group("evidence_id"))
            except ValueError:
                return _reject("claim evidence_id khong parse duoc UUID")
            source = evidence_by_id.get(evidence_id)
            if source is None:
                return _reject("claim evidence_id khong co trong run_evidence")
            if not _same_number(claim.group("number"), source.value_text):
                return _reject(
                    f"so trong claim lech evidence: draft={claim.group('number')!r} evidence={source.value_text!r}"
                )
            start, end = claim.span("number")
            cited_digit_positions.update(index for index in range(start, end) if draft_answer_masked[index].isdigit())
        uncited_view = CITATION_PATTERN.sub(lambda match: " " * len(match.group(0)), draft_answer_masked)
        digit_positions = {index for index, character in enumerate(uncited_view) if character.isdigit()}
        if digit_positions != cited_digit_positions:
            return _reject(
                "con chu so ngoai citation sau khi mask quote/ten xe "
                f"(uncited_positions={sorted(digit_positions - cited_digit_positions)})"
            )
        return True


def _mask_vehicle_names(draft_answer: str, names: Sequence[str]) -> str:
    """Hide only run-scoped model-name digits before checking numeric claims."""

    masked = draft_answer
    unique_names = {name for name in names if name.strip()}
    for name in sorted(unique_names, key=len, reverse=True):
        pattern = re.compile(re.escape(name), re.IGNORECASE)
        masked = pattern.sub(lambda match: " " * len(match.group(0)), masked)
    return masked


def _same_number(draft_text: str, evidence_text: str | None) -> bool:
    """ "457" và "457.00" là MỘT con số: snapshot lưu Decimal chuỗi, câu viết cho khách
    đã cắt số 0 thừa (2026-08-28). So chuỗi thì mọi bản đề xuất có số thập phân
    đều bị loại rồi đẩy tư vấn viên (prod 17:25 29/08)."""

    if evidence_text is None:
        return False
    if draft_text == evidence_text:
        return True
    try:
        return Decimal(draft_text.replace(",", ".")) == Decimal(str(evidence_text).replace(",", "."))
    except (InvalidOperation, ValueError):
        return False
