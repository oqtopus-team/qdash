"""Assertions for unexpected failures reported with a public message and an error ID."""

from __future__ import annotations

import logging
import re
import traceback
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx
    import httpx2
    import pytest

ERRORS_LOGGER = "qdash.api.lib.errors"


def assert_operation_failure(
    response: httpx.Response | httpx2.Response,
    caplog: pytest.LogCaptureFixture,
    *,
    code: str,
    message: str,
    cause: type[BaseException],
    hidden: tuple[str, ...],
) -> None:
    """Check the 500 body is safe and its error ID names the logged traceback.

    ``hidden`` lists text of the underlying exception, such as paths, that the response
    must not carry.
    """
    assert response.status_code == 500
    body = response.json()
    assert set(body) == {"detail", "code", "error_id"}
    assert body["detail"] == message
    assert body["code"] == code
    assert re.fullmatch(r"[0-9a-f]{32}", body["error_id"])
    for text in hidden:
        assert text not in response.text

    records = [
        record
        for record in caplog.records
        if record.name == ERRORS_LOGGER and getattr(record, "error_id", None) == body["error_id"]
    ]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.ERROR
    assert body["error_id"] in record.getMessage()
    assert record.exc_info is not None
    logged = "".join(traceback.format_exception(*record.exc_info))
    assert cause.__name__ in logged
    assert isinstance(record.exc_info[1].__cause__, cause)  # type: ignore[union-attr]
