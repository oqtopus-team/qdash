"""Which failed requests QDashClient sends again, and which it must not."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest

from qdash.client import (
    ListChipsResponse,
    QDashApiError,
    QDashClient,
    QDashConfig,
    QDashTransportError,
)
from qdash.client.rest import ApiClient, ApiException, Configuration

if TYPE_CHECKING:
    from collections.abc import Callable

EXECUTE_PAYLOAD = {
    "execution_id": "exec-1",
    "flow_run_id": "run-1",
    "flow_run_url": "https://prefect.local/runs/run-1",
    "qdash_ui_url": "https://qdash.local/executions/exec-1",
    "message": "started",
}
CHIPS_PAYLOAD = {"chips": [{"chip_id": "chip-a"}], "total": 1}


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    use_api_token: bool = True,
    max_attempts: int = 3,
) -> QDashClient:
    config = QDashConfig.model_validate(
        {
            "base_url": "http://qdash.local",
            "api_token": "api-token" if use_api_token else None,
            "username": None if use_api_token else "tester",
            "password_env": None if use_api_token else "QDASH_PASSWORD",
            "retry": {"max_attempts": max_attempts, "base_delay_sec": 0, "max_delay_sec": 0},
        }
    )
    http_client = httpx.Client(base_url=config.base_url, transport=httpx.MockTransport(handler))
    return QDashClient(config, http_client=http_client, sleep_fn=lambda _sec: None)


class _Script:
    """Answer each matching request with the next scripted failure or response."""

    def __init__(self, method: str, path: str, outcomes: list[Any]) -> None:
        self.method = method
        self.path = path
        self.outcomes = outcomes
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method != self.method or request.url.path != self.path:
            return httpx.Response(500, json={"detail": "unexpected request"})
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        if isinstance(outcome, type) and issubclass(outcome, httpx.TransportError):
            raise outcome("transport failure", request=request)
        return httpx.Response(outcome[0], json=outcome[1])


@pytest.mark.parametrize(
    "error", [httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.ConnectError]
)
def test_get_is_retried_after_any_transport_failure(error: type[httpx.TransportError]) -> None:
    script = _Script("GET", "/chips", [error, (200, CHIPS_PAYLOAD)])
    client = _client(script)
    try:
        assert isinstance(client.list_chips(), ListChipsResponse)
    finally:
        client.close()
    assert script.calls == 2


def test_get_gives_up_after_max_attempts() -> None:
    script = _Script("GET", "/chips", [httpx.ReadTimeout])
    client = _client(script, max_attempts=3)
    try:
        with pytest.raises(QDashTransportError):
            client.list_chips()
    finally:
        client.close()
    assert script.calls == 3


@pytest.mark.parametrize(
    "error", [httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError, httpx.ReadError]
)
def test_write_is_not_resent_when_the_server_may_have_received_it(
    error: type[httpx.TransportError],
) -> None:
    # The server may already have started the flow; sending it again could start it twice.
    script = _Script("POST", "/flows/demo/execute", [error, (200, EXECUTE_PAYLOAD)])
    client = _client(script)
    try:
        with pytest.raises(QDashTransportError):
            client.execute_flow("demo")
    finally:
        client.close()
    assert script.calls == 1


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_no_write_method_is_resent_after_a_read_timeout(method: str) -> None:
    script = _Script(method, "/resource", [httpx.ReadTimeout, (200, {})])
    client = _client(script)
    try:
        with pytest.raises(QDashTransportError):
            client._request(method, "/resource", json={})
    finally:
        client.close()
    assert script.calls == 1


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout])
def test_write_is_resent_when_the_connection_was_never_made(
    error: type[httpx.TransportError],
) -> None:
    script = _Script("POST", "/flows/demo/execute", [error, (200, EXECUTE_PAYLOAD)])
    client = _client(script)
    try:
        assert client.execute_flow("demo").execution_id == "exec-1"
    finally:
        client.close()
    assert script.calls == 2


def test_write_rejected_with_401_is_resent_once_after_a_fresh_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QDASH_PASSWORD", "secret")
    logins = 0
    executes: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal logins
        if request.url.path == "/auth/login":
            logins += 1
            return httpx.Response(200, json={"access_token": f"token-{logins}"})
        executes.append(request.headers.get("Authorization"))
        if len(executes) == 1:
            return httpx.Response(401, json={"detail": "expired"})
        return httpx.Response(200, json=EXECUTE_PAYLOAD)

    client = _client(handler, use_api_token=False)
    try:
        assert client.execute_flow("demo").execution_id == "exec-1"
    finally:
        client.close()
    # A 401 means the server rejected the request without acting on it.
    assert executes == ["Bearer token-1", "Bearer token-2"]
    assert logins == 2


def test_write_rejected_with_401_under_an_api_token_is_not_resent() -> None:
    script = _Script("POST", "/flows/demo/execute", [(401, {"detail": "invalid token"})])
    client = _client(script)
    try:
        with pytest.raises(QDashApiError) as caught:
            client.execute_flow("demo")
    finally:
        client.close()
    assert caught.value.status_code == 401
    assert script.calls == 1


@pytest.mark.parametrize(
    ("error", "request_sent"),
    [
        (httpx.ConnectError, False),
        (httpx.ConnectTimeout, False),
        (httpx.PoolTimeout, False),
        (httpx.ReadTimeout, True),
        (httpx.WriteError, True),
        (httpx.RemoteProtocolError, True),
    ],
)
def test_rest_client_reports_whether_a_failed_request_may_have_been_sent(
    error: type[httpx.TransportError], request_sent: bool
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error("transport failure", request=request)

    configuration = Configuration(host="http://qdash.local")
    rest = ApiClient(
        configuration,
        http_client=httpx.Client(
            base_url=configuration.host, transport=httpx.MockTransport(handler)
        ),
    )
    try:
        with pytest.raises(ApiException) as caught:
            rest.request("POST", "/flows/demo/execute", json={})
    finally:
        rest.close()
    assert caught.value.status is None
    assert caught.value.request_sent is request_sent


def test_rest_client_returns_a_401_as_a_response_not_a_transport_failure() -> None:
    configuration = Configuration(host="http://qdash.local")
    rest = ApiClient(
        configuration,
        http_client=httpx.Client(
            base_url=configuration.host,
            transport=httpx.MockTransport(lambda _request: httpx.Response(401, json={})),
        ),
    )
    try:
        assert rest.request("POST", "/flows/demo/execute", json={}).status_code == 401
        with pytest.raises(ApiException) as caught:
            rest.request("POST", "/flows/demo/execute", json={}, raise_on_status=True)
    finally:
        rest.close()
    assert caught.value.status == 401
    assert caught.value.request_sent is True


@pytest.mark.asyncio
async def test_async_get_is_retried_after_a_read_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    class FlakyAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> FlakyAsyncClient:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def get(self, path: str, **kwargs: object) -> httpx.Response:
            nonlocal calls
            calls += 1
            request = httpx.Request("GET", f"http://qdash.local{path}")
            if calls == 1:
                raise httpx.ReadTimeout("slow", request=request)
            return httpx.Response(200, json=CHIPS_PAYLOAD, request=request)

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("qdash.client.services.client.httpx.AsyncClient", FlakyAsyncClient)
    monkeypatch.setattr("qdash.client.services.client.asyncio.sleep", no_sleep)
    client = _client(lambda _request: httpx.Response(500))
    try:
        assert isinstance(await client.list_chips_async(), ListChipsResponse)
    finally:
        client.close()
    assert calls == 2
