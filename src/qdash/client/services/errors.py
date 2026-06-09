from __future__ import annotations


class QDashApiError(Exception):
    """Base error for qdash-client API and transport failures."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        payload: object | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class QDashConfigError(ValueError):
    """Raised when client configuration is invalid or missing."""


class QDashAuthError(QDashApiError):
    """Authentication failure (401)."""


class QDashNotFoundError(QDashApiError):
    """Requested resource not found (404)."""


class QDashValidationError(QDashApiError):
    """Invalid request payload or parameters (422)."""


class QDashTransportError(QDashApiError):
    """Transport-level failure (network/timeouts/unexpected status)."""


QDashClientError = QDashApiError
