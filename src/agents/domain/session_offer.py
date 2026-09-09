"""Domain model for advisor-approved session-scoped offers (T4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SessionOffer:
    """An offer a customer may hear about in later turns."""

    offer_id: UUID
    session_id: UUID
    source_kind: str
    promotion_code: str
    value_snapshot: dict
    status: str
    approved_by: str
    expires_at: datetime | None

    @property
    def display_name(self) -> str:
        name = self.value_snapshot.get("display_name")
        return name if isinstance(name, str) and name else self.promotion_code
