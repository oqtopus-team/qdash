"""Building the generated client from a config, and the SDK's error translation."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

import httpx

from qdash.sdk._generated.client import QDashApi
from qdash.sdk._generated.core.api_error import ApiError
from qdash.sdk._generated.core.parse_error import ParsingError
from qdash.sdk.errors import (
    QDashApiError,
    QDashAuthError,
    QDashConfigError,
    QDashConflictError,
    QDashNotFoundError,
    QDashTransportError,
    QDashValidationError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from pydantic import BaseModel

    from qdash.sdk._config import QDashConfig
    from qdash.sdk._generated.core.request_options import RequestOptions

_STATUS_ERRORS: dict[int, type[QDashApiError]] = {
    401: QDashAuthError,
    403: QDashAuthError,
    404: QDashNotFoundError,
    409: QDashConflictError,
    422: QDashValidationError,
}


def user_agent(config: QDashConfig) -> str:
    if config.user_agent:
        return config.user_agent
    try:
        return f"qdash-sdk/{version('qdash-sdk')}"
    except PackageNotFoundError:
        return "qdash-sdk/unknown"


def common_headers(config: QDashConfig) -> dict[str, str]:
    """Headers every request carries, besides the token and ``X-Project-Id``."""
    headers = {"Accept": "application/json", "User-Agent": user_agent(config)}
    if config.cf_access_client_id:
        headers["CF-Access-Client-Id"] = config.cf_access_client_id
    if config.cf_access_client_secret:
        headers["CF-Access-Client-Secret"] = config.cf_access_client_secret
    return headers


def owned_http_client(config: QDashConfig) -> httpx.Client:
    """The HTTP client a session creates, and closes, for ``config``."""
    return httpx.Client(timeout=config.timeout_sec, verify=config.verify_tls, proxy=config.proxy)


def token_provider(config: QDashConfig, http_client: httpx.Client) -> str | Callable[[], str]:
    """The bearer token, or a function that signs in once with username and password."""
    if config.api_token:
        return config.api_token
    if not config.username:
        raise QDashConfigError(
            "No authentication configured: set QDASH_API_TOKEN (api_token), or username "
            "with the password in the environment variable password_env."
        )
    username, password_env = config.username, config.password_env
    if not password_env:
        raise QDashConfigError("password_env is required when using username/password")
    lock = threading.Lock()
    token: list[str] = []

    def sign_in() -> str:
        with lock:
            if token:
                return token[0]
            password = os.getenv(password_env)
            if not password:
                raise QDashConfigError(f"Missing password in env var {password_env}")
            with api_errors():
                response = http_client.post(
                    f"{config.base_url}/auth/login",
                    data={"username": username, "password": password},
                    headers=common_headers(config),
                    timeout=config.timeout_sec,
                )
                if response.status_code >= 400:
                    raise ApiError(
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        body=_body(response),
                    )
            try:
                payload = response.json()
            except ValueError:
                raise QDashAuthError("Login response was not valid JSON") from None
            if not isinstance(payload, dict):
                raise QDashAuthError("Login response must be a JSON object")
            access = payload.get("access_token")
            if not isinstance(access, str) or not access:
                raise QDashAuthError("Login response did not include access_token")
            token.append(access)
            return access

    return sign_in


def build_api(
    config: QDashConfig, http_client: httpx.Client, *, project_id: str | None
) -> QDashApi:
    """The generated client for ``config`` on ``http_client``, scoped to ``project_id``.

    Retries are off unless a call asks for them (see :func:`read_options`), so a request that
    changes state is sent once even after a 409, a 5xx or a timeout.
    """
    return QDashApi(
        base_url=config.base_url,
        token=token_provider(config, http_client),
        project_id=project_id,
        headers=common_headers(config),
        timeout=config.timeout_sec,
        max_retries=0,
        httpx_client=http_client,
    )


def read_options(config: QDashConfig) -> RequestOptions:
    """Request options for a GET the SDK may send again after a transient failure."""
    return {"max_retries": config.read_attempts - 1, "retry_remote_protocol_errors": True}


def given(**values: Any) -> dict[str, Any]:
    """The keyword arguments that were given: None leaves the generated default (omitted)."""
    return {key: value for key, value in values.items() if value is not None}


def body(request: BaseModel) -> dict[str, Any]:
    """A strict request model as keyword arguments: fields set, including explicit nulls."""
    dumped: dict[str, Any] = request.model_dump(mode="json", exclude_unset=True)
    return dumped


def _body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _message(status: int | None, payload: Any) -> str:
    if isinstance(payload, dict) and payload.get("detail"):
        return f"{status}: {payload['detail']}"
    if isinstance(payload, str) and payload:
        return f"{status}: {payload}"
    return str(status)


def translate(error: Exception) -> QDashApiError:
    """The SDK error for an error of the generated client or of httpx."""
    if isinstance(error, QDashApiError):
        return error
    if isinstance(error, ParsingError):
        return QDashTransportError(
            f"{error.status_code}: the response did not match the API schema",
            status_code=error.status_code,
            body=error.body,
            headers=error.headers,
        )
    if isinstance(error, ApiError):
        status = error.status_code
        cls = _STATUS_ERRORS.get(status or 0, QDashApiError)
        return cls(
            _message(status, error.body), status_code=status, body=error.body, headers=error.headers
        )
    return QDashTransportError(str(error) or type(error).__name__)


@contextmanager
def api_errors() -> Iterator[None]:
    """Raise the SDK's error types for failures of the generated client inside the block."""
    try:
        yield
    except (ApiError, ParsingError, httpx.HTTPError) as error:
        translated = translate(error)
        if translated is error:
            raise
        raise translated from error
