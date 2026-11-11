"""Check the Codespaces demo: its Compose override, image tags, workflow and demo.sh.

The override tests render the real compose files and need the Docker Compose CLI;
they skip without it. The images.sh and demo.sh tests run the scripts in a scratch
git checkout, demo.sh against a fake `docker` that records its arguments and
replays scripted container states. The persistence smoke test at the end starts
containers and runs only with QDASH_COMPOSE_SMOKE=1.
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
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO_ROOT / ".devcontainer" / "codespaces-demo"
OVERRIDE = DEMO_DIR / "compose.yaml"
IMAGES = DEMO_DIR / "images.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "demo-images.yml"
DEVCONTAINER = DEMO_DIR / "devcontainer.json"
DEMO_DEVCONTAINER_PATH = ".devcontainer/codespaces-demo/devcontainer.json"
REGISTRY = "ghcr.io/oqtopus-team"
# Services that compose.yaml builds from a Dockerfile, and the image the demo runs.
DEMO_IMAGES = {
    "api": "qdash-demo-api",
    "calibration-migration": "qdash-demo-api",
    "agent-runtime-auth": "qdash-demo-api",
    "deployment-service": "qdash-demo-deployment-service",
    "user-flow-worker": "qdash-demo-workflow",
    "ui": "qdash-demo-ui",
}
# What demo.sh starts; Compose starts their dependencies too.
STARTED = ("caddy", "user-flow-worker")
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
  image)
    # `image inspect REF` succeeds for refs pulled or built so far.
    grep -qxF "$3" "$FAKE_STATES/images" 2>/dev/null
    exit ;;
  pull)
    [ "${FAKE_PULL_EXIT:-0}" = 0 ] || exit "$FAKE_PULL_EXIT"
    echo "${@: -1}" >>"$FAKE_STATES/images"
    exit 0 ;;
  build)
    while [ "$#" -gt 0 ]; do
      [ "$1" = -t ] && echo "$2" >>"$FAKE_STATES/images"
      shift
    done
    exit 0 ;;
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


def images_sh(root: Path, *arguments: str, **env: str) -> subprocess.CompletedProcess[str]:
    """Run the images.sh of checkout `root` from another directory."""
    return subprocess.run(  # noqa: S603
        ["bash", str(root / ".devcontainer/codespaces-demo/images.sh"), *arguments],  # noqa: S607
        capture_output=True,
        check=False,
        cwd=root.parent,
        env=dict(clean_environment(), **env),
        text=True,
    )


def image_env(root: Path = REPO_ROOT) -> dict[str, str]:
    """Return the QDASH_DEMO_*_IMAGE settings images.sh prints for `root`."""
    result = images_sh(root, "env")
    assert result.returncode == 0, result.stderr
    return {
        key: value.strip('"')
        for key, value in (line.split("=", 1) for line in result.stdout.splitlines())
    }


@pytest.fixture
def demo_env_file(tmp_path: Path) -> Path:
    """Return .env.example plus the image settings demo.sh writes."""
    env_file = tmp_path / "demo.env"
    env_file.write_text(
        (REPO_ROOT / ".env.example").read_text()
        + "".join(f'{key}="{value}"\n' for key, value in image_env().items())
    )
    return env_file


def started_services(compose: dict[str, Any]) -> set[str]:
    """Return the services `up` starts for STARTED, with their dependencies."""
    pending, seen = list(STARTED), set()
    while pending:
        name = pending.pop()
        if name not in seen:
            seen.add(name)
            pending.extend(compose["services"][name].get("depends_on", {}))
    return seen


def read_jsonc(path: Path) -> dict[str, Any]:
    """Parse a devcontainer.json whose comments are whole // lines."""
    lines = [line for line in path.read_text().splitlines() if not line.strip().startswith("//")]
    data: dict[str, Any] = json.loads("\n".join(lines))
    return data


def mount(service: dict[str, Any], target: str) -> dict[str, Any]:
    """Return the service's mount at `target`."""
    matches: list[dict[str, Any]] = [
        volume for volume in service.get("volumes", []) if volume["target"] == target
    ]
    assert len(matches) == 1, service.get("volumes")
    return matches[0]


