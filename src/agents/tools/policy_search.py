"""Input contract and ranking helpers for policy-document search."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class PolicySearchInput:
    """Validated policy search parameters."""

    query: str
    top_k: int = 5
    category_filter: str | None = None
    model_filter: str | None = None
    effective_after: date | None = None

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("policy search query must not be empty")
        if not 1 <= self.top_k <= 50:
            raise ValueError("policy search top_k must be between 1 and 50")


def reciprocal_rank_fusion(*ranked_lists: list[str], k: int = 60) -> list[str]:
    """Merge document IDs from independent ranked lists using RRF."""

    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return [item for item, _score in sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))]
