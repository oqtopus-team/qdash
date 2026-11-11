"""Run config/caddy/Caddyfile against local upstreams.

Mock UI, API and Prefect servers check routing and the Prefect access gate. The QDash
API, served by the gunicorn command of compose.yaml, checks the redirects browsers get.
These tests need a Caddy executable (``CADDY_BIN`` or ``caddy`` on ``PATH``) and skip
without one. QDASH_API_UPSTREAM and QDASH_UI_UPSTREAM point Caddy at local ports, as
compose.yaml and compose.dev-local.yaml point it at their servers; the Prefect service
name in the Caddyfile is swapped for a local port.
"""

import base64
import hashlib
import http.client
import json
import os
import re
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
from qdash.api.services.flow_service.execution import _flow_run_url

REPO_ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = REPO_ROOT / "config/caddy/Caddyfile"
# The tunnel's public URL in .env; requests to its host come from browsers using HTTPS.
PUBLIC_HTTPS_URL = "https://qdash.example.com"
DEPLOYMENT_ID = "123e4567-e89b-12d3-a456-426614174000"
CHAT_STREAM = "/api/copilot/chat/stream"
CREATE_RUN = f"/prefect/api/deployments/{DEPLOYMENT_ID}/create_flow_run"


class Seen:
    """Requests one mock upstream received."""

    def __init__(self, service: str) -> None:
        self.service = service
        self.requests: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        # The chat stream holds its connection open until the test sets this.
        self.release_stream = threading.Event()
        # Set when the chat stream can no longer write: the client went away.
        self.stream_cancelled = threading.Event()

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

        if seen.service == "api" and self.path == CHAT_STREAM:
            self.stream_events(seen)
            return

        # Prefect's event streams, and the Next.js dev server's HMR socket.
        if (
            seen.service in {"prefect", "ui"}
            and self.headers.get("Upgrade", "").lower() == "websocket"
        ):
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

    def stream_events(self, seen: Seen) -> None:
        """Answer like the Copilot chat stream: SSE events while the connection lasts."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(b"event: status\ndata: first\n\n")
            self.wfile.flush()
            seen.release_stream.wait(timeout=30)
            # Keep writing, as the API's pings do, until the client is gone.
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
                time.sleep(0.05)
        except OSError:
            seen.stream_cancelled.set()

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
    """Return the Caddyfile listening on a local port, with Prefect at a local port."""
    text = CADDYFILE.read_text()
    replacements = {
        # Any Host header, as through a tunnel, but listen on loopback only.
        ":80 {": f"http://:{port} {{\n\tbind 127.0.0.1",
        "prefect-server:4200": f"127.0.0.1:{upstreams['prefect']}",
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
        "QDASH_API_UPSTREAM": f"127.0.0.1:{upstreams['api']}",
        "QDASH_UI_UPSTREAM": f"127.0.0.1:{upstreams['ui']}",
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


# The Prefect UI of the installed prefect package, served as `prefect server start` serves
# it: the UI app at /, the API at /api. A stub API stands in for Prefect's database-backed one.
PREFECT_UI_MODULE = """\
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from prefect.server.api.server import create_ui_app

api = FastAPI()


@api.get("/health")
def health():
    return True


@api.api_route("/{path:path}", methods=["GET", "POST"])
def missing(path: str):
    return JSONResponse({"detail": "Not Found"}, status_code=404)


app = FastAPI()
app.mount("/api", api)
app.mount("/", create_ui_app(ephemeral=False))
"""
# What a browser sends when it opens or reloads a page.
NAVIGATION = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Dest": "document",
}


@pytest.fixture(scope="module")
def prefect_ui_proxy(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """Start Caddy in front of the real Prefect UI, with the settings of compose.yaml."""
    caddy_executable()
    tmp_path = tmp_path_factory.mktemp("prefect-ui")
    (tmp_path / "caddy_test_prefect.py").write_text(PREFECT_UI_MODULE)
    compose = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text())
    settings = dict(
        setting.split("=", 1) for setting in compose["services"]["prefect-server"]["environment"]
    )
    port = free_port()
    env = {
        "PYTHONPATH": os.pathsep.join([str(tmp_path), os.environ.get("PYTHONPATH", "")]),
        "PREFECT_HOME": str(tmp_path / "home"),
        # Build the base-path copy of the UI here, not inside the installed package.
        "PREFECT_SERVER_UI_STATIC_DIRECTORY": str(tmp_path / "ui"),
        "PREFECT_SERVER_UI_SERVE_BASE": settings["PREFECT_SERVER_UI_SERVE_BASE"],
        "PREFECT_SERVER_UI_API_URL": settings["PREFECT_SERVER_UI_API_URL"],
    }
    command = [sys.executable, "-m", "uvicorn", "caddy_test_prefect:app", "--port", str(port)]
    command += ["--host", "127.0.0.1"]
    api = MockServer(("127.0.0.1", 0), MockHandler)
    api.daemon_threads = True
    api.seen = Seen("api")  # type: ignore[attr-defined]
    threading.Thread(target=api.serve_forever, daemon=True).start()
    upstreams = {"api": api.server_port, "prefect": port, "ui": free_port()}
    try:
        with (
            running(command, port, tmp_path / "prefect.log", env),
            caddy_proxy(tmp_path_factory.mktemp("caddy-prefect"), upstreams, "") as proxy_port,
        ):
            yield {"port": proxy_port}
    finally:
        api.shutdown()
        api.server_close()


@pytest.fixture
def proxy(caddy: dict[str, Any]) -> dict[str, Any]:
    """Return the running proxy with empty request records."""
    for seen in caddy["seen"].values():
        with seen.lock:
            seen.requests.clear()
        seen.release_stream.clear()
        seen.stream_cancelled.clear()
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
    "path",
    [
        # The Sidebar's Prefect link.
        "/prefect/dashboard",
        # The flow run links of QDash executions.
        _flow_run_url("", DEPLOYMENT_ID),
    ],
)
def test_prefect_pages_load_on_direct_navigation(
    prefect_ui_proxy: dict[str, Any], path: str
) -> None:
    """Opening or reloading a Prefect page gets its UI and the UI's assets, under /prefect."""
    status, headers, body = request(prefect_ui_proxy, path, token="viewer", headers=NAVIGATION)

    assert status == 200, body[:200]
    assert headers["Content-Type"].startswith("text/html")
    html = body.decode()
    scripts = re.findall(r'<script[^>]*src="([^"]+)"', html)
    assert scripts
    for asset in scripts + re.findall(r'<link[^>]*href="([^"]+\.css)"', html):
        assert asset.startswith("/prefect/assets/"), asset
        status, _headers, _body = request(prefect_ui_proxy, asset, token="viewer")
        assert status == 200, asset

    status, _headers, body = request(prefect_ui_proxy, "/prefect/ui-settings", token="viewer")
    assert json.loads(body)["api_url"] == "/prefect/api"


