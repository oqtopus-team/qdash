"""Run config/caddy/Caddyfile against local upstreams.

Mock UI, API and Prefect servers check routing and the Prefect access gate. The QDash
API, served by the gunicorn command of compose.yaml, checks the redirects browsers get.
These tests need a Caddy executable (``CADDY_BIN`` or ``caddy`` on ``PATH``) and skip
without one. The Compose service names in the Caddyfile are swapped for local ports.
"""

import base64
import hashlib
import http.client
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml

from qdash.api.lib.prefect_access import is_prefect_read_request

REPO_ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = REPO_ROOT / "config/caddy/Caddyfile"
# The tunnel's public URL in .env; requests to its host come from browsers using HTTPS.
PUBLIC_HTTPS_URL = "https://qdash.example.com"
DEPLOYMENT_ID = "123e4567-e89b-12d3-a456-426614174000"
CREATE_RUN = f"/prefect/api/deployments/{DEPLOYMENT_ID}/create_flow_run"


class Seen:
    """Requests one mock upstream received."""

    def __init__(self, service: str) -> None:
        self.service = service
        self.requests: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def paths(self) -> list[str]:
        """Return the received request paths."""
        with self.lock:
            return [request["path"] for request in self.requests]


class MockServer(ThreadingHTTPServer):
    """Ignore the connection resets of closed websocket handshakes."""

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Report only unexpected errors."""
        if not isinstance(sys.exc_info()[1], ConnectionError):
            super().handle_error(request, client_address)


class MockHandler(BaseHTTPRequestHandler):
    """Answer as the QDash UI, the QDash API (with its Prefect access check) or Prefect."""

    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: Any) -> None:
        """Keep mock output out of pytest logs."""

    def do_GET(self) -> None:
        """Handle GET."""
        self.respond()

    def do_HEAD(self) -> None:
        """Handle HEAD."""
        self.respond(send_body=False)

    def do_POST(self) -> None:
        """Handle POST."""
        self.respond()

    def respond(self, *, send_body: bool = True) -> None:
        """Record the request and answer for the configured service."""
        seen: Seen = self.server.seen  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode() if length else ""
        with seen.lock:
            seen.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})

        # Like FastAPI, route on the path alone: Caddy's rewrite keeps the query string.
        if seen.service == "api" and self.path.partition("?")[0] == "/auth/prefect-access":
            self.send_json(self.access_status(), {}, send_body=send_body)
            return

        if seen.service == "prefect" and self.headers.get("Upgrade", "").lower() == "websocket":
            key = self.headers["Sec-WebSocket-Key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
            accept = base64.b64encode(hashlib.sha1(key.encode(), usedforsecurity=False).digest())
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept.decode())
            self.end_headers()
            self.close_connection = True
            return

        self.send_json(
            200,
            {
                "service": seen.service,
                "path": self.path,
                "body": body,
                "proto": self.headers.get("X-Forwarded-Proto"),
            },
            send_body=send_body,
        )

    def access_status(self) -> int:
        """Mimic GET /auth/prefect-access for the fixed test tokens."""
        if self.headers.get("Upgrade") or self.headers.get("Content-Length"):
            return 400  # The check must be a plain, bodiless request.
        authorization = self.headers.get("Authorization", "")
        allowed = is_prefect_read_request(
            self.headers.get("X-Forwarded-Method", ""),
            self.headers.get("X-Forwarded-Uri", ""),
            self.headers.get("X-Forwarded-Upgrade", ""),
        )
        statuses = {
            "Bearer admin": 204,
            "Bearer viewer": 204 if allowed else 403,
            "Bearer disabled": 403,
            "Bearer failure": 503,
        }
        return statuses.get(authorization, 401)

    def send_json(self, status: int, payload: dict[str, Any], *, send_body: bool) -> None:
        """Write a JSON response with a fixed length."""
        data = json.dumps(payload).encode() if status != 204 else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if send_body:
            self.wfile.write(data)


def local_caddyfile(port: int, upstreams: dict[str, int]) -> str:
    """Return the Caddyfile with its Compose addresses replaced by local ones."""
    text = CADDYFILE.read_text()
    replacements = {
        # Any Host header, as through a tunnel, but listen on loopback only.
        ":80 {": f"http://:{port} {{\n\tbind 127.0.0.1",
        "api:{$API_PORT}": f"127.0.0.1:{upstreams['api']}",
        "prefect-server:4200": f"127.0.0.1:{upstreams['prefect']}",
        "ui:{$UI_PORT}": f"127.0.0.1:{upstreams['ui']}",
    }
    for compose_address, local_address in replacements.items():
        assert compose_address in text, compose_address
        text = text.replace(compose_address, local_address)
    return text


def caddy_executable() -> str:
    """Return the Caddy executable, or skip the test without one."""
    caddy = os.environ.get("CADDY_BIN") or shutil.which("caddy")
    if caddy is None:
        pytest.skip("Set CADDY_BIN or put caddy on PATH to run the proxy tests")
    return caddy


def free_port() -> int:
    """Return a currently unused local port."""
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port: int = reservation.getsockname()[1]
        return port


def wait_until_listening(process: subprocess.Popen[bytes], port: int, log: Path) -> None:
    """Wait until the process accepts connections on the port."""
    deadline = time.monotonic() + 60
    while True:
        if process.poll() is not None:
            pytest.fail(f"{process.args!r} exited:\n{log.read_text()}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            if time.monotonic() > deadline:
                pytest.fail(f"{process.args!r} did not listen:\n{log.read_text()}")
            time.sleep(0.05)


@contextmanager
def running(command: list[str], port: int, log: Path, env: dict[str, str]) -> Iterator[None]:
    """Run a server process until the block exits."""
    with log.open("wb") as output:
        process = subprocess.Popen(  # noqa: S603
            command, env={**os.environ, **env}, stdout=output, stderr=subprocess.STDOUT
        )
        try:
            wait_until_listening(process, port, log)
            yield
        finally:
            process.terminate()
            process.wait(timeout=10)


@contextmanager
def caddy_proxy(tmp_path: Path, upstreams: dict[str, int], client_url: str) -> Iterator[int]:
    """Run Caddy with the repository Caddyfile in front of local upstreams."""
    caddy = caddy_executable()
    port = free_port()
    config = tmp_path / "Caddyfile"
    config.write_text(local_caddyfile(port, upstreams))
    env = {
        "CLIENT_URL": client_url,
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
    }
    command = [caddy, "run", "--config", str(config), "--adapter", "caddyfile"]
    with running(command, port, tmp_path / "caddy.log", env):
        yield port


@pytest.fixture(scope="module")
def caddy(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """Start Caddy in front of the mock upstreams, with an https:// CLIENT_URL."""
    caddy_executable()
    servers: dict[str, MockServer] = {}
    for service in ("api", "prefect", "ui"):
        server = MockServer(("127.0.0.1", 0), MockHandler)
        server.daemon_threads = True
        server.seen = Seen(service)  # type: ignore[attr-defined]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers[service] = server
    upstreams = {name: server.server_port for name, server in servers.items()}
    try:
        with caddy_proxy(tmp_path_factory.mktemp("caddy"), upstreams, PUBLIC_HTTPS_URL) as port:
            yield {"port": port, "seen": {name: s.seen for name, s in servers.items()}}  # type: ignore[attr-defined]
    finally:
        for server in servers.values():
            server.shutdown()
            server.server_close()


