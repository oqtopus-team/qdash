from __future__ import annotations


class ApiException(Exception):
    """Exception raised by low-level REST transport.

    ``request_sent`` is ``False`` only when the failure happened before a connection to the
    server was established, so the server cannot have received the request. Any other
    transport failure, such as a read timeout or a dropped connection, leaves it ``True``:
    the server may have processed the request.
    """

    def __init__(
        self,
        status: int | None,
        reason: str,
        body: object | None = None,
        *,
        request_sent: bool = True,
    ) -> None:
        self.status = status
        self.reason = reason
        self.body = body
        self.request_sent = request_sent
        super().__init__(f"HTTP {status}: {reason}" if status is not None else reason)
