"""Domain errors for the Image feature."""


class ImageDomainError(ValueError):
    """Base error for invalid image domain state."""


class InvalidImageIdError(ImageDomainError):
    """Raised when an image identifier is not a valid UUID."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid image id: {value}")


class InvalidFilenameError(ImageDomainError):
    """Raised when an uploaded image filename is empty."""

    def __init__(self) -> None:
        super().__init__("image filename must not be empty")
