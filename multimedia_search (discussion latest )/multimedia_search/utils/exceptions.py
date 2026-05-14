"""Custom exceptions for the search engine."""

class UnsupportedFormatError(Exception):
    """Raised when a file format is not supported."""
    pass

class IndexNotFoundError(Exception):
    """Raised when no index is found on disk."""
    pass