def test_override_keeps_databases_in_named_volumes(demo_env_file: Path) -> None:
    """The demo moves only the database data off the checkout; compose.yaml keeps its binds."""
    base = render(REPO_ROOT, REPO_ROOT / "compose.yaml")
    demo = render(REPO_ROOT, REPO_ROOT / "compose.yaml", OVERRIDE, env_file=demo_env_file)

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


def test_override_adds_healthchecks_only_where_the_seed_waits(demo_env_file: Path) -> None:
    """Prefect and the deployment service get healthchecks; other services are unchanged."""
    base = render(REPO_ROOT, REPO_ROOT / "compose.yaml")
    demo = render(REPO_ROOT, REPO_ROOT / "compose.yaml", OVERRIDE, env_file=demo_env_file)

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
    for path in (".devcontainer/devcontainer.json", "compose.devcontainer.yaml", "compose.yaml"):
        text = (REPO_ROOT / path).read_text()
        assert "codespaces-demo" not in text, path
        assert "qdash-demo" not in text, path


def test_demo_starts_no_service_that_needs_a_build(demo_env_file: Path) -> None:
    """Every service `up` starts for the demo, dependencies included, runs a pulled image."""
    demo = render(REPO_ROOT, REPO_ROOT / "compose.yaml", OVERRIDE, env_file=demo_env_file)
    refs = set(image_env().values())

    started = started_services(demo)
    # The setup jobs are reached only through depends_on.
    assert {"calibration-migration", "agent-runtime-auth", "api", "ui"} <= started
    for name in started:
        service = demo["services"][name]
        assert "build" not in service, name
        assert service.get("pull_policy") != "build", name
        assert service.get("image"), name
    custom = {name: demo["services"][name]["image"] for name in started if name in DEMO_IMAGES}
    assert set(custom) == set(DEMO_IMAGES)
    for name, image in custom.items():
        assert image.startswith(f"{REGISTRY}/{DEMO_IMAGES[name]}:src-"), image
    # Exactly the images images.sh names, so the workflow publishes what start pulls.
    assert set(custom.values()) == refs


def test_development_compose_still_builds() -> None:
    """Without the override, compose.yaml builds every QDash image as before."""
    base = render(REPO_ROOT, REPO_ROOT / "compose.yaml")

    for name in DEMO_IMAGES:
        assert "build" in base["services"][name], name
        assert "qdash-demo" not in str(base["services"][name].get("image", "")), name
    assert base["services"]["ui"]["pull_policy"] == "build"


def test_override_without_image_settings_fails_with_a_hint() -> None:
    """Compose refuses the override until demo.sh has written the image references."""
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose CLI is not installed")
    command = ["docker", "compose", "-f", "compose.yaml", "-f", str(OVERRIDE)]
    command += ["--env-file", ".env.example", "config", "--quiet"]
    result = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        check=False,
        cwd=REPO_ROOT,
        env=clean_environment(),
        text=True,
    )
    assert result.returncode != 0
    assert "demo.sh start" in result.stderr


def make_checkout(root: Path) -> Path:
    """Create a git checkout at `root` with images.sh and stub build inputs."""
    demo_dir = root / ".devcontainer" / "codespaces-demo"
    demo_dir.mkdir(parents=True)
    shutil.copy(IMAGES, demo_dir / "images.sh")
    for line in images_sh(REPO_ROOT, "inputs").stdout.split():
        path = root / line
        if line == "ui":
            path = root / "ui" / "package.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"stub {line}\n")
    (root / "README.md").write_text("readme\n")
    commit(root, "initial")
    return root


def commit(root: Path, message: str) -> None:
    """Commit everything in the scratch checkout."""
    for command in (["add", "-A"], ["commit", "-q", "-m", message]):
        subprocess.run(  # noqa: S603
            ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *command],  # noqa: S607
            check=True,
            cwd=root,
            capture_output=True,
            env=clean_environment(),
        )


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """Return a scratch git checkout with images.sh."""
    if shutil.which("git") is None or shutil.which("bash") is None:
        pytest.skip("git and bash are required")
    root = tmp_path / "checkout"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], check=True, cwd=root)  # noqa: S607
    return make_checkout(root)


