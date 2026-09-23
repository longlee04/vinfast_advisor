"""Input contract and ranking helpers for policy-document search."""

from __future__ import annotations


def reciprocal_rank_fusion(*ranked_lists: list[str], k: int = 60) -> list[str]:
    """Merge document IDs from independent ranked lists using RRF."""

    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return [item for item, _score in sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))]
