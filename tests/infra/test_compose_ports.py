"""Verify the published ports in each supported Compose mode."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HTTPS_ENTRYPOINT = REPO_ROOT / "config/caddy/https-entrypoint.sh"


def render_compose(
    *files: str,
    profile: str | None = None,
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Render Compose configuration without resolving container environment files."""
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose CLI is not installed")

    command = ["docker", "compose", "--env-file", ".env.example"]
    for compose_file in files:
        command.extend(("-f", compose_file))
    if profile is not None:
        command.extend(("--profile", profile))
    command.extend(("config", "--format", "json", "--no-env-resolution"))
    environment = os.environ.copy()
    environment["CLIENT_URL"] = "https://qdash.example.test"
    environment.update(variables or {})
    result = subprocess.run(  # noqa: S603
        command,
        check=True,
        capture_output=True,
        cwd=REPO_ROOT,
        env=environment,
        text=True,
    )
    return json.loads(result.stdout)


def published_ports(compose: dict[str, Any]) -> dict[str, set[tuple[str, str, int]]]:
    """Return service host bindings as (host IP, published port, target port)."""
    return {
        name: {
            (port.get("host_ip", ""), str(port["published"]), port["target"])
            for port in service.get("ports", [])
        }
        for name, service in compose["services"].items()
        if service.get("ports")
    }


def test_default_compose_publishes_only_caddy() -> None:
    """The standard deployment exposes only the browser entry point."""
    actual = published_ports(render_compose("compose.yaml"))

    assert actual == {"caddy": {("", "5714", 80)}}


def test_host_development_publishes_loopback_dependencies() -> None:
    """The CLI development override exposes only local service dependencies."""
    actual = published_ports(render_compose("compose.yaml", "compose.host.yaml"))

    assert actual == {
        "caddy": {("", "5714", 80)},
        "deployment-service": {("127.0.0.1", "4006", 8001)},
        "mongo": {("127.0.0.1", "27017", 27017)},
        "prefect-server": {("127.0.0.1", "4200", 4200)},
    }


def test_https_override_replaces_http_port() -> None:
    """HTTPS mode publishes only TCP 80 and 443 from Caddy."""
    actual = published_ports(render_compose("compose.yaml", "compose.https.yaml"))

    assert actual == {"caddy": {("", "80", 80), ("", "443", 443)}}


def test_devcontainer_publishes_only_its_browser_gateway() -> None:
    """The devcontainer exposes its Caddy port to the host on loopback."""
    compose = render_compose("compose.devcontainer.yaml")

    assert published_ports(compose) == {"devcontainer": {("127.0.0.1", "5714", 5714)}}
    assert compose["services"]["devcontainer"]["environment"]["QDASH_DEV_CONTAINER"] == "1"


def test_admin_override_publishes_loopback_management_ports() -> None:
    """Admin access remains loopback-only and enables mongo-express explicitly."""
    actual = published_ports(render_compose("compose.yaml", "compose.admin.yaml", profile="admin"))

    assert actual == {
        "caddy": {("", "5714", 80)},
        "mongo": {("127.0.0.1", "27017", 27017)},
        "mongo-express": {("127.0.0.1", "8081", 8081)},
        "postgres": {("127.0.0.1", "5432", 5432)},
    }


def test_compose_upstream_tracks_custom_api_port() -> None:
    """Caddy targets the API container's configured listening port."""
    compose = render_compose("compose.yaml", variables={"API_PORT": "5730"})

    assert compose["services"]["caddy"]["environment"]["CADDY_API_UPSTREAM"] == "api:5730"
    assert compose["services"]["api"]["command"][-4:-2] == ["--bind", ":5730"]


def test_compose_ui_port_is_independent_of_host_dev_port() -> None:
    """The Compose UI keeps its internal port separate from the host dev port."""
    compose = render_compose("compose.yaml")

    assert compose["services"]["ui"]["environment"]["PORT"] == "5714"


def test_api_and_prefect_trust_forwarded_headers_on_internal_network() -> None:
    """Only unpublished API and Prefect services trust Docker proxy peers."""
    compose = render_compose("compose.yaml")

    assert compose["services"]["api"]["environment"]["FORWARDED_ALLOW_IPS"] == "*"
    assert compose["services"]["prefect-server"]["environment"]["FORWARDED_ALLOW_IPS"] == "*"
    assert set(published_ports(compose)) == {"caddy"}


def test_https_override_requires_https_client_url() -> None:
    """HTTPS mode runs the mounted entrypoint that validates CLIENT_URL."""
    caddy = render_compose("compose.yaml", "compose.https.yaml")["services"]["caddy"]

    assert caddy["entrypoint"] == ["/bin/sh", "/etc/caddy/https-entrypoint.sh"]
    assert any(
        volume["source"].endswith("config/caddy/https-entrypoint.sh")
        and volume["target"] == "/etc/caddy/https-entrypoint.sh"
        and volume.get("read_only") is True
        for volume in caddy["volumes"]
    )


