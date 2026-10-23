"""Exercise the Caddy routes against local mock QDash and Prefect upstreams."""

import base64
import hashlib
import http.client
import json
import os
import select
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


class BackendState:
    """Hold mock service observations and synchronization events."""

    def __init__(self, service: str) -> None:
        self.service = service
        self.seen: list[tuple[str, str | None]] = []
        self.lock = threading.Lock()
        self.stream_started = threading.Event()
        self.stream_release = threading.Event()
        self.stream_disconnected = threading.Event()


class MockHTTPServer(ThreadingHTTPServer):
    """Suppress expected socket-close errors from proxy disconnect tests."""

    def handle_error(self, _request: Any, _client_address: Any) -> None:
        """Ignore expected resets after a downstream disconnect."""
        error = sys.exc_info()[1]
        if isinstance(error, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(_request, _client_address)


class MockHandler(BaseHTTPRequestHandler):
    """Provide minimal UI, API auth, Prefect, and websocket responses."""

    protocol_version = "HTTP/1.1"

    @property
    def state(self) -> BackendState:
        """Return the state attached to this handler's server."""
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, _format: str, *_args: Any) -> None:
        """Keep test server output out of pytest logs."""

    def do_GET(self) -> None:
        """Handle GET requests for mock services."""
        self.handle_request()

    def do_POST(self) -> None:
        """Handle POST requests for mock services."""
        self.handle_request()

    def do_HEAD(self) -> None:
        """Handle HEAD requests for mock services."""
        self.handle_request(send_body=False)

    def handle_request(self, *, send_body: bool = True) -> None:
        """Record a request and return the service's configured response."""
        state = self.state
        with state.lock:
            state.seen.append((self.path, self.headers.get("Authorization")))

        if state.service == "api" and self.path == "/auth/me":
            token_status = {
                "Bearer valid": 200,
                "Bearer disabled": 403,
                "Bearer failure": 503,
            }
            status = token_status.get(self.headers.get("Authorization", ""), 401)
            self.send_json(status, {"status": status}, send_body=send_body)
            return

        if state.service == "prefect" and self.path == "/prefect/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(b"data: first\n\n")
            self.wfile.flush()
            state.stream_started.set()
            deadline = time.monotonic() + 5
            try:
                while time.monotonic() < deadline and not state.stream_release.is_set():
                    readable, _, _ = select.select([self.connection], [], [], 0.05)
                    if readable and not self.connection.recv(1):
                        state.stream_disconnected.set()
                        return
            except (ConnectionResetError, OSError):
                state.stream_disconnected.set()
            return

        if state.service == "prefect" and self.headers.get("Upgrade", "").lower() == "websocket":
            websocket_key = self.headers["Sec-WebSocket-Key"]
            accept = base64.b64encode(
                hashlib.sha1(
                    (websocket_key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode(),
                    usedforsecurity=False,
                ).digest()
            ).decode()
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept)
            self.end_headers()
            self.wfile.write(b"\x81\x02OK")
            self.wfile.flush()
            self.close_connection = True
            return

        self.send_json(
            200,
            {
                "service": state.service,
                "path": self.path,
                "proto": self.headers.get("X-Forwarded-Proto"),
            },
            send_body=send_body,
        )

    def send_json(self, status: int, body: dict[str, Any], *, send_body: bool) -> None:
        """Write a small JSON response with a fixed length."""
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if send_body:
            self.wfile.write(payload)


@pytest.fixture
def caddy_binary() -> str:
    """Find the Caddy executable or skip integration tests."""
    binary = os.environ.get("CADDY_BIN") or shutil.which("caddy")
    if binary is None:
        pytest.skip("Set CADDY_BIN or install Caddy to run proxy integration tests")
    return binary


@pytest.fixture
def proxy(caddy_binary: str, tmp_path: Path, request: pytest.FixtureRequest) -> Any:
    """Start Caddy with local mock services and clean up all processes."""
    states = {name: BackendState(name) for name in ("api", "ui", "prefect")}
    servers: list[MockHTTPServer] = []
    threads: list[threading.Thread] = []
    process: subprocess.Popen[bytes] | None = None
    log_path = tmp_path / "caddy.log"
    log = log_path.open("wb")

    try:
        for state in states.values():
            server = MockHTTPServer(("127.0.0.1", 0), MockHandler)
            server.daemon_threads = True
            server.state = state  # type: ignore[attr-defined]
            servers.append(server)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            threads.append(thread)

        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]

        environment = os.environ.copy()
        environment.update(
            {
                "CADDY_SITE_ADDRESS": f"http://localhost:{port}",
                "CADDY_BIND_ADDRESS": "127.0.0.1",
                "CADDY_TRUSTED_PROXIES": getattr(request, "param", "127.0.0.1/32 ::1/128"),
                "CADDY_API_UPSTREAM": f"127.0.0.1:{servers[0].server_port}",
                "CADDY_UI_UPSTREAM": f"127.0.0.1:{servers[1].server_port}",
                "CADDY_PREFECT_UPSTREAM": f"127.0.0.1:{servers[2].server_port}",
                "XDG_CONFIG_HOME": str(tmp_path / "config"),
                "XDG_DATA_HOME": str(tmp_path / "data"),
            }
        )
        process = subprocess.Popen(  # noqa: S603
            [caddy_binary, "run", "--config", "config/caddy/Caddyfile", "--adapter", "caddyfile"],
            cwd=REPO_ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"Caddy exited during startup:\n{log_path.read_text()}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            pytest.fail(f"Caddy did not listen in time:\n{log_path.read_text()}")

        yield {"url": f"http://localhost:{port}", "states": states}
    finally:
        for state in states.values():
            state.stream_release.set()
        if process is not None:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)
        log.close()


