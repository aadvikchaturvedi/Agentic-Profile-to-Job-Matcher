class AppError(Exception):
    """Base error for all application-level exceptions."""
    pass


class FileConversionError(AppError):
    """Raised when resume file cannot be parsed (unsupported format, corrupted, empty)."""
    pass


class ParsingError(AppError):
    """Raised when resume/JD parsing fails (both Ollama and regex fallback)."""
    pass


class FetchError(AppError):
    """Raised when job scraping fails across all sources."""
    pass


class ScoringError(AppError):
    """Raised when scoring encounters an unrecoverable error."""
    pass


class ReportError(AppError):
    """Raised when report generation fails."""
    pass


class ConfigError(AppError):
    """Raised when configuration is invalid or missing."""
    pass