def test_image_tags_follow_only_their_build_inputs(checkout: Path) -> None:
    """A tag changes with its own inputs only, and from any working directory."""
    before = image_env(checkout)
    assert set(before) == {
        "QDASH_DEMO_API_IMAGE",
        "QDASH_DEMO_DEPLOYMENT_SERVICE_IMAGE",
        "QDASH_DEMO_WORKFLOW_IMAGE",
        "QDASH_DEMO_UI_IMAGE",
    }
    for key, ref in before.items():
        name = key.removeprefix("QDASH_DEMO_").removesuffix("_IMAGE").lower().replace("_", "-")
        assert ref.startswith(f"{REGISTRY}/qdash-demo-{name}:src-"), ref
    assert image_env(checkout) == before

    (checkout / "README.md").write_text("changed\n")
    commit(checkout, "docs only")
    assert image_env(checkout) == before

    (checkout / "uv.lock").write_text("new lock\n")
    commit(checkout, "lock")
    after_lock = image_env(checkout)
    assert after_lock["QDASH_DEMO_UI_IMAGE"] == before["QDASH_DEMO_UI_IMAGE"]
    for key in ("API", "DEPLOYMENT_SERVICE", "WORKFLOW"):
        assert after_lock[f"QDASH_DEMO_{key}_IMAGE"] != before[f"QDASH_DEMO_{key}_IMAGE"]

    (checkout / "ui" / "page.tsx").write_text("ui change\n")
    commit(checkout, "ui")
    after_ui = image_env(checkout)
    assert after_ui["QDASH_DEMO_UI_IMAGE"] != after_lock["QDASH_DEMO_UI_IMAGE"]
    assert after_ui["QDASH_DEMO_API_IMAGE"] == after_lock["QDASH_DEMO_API_IMAGE"]


def test_uncommitted_changes_do_not_change_tags(checkout: Path) -> None:
    """Tags come from the commit, matching what the workflow builds for it."""
    before = image_env(checkout)
    (checkout / "uv.lock").write_text("uncommitted\n")
    assert image_env(checkout) == before


def test_registry_can_be_overridden(checkout: Path) -> None:
    """QDASH_DEMO_REGISTRY changes the namespace but not the tag."""
    result = images_sh(checkout, "refs", QDASH_DEMO_REGISTRY="ghcr.io/example")
    assert result.returncode == 0, result.stderr
    default = images_sh(checkout, "refs").stdout.splitlines()
    assert result.stdout.splitlines() == [
        ref.replace(REGISTRY, "ghcr.io/example") for ref in default
    ]


def test_missing_build_input_is_an_error(checkout: Path) -> None:
    """An input missing from the commit stops images.sh with the path."""
    (checkout / "clients" / "python" / "README.md").unlink()
    commit(checkout, "remove input")
    result = images_sh(checkout, "env")
    assert result.returncode == 1
    assert "clients/python/README.md" in result.stderr


def test_matrix_matches_the_repository() -> None:
    """The workflow matrix builds existing Dockerfiles under the tags demo.sh pulls."""
    result = images_sh(REPO_ROOT, "matrix")
    assert result.returncode == 0, result.stderr
    matrix = json.loads(result.stdout)
    refs = set(image_env().values())

    assert {f"{REGISTRY}/{entry['name']}:{entry['tag']}" for entry in matrix} == refs
    for entry in matrix:
        assert (REPO_ROOT / entry["dockerfile"]).is_file(), entry
        assert entry["name"].startswith("qdash-demo-"), entry
    ui = next(entry for entry in matrix if entry["name"] == "qdash-demo-ui")
    assert ui["build_args"].split("\n") == [
        "NEXT_PUBLIC_API_URL=/api",
        "NEXT_PUBLIC_ENV=codespaces-demo",
        "NEXT_PUBLIC_DEFAULT_THEME=light",
    ]
    for line in images_sh(REPO_ROOT, "inputs").stdout.split():
        assert (REPO_ROOT / line).exists(), line