def compose_api_command(module: str, port: int) -> list[str]:
    """Return the api service command of compose.yaml for a local app module and port."""
    compose = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text())
    command = shlex.split(compose["services"]["api"]["command"])
    assert command[:2] == ["gunicorn", "main:app"], command
    local = [sys.executable, "-m", "gunicorn", module]
    arguments = iter(command[2:])
    for argument in arguments:
        if argument == "--reload":
            continue
        if argument in {"--workers", "--bind"}:
            next(arguments)
            local += [argument, "1" if argument == "--workers" else f"127.0.0.1:{port}"]
            continue
        local.append(argument)
    return local


# The QDash API app without its database startup; routing and redirects are unchanged.
API_MODULE = """\
from contextlib import asynccontextmanager

from qdash.api.app.factory import create_app

app = create_app()


@asynccontextmanager
async def no_database(_app):
    yield


app.router.lifespan_context = no_database
"""


@pytest.fixture(scope="module")
def api_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[int]:
    """Serve the QDash API with the server command and options of compose.yaml."""
    caddy_executable()
    tmp_path = tmp_path_factory.mktemp("api")
    (tmp_path / "caddy_test_api.py").write_text(API_MODULE)
    port = free_port()
    env = {
        "PYTHONPATH": os.pathsep.join([str(tmp_path), os.environ.get("PYTHONPATH", "")]),
        # Let gunicorn fork its worker on macOS.
        "OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES",
        # In Compose, Caddy reaches the API from a custom_net address, not loopback, so
        # the default trust (127.0.0.1) must not cover the local Caddy here either.
        "FORWARDED_ALLOW_IPS": "192.0.2.1",
    }
    command = compose_api_command("caddy_test_api:app", port)
    with running(command, port, tmp_path / "api.log", env):
        yield port


