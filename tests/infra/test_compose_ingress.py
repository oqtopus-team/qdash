"""Check the rendered compose.yaml: Caddy on UI_PORT is the only published port.

These tests need the Docker Compose CLI and skip without it. The two-stack smoke
test at the end also starts containers and runs only with QDASH_COMPOSE_SMOKE=1.
"""

import http.client
import json
import os
import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_OVERLAY = REPO_ROOT / "compose.dev-local.yaml"

# URL and port settings of the .env.example shipped before Caddy, which existing
# deployments still use unchanged.
LEGACY_ENV = """\
ENV="dev-fake"
DEFAULT_BACKEND="fake"
MONGO_PORT=27017
MONGO_EXPRESS_PORT=8081
POSTGRES_PORT=5432
PREFECT_PORT=4200
API_PORT=5715
UI_PORT=5714
DEPLOYMENT_SERVICE_PORT=4006
CLIENT_URL=http://localhost:${UI_PORT}
NEXT_PUBLIC_API_URL=/api
NEXT_PUBLIC_DEFAULT_THEME=light
NEXT_PUBLIC_PREFECT_URL=http://localhost:${PREFECT_PORT}
PREFECT_API_URL=http://localhost:${PREFECT_PORT}/api
INTERNAL_API_URL=http://api:${API_PORT}
MONGO_INITDB_ROOT_USERNAME=root
MONGO_INITDB_ROOT_PASSWORD=example
POSTGRES_USER=postgres
POSTGRES_PASSWORD=prefect
POSTGRES_DB=prefect
"""


def clean_environment() -> dict[str, str]:
    """Return the caller's environment without settings that Compose would interpolate."""
    return {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME"} or key.startswith("DOCKER_")
    }


def render(
    tmp_path: Path,
    env: str = LEGACY_ENV,
    *profiles: str,
    files: tuple[Path, ...] = (REPO_ROOT / "compose.yaml",),
) -> dict[str, Any]:
    """Render the compose files with only the given .env content for interpolation."""
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose CLI is not installed")
    env_file = tmp_path / "env"
    env_file.write_text(env)
    command = ["docker", "compose"]
    for file in files:
        command += ["-f", str(file)]
    command += ["--env-file", str(env_file)]
    for profile in profiles:
        command += ["--profile", profile]
    command += ["config", "--format", "json", "--no-env-resolution"]
    # Keep the caller's shell variables (UI_PORT and so on) out of the result.
    result = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        check=False,
        cwd=tmp_path,
        env=clean_environment(),
        text=True,
    )
    assert result.returncode == 0, result.stderr
    compose: dict[str, Any] = json.loads(result.stdout)
    return compose


def published(compose: dict[str, Any]) -> dict[str, set[tuple[str, str, int]]]:
    """Return each service's (host IP, published port, container port) bindings."""
    return {
        name: {
            (port.get("host_ip", ""), str(port["published"]), port["target"])
            for port in service["ports"]
        }
        for name, service in compose["services"].items()
        if service.get("ports")
    }


def environment(service: dict[str, Any]) -> dict[str, str]:
    """Return a service's environment as a mapping."""
    return dict(service.get("environment") or {})


def test_legacy_env_publishes_only_caddy(tmp_path: Path) -> None:
    """With an unchanged old .env, Caddy on UI_PORT is the only host port, even on loopback."""
    compose = render(tmp_path, LEGACY_ENV, "tunnel")

    assert published(compose) == {"caddy": {("", "5714", 80)}}
    # The tunnel shares the host network and forwards to UI_PORT, as before.
    assert compose["services"]["tunnel"]["network_mode"] == "host"


def test_stacks_differing_only_in_env_and_ui_port_do_not_share_host_ports(
    tmp_path: Path,
) -> None:
    """Two stacks with the same internal ports need only distinct ENV and UI_PORT."""
    second_env = LEGACY_ENV.replace('ENV="dev-fake"', 'ENV="dev-fake-2"').replace(
        "UI_PORT=5714", "UI_PORT=6714"
    )
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = render(first_dir, LEGACY_ENV)
    second = render(second_dir, second_env)

    def host_ports(compose: dict[str, Any]) -> set[str]:
        return {port for bindings in published(compose).values() for _, port, _ in bindings}

    assert host_ports(first) == {"5714"}
    assert host_ports(second) == {"6714"}
    assert first["name"] == "dev-fake"
    assert second["name"] == "dev-fake-2"
    assert first["networks"]["custom_net"]["name"] == "dev-fake_custom_net"
    assert second["networks"]["custom_net"]["name"] == "dev-fake-2_custom_net"
    # Data directories are not derived from ENV or UI_PORT; separate checkouts or
    # *_DATA_PATH settings keep them apart.
    assert first["services"]["mongo"]["volumes"] == second["services"]["mongo"]["volumes"]


