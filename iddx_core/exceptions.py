"""Typed exceptions for iddx_core."""


class IddxError(Exception):
    """Base exception for all iddx_core errors."""


class IddxParseError(IddxError):
    """Raised when an .iddx file cannot be parsed."""

    def __init__(self, message: str, filepath: str = ""):
        self.filepath = filepath
        super().__init__(f"{filepath}: {message}" if filepath else message)


class IddxValidationError(IddxError):
    """Raised when model data fails a validation check."""


class ResultsError(IddxError):
    """Raised when a SWMM .out results file cannot be read or is corrupt."""

    def __init__(self, message: str, filepath: str = ""):
        self.filepath = filepath
        super().__init__(f"{filepath}: {message}" if filepath else message)


class ElementNotFoundError(IddxError):
    """Raised when a requested model element (junction, catchment, etc.) is not found."""

    def __init__(self, element_type: str, identifier: str):
        self.element_type = element_type
        self.identifier = identifier
        super().__init__(f"{element_type} '{identifier}' not found")
