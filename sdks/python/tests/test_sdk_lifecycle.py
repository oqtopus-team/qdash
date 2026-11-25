"""Lifetime of the HTTP connection a QDash session owns or borrows.

A session from ``QDash(config)`` owns its ``httpx.Client``: it stays usable while anything
that sends through it is referenced, and is closed by ``close()`` or at normal interpreter
exit. A borrowed client is never closed by the SDK.
"""

from __future__ import annotations

import gc
import subprocess
import sys
import textwrap
from typing import Any

import httpx
import pytest

from qdash.sdk import QDash, QDashConfig, QDashConfigError, _http
from qdash.sdk import _session as session_module

CHIPS = {"chips": [], "total": 0}
RealClient = httpx.Client


class CountingTransport(httpx.MockTransport):
    """A mock transport that answers ``GET /chips`` and counts how often it is closed."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.closes = 0
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json=CHIPS)

    def close(self) -> None:
        self.closes += 1


@pytest.fixture
def transports(monkeypatch: pytest.MonkeyPatch) -> list[CountingTransport]:
    """Route every client the SDK creates through a new ``CountingTransport``."""
    created: list[CountingTransport] = []

    class Client(RealClient):
        def __init__(self, **kwargs: Any) -> None:
            transport = CountingTransport()
            created.append(transport)
            super().__init__(transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "Client", Client)
    return created


def config(**updates: Any) -> QDashConfig:
    values: dict[str, Any] = {
        "base_url": "http://qdash.local",
        "api_token": "api-token",
        "project_id": "project-a",
    }
    values.update(updates)
    return QDashConfig(**values)


def owned() -> list[httpx.Client]:
    return list(_http._owned_clients)


def test_explicit_close_releases_the_connection_once_and_unregisters_it(
    transports: list[CountingTransport],
) -> None:
    qdash = QDash(config())
    client = qdash._http_client
    assert client in owned()

    qdash.close()
    qdash.close()

    assert client.is_closed
    assert transports[0].closes == 1
    assert client not in owned()


def test_with_block_releases_the_connection(transports: list[CountingTransport]) -> None:
    with QDash(config()) as qdash:
        client = qdash._http_client
        qdash.api.chip.list_chips()

    assert client.is_closed
    assert transports[0].closes == 1
    assert client not in owned()


def test_a_borrowed_client_is_never_registered_or_closed() -> None:
    transport = CountingTransport()
    client = httpx.Client(transport=transport)

    qdash = QDash(config(), http_client=client)
    scoped = qdash.with_project("project-b")
    assert client not in owned()
    scoped.close()
    qdash.close()
    _http._close_owned_http_clients()

    assert not client.is_closed
    assert transport.closes == 0
    client.close()


def test_with_project_outlives_the_original_session(
    transports: list[CountingTransport],
) -> None:
    scoped = QDash(config()).with_project("project-b")
    gc.collect()

    scoped.api.chip.list_chips()
    scoped.chips.list()
    scoped.close()

    assert not scoped._http_client.is_closed
    assert transports[0].closes == 0
    assert [r.headers["X-Project-Id"] for r in transports[0].requests] == ["project-b"] * 2
    assert scoped._http_client in owned()


def test_the_api_and_helpers_outlive_the_session(transports: list[CountingTransport]) -> None:
    qdash = QDash(config())
    api, chips = qdash.api, qdash.chips
    del qdash
    gc.collect()

    api.chip.list_chips()
    chips.list()

    assert len(transports[0].requests) == 2
    assert transports[0].closes == 0


def test_closing_the_owner_closes_the_connection_its_clones_use(
    transports: list[CountingTransport],
) -> None:
    qdash = QDash(config())
    scoped = qdash.with_project("project-b")
    qdash.close()

    assert scoped._http_client.is_closed
    assert transports[0].closes == 1


def test_an_unused_session_is_not_kept_alive_by_the_registry(
    transports: list[CountingTransport],
) -> None:
    gc.collect()
    before = len(owned())
    qdash = QDash(config())
    assert len(owned()) == before + 1

    del qdash
    gc.collect()

    assert len(owned()) == before


def test_init_failure_closes_and_unregisters_the_owned_client(
    transports: list[CountingTransport],
) -> None:
    before = owned()
    with pytest.raises(QDashConfigError):
        QDash(config(api_token=None))

    assert transports[0].closes == 1
    assert owned() == before


def test_helper_failure_closes_the_owned_client_but_not_a_borrowed_one(
    transports: list[CountingTransport], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("helper failed")

    monkeypatch.setattr(session_module, "Chips", broken)
    before = owned()

    with pytest.raises(RuntimeError, match="helper failed"):
        QDash(config())
    assert transports[0].closes == 1
    assert owned() == before

    borrowed = CountingTransport()
    client = RealClient(transport=borrowed)
    with pytest.raises(RuntimeError, match="helper failed"):
        QDash(config(), http_client=client)
    assert not client.is_closed
    assert borrowed.closes == 0
    client.close()


def test_explicit_close_raises_the_transport_error_and_still_unregisters(
    transports: list[CountingTransport], monkeypatch: pytest.MonkeyPatch
) -> None:
    qdash = QDash(config())
    client = qdash._http_client

    def failing_close() -> None:
        raise OSError("close failed")

    monkeypatch.setattr(transports[0], "close", failing_close)
    with pytest.raises(OSError, match="close failed"):
        qdash.close()

    assert client not in owned()


SHUTDOWN = textwrap.dedent(
    """
    import sys

    import httpx

    from qdash.sdk import QDash, QDashConfig
    from qdash.sdk import _http


    class Transport(httpx.MockTransport):
        def __init__(self, name, fail=False):
            super().__init__(lambda request: httpx.Response(200, json={"chips": [], "total": 0}))
            self.name, self.fail = name, fail

        def close(self):
            print("closed", self.name, flush=True)
            if self.fail:
                raise OSError("close failed")


    names = iter(sys.argv[1].split(","))
    base = httpx.Client


    class Client(base):
        def __init__(self, **kwargs):
            name = next(names)
            super().__init__(transport=Transport(name, fail=name == "failing"), **kwargs)


    _http.httpx.Client = Client
    config = QDashConfig(base_url="http://qdash.local", api_token="t", project_id="p")

    # Kept only through a clone and a helper; the original sessions are discarded.
    scoped = QDash(config).with_project("q")
    chips = QDash(config).chips
    failing = QDash(config)
    closed = QDash(config)
    closed.close()

    borrowed = base(transport=Transport("borrowed"))
    QDash(config, http_client=borrowed).close()

    scoped.api.chip.list_chips()
    chips.list()
    print("done", flush=True)
    """
)


def test_normal_interpreter_exit_closes_every_owned_connection_once() -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", SHUTDOWN, "scoped,helper,failing,closed"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    # The explicitly closed client closes before exit and not again; the borrowed one never.
    assert lines[:2] == ["closed closed", "done"]
    assert sorted(lines[2:]) == ["closed failing", "closed helper", "closed scoped"]
    assert "close failed" not in result.stderr
