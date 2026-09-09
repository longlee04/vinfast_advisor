"""Extensible semantic support rules for claims that cannot be checked numerically."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class SemanticClaimRule:
    """A claim family and the evidence language that supports or conflicts with it."""

    code: str
    claim_patterns: tuple[re.Pattern[str], ...]
    support_patterns: tuple[re.Pattern[str], ...]
    conflict_patterns: tuple[re.Pattern[str], ...]


def _patterns(*values: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(value) for value in values)


SEMANTIC_CLAIM_RULES: Final[tuple[SemanticClaimRule, ...]] = (
    SemanticClaimRule(
        code="LONG_DISTANCE_SUITABILITY",
        claim_patterns=_patterns(
            r"(?:phu hop|ly tuong|thich hop|tot cho|dap ung|ho tro).{0,48}"
            r"(?:di xa|duong dai|duong truong|di tinh|ve que)",
            r"(?:di xa|duong dai|duong truong|di tinh|ve que).{0,48}"
            r"(?:phu hop|ly tuong|thich hop|tot|dap ung)",
        ),
        support_patterns=_patterns(
            r"(?:phu hop|ly tuong|thich hop|ho tro|danh cho).{0,48}"
            r"(?:di xa|duong dai|duong truong|di tinh|ve que)",
            r"(?:di xa|duong dai|duong truong|di tinh|ve que).{0,48}"
            r"(?:phu hop|ly tuong|thich hop|ho tro)",
        ),
        conflict_patterns=_patterns(
            r"(?:phu hop|toi uu|danh cho).{0,48}"
            r"(?:noi do|do thi|trong pho|chuyen di ngan|di ngan)",
            r"(?:chi|chu yeu).{0,32}(?:noi do|do thi|trong pho|di ngan)",
        ),
    ),
)


def semantic_claims_are_supported(answer: str, evidence_texts: Sequence[str]) -> bool:
    """Return false when a detected claim lacks support or meets conflicting evidence."""

    normalized_answer = _normalize(answer)
    normalized_evidence = tuple(_normalize(text) for text in evidence_texts if text.strip())
    for rule in SEMANTIC_CLAIM_RULES:
        if not _matches_positive_claim(normalized_answer, rule.claim_patterns):
            continue
        if any(pattern.search(evidence) for evidence in normalized_evidence for pattern in rule.conflict_patterns):
            return False
        if not any(pattern.search(evidence) for evidence in normalized_evidence for pattern in rule.support_patterns):
            return False
    return True


def _matches_positive_claim(text: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    for pattern in patterns:
        for match in pattern.finditer(text):
            prefix = text[max(0, match.start() - 12) : match.start()]
            if not re.search(r"(?:khong|chua)\s*$", prefix):
                return True
    return False


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold())
    without_marks = "".join(character for character in decomposed if unicodedata.category(character) != "Mn")
    return re.sub(r"\s+", " ", without_marks.replace("đ", "d")).strip()
