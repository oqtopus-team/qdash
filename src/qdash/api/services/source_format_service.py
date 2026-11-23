"""Format Python source for the editors with the shared Ruff formatter."""

from __future__ import annotations

from fastapi import HTTPException

from qdash.api.lib.python_format import (
    FormatterUnavailableError,
    SourceTooLargeError,
    format_python_source,
)
from qdash.api.schemas.source_format import FormatSourceDiagnostic, FormatSourceResponse


def format_source(source: str) -> FormatSourceResponse:
    """Format ``source`` and return the response; nothing is stored or executed.

    Raises:
        HTTPException: 413 for a source over the size limit, 503 when Ruff cannot run.
    """
    try:
        result = format_python_source(source)
    except SourceTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except FormatterUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"Formatting failed: {exc}") from exc
    diagnostic = (
        FormatSourceDiagnostic(message=result.message, line=result.line, column=result.column)
        if result.status == "syntax_error" and result.message is not None
        else None
    )
    return FormatSourceResponse(status=result.status, source=result.source, diagnostic=diagnostic)
