"""Unexpected API failures reported with a stable public message and an error ID.

A service raises :class:`OperationFailedError` from the underlying exception when an
operation fails for a reason the client cannot fix. The exception handler logs the
traceback once, under an opaque error ID, and returns only the operation's public message,
its code and that ID, so the response never carries raw exception text.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)


class OperationFailedError(HTTPException):
    """An operation failed unexpectedly; the cause stays in the server log.

    It is an :class:`HTTPException` so handlers that re-raise HTTP errors pass it through
    unchanged. ``detail`` holds only the public message.
    """

    def __init__(self, *, code: str, message: str, status_code: int = 500) -> None:
        """Create the error with a new opaque ID.

        Parameters
        ----------
        code : str
            Stable machine-readable code of the failed operation, e.g. ``file_read_failed``.
        message : str
            Public message naming the operation; never include exception text or paths.
        status_code : int
            HTTP status of the response, a 5xx status.

        """
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.error_id = uuid.uuid4().hex


async def _handle_operation_failed(request: Request, exc: Exception) -> JSONResponse:
    """Log the failure with its traceback and return the public error body."""
    if not isinstance(exc, OperationFailedError):  # pragma: no cover - registered for the type
        raise exc
    logger.error(
        "Operation failed: %s %s code=%s error_id=%s",
        request.method,
        request.url.path,
        exc.code,
        exc.error_id,
        exc_info=exc,
        extra={"error_id": exc.error_id, "error_code": exc.code},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code, "error_id": exc.error_id},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Install the handler that reports :class:`OperationFailedError` responses."""
    app.add_exception_handler(OperationFailedError, _handle_operation_failed)