def test_dev_overlay_publishes_only_host_development_dependencies(tmp_path: Path) -> None:
    """compose.dev-local.yaml adds loopback ports for the host API and nothing else."""
    compose = render(tmp_path, files=(REPO_ROOT / "compose.yaml", DEV_OVERLAY))

    # Browsers still use only Caddy on UI_PORT; the rest is loopback for the host API.
    assert published(compose) == {
        "caddy": {("", "5714", 80)},
        "mongo": {("127.0.0.1", "27017", 27017)},
        "prefect-server": {("127.0.0.1", "4200", 4200)},
        "deployment-service": {("127.0.0.1", "4006", 8001)},
        "agent-runtime": {("127.0.0.1", "8002", 8002)},
    }

    custom = (
        LEGACY_ENV.replace("MONGO_PORT=27017", "MONGO_PORT=27018")
        .replace("PREFECT_PORT=4200", "PREFECT_PORT=4201")
        .replace("DEPLOYMENT_SERVICE_PORT=4006", "DEPLOYMENT_SERVICE_PORT=4007")
        + "AGENT_RUNTIME_PORT=8003\n"
    )
    ports = published(render(tmp_path, custom, files=(REPO_ROOT / "compose.yaml", DEV_OVERLAY)))
    assert ports["mongo"] == {("127.0.0.1", "27018", 27017)}
    assert ports["prefect-server"] == {("127.0.0.1", "4201", 4200)}
    assert ports["deployment-service"] == {("127.0.0.1", "4007", 8001)}
    assert ports["agent-runtime"] == {("127.0.0.1", "8003", 8003)}


@pytest.mark.parametrize(
    ("extra_env", "dev_host", "ui_dev_port"),
    [
        # macOS and Linux hosts: Caddy reaches host processes at host.docker.internal.
        ("", "host.docker.internal", "5713"),
        # The DevContainer sets QDASH_DEV_HOST; Caddy reaches it on custom_net.
        ("QDASH_DEV_HOST=devcontainer\nUI_DEV_PORT=3000\n", "devcontainer", "3000"),
    ],
)
def test_dev_overlay_points_caddy_at_the_development_servers(
    tmp_path: Path, extra_env: str, dev_host: str, ui_dev_port: str
) -> None:
    """The same Caddyfile proxies to the hot-reloading API and UI, not their images."""
    env = LEGACY_ENV.replace("API_PORT=5715", "API_PORT=5730") + extra_env
    services = render(tmp_path, env, files=(REPO_ROOT / "compose.yaml", DEV_OVERLAY))["services"]

    caddy = services["caddy"]
    assert environment(caddy) == {
        "QDASH_API_UPSTREAM": f"{dev_host}:5730",
        "QDASH_UI_UPSTREAM": f"{dev_host}:{ui_dev_port}",
        "CLIENT_URL": "http://localhost:5714",
    }
    # Linux Docker Engine resolves host.docker.internal only with this entry.
    assert caddy["extra_hosts"] == ["host.docker.internal=host-gateway"]
    # Starting caddy or agent-runtime must not build and start the api and ui images.
    assert set(caddy["depends_on"]) == {"prefect-server"}
    assert set(services["agent-runtime"]["depends_on"]) == {"agent-exec", "agent-runtime-auth"}
    # The runtime calls the development API back; the browser never reaches it.
    runtime = environment(services["agent-runtime"])
    assert runtime["QDASH_BASE_URL"] == f"http://{dev_host}:5730"
    # Same Caddyfile in both stacks.
    assert caddy["volumes"] == render(tmp_path)["services"]["caddy"]["volumes"]


def test_devcontainer_marks_itself_as_the_development_host(tmp_path: Path) -> None:
    """compose.devcontainer.yaml names itself for Caddy and shares custom_net."""
    compose = render(tmp_path, files=(REPO_ROOT / "compose.devcontainer.yaml",))
    devcontainer = compose["services"]["devcontainer"]

    assert environment(devcontainer)["QDASH_DEV_HOST"] == "devcontainer"
    assert "custom_net" in devcontainer["networks"]
    assert compose["networks"]["custom_net"]["name"] == "dev-fake_custom_net"


