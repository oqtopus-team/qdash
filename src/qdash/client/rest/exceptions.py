from __future__ import annotations


class ApiException(Exception):
    """Exception raised by low-level REST transport."""

    def __init__(self, status: int | None, reason: str, body: object | None = None) -> None:
        self.status = status
        self.reason = reason
        self.body = body
        super().__init__(f"HTTP {status}: {reason}" if status is not None else reason)
