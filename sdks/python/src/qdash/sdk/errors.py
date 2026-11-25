"""Errors raised by the QDash SDK.

:class:`QDashApiError` subclasses the generated client's ``ApiError``, so ``except ApiError``
catches both the errors of the SDK operations and those of the generated resource clients
reached through ``QDash.api``. The SDK operations raise the subclass matching the HTTP status;
the generated resource clients raise ``ApiError`` (``UnprocessableEntityError`` for 422) and
let ``httpx`` transport errors through.
"""

from __future__ import annotations

from typing import Any

from qdash.sdk._generated.core.api_error import ApiError

__all__ = [
    "ApiError",
    "QDashApiError",
    "QDashAuthError",
    "QDashConfigDeprecationWarning",
    "QDashConfigError",
    "QDashConflictError",
    "QDashNotFoundError",
    "QDashTransportError",
    "QDashValidationError",
]


class QDashConfigError(ValueError):
    """The SDK configuration is missing or invalid; nothing was sent."""


class QDashConfigDeprecationWarning(FutureWarning):
    """The SDK read a deprecated configuration source, such as an INI config file."""


class QDashApiError(ApiError):
    """A QDash API request failed.

    ``status_code`` is the HTTP status, or None when no response arrived. ``body`` (also
    ``payload``) is the response body as the server sent it, decoded from JSON when possible.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(headers=headers, status_code=status_code, body=body)
        self.message = message

    @property
    def payload(self) -> Any:
        return self.body

    def __str__(self) -> str:
        return self.message


class QDashAuthError(QDashApiError):
    """The request was not authenticated or not allowed (401 or 403)."""


class QDashNotFoundError(QDashApiError):
    """The requested resource does not exist (404)."""


class QDashConflictError(QDashApiError):
    """The request conflicts with the stored state (409), such as a stale revision.

    Nothing is retried: read the current state and decide whether to save again.
    """


class QDashValidationError(QDashApiError):
    """The server rejected the request's parameters or body (422)."""


class QDashTransportError(QDashApiError):
    """No usable response: the connection failed, timed out or the response did not parse.

    For a request that changes state, the server may still have acted on it.
    """
