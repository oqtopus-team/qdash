"""Chip reads: QDash.chips list and get, apart from the QDash.chip calibration handle."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from test_sdk_session import Server

from qdash.sdk import Chip, Chips, QDashApiError, QDashAuthError, QDashNotFoundError
from qdash.sdk.types import ChipResponse


def chip_body(chip_id: str = "64Qv3", **extra: Any) -> dict[str, Any]:
    return {"chip_id": chip_id, "size": 64, "qubit_count": 64, "coupling_count": 128, **extra}


def test_list_returns_chip_metadata_scoped_to_the_project() -> None:
    server = Server(
        {
            ("GET", "/chips"): [
                httpx.Response(
                    200,
                    json={
                        "chips": [chip_body(), chip_body("144Qv1", size=144, extra="kept")],
                        "total": 2,
                    },
                )
            ]
        }
    )
    with server.session(project_id="project-b") as qdash:
        assert isinstance(qdash.chips, Chips)
        chips = qdash.chips.list()

    assert [type(chip) for chip in chips] == [ChipResponse, ChipResponse]
    assert [(chip.chip_id, chip.size) for chip in chips] == [("64Qv3", 64), ("144Qv1", 144)]
    assert server.paths() == [("GET", "/chips")]
    assert server.requests[0].headers["X-Project-Id"] == "project-b"


def test_get_reads_one_chip_and_quotes_its_id() -> None:
    server = Server(
        {
            ("GET", "/chips/64Qv3"): [httpx.Response(200, json=chip_body())],
            ("GET", "/chips/a/b"): [httpx.Response(200, json=chip_body("a/b"))],
        }
    )
    qdash = server.session()

    chip = qdash.chips.get("64Qv3")
    assert isinstance(chip, ChipResponse)
    assert (chip.chip_id, chip.qubit_count, chip.coupling_count) == ("64Qv3", 64, 128)
    assert qdash.chips.get("a/b").chip_id == "a/b"
    assert server.requests[1].url.raw_path == b"/chips/a%2Fb"
    assert all(request.headers["X-Project-Id"] == "project-a" for request in server.requests)


@pytest.mark.parametrize(
    ("status", "error"), [(404, QDashNotFoundError), (401, QDashAuthError), (403, QDashAuthError)]
)
def test_errors_are_translated(status: int, error: type[QDashApiError]) -> None:
    server = Server(
        {
            ("GET", "/chips"): [httpx.Response(status, json={"detail": "nope"})],
            ("GET", "/chips/missing"): [httpx.Response(status, json={"detail": "nope"})],
        }
    )
    chips = server.session().chips

    with pytest.raises(error, match="nope") as raised:
        chips.get("missing")
    assert raised.value.status_code == status
    with pytest.raises(error):
        chips.list()


def test_reads_retry_transient_statuses_within_read_attempts() -> None:
    server = Server(
        {
            ("GET", "/chips"): [
                httpx.Response(503, headers={"retry-after-ms": "1"}),
                httpx.Response(200, json={"chips": [chip_body()], "total": 1}),
            ]
        }
    )
    assert [chip.chip_id for chip in server.session().chips.list()] == ["64Qv3"]
    assert len(server.requests) == 2


@pytest.mark.parametrize("chip_id", ["", None, 3])
def test_get_rejects_an_empty_chip_id_before_a_request(chip_id: Any) -> None:
    server = Server()
    with pytest.raises(ValueError, match="chip_id"):
        server.session().chips.get(chip_id)
    assert server.requests == []


def test_the_calibration_handle_still_sends_no_request() -> None:
    server = Server()
    chip = server.session().chip("64Qv3")

    assert isinstance(chip, Chip)
    assert chip.chip_id == "64Qv3"
    assert server.requests == []