def test_prefect_answers_non_page_requests_without_its_ui(
    prefect_ui_proxy: dict[str, Any],
) -> None:
    """Prefect API errors and missing assets reach the browser as they are, never as a page."""
    status, headers, body = request(
        prefect_ui_proxy, "/prefect/api/flow_runs/" + DEPLOYMENT_ID, token="viewer"
    )
    assert status == 404
    assert json.loads(body) == {"detail": "Not Found"}

    status, _headers, _body = request(
        prefect_ui_proxy, "/prefect/api/does-not-exist", token="viewer", headers=NAVIGATION
    )
    assert status == 404

    # Prefect serves its UI for page paths only to HTML navigations, so a missing asset or a
    # fetch of a page path without `Accept: text/html` is a 404, not the UI.
    for path in ("/prefect/assets/missing.js", "/prefect/dashboard"):
        status, headers, _body = request(
            prefect_ui_proxy, path, token="viewer", headers={"Accept": "*/*"}
        )
        assert status == 404, path
        assert not headers.get("Content-Type", "").startswith("text/html"), path

    status, headers, _body = request(prefect_ui_proxy, "/prefect/dashboard", headers=NAVIGATION)
    assert status == 302
    assert headers["Location"] == "/login"


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


def test_next_dev_hmr_websocket_reaches_the_ui(proxy: dict[str, Any]) -> None:
    """The Next.js 16 dev server's HMR socket (/_next/hmr) upgrades with the browser's Host."""
    assert websocket_status(proxy, "/_next/hmr", None) == 101

    hmr = proxy["seen"]["ui"].requests[-1]
    assert hmr["path"] == "/_next/hmr"
    assert hmr["headers"]["Host"] == f"127.0.0.1:{proxy['port']}"
    assert proxy["seen"]["api"].paths() == []


def read_until(sock: socket.socket, marker: bytes, received: bytes = b"") -> bytes:
    """Read from the socket until the marker arrives, failing on timeout or EOF."""
    while marker not in received:
        chunk = sock.recv(4096)
        assert chunk, f"connection closed before {marker!r}: {received!r}"
        received += chunk
    return received


def test_chat_stream_events_arrive_while_the_api_holds_the_connection(
    proxy: dict[str, Any],
) -> None:
    """Caddy forwards each SSE event at once, and a closed browser connection stops the API."""
    seen = proxy["seen"]["api"]
    body = b'{"message": "hi"}'
    with socket.create_connection(("127.0.0.1", proxy["port"]), timeout=5) as sock:
        sock.sendall(
            f"POST {CHAT_STREAM} HTTP/1.1\r\nHost: localhost:5714\r\n"
            "Authorization: Bearer user-token\r\nX-Project-Id: project-1\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n".encode()
            + body
        )
        # The first event arrives while the API still holds the stream open.
        received = read_until(sock, b"data: first\n\n")
        assert b"200 OK" in received.split(b"\r\n", 1)[0]
        assert b"text/event-stream" in received.lower()
        assert not seen.release_stream.is_set()

        chat = seen.requests[-1]
        assert chat["headers"]["Authorization"] == "Bearer user-token"
        assert chat["headers"]["X-Project-Id"] == "project-1"
        assert chat["body"] == body.decode()

        seen.release_stream.set()
        read_until(sock, b": ping\n\n")
    # Stop in the browser closes its connection; Caddy then closes the API's.
    assert seen.stream_cancelled.wait(timeout=10)