def test_workflow_publishes_only_from_trusted_events() -> None:
    """Pull requests build with a read-only token; only publish may write packages."""
    workflow = yaml.safe_load(WORKFLOW.read_text())
    triggers = workflow[True]  # PyYAML reads the `on` key as True.
    jobs = workflow["jobs"]

    assert workflow["permissions"] == {}
    assert triggers["push"]["branches"] == ["develop", "main", "t3/github-pages-demo-hosting"]
    assert "pull_request_target" not in triggers
    assert jobs["plan"]["permissions"] == {"contents": "read"}
    assert jobs["build"]["permissions"] == {"contents": "read"}
    assert jobs["publish"]["permissions"] == {"contents": "read", "packages": "write"}
    assert jobs["build"]["if"] == "needs.plan.outputs.publish != 'true'"
    assert jobs["publish"]["if"] == "needs.plan.outputs.publish == 'true'"
    assert "images.sh matrix" in jobs["plan"]["steps"][1]["run"]

    builds = [
        step["with"]
        for job in ("build", "publish")
        for step in jobs[job]["steps"]
        if str(step.get("uses", "")).startswith("docker/build-push-action@")
    ]
    assert len(builds) == 2
    for build in builds:
        assert build["platforms"] == "linux/amd64"
    assert builds[0]["push"] is False
    assert builds[1]["push"] is True
    labels = builds[1]["labels"]
    assert "org.opencontainers.image.source=" in labels
    assert "org.opencontainers.image.revision=${{ github.sha }}" in labels
    for job in jobs.values():
        for step in job["steps"]:
            uses = step.get("uses")
            if uses:
                assert len(uses.split("@", 1)[1]) == 40, uses


def test_workflow_runs_for_pull_requests_that_change_an_image_input() -> None:
    """The pull request path filter covers every build input images.sh hashes."""
    paths = yaml.safe_load(WORKFLOW.read_text())[True]["pull_request"]["paths"]
    for line in images_sh(REPO_ROOT, "inputs").stdout.split():
        directories = [path.removesuffix("**") for path in paths if path.endswith("/**")]
        assert line in paths or any(f"{line}/".startswith(d) for d in directories), line
    assert ".devcontainer/codespaces-demo/images.sh" in paths


def test_demo_devcontainer_pulls_and_opens_qdash() -> None:
    """The demo configuration is named as a demo, pulls instead of building, opens QDash."""
    config = read_jsonc(DEVCONTAINER)

    assert config["name"] == "QDash Demo (sample data)"
    assert config["postCreateCommand"].endswith("demo.sh pull")
    assert config["postStartCommand"].endswith("demo.sh start")
    assert config["waitFor"] == "postStartCommand"
    assert "build" not in json.dumps(config)
    port = config["portsAttributes"]["5714"]
    assert port["onAutoForward"] == "openBrowser"
    assert config["forwardPorts"] == [5714]
    assert config["otherPortsAttributes"]["onAutoForward"] == "ignore"
    assert "visibility" not in json.dumps(config)


def test_readme_launches_the_demo_configuration() -> None:
    """The README button opens the demo configuration, not the development container."""
    readme = (REPO_ROOT / "README.md").read_text()
    assert "Launch QDash Demo" in readme
    assert "devcontainer_path=.devcontainer%2Fcodespaces-demo%2Fdevcontainer.json" in readme


class Demo:
    """A copy of the demo files in a scratch checkout, run against the fake docker."""

    def __init__(self, root: Path) -> None:
        self.root = root
        demo_dir = root / ".devcontainer" / "codespaces-demo"
        subprocess.run(["git", "init", "-q"], check=True, cwd=root)  # noqa: S607
        make_checkout(root)
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

    def refs(self) -> list[str]:
        """Return the image references of this checkout."""
        return list(image_env(self.root).values())

    def have_images(self) -> None:
        """Make the fake docker report every demo image as present."""
        (self.states / "images").write_text("".join(f"{ref}\n" for ref in self.refs()))

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
    """pull, start, stop and status pass compose.yaml and the override to Compose."""
    for command in ("pull", "start", "stop", "status"):
        result = demo.run(command)
        assert result.returncode == 0, result.stdout + result.stderr

    calls = demo.compose_calls()
    prefix = "compose -f compose.yaml -f .devcontainer/codespaces-demo/compose.yaml "
    assert calls
    assert all(call.startswith(prefix) for call in calls), calls
    commands = [call.removeprefix(prefix) for call in calls]
    assert "up -d --no-build caddy user-flow-worker" in commands
    assert not any(command.startswith("build") for command in commands)
    assert "exec -T api python -" in commands
    assert "stop" in commands
    assert "ps" in commands