def request(
    proxy: dict[str, Any],
    path: str,
    *,
    token: str | None = None,
    accept: str | None = None,
    method: str = "GET",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """Send one HTTP request through Caddy and return its response."""
    request_headers = dict(headers or {})
    if token is not None:
        request_headers["Cookie"] = f"access_token={token}"
    if accept is not None:
        request_headers["Accept"] = accept
    connection = http.client.HTTPConnection(
        "localhost", int(proxy["url"].rsplit(":", 1)[1]), timeout=5
    )
    try:
        connection.request(method, path, headers=request_headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_routes_api_prefix_boundaries_and_path_stripping(proxy: dict[str, Any]) -> None:
    """API prefix is stripped while unrelated paths go to the UI."""
    expected = {
        "/": ("ui", "/"),
        "/api": ("api", "/"),
        "/api/docs": ("api", "/docs"),
        "/api/openapi.json": ("api", "/openapi.json"),
        "/prefect-other": ("ui", "/prefect-other"),
    }
    for path, (service, upstream_path) in expected.items():
        status, _headers, body = request(proxy, path)
        assert status == 200
        assert json.loads(body)["service"] == service
        assert json.loads(body)["path"] == upstream_path


def test_trusted_proxy_forwarded_scheme_is_preserved(proxy: dict[str, Any]) -> None:
    """A configured trusted proxy can preserve its public HTTPS scheme."""
    status, _headers, body = request(proxy, "/api/docs", headers={"X-Forwarded-Proto": "https"})

    assert status == 200
    assert json.loads(body)["proto"] == "https"


@pytest.mark.parametrize("proxy", ["192.0.2.0/24"], indirect=True)
def test_untrusted_forwarded_scheme_is_overwritten(proxy: dict[str, Any]) -> None:
    """A direct client cannot spoof the scheme seen by upstream services."""
    status, _headers, body = request(proxy, "/api/docs", headers={"X-Forwarded-Proto": "https"})

    assert status == 200
    assert json.loads(body)["proto"] == "http"


def test_prefect_auth_fails_closed_and_preserves_paths(proxy: dict[str, Any]) -> None:
    """Only a successful QDash auth check reaches Prefect with its path intact."""
    paths = ("/prefect", "/prefect/dashboard", "/prefect/assets/app.js", "/prefect/api/health")
    for path in paths:
        for token, expected_status in (
            (None, 401),
            ("invalid", 401),
            ("disabled", 403),
            ("failure", 503),
        ):
            status, _headers, _body = request(proxy, path, token=token)
            assert status == expected_status, (path, token, status)

        status, _headers, body = request(proxy, path, token="valid")
        assert status == 200
        assert json.loads(body)["service"] == "prefect"
        assert json.loads(body)["path"] == path


def test_html_redirect_is_limited_to_get_and_head_navigation(proxy: dict[str, Any]) -> None:
    """HTML GET/HEAD requests redirect, while HTML POST requests return 401."""
    get_status, headers, _body = request(proxy, "/prefect/dashboard", accept="text/html")
    assert get_status == 302
    assert headers["Location"] == "/login"

    head_status, _headers, _body = request(
        proxy, "/prefect/dashboard", method="HEAD", accept="text/html"
    )
    assert head_status == 302

    post_status, _headers, _body = request(
        proxy, "/prefect/dashboard", method="POST", accept="text/html"
    )
    assert post_status == 401


def test_websocket_upgrade_is_auth_gated(proxy: dict[str, Any]) -> None:
    """Authenticated websocket upgrades pass through and unauthorized ones do not."""
    handshake = {
        "Connection": "Upgrade",
        "Upgrade": "websocket",
        "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
        "Sec-WebSocket-Version": "13",
    }
    for token, expected_status in (("valid", 101), (None, 401), ("disabled", 403)):
        headers = dict(handshake)
        if token is not None:
            headers["Cookie"] = f"access_token={token}"
        connection = http.client.HTTPConnection(
            "localhost", int(proxy["url"].rsplit(":", 1)[1]), timeout=5
        )
        response: http.client.HTTPResponse | None = None
        try:
            connection.request("GET", "/prefect/api/events/out", headers=headers)
            response = connection.getresponse()
            assert response.status == expected_status
            if expected_status == 101:
                assert response.getheader("Upgrade") == "websocket"
                state: BackendState = proxy["states"]["prefect"]
                with state.lock:
                    assert ("/prefect/api/events/out", None) in state.seen
        finally:
            if response is not None:
                response.close()
            connection.close()


def test_prefect_sse_streaming_and_disconnect_cancel(proxy: dict[str, Any]) -> None:
    """SSE data streams promptly and closing the client cancels the upstream."""
    state: BackendState = proxy["states"]["prefect"]
    connection = http.client.HTTPConnection(
        "localhost", int(proxy["url"].rsplit(":", 1)[1]), timeout=5
    )
    connection.request("GET", "/prefect/stream", headers={"Cookie": "access_token=valid"})
    response = connection.getresponse()
    assert response.status == 200
    assert response.getheader("Content-Type") == "text/event-stream"
    assert state.stream_started.wait(timeout=2)
    assert response.read1(5).startswith(b"data:")
    response.close()
    connection.close()
    assert state.stream_disconnected.wait(timeout=3)
