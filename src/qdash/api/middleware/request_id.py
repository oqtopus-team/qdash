"""Request ID middleware for correlating log entries across a single request."""

import logging
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_CTX_VAR: ContextVar[str] = ContextVar("request_id", default="")

HEADER_NAME = "X-Request-ID"


class RequestIdFilter(logging.Filter):
    """Logging filter that injects the current request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = REQUEST_ID_CTX_VAR.get("")  # dynamic attr on LogRecord
        return True


class RequestIdMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that assigns a request ID to each incoming request.

    - Uses the ``X-Request-ID`` header if present, otherwise generates a short UUID.
    - Stores the ID in a ``ContextVar`` so that ``RequestIdFilter`` can read it.
    - Echoes the ID back in the ``X-Request-ID`` response header.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(HEADER_NAME, uuid.uuid4().hex[:8])
        REQUEST_ID_CTX_VAR.set(request_id)

        response = await call_next(request)
        response.headers[HEADER_NAME] = request_id
        return response