@pytest.fixture(scope="module", params=["http://localhost:5714", PUBLIC_HTTPS_URL])
def api_proxy(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory, api_server: int
) -> Iterator[dict[str, Any]]:
    """Start Caddy in front of the QDash API with a local or an https:// CLIENT_URL."""
    # Only /api is requested, so the UI and Prefect upstreams can stay closed.
    upstreams = {"api": api_server, "prefect": free_port(), "ui": free_port()}
    client_url: str = request.param
    with caddy_proxy(tmp_path_factory.mktemp("caddy-api"), upstreams, client_url) as port:
        yield {"port": port, "client_url": client_url}


@pytest.fixture
def proxy(caddy: dict[str, Any]) -> dict[str, Any]:
    """Return the running proxy with empty request records."""
    for seen in caddy["seen"].values():
        with seen.lock:
            seen.requests.clear()
    return caddy


def request(
    proxy: dict[str, Any],
    path: str,
    *,
    token: str | None = None,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """Send one request through Caddy."""
    request_headers = dict(headers or {})
    if token is not None:
        request_headers["Cookie"] = f"access_token={token}"
    connection = http.client.HTTPConnection("127.0.0.1", proxy["port"], timeout=5)
    try:
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def websocket_status(proxy: dict[str, Any], path: str, token: str | None) -> int:
    """Send a websocket handshake through Caddy and return the status."""
    headers = {
        "Connection": "Upgrade",
        "Upgrade": "websocket",
        "Sec-WebSocket-Key": base64.b64encode(os.urandom(16)).decode(),
        "Sec-WebSocket-Version": "13",
    }
    if token is not None:
        headers["Cookie"] = f"access_token={token}"
    connection = http.client.HTTPConnection("127.0.0.1", proxy["port"], timeout=5)
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        status = response.status
        response.close()
        return status
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("path", "service", "upstream_path"),
    [
        ("/", "ui", "/"),
        ("/execution/chip-1", "ui", "/execution/chip-1"),
        ("/apix", "ui", "/apix"),
        ("/prefect-other", "ui", "/prefect-other"),
        ("/api", "api", "/api"),
        ("/api/auth/me", "api", "/api/auth/me"),
        (
            "/api/executions/figure?path=a%2Fb.png",
            "api",
            "/api/executions/figure?path=a%2Fb.png",
        ),
    ],
)
def test_routes_ui_and_api(
    proxy: dict[str, Any], path: str, service: str, upstream_path: str
) -> None:
    """The UI gets everything but /api and /prefect; the API gets /api with its prefix."""
    status, _headers, body = request(proxy, path)

    assert status == 200
    assert json.loads(body)["service"] == service
    assert json.loads(body)["path"] == upstream_path


def test_api_post_body_reaches_the_api(proxy: dict[str, Any]) -> None:
    """API requests are not gated by Caddy and keep their body."""
    status, _headers, body = request(proxy, "/api/auth/login", method="POST", body="a=1")

    assert status == 200
    assert json.loads(body)["body"] == "a=1"


