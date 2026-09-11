class ConvolvgerError(Exception):
    """Base class for all Convolvger errors."""


class ProviderNotFoundError(ConvolvgerError):
    """Raised when no provider can handle the requested source."""