def test_env_points_plain_compose_commands_at_the_override(demo: Demo) -> None:
    """COMPOSE_FILE in .env makes `docker compose` in the codespace render the same volumes."""
    assert demo.run("pull").returncode == 0
    assert demo.env_value("COMPOSE_FILE") == COMPOSE_FILE

    compose = render(demo.root, env_file=demo.root / ".env")
    for service, target in DATABASE_TARGETS.items():
        assert mount(compose["services"][service], target)["type"] == "volume"


def test_env_from_an_earlier_demo_gains_compose_file(demo: Demo) -> None:
    """A demo .env written before the override existed is updated, its password kept."""
    assert demo.run("pull").returncode == 0
    password = demo.env_value("QDASH_ADMIN_PASSWORD")
    env = demo.root / ".env"
    env.write_text(
        "".join(
            line + "\n"
            for line in env.read_text().splitlines()
            if not line.startswith("COMPOSE_FILE=")
        )
    )

    assert demo.run("pull").returncode == 0
    assert demo.env_value("COMPOSE_FILE") == COMPOSE_FILE
    assert demo.env_value("QDASH_ADMIN_PASSWORD") == password


def test_stop_keeps_the_data(demo: Demo) -> None:
    """stop only stops containers: no down, volume removal, or .env change."""
    assert demo.run("pull").returncode == 0
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


def test_start_pulls_only_missing_images(demo: Demo) -> None:
    """start pulls the images of this commit it lacks and never builds one."""
    result = demo.run("start")

    assert result.returncode == 0, result.stdout + result.stderr
    pulls = [call for call in demo.calls() if call.startswith("pull ")]
    assert sorted(call.split()[-1] for call in pulls) == sorted(set(demo.refs()))
    assert not any(call.startswith("build") for call in demo.calls())
    for key, ref in image_env(demo.root).items():
        assert demo.env_value(key) == ref

    demo.log.unlink()
    assert demo.run("start").returncode == 0
    assert not any(call.startswith("pull ") for call in demo.calls())


def test_pull_writes_image_settings_for_plain_compose(demo: Demo) -> None:
    """After pull, plain `docker compose` renders the demo images without a build."""
    assert demo.run("pull").returncode == 0

    compose = render(demo.root, env_file=demo.root / ".env")
    for name, image in DEMO_IMAGES.items():
        assert "build" not in compose["services"][name], name
        assert compose["services"][name]["image"].startswith(f"{REGISTRY}/{image}:src-")


def test_missing_images_stop_startup_with_next_steps(demo: Demo) -> None:
    """An image that cannot be pulled ends startup before Compose, with what to do."""
    result = demo.run("start", FAKE_PULL_EXIT="1")

    assert result.returncode == 1
    assert "Cannot pull ghcr.io/oqtopus-team/qdash-demo-" in result.stdout
    assert "QDash Demo Images" in result.stdout
    assert "demo.sh build-local" in result.stdout
    assert not demo.compose_calls()
    assert not any(call.startswith("build") for call in demo.calls())


def test_build_local_is_separate_from_start(demo: Demo) -> None:
    """build-local builds the tags start looks for; start then pulls nothing."""
    result = demo.run("build-local")

    assert result.returncode == 0, result.stdout + result.stderr
    builds = [call for call in demo.calls() if call.startswith("build ")]
    assert len(builds) == len(image_env(demo.root))
    assert any(
        "-f ui/Dockerfile" in call and "--build-arg NEXT_PUBLIC_ENV=codespaces-demo" in call
        for call in builds
    )
    assert not demo.compose_calls()

    demo.log.unlink()
    assert demo.run("start").returncode == 0
    assert not any(call.startswith(("pull ", "build ")) for call in demo.calls())


def test_uncommitted_image_inputs_are_reported(demo: Demo) -> None:
    """start says when local changes to build inputs are missing from the images."""
    demo.have_images()
    (demo.root / "uv.lock").write_text("local change\n")

    result = demo.run("start")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Uncommitted changes to image build inputs" in result.stdout
    assert "uv.lock" in result.stdout


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
    # The smoke test starts only the databases; the image settings need values.
    with (tmp_path / ".env").open("a") as env:
        for key in ("API", "DEPLOYMENT_SERVICE", "WORKFLOW", "UI"):
            env.write(f'QDASH_DEMO_{key}_IMAGE="{REGISTRY}/unused:{key.lower()}"\n')
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
