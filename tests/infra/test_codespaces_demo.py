"""Check the Codespaces demo: its Compose override and the commands of demo.sh.

The override tests render the real compose files and need the Docker Compose CLI;
they skip without it. The demo.sh tests run the script against a fake `docker`
that records its arguments and replays scripted container states. The
persistence smoke test at the end starts containers and runs only with
QDASH_COMPOSE_SMOKE=1.
"""

import json
import os
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO_ROOT / ".devcontainer" / "codespaces-demo"
OVERRIDE = DEMO_DIR / "compose.yaml"
COMPOSE_FILE = "compose.yaml:.devcontainer/codespaces-demo/compose.yaml"
DATABASE_TARGETS = {"mongo": "/data/db", "postgres": "/var/lib/postgresql/data"}

# Every service demo.sh waits for, in the state that lets the seed run.
READY = {
    "mongo": "running healthy 0 0",
    "postgres": "running healthy 0 0",
    "calibration-migration": "exited none 0 0",
    "agent-runtime-auth": "exited none 0 0",
    "prefect-server": "running healthy 0 0",
    "deployment-service": "running healthy 0 0",
    "api": "running none 0 0",
    "user-flow-worker": "running none 0 0",
    "ui": "running none 0 0",
    "caddy": "running none 0 0",
}

# Records each call and replays $FAKE_STATES/states.N for the Nth `docker
# inspect` call, repeating the last file. The first call is demo.sh's baseline.
FAKE_DOCKER = """\
#!/usr/bin/env bash
printf '%s\\n' "$*" >>"$FAKE_DOCKER_LOG"
case "$1" in
  info) exit 0 ;;
  inspect)
    n=$(( $(cat "$FAKE_STATES/count" 2>/dev/null || echo 0) + 1 ))
    echo "$n" >"$FAKE_STATES/count"
    file="$FAKE_STATES/states.$n"
    [ -f "$file" ] || file="$FAKE_STATES/states.last"
    cat "$file"
    exit 0 ;;
  compose)
    shift
    while [ "${1:-}" = -f ]; do shift 2; done
    case "$1" in
      ps) [ "${2:-}" = -aq ] && echo "c1 c2"; exit 0 ;;
      exec) cat >/dev/null; echo "[qdash-demo] seed ran"; exit 0 ;;
      up)
        if [ "${FAKE_UP_HANG:-0}" = 1 ]; then exec sleep 120; fi
        exit "${FAKE_UP_EXIT:-0}" ;;
      *) exit 0 ;;
    esac ;;
esac
exit 0
"""


def clean_environment() -> dict[str, str]:
    """Return the caller's environment without settings Compose or demo.sh would read."""
    return {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME"} or key.startswith("DOCKER_")
    }


def render(directory: Path, *files: Path, env_file: Path | None = None) -> dict[str, Any]:
    """Render compose files from `directory` with the .env.example settings."""
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose CLI is not installed")
    command = ["docker", "compose"]
    for file in files:
        command += ["-f", str(file)]
    command += ["--env-file", str(env_file or REPO_ROOT / ".env.example")]
    command += ["config", "--format", "json", "--no-env-resolution"]
    result = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        check=False,
        cwd=directory,
        env=clean_environment(),
        text=True,
    )
    assert result.returncode == 0, result.stderr
    compose: dict[str, Any] = json.loads(result.stdout)
    return compose


def mount(service: dict[str, Any], target: str) -> dict[str, Any]:
    """Return the service's mount at `target`."""
    matches: list[dict[str, Any]] = [
        volume for volume in service.get("volumes", []) if volume["target"] == target
    ]
    assert len(matches) == 1, service.get("volumes")
    return matches[0]


def test_override_keeps_databases_in_named_volumes(tmp_path: Path) -> None:
    """The demo moves only the database data off the checkout; compose.yaml keeps its binds."""
    base = render(REPO_ROOT, REPO_ROOT / "compose.yaml")
    demo = render(REPO_ROOT, REPO_ROOT / "compose.yaml", OVERRIDE)

    for service, target in DATABASE_TARGETS.items():
        assert mount(base["services"][service], target)["type"] == "bind"
        volume = mount(demo["services"][service], target)
        assert volume["type"] == "volume"
        assert volume["source"] in demo["volumes"]
        # The override replaces the bind mount instead of adding a second one.
        assert len(demo["services"][service]["volumes"]) == len(
            base["services"][service]["volumes"]
        )

    for name, service in base["services"].items():
        if name not in DATABASE_TARGETS:
            assert demo["services"][name].get("volumes") == service.get("volumes"), name