def test_only_host_development_tasks_load_the_dev_overlay() -> None:
    """dev-services and dev-local-down add the overlay; deployment tasks do not."""
    tasks = yaml.safe_load((REPO_ROOT / "Taskfile.yaml").read_text())["tasks"]

    def commands(name: str) -> list[str]:
        return [command for command in tasks[name]["cmds"] if isinstance(command, str)]

    overlay = "docker compose -f compose.yaml -f compose.dev-local.yaml"
    assert commands("dev-services")[0].startswith(f"{overlay} up -d ")
    # Caddy and the Pi Agent Runtime start with the other development services; the
    # API and UI images do not.
    started = set(commands("dev-services")[0].removeprefix(f"{overlay} up -d ").split())
    assert {"caddy", "agent-runtime", "prefect-server", "mongo"} <= started
    assert not started & {"api", "ui"}
    assert commands("dev-local-down")[-1] == f"{overlay} down"
    for name in ("deploy", "deploy-local", "deploy-local-fake"):
        assert all("compose.dev-local.yaml" not in command for command in commands(name))


def test_dev_processes_leave_the_ingress_port_to_caddy() -> None:
    """Next.js listens on UI_DEV_PORT, and dev-local-down never stops UI_PORT's listener."""
    tasks = yaml.safe_load((REPO_ROOT / "Taskfile.yaml").read_text())["tasks"]
    ui = "\n".join(tasks["dev-ui-local"]["cmds"])
    down = "\n".join(c for c in tasks["dev-local-down"]["cmds"] if isinstance(c, str))

    assert 'PORT="${UI_DEV_PORT:-5713}"' in ui
    assert "UI_PORT" not in ui
    assert 'stop_port "${UI_DEV_PORT:-5713}" "UI"' in down
    assert 'stop_port "${UI_PORT' not in down
    # The Next.js rewrites these variables configured are gone.
    for name in ("dev-api-local", "dev-ui-local"):
        assert "INTERNAL_" not in "\n".join(tasks[name]["cmds"])


def test_prefect_ui_moves_under_prefect_while_services_keep_its_api(tmp_path: Path) -> None:
    """The browser uses /prefect and /prefect/api; services keep Prefect's /api."""
    services = render(tmp_path)["services"]

    prefect = environment(services["prefect-server"])
    assert prefect["PREFECT_SERVER_UI_SERVE_BASE"] == "/prefect"
    assert prefect["PREFECT_SERVER_UI_API_URL"] == "/prefect/api"
    assert prefect["PREFECT_SERVER_API_CSRF_PROTECTION_ENABLED"] == "true"
    for name in ("api", "deployment-service", "user-flow-worker"):
        assert environment(services[name])["PREFECT_API_URL"] == "http://prefect-server:4200/api"


def test_ui_image_ignores_browser_urls_from_env(tmp_path: Path) -> None:
    """Old NEXT_PUBLIC_* URLs in .env cannot point the browser past Caddy."""
    env = LEGACY_ENV.replace("NEXT_PUBLIC_API_URL=/api", "NEXT_PUBLIC_API_URL=http://host:5715")
    ui = render(tmp_path, env)["services"]["ui"]

    assert ui["build"]["args"]["NEXT_PUBLIC_API_URL"] == "/api"
    assert "NEXT_PUBLIC_PREFECT_URL" not in ui["build"]["args"]
    # Caddy proxies /api, so the image no longer gets an internal API URL.
    assert "INTERNAL_API_URL" not in ui["build"]["args"]
    # A plain `docker compose up -d` rebuilds the UI instead of reusing an old image.
    assert ui["pull_policy"] == "build"


def test_custom_ports_follow_env(tmp_path: Path) -> None:
    """A non-default UI_PORT moves the entry point; Caddy follows the API and UI ports."""
    env = LEGACY_ENV.replace("UI_PORT=5714", "UI_PORT=8080").replace(
        "API_PORT=5715", "API_PORT=5730"
    )
    compose = render(tmp_path, env)
    services = compose["services"]

    assert published(compose)["caddy"] == {("", "8080", 80)}
    assert environment(services["caddy"]) == {
        "QDASH_API_UPSTREAM": "api:5730",
        "QDASH_UI_UPSTREAM": "ui:8080",
        "CLIENT_URL": "http://localhost:8080",
    }
    assert environment(services["ui"])["PORT"] == "8080"
    assert "--bind :5730" in " ".join(services["api"]["command"])


def test_caddy_gets_client_url_and_the_api_trusts_its_scheme(tmp_path: Path) -> None:
    """Caddy derives the browser scheme from CLIENT_URL; the API uses the header it sets."""
    env = LEGACY_ENV.replace(
        "CLIENT_URL=http://localhost:${UI_PORT}", "CLIENT_URL=https://qdash.example.com"
    )
    services = render(tmp_path, env)["services"]

    assert environment(services["caddy"])["CLIENT_URL"] == "https://qdash.example.com"
    assert "--forwarded-allow-ips=*" in services["api"]["command"]

    without_client_url = LEGACY_ENV.replace("CLIENT_URL=http://localhost:${UI_PORT}\n", "")
    caddy = render(tmp_path, without_client_url)["services"]["caddy"]
    assert environment(caddy)["CLIENT_URL"] == ""