def run_https_entrypoint(client_url: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run the HTTPS entrypoint script with a stub Caddy executable."""
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir(exist_ok=True)
    stub = stub_bin / "caddy"
    stub.write_text('#!/bin/sh\nprintf "%s" "$CADDY_SITE_ADDRESS"\n')
    stub.chmod(0o755)
    return subprocess.run(  # noqa: S603
        ["/bin/sh", str(HTTPS_ENTRYPOINT)],
        check=False,
        capture_output=True,
        env={
            **os.environ,
            "CLIENT_URL": client_url,
            "CADDY_SITE_ADDRESS": client_url,
            "PATH": f"{stub_bin}:{os.environ['PATH']}",
        },
        text=True,
    )


@pytest.mark.parametrize(
    ("client_url", "expected_site"),
    [
        ("https://qdash.example.test/", "https://qdash.example.test"),
        ("https://qdash.example.test:443/", "https://qdash.example.test:443"),
        ("https://[2001:db8::1]", "https://[2001:db8::1]"),
        ("https://[2001:db8::1]:443/", "https://[2001:db8::1]:443"),
    ],
)
def test_https_override_normalizes_trailing_slash(
    client_url: str, expected_site: str, tmp_path: Path
) -> None:
    """A single trailing slash is removed before Caddy receives the site address."""
    result = run_https_entrypoint(client_url, tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == expected_site


@pytest.mark.parametrize(
    "client_url",
    [
        "http://qdash.example.test",
        "https://qdash.example.test/path",
        "https://qdash.example.test:8443",
        "https://user@qdash.example.test",
        "https://qdash.example.test?next=/login",
        "https://qdash.example.test#fragment",
        "https://qdash.example.test:443:443",
        "https://[2001:db8::1]:8443",
        "https://2001:db8::1",
        "https://",
    ],
)
def test_https_override_rejects_non_origin_urls(client_url: str, tmp_path: Path) -> None:
    """HTTPS mode rejects URLs that are not supported public origins."""
    result = run_https_entrypoint(client_url, tmp_path)

    assert result.returncode != 0
    assert (
        "Paths, credentials, queries, fragments, and other ports are unsupported." in result.stderr
    )


def run_task_with_stub(
    task_name: str,
    executable_name: str,
    script: str,
    devcontainer: bool,
    tmp_path: Path,
) -> list[str]:
    """Run one long-running dev task against a stub executable and capture its environment."""
    task_cli = shutil.which("task")
    if task_cli is None:
        pytest.skip("Task CLI is not installed")

    stub_bin = tmp_path / "bin"
    stub_bin.mkdir(exist_ok=True)
    stub = stub_bin / executable_name
    stub.write_text(script)
    stub.chmod(0o755)
    capture = tmp_path / "task-environment.txt"
    environment = os.environ.copy()
    environment.update(
        {
            "QDASH_DEV_CONTAINER": "1" if devcontainer else "0",
            "TASK_CAPTURE": str(capture),
            "PATH": f"{stub_bin}:{os.environ['PATH']}",
            "UI_PORT": "5714",
            "UI_INTERNAL_PORT": "5716",
            "API_PORT": "5715",
            "PREFECT_PORT": "4200",
            "DEPLOYMENT_SERVICE_PORT": "4006",
            "MONGO_HOST": "",
            "PREFECT_API_URL": "",
            "DEPLOYMENT_SERVICE_URL": "",
            "CADDY_LOCAL_SITE_ADDRESS": "",
            "CADDY_LOCAL_BIND_ADDRESS": "",
            "CADDY_SITE_ADDRESS": "",
            "CADDY_BIND_ADDRESS": "",
            "CADDY_UI_UPSTREAM": "",
            "CADDY_API_UPSTREAM": "",
            "CADDY_PREFECT_UPSTREAM": "",
            "CADDY_TRUSTED_PROXIES": "",
            "FORWARDED_ALLOW_IPS": "",
        }
    )
    result = subprocess.run(  # noqa: S603
        [task_cli, task_name],
        check=True,
        capture_output=True,
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    return capture.read_text().splitlines()


@pytest.mark.parametrize(
    ("devcontainer", "expected"),
    [
        (
            False,
            [
                "http://localhost:5714",
                "127.0.0.1",
                "127.0.0.1:5716",
                "127.0.0.1:5715",
                "127.0.0.1:4200",
                "127.0.0.1/32 ::1/128",
            ],
        ),
        (
            True,
            [
                "http://:5714",
                "0.0.0.0",  # noqa: S104
                "127.0.0.1:5716",
                "127.0.0.1:5715",
                "prefect-server:4200",
                "127.0.0.1/32 ::1/128",
            ],
        ),
    ],
)
def test_dev_proxy_task_uses_context_upstreams(
    devcontainer: bool, expected: list[str], tmp_path: Path
) -> None:
    """The actual proxy task selects host or devcontainer settings."""
    script = '#!/bin/sh\nprintf "%s\\n" "$CADDY_SITE_ADDRESS" "$CADDY_BIND_ADDRESS" "$CADDY_UI_UPSTREAM" "$CADDY_API_UPSTREAM" "$CADDY_PREFECT_UPSTREAM" "$CADDY_TRUSTED_PROXIES" > "$TASK_CAPTURE"\n'
    actual = run_task_with_stub("dev-proxy-local", "caddy", script, devcontainer, tmp_path)

    assert actual == expected


@pytest.mark.parametrize(
    ("devcontainer", "expected"),
    [
        (
            False,
            [
                "localhost",
                "http://127.0.0.1:4200/prefect/api",
                "http://127.0.0.1:4006",
                "127.0.0.1",
            ],
        ),
        (
            True,
            [
                "mongo",
                "http://prefect-server:4200/prefect/api",
                "http://deployment-service:8001",
                "*",
            ],
        ),
    ],
)
def test_dev_api_task_uses_context_upstreams(
    devcontainer: bool, expected: list[str], tmp_path: Path
) -> None:
    """The actual API task selects host ports or Docker service DNS."""
    script = '#!/bin/sh\nprintf "%s\\n" "$MONGO_HOST" "$PREFECT_API_URL" "$DEPLOYMENT_SERVICE_URL" "$FORWARDED_ALLOW_IPS" > "$TASK_CAPTURE"\n'
    actual = run_task_with_stub("dev-api-local", "uv", script, devcontainer, tmp_path)

    assert actual == expected