@pytest.mark.parametrize("path", ["/", "/api/auth/me", "/prefect/dashboard"])
@pytest.mark.parametrize(
    ("host", "client_proto", "proto"),
    [
        ("qdash.example.com", None, "https"),
        ("qdash.example.com", "http", "https"),
        ("localhost:5714", None, "http"),
        ("localhost:5714", "https", "http"),
        ("other.example.com", "https", "http"),
    ],
)
def test_upstreams_get_the_scheme_of_client_url(
    proxy: dict[str, Any], path: str, host: str, client_proto: str | None, proto: str
) -> None:
    """Upstreams get https only for the host of an https:// CLIENT_URL; clients cannot set it."""
    headers = {"Host": host}
    if client_proto is not None:
        headers["X-Forwarded-Proto"] = client_proto

    status, _headers, body = request(proxy, path, token="viewer", headers=headers)

    assert status == 200
    assert json.loads(body)["proto"] == proto


@pytest.mark.parametrize(
    ("path", "upstream_path"),
    [
        ("/prefect", "/prefect"),
        ("/prefect/dashboard", "/prefect/dashboard"),
        ("/prefect/runs/flow-run/abc", "/prefect/runs/flow-run/abc"),
        ("/prefect/api/health", "/api/health"),
        ("/prefect/api/flow_runs/abc?limit=1", "/api/flow_runs/abc?limit=1"),
    ],
)
def test_prefect_requires_sign_in_and_maps_its_api(
    proxy: dict[str, Any], path: str, upstream_path: str
) -> None:
    """Prefect is reached only after a successful check; /prefect/api maps to /api."""
    for token, expected in ((None, 401), ("bogus", 401), ("disabled", 403), ("failure", 503)):
        status, _headers, _body = request(proxy, path, token=token)
        assert status == expected, (path, token)
    assert proxy["seen"]["prefect"].paths() == []

    status, _headers, body = request(proxy, path, token="viewer")

    assert status == 200
    assert json.loads(body)["service"] == "prefect"
    assert json.loads(body)["path"] == upstream_path


def test_access_check_gets_the_original_request(proxy: dict[str, Any]) -> None:
    """The check sees the browser's method and URI, from the cookie only, without a body."""
    request(
        proxy,
        "/prefect/api/flow_runs/filter?limit=1",
        token="viewer",
        method="POST",
        body='{"limit": 1}',
        headers={
            "Authorization": "Bearer admin",
            "X-Forwarded-Method": "GET",
            "X-Forwarded-Uri": "/prefect/dashboard",
        },
    )

    check = proxy["seen"]["api"].requests[-1]
    assert check["path"].partition("?")[0] == "/auth/prefect-access"
    assert check["headers"]["Authorization"] == "Bearer viewer"
    assert check["headers"]["X-Forwarded-Method"] == "POST"
    assert check["headers"]["X-Forwarded-Uri"] == "/prefect/api/flow_runs/filter?limit=1"
    assert check["body"] == ""


def test_client_authorization_header_does_not_replace_the_cookie(proxy: dict[str, Any]) -> None:
    """Only the browser session cookie signs a Prefect request in."""
    status, _headers, _body = request(
        proxy, "/prefect/dashboard", headers={"Authorization": "Bearer admin"}
    )

    assert status == 401


def test_signed_out_page_navigation_redirects_to_login(proxy: dict[str, Any]) -> None:
    """HTML GET and HEAD navigations go to the login page; other requests get 401."""
    for method in ("GET", "HEAD"):
        status, headers, _body = request(
            proxy, "/prefect/dashboard", method=method, headers={"Accept": "text/html"}
        )
        assert status == 302
        assert headers["Location"] == "/login"

    status, _headers, _body = request(
        proxy, "/prefect/dashboard", method="POST", headers={"Accept": "text/html"}
    )
    assert status == 401


def test_viewer_queries_keep_their_body(proxy: dict[str, Any]) -> None:
    """An allowlisted POST query of a non-admin reaches Prefect with its body."""
    status, _headers, body = request(
        proxy, "/prefect/api/flow_runs/filter", token="viewer", method="POST", body='{"limit":5}'
    )

    assert status == 200
    assert json.loads(body)["path"] == "/api/flow_runs/filter"
    assert json.loads(body)["body"] == '{"limit":5}'