def test_override_adds_healthchecks_only_where_the_seed_waits(tmp_path: Path) -> None:
    """Prefect and the deployment service get healthchecks; other services are unchanged."""
    base = render(REPO_ROOT, REPO_ROOT / "compose.yaml")
    demo = render(REPO_ROOT, REPO_ROOT / "compose.yaml", OVERRIDE)

    changed = {
        name
        for name, service in demo["services"].items()
        if service.get("healthcheck") != base["services"][name].get("healthcheck")
    }
    assert changed == {"prefect-server", "deployment-service"}
    assert "localhost:4200/api/health" in " ".join(
        demo["services"]["prefect-server"]["healthcheck"]["test"]
    )
    assert "localhost:8001/health" in " ".join(
        demo["services"]["deployment-service"]["healthcheck"]["test"]
    )


def test_default_devcontainer_does_not_use_the_demo_override() -> None:
    """The development container keeps the plain compose.yaml data directories."""
    assert "codespaces-demo" not in (REPO_ROOT / ".devcontainer/devcontainer.json").read_text()
    assert "codespaces-demo" not in (REPO_ROOT / "compose.devcontainer.yaml").read_text()


class Demo:
    """A copy of the demo files in a scratch checkout, run against the fake docker."""

    def __init__(self, root: Path) -> None:
        self.root = root
        demo_dir = root / ".devcontainer" / "codespaces-demo"
        demo_dir.mkdir(parents=True)
        for name in ("demo.sh", "compose.yaml", "seed.py"):
            shutil.copy(DEMO_DIR / name, demo_dir / name)
        shutil.copy(REPO_ROOT / ".env.example", root / ".env.example")
        shutil.copy(REPO_ROOT / "compose.yaml", root / "compose.yaml")
        self.bin = root / "fake-bin"
        self.bin.mkdir()
        docker = self.bin / "docker"
        docker.write_text(FAKE_DOCKER)
        docker.chmod(0o755)
        self.states = root / "fake-states"
        self.states.mkdir()
        self.log = root / "docker.log"
        self.set_states(READY)

    def set_states(self, *steps: dict[str, str]) -> None:
        """Replay these container states on successive checks; the last one repeats."""
        for index, states in enumerate(steps, start=1):
            (self.states / f"states.{index}").write_text(
                "".join(f"{name} {state}\n" for name, state in states.items())
            )
        (self.states / "states.last").write_text((self.states / f"states.{len(steps)}").read_text())

    def run(self, command: str, **env: str) -> subprocess.CompletedProcess[str]:
        """Run demo.sh with the fake docker first on PATH."""
        environment = clean_environment()
        environment.update(
            PATH=f"{self.bin}:{environment['PATH']}",
            FAKE_DOCKER_LOG=str(self.log),
            FAKE_STATES=str(self.states),
            QDASH_DEMO_READY_INTERVAL="0.1",
        )
        environment.update(env)
        return subprocess.run(  # noqa: S603
            ["bash", str(self.root / ".devcontainer/codespaces-demo/demo.sh"), command],  # noqa: S607
            capture_output=True,
            check=False,
            cwd=self.root,
            env=environment,
            text=True,
            timeout=60,
        )

    def calls(self) -> list[str]:
        """Return the recorded docker calls."""
        return self.log.read_text().splitlines() if self.log.exists() else []

    def compose_calls(self) -> list[str]:
        """Return the recorded `docker compose` calls."""
        return [call for call in self.calls() if call.startswith("compose ")]

    def env_value(self, key: str) -> str:
        """Return KEY's value from the generated .env."""
        for line in reversed((self.root / ".env").read_text().splitlines()):
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip('"')
        raise AssertionError(f"{key} not in .env")


@pytest.fixture
def demo(tmp_path: Path) -> Demo:
    """Return a scratch demo checkout."""
    if shutil.which("bash") is None:
        pytest.skip("bash is not installed")
    return Demo(tmp_path)


