"""Domain exceptions used across agents, services and the API layer."""
from __future__ import annotations


class ResumeBuilderError(Exception):
    """Base error for the application."""

    status_code: int = 500

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class UnsupportedFileTypeError(ResumeBuilderError):
    status_code = 415


class FileTooLargeError(ResumeBuilderError):
    status_code = 413


class ExtractionError(ResumeBuilderError):
    status_code = 422


class NotFoundError(ResumeBuilderError):
    status_code = 404


class LLMUnavailableError(ResumeBuilderError):
    status_code = 503


class ExportError(ResumeBuilderError):
    status_code = 500


class TemplateError(ResumeBuilderError):
    status_code = 422
