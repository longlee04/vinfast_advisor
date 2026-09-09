from dataclasses import dataclass
from enum import StrEnum


class DocumentAction(StrEnum):
    CREATE = "create"
    READ = "read"
    ARCHIVE = "archive"


@dataclass(frozen=True, slots=True)
class DocumentAuthorization:
    """Application authorization policy supplied by the composition boundary."""

    allowed_actor_ids: frozenset[str]

    def require(self, actor_id: str, action: DocumentAction) -> None:
        """Reject an actor/action pair not granted by the application policy."""
        if actor_id not in self.allowed_actor_ids:
            raise PermissionError(f"actor is not authorized for document action: {action.value}")
