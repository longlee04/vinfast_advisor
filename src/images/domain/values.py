"""Value objects for the Image feature."""

from dataclasses import dataclass
from uuid import UUID

from .errors import InvalidImageIdError


@dataclass(frozen=True, slots=True)
class ImageId:
    """Opaque image identifier backed by a UUID."""

    value: str

    def __post_init__(self) -> None:
        try:
            UUID(self.value)
        except ValueError as error:
            raise InvalidImageIdError(self.value) from error