def test_caddy_reads_the_repository_caddyfile(tmp_path: Path) -> None:
    """Caddy mounts config/caddy/Caddyfile read-only and gets no .env secrets."""
    caddy = render(tmp_path)["services"]["caddy"]

    assert "env_file" not in caddy
    assert any(
        volume["source"] == str(REPO_ROOT / "config/caddy/Caddyfile")
        and volume["target"] == "/etc/caddy/Caddyfile"
        and volume.get("read_only") is True
        for volume in caddy["volumes"]
    )
    assert set(caddy["depends_on"]) == {"ui", "api", "prefect-server"}


def free_port() -> int:
    """Return a TCP port that is free on all interfaces right now."""
    with socket.socket() as reservation:
        reservation.bind(("", 0))
        port: int = reservation.getsockname()[1]
        return port


@pytest.fixture
def smoke_stacks(tmp_path: Path) -> Iterator[list[tuple[str, int]]]:
    """Start Caddy and MongoDB of two stacks from the repository compose.yaml.

    Both stacks keep every internal port setting of LEGACY_ENV and differ only in
    ENV, UI_PORT and data paths. Upstreams such as the UI and API are not started,
    so Caddy answers 502; the test checks host bindings, not the application.
    """
    if os.environ.get("QDASH_COMPOSE_SMOKE") != "1":
        pytest.skip("set QDASH_COMPOSE_SMOKE=1 to start containers")
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose CLI is not installed")
    run_id = uuid.uuid4().hex[:8]
    stacks: list[tuple[str, int, Path]] = []
    for index in range(2):
        # A copy of the checkout files Compose reads, with its own .env.
        directory = tmp_path / f"stack{index}"
        (directory / "config/caddy").mkdir(parents=True)
        shutil.copy(REPO_ROOT / "compose.yaml", directory / "compose.yaml")
        shutil.copy(REPO_ROOT / "config/caddy/Caddyfile", directory / "config/caddy/Caddyfile")
        project = f"qdash-smoke-{run_id}-{index}"
        ui_port = free_port()
        env = LEGACY_ENV.replace('ENV="dev-fake"', f'ENV="{project}"').replace(
            "UI_PORT=5714", f"UI_PORT={ui_port}"
        )
        env += f"MONGO_DATA_PATH={directory / 'mongo'}\n"
        (directory / ".env").write_text(env)
        stacks.append((project, ui_port, directory))

    def compose(directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            ["docker", "compose", *arguments],  # noqa: S607
            capture_output=True,
            check=False,
            cwd=directory,
            env=clean_environment(),
            text=True,
            timeout=300,
        )

    try:
        for _, _, directory in stacks:
            started = compose(directory, "up", "-d", "--no-deps", "--no-build", "caddy", "mongo")
            assert started.returncode == 0, started.stderr
            # Each stack keeps its MongoDB data in its own MONGO_DATA_PATH.
            assert (directory / "mongo").is_dir()
        yield [(project, ui_port) for project, ui_port, _ in stacks]
    finally:
        for _, _, directory in stacks:
            compose(directory, "down", "--volumes", "--remove-orphans")


def test_two_stacks_run_side_by_side(smoke_stacks: list[tuple[str, int]]) -> None:
    """Two real stacks with identical internal ports bind only their own UI_PORT."""
    for project, ui_port in smoke_stacks:
        listed = subprocess.run(  # noqa: S603
            ["docker", "compose", "-p", project, "ps", "--format", "json"],  # noqa: S607
            capture_output=True,
            check=True,
            text=True,
        ).stdout
        services = [json.loads(line) for line in listed.splitlines() if line.strip()]
        assert {service["Service"] for service in services} == {"caddy", "mongo"}
        assert all(service["State"] == "running" for service in services)
        host_ports = {
            publisher["PublishedPort"]
            for service in services
            for publisher in service.get("Publishers") or []
            if publisher.get("PublishedPort")
        }
        assert host_ports == {ui_port}

        # Caddy of this stack answers on its UI_PORT; the absent UI gives 502.
        deadline = time.monotonic() + 30
        while True:
            try:
                connection = http.client.HTTPConnection("127.0.0.1", ui_port, timeout=5)
                connection.request("GET", "/")
                status = connection.getresponse().status
                connection.close()
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        assert status == 502