def test_every_command_uses_the_demo_compose_files(demo: Demo) -> None:
    """build, start, stop and status pass compose.yaml and the override to Compose."""
    for command in ("build", "start", "stop", "status"):
        result = demo.run(command)
        assert result.returncode == 0, result.stdout + result.stderr

    calls = demo.compose_calls()
    prefix = "compose -f compose.yaml -f .devcontainer/codespaces-demo/compose.yaml "
    assert calls
    assert all(call.startswith(prefix) for call in calls), calls
    commands = [call.removeprefix(prefix) for call in calls]
    assert "build api ui deployment-service user-flow-worker" in commands
    assert "up -d --build caddy user-flow-worker" in commands
    assert "exec -T api python -" in commands
    assert "stop" in commands
    assert "ps" in commands


def test_env_points_plain_compose_commands_at_the_override(demo: Demo) -> None:
    """COMPOSE_FILE in .env makes `docker compose` in the codespace render the same volumes."""
    assert demo.run("build").returncode == 0
    assert demo.env_value("COMPOSE_FILE") == COMPOSE_FILE

    compose = render(demo.root, env_file=demo.root / ".env")
    for service, target in DATABASE_TARGETS.items():
        assert mount(compose["services"][service], target)["type"] == "volume"


def test_env_from_an_earlier_demo_gains_compose_file(demo: Demo) -> None:
    """A demo .env written before the override existed is updated, its password kept."""
    assert demo.run("build").returncode == 0
    password = demo.env_value("QDASH_ADMIN_PASSWORD")
    env = demo.root / ".env"
    env.write_text(
        "".join(
            line + "\n"
            for line in env.read_text().splitlines()
            if not line.startswith("COMPOSE_FILE=")
        )
    )

    assert demo.run("build").returncode == 0
    assert demo.env_value("COMPOSE_FILE") == COMPOSE_FILE
    assert demo.env_value("QDASH_ADMIN_PASSWORD") == password


def test_stop_keeps_the_data(demo: Demo) -> None:
    """stop only stops containers: no down, volume removal, or .env change."""
    assert demo.run("build").returncode == 0
    before = (demo.root / ".env").read_text()

    assert demo.run("stop").returncode == 0

    assert (demo.root / ".env").read_text() == before
    for call in demo.calls():
        words = call.split()
        assert "down" not in words, call
        assert "-v" not in words and "--volumes" not in words, call
        assert "volume" not in words and "rm" not in words, call


def test_start_seeds_once_every_service_is_ready(demo: Demo) -> None:
    """The seed runs after Prefect and the deployment service turn healthy."""
    starting = dict(
        READY,
        **{"prefect-server": "running starting 0 0", "deployment-service": "running starting 0 0"},
    )
    demo.set_states(starting, starting, READY)

    result = demo.run("start")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "seed ran" in result.stdout
    assert "Password:" in result.stdout
    inspects = [call for call in demo.calls() if call.startswith("inspect")]
    assert len(inspects) == 3


def test_start_stops_when_a_setup_job_fails(demo: Demo) -> None:
    """A failed migration ends startup at once with its logs, and nothing is seeded."""
    demo.set_states(READY, dict(READY, **{"calibration-migration": "exited none 1 0"}))

    started = time.monotonic()
    result = demo.run("start", QDASH_DEMO_READY_TIMEOUT="30")

    assert result.returncode == 1
    assert time.monotonic() - started < 15
    assert "calibration-migration exited with code 1" in result.stdout
    assert any("logs --no-color --tail 40 calibration-migration" in c for c in demo.calls())
    assert not any(" exec " in f" {call} " for call in demo.compose_calls())


def test_start_stops_when_a_service_keeps_restarting(demo: Demo) -> None:
    """New restarts past the limit end startup; restarts from earlier sessions do not count."""
    earlier = dict(READY, mongo="running healthy 0 5")
    demo.set_states(
        earlier,
        dict(READY, mongo="restarting starting 0 6"),
        dict(READY, mongo="restarting starting 0 8"),
    )

    result = demo.run("start", QDASH_DEMO_READY_TIMEOUT="30")

    assert result.returncode == 1
    assert "mongo restarted 3 times while starting" in result.stdout
    assert any("logs --no-color --tail 40 mongo" in c for c in demo.calls())
    assert not any(" exec " in f" {call} " for call in demo.compose_calls())


def test_restarts_from_earlier_sessions_do_not_block_start(demo: Demo) -> None:
    """A container that restarted before this start is ready once it runs."""
    demo.set_states(dict(READY, api="running none 0 7"))

    result = demo.run("start")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "seed ran" in result.stdout


