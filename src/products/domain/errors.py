"""Domain-level errors for the Product module."""


class ProductDomainError(Exception):
    """Base error for the Product domain."""


class ProductNotFoundError(ProductDomainError):
    """Raised when a requested product does not exist."""


class ProductPermissionError(ProductDomainError):
    """Raised when the caller does not have permission to perform the action."""
