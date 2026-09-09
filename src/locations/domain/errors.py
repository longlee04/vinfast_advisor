"""Domain-level errors for the Locations module."""


class LocationsDomainError(Exception):
    """Base error for the Locations domain."""


class InvalidBoundsError(LocationsDomainError):
    """Raised when a coordinate or map window is not a point on Earth."""


class InvalidRadiusError(LocationsDomainError):
    """Raised when a search radius is outside the allowed range."""