def test_start_gives_up_after_the_timeout(demo: Demo) -> None:
    """A service that never turns healthy ends startup after the timeout with its logs."""
    demo.set_states(dict(READY, **{"deployment-service": "running unhealthy 0 0"}))

    started = time.monotonic()
    result = demo.run("start", QDASH_DEMO_READY_TIMEOUT="1")

    assert result.returncode == 1
    assert time.monotonic() - started < 15
    assert "Not ready after 1s: deployment-service" in result.stdout
    assert any("logs --no-color --tail 40 deployment-service" in c for c in demo.calls())
    assert not any(" exec " in f" {call} " for call in demo.compose_calls())


def test_start_reports_a_failed_up(demo: Demo) -> None:
    """When Compose cannot start the stack, startup shows the database logs and stops."""
    result = demo.run("start", FAKE_UP_EXIT="1")

    assert result.returncode == 1
    assert "Services did not start" in result.stdout
    assert any("logs --no-color --tail 40 mongo" in c for c in demo.calls())
    assert not any(c.startswith("inspect") for c in demo.calls())


def test_start_bounds_a_hanging_compose_setup_job(demo: Demo) -> None:
    """Compose waiting forever for a setup job must time out before readiness checks."""
    started = time.monotonic()
    result = demo.run("start", FAKE_UP_HANG="1", QDASH_DEMO_READY_TIMEOUT="1")

    assert result.returncode == 1
    assert time.monotonic() - started < 15
    assert "Services did not start within 1s" in result.stdout
    assert any("logs --no-color --tail 40 calibration-migration" in c for c in demo.calls())
    assert not any(" exec " in f" {call} " for call in demo.compose_calls())


@pytest.fixture
def smoke_project(tmp_path: Path) -> Iterator[tuple[Path, str]]:
    """Yield a scratch checkout and a unique Compose project, removed afterwards."""
    if os.environ.get("QDASH_COMPOSE_SMOKE") != "1":
        pytest.skip("set QDASH_COMPOSE_SMOKE=1 to start containers")
    demo_dir = tmp_path / ".devcontainer" / "codespaces-demo"
    demo_dir.mkdir(parents=True)
    shutil.copy(OVERRIDE, demo_dir / "compose.yaml")
    shutil.copy(REPO_ROOT / "compose.yaml", tmp_path / "compose.yaml")
    shutil.copy(REPO_ROOT / ".env.example", tmp_path / ".env")
    project = f"qdash-demo-smoke-{uuid.uuid4().hex[:8]}"
    yield tmp_path, project
    subprocess.run(  # noqa: S603
        ["docker", "compose", "-p", project, "down", "-v"],  # noqa: S607
        capture_output=True,
        check=False,
        cwd=tmp_path,
        env=dict(clean_environment(), COMPOSE_FILE=COMPOSE_FILE),
    )


def test_database_data_survives_stop_and_start(smoke_project: tuple[Path, str]) -> None:
    """MongoDB and PostgreSQL keep their data in the volumes across stop and start."""
    directory, project = smoke_project
    env = dict(clean_environment(), COMPOSE_FILE=COMPOSE_FILE)

    def compose(*arguments: str) -> str:
        result = subprocess.run(  # noqa: S603
            ["docker", "compose", "-p", project, *arguments],  # noqa: S607
            capture_output=True,
            check=False,
            cwd=directory,
            env=env,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout.strip()

    mongosh = ["exec", "-T", "mongo", "mongosh", "--quiet", "-u", "root", "-p", "example"]
    mongosh += ["--authenticationDatabase", "admin", "--eval"]
    psql = ["exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "prefect", "-tAc"]

    compose("up", "-d", "--wait", "mongo", "postgres")
    compose(*mongosh, "db.getSiblingDB('qdash').smoke.insertOne({k: 1})")
    compose(*psql, "create table smoke (k int); insert into smoke values (1)")
    compose("stop")
    compose("up", "-d", "--wait", "mongo", "postgres")

    assert compose(*mongosh, "db.getSiblingDB('qdash').smoke.countDocuments()") == "1"
    assert compose(*psql, "select count(*) from smoke") == "1"
    assert not (directory / "mongo_data").exists()
    assert not (directory / "postgres_data").exists()