@pytest.mark.parametrize(
    "path",
    [CREATE_RUN, f"{CREATE_RUN}?x=/filter", "/prefect/api/flow_runs/filter/../../flows/x"],
)
def test_viewer_cannot_change_prefect_state(proxy: dict[str, Any], path: str) -> None:
    """A non-admin state change is denied before Prefect sees it."""
    status, _headers, _body = request(proxy, path, token="viewer", method="POST", body="{}")

    assert status == 403
    assert proxy["seen"]["prefect"].paths() == []


def test_admin_can_change_prefect_state(proxy: dict[str, Any]) -> None:
    """A system administrator's state change reaches Prefect with its body."""
    status, _headers, body = request(proxy, CREATE_RUN, token="admin", method="POST", body="{}")

    assert status == 200
    assert json.loads(body)["path"] == CREATE_RUN.removeprefix("/prefect")
    assert json.loads(body)["body"] == "{}"


def test_websockets_are_gated_by_direction(proxy: dict[str, Any]) -> None:
    """Viewers may open outbound event streams; inbound ones need an administrator."""
    assert websocket_status(proxy, "/prefect/api/events/out", None) == 401
    assert websocket_status(proxy, "/prefect/api/events/out", "viewer") == 101
    assert websocket_status(proxy, "/prefect/api/events/in", "viewer") == 403
    assert websocket_status(proxy, "/prefect/api/events/in", "admin") == 101
    assert "/api/events/out" in proxy["seen"]["prefect"].paths()


@pytest.mark.parametrize(
    ("client_url", "host", "scheme"),
    [
        ("https://QDASH.EXAMPLE.COM", "qdash.example.com", "https"),
        ("https://qdash.example.com", "QDASH.EXAMPLE.COM", "https"),
        ("https://[::1]:8443", "[::1]:8443", "https"),
        ("https://[::1]", "[::1]", "https"),
        ("https://[2001:DB8::1]:8443", "[2001:db8::1]:8443", "https"),
        ("https://[::1]:8443", "[::2]:8443", "http"),
        ("https://qdash.example.com", "qdash.example.com.evil.test", "http"),
    ],
)
def test_api_redirect_host_matching(
    tmp_path: Path, api_server: int, client_url: str, host: str, scheme: str
) -> None:
    """DNS case and IPv6 brackets do not downgrade matching public HTTPS redirects."""
    upstreams = {"api": api_server, "prefect": free_port(), "ui": free_port()}
    with caddy_proxy(tmp_path, upstreams, client_url) as port:
        status, headers, _body = request(
            {"port": port},
            "/api/auth/me/",
            headers={"Host": host, "X-Forwarded-Proto": "http" if scheme == "https" else "https"},
        )

    assert status == 307
    assert headers["Location"] == f"{scheme}://{host}/api/auth/me"


@pytest.mark.parametrize("client_proto", [None, "http", "https"])
def test_api_redirects_keep_the_browser_scheme(
    api_proxy: dict[str, Any], client_proto: str | None
) -> None:
    """A trailing-slash redirect of the API points at the URL the browser used, under /api."""
    tunnel = api_proxy["client_url"] == PUBLIC_HTTPS_URL
    host = "qdash.example.com" if tunnel else "localhost:5714"
    headers = {"Host": host}
    if client_proto is not None:
        headers["X-Forwarded-Proto"] = client_proto

    status, response_headers, _body = request(api_proxy, "/api/auth/me/", headers=headers)

    assert status == 307
    scheme = "https" if tunnel else "http"
    assert response_headers["Location"] == f"{scheme}://{host}/api/auth/me"


def test_api_redirects_for_local_hosts_stay_http(api_proxy: dict[str, Any]) -> None:
    """With any CLIENT_URL, opening QDash at localhost keeps plain HTTP redirects."""
    status, response_headers, _body = request(
        api_proxy, "/api/auth/me/", headers={"Host": "localhost:5714", "X-Forwarded-Proto": "https"}
    )

    assert status == 307
    assert response_headers["Location"] == "http://localhost:5714/api/auth/me"


def test_api_routes_requests_under_its_prefix(api_proxy: dict[str, Any]) -> None:
    """The API routes /api paths and documents itself under /api."""
    status, _headers, _body = request(api_proxy, "/api/auth/me")
    assert status == 401

    status, _headers, body = request(api_proxy, "/api/openapi.json")
    assert status == 200
    assert {"url": "/api"} in json.loads(body)["servers"]
