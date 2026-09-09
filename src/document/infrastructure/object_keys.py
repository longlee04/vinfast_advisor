"""Server-controlled object-key allocation."""

from secrets import token_urlsafe

from src.document.domain.values import DocumentId


def generate_object_key(
    document_id: DocumentId,
    _filename: str,
    content_type: str | None = None,
    document_type: str | None = None,
) -> str:
    """Return an opaque private object key independent of the client filename."""
    is_image = (content_type is not None and content_type.startswith("image/")) or (
        document_type is not None and "IMAGE" in document_type.upper()
    )
    prefix = "image" if is_image else "document"
    return f"{prefix}/{document_id.value}/{token_urlsafe(24)}"
