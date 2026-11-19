"""Backend that runs Qibocal protocols on a Qibolab emulator in an isolated runner.

QDash does not import Qibocal or Qibolab. Their pinned dependencies conflict with qubex
(``cma<4`` against ``cma>=4``), so they live in their own environment under
``src/qdash/workflow/qibocal_runner`` and run as a subprocess. This module owns the protocol boundary;
``qibocal_process`` owns process transport:

* settings come from ``config/app/qibocal.yaml``, separate from the Qibolab platform files;
* every run gets its own artifact directory and its own copy of the platform, so the
  configured platform stays unchanged and concurrent runs never share files;
* the runner is started without a shell, in its own process group, and is stopped on
  timeout, cancellation, or any other exception;
* the runner result is accepted only when it reports an emulator-only platform, an
  executor with ``update=False``, and an unchanged platform.

The backend is limited to emulators. Results can be adopted only on a matching bound chip.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qdash.common.config.loader import ConfigLoader
from qdash.common.qibocal_platform import PlatformTemplate, native_assignments, readback_mismatches
from qdash.common.simulation_binding import require_qibocal_binding
from qdash.workflow.engine.backend.base import BaseBackend
from qdash.workflow.engine.backend.persistence import PersistencePolicy
from qdash.workflow.engine.backend.qibocal_process import run_process

if TYPE_CHECKING:
    from qdash.datamodel.simulation import SimulationBindingModel

SETTINGS_FILE = "app/qibocal.yaml"
EMULATOR_CONTROLLER = "qibolab._core.instruments.emulator.emulator.EmulatorController"
EMULATOR_SOURCE = "qibolab-emulator"
EXIT_REJECTED = 3
EXIT_INVALID = 4
LOG_TAIL_CHARS = 4000


class QibocalRunnerError(RuntimeError):
    """The Qibocal runner failed or returned a result QDash cannot accept."""


class QibocalPlatformRejectedError(QibocalRunnerError):
    """The runner refused the platform before acquisition."""


class QibocalRunnerTimeoutError(QibocalRunnerError):
    """The runner did not finish within the configured timeout."""


@dataclass(frozen=True)
class QibocalRunnerSettings:
    """Where the runner and the Qibolab platform are, and how long a run may take."""

    python: Path
    script: Path
    platforms_dir: Path
    platform: str
    timeout_seconds: float = 600.0
    terminate_grace_seconds: float = 5.0

    @classmethod
    def load(cls, overrides: Mapping[str, Any] | None = None) -> QibocalRunnerSettings:
        """Read ``config/app/qibocal.yaml`` and apply backend-config overrides.

        ``overrides`` may set ``runner_python``, ``runner_script``, ``platforms_dir``,
        ``platform``, ``timeout_seconds``, and ``terminate_grace_seconds``. Tests use
        them; deployments use the YAML file.
        """
        overrides = overrides or {}
        data = ConfigLoader._load_config(SETTINGS_FILE)
        runner = data.get("runner") or {}
        platform = data.get("platform") or {}
        if not isinstance(runner, dict) or not isinstance(platform, dict):
            raise ValueError(f"{SETTINGS_FILE}: 'runner' and 'platform' must be mappings")

        # Runner paths are relative to the directory that holds the config directory: the
        # repository root on a host, /app in the workflow image (/app/config is mounted there
        # and the runner is installed under /app/src/qdash/workflow/qibocal_runner).
        app_root = ConfigLoader.get_config_dir().parent

        def repo_path(value: Any) -> Path:
            path = Path(str(value)).expanduser()
            return path if path.is_absolute() else app_root / path

        def config_path(value: Any) -> Path:
            path = Path(str(value)).expanduser()
            return path if path.is_absolute() else ConfigLoader.get_config_dir() / path

        python = overrides.get("runner_python", runner.get("python"))
        script = overrides.get("runner_script", runner.get("script"))
        platforms_dir = overrides.get("platforms_dir", platform.get("directory"))
        platform_name = overrides.get("platform", platform.get("name"))
        if not python or not script or not platforms_dir or not platform_name:
            raise ValueError(
                f"{SETTINGS_FILE} must set runner.python, runner.script, "
                "platform.directory, and platform.name"
            )
        timeout = float(overrides.get("timeout_seconds", runner.get("timeout_seconds", 600)))
        grace = float(
            overrides.get("terminate_grace_seconds", runner.get("terminate_grace_seconds", 5))
        )
        if timeout <= 0 or grace < 0:
            raise ValueError(f"{SETTINGS_FILE}: timeouts must be positive")
        name = str(platform_name)
        if Path(name).name != name or name in {".", ".."}:
            raise ValueError(f"{SETTINGS_FILE}: platform.name must be a folder name")
        return cls(
            python=repo_path(python),
            script=repo_path(script),
            platforms_dir=config_path(platforms_dir),
            platform=name,
            timeout_seconds=timeout,
            terminate_grace_seconds=grace,
        )

    @property
    def platform_dir(self) -> Path:
        return self.platforms_dir / self.platform


@dataclass(frozen=True)
class QibocalRequest:
    """An allowlisted protocol with final resolved calibration inputs."""

    qubit: int
    protocol: str
    parameters: dict[str, Any]
    calibration: dict[str, float]
    seed: int


@dataclass(frozen=True)
class QibocalRunResult:
    """A runner result QDash accepted, with the paths of its artifacts."""

    result: dict[str, Any]
    run_dir: Path
    stdout_path: Path
    stderr_path: Path

    @property
    def fit(self) -> dict[str, Any]:
        return dict(self.result["fit"])

    @property
    def provenance(self) -> dict[str, Any]:
        return dict(self.result["provenance"])


def hash_tree(root: Path) -> dict[str, str]:
    """Return the SHA-256 of every file below ``root`` keyed by relative path."""
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            hashes[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return hashes


def _tail(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-LOG_TAIL_CHARS:]
    except OSError:
        return ""


class QibocalBackend(BaseBackend):
    """Run Qibocal protocols on a Qibolab emulator through the isolated runner."""

    name: str = "qibocal"
    persistence_policy = PersistencePolicy.BOUND_SIMULATION

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._settings: QibocalRunnerSettings | None = None

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    @property
    def settings(self) -> QibocalRunnerSettings:
        if self._settings is None:
            self.connect()
        assert self._settings is not None
        return self._settings

    def version(self) -> str:
        return "qibocal-runner"

    def connect(self) -> None:
        """Validate the runner and platform paths; no library is imported here."""
        if self._settings is not None:
            return
        settings = QibocalRunnerSettings.load(self._config)
        missing = [
            f"{label} {path}"
            for label, path in (
                ("runner python", settings.python),
                ("runner script", settings.script),
                ("platform", settings.platform_dir / "platform.py"),
            )
            if not path.is_file()
        ]
        if missing:
            raise QibocalRunnerError(
                "Qibocal backend is not installed: missing "
                + ", ".join(missing)
                + ". Run `uv sync --frozen` in src/qdash/workflow/qibocal_runner."
            )
        self._settings = settings

    def disconnect(self) -> None:
        self._settings = None

    @property
    def is_connected(self) -> bool:
        return self._settings is not None

    def get_instance(self) -> QibocalBackend:
        self.connect()
        return self

    def binding(self) -> SimulationBindingModel:
        settings = self.settings
        return require_qibocal_binding(
            self.config.get("project_id"),
            self.config["chip_id"],
            PlatformTemplate(settings.platforms_dir, settings.platform),
        )

    def artifact_root(self) -> Path:
        """Directory below which each run gets its own folder."""
        calib_dir = self._config.get("calib_data_path")
        if not calib_dir:
            note_path = self._config.get("note_path")
            if not note_path:
                raise QibocalRunnerError("Backend config has no calib_data_path")
            calib_dir = str(Path(str(note_path)).parent.parent)
        return Path(str(calib_dir)) / "qibocal"

    def run_protocol(self, request: QibocalRequest, label: str) -> QibocalRunResult:
        """Run an allowlisted Qibocal protocol and return its verified result.

        Raises ``QibocalPlatformRejectedError`` when the platform is not an emulator,
        ``QibocalRunnerTimeoutError`` on timeout, and ``QibocalRunnerError`` for every
        other failure, including a changed platform.
        """
        settings = self.settings
        binding = self.binding()
        assignments = native_assignments(request.qubit, request.calibration)
        run_dir = self.artifact_root() / f"{label}_{uuid.uuid4().hex[:12]}"
        run_dir.mkdir(parents=True, exist_ok=False)
        self.last_run_dir = run_dir

        source_hash = hash_tree(settings.platform_dir)
        platforms_copy = run_dir / "platforms"
        shutil.copytree(
            settings.platform_dir,
            platforms_copy / settings.platform,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        request_payload = {
            **asdict(request),
            "targets": [request.qubit],
            "platform": settings.platform,
            "platforms_dir": str(platforms_copy),
            "output_dir": str(run_dir),
        }
        request_path = run_dir / "request.json"
        request_path.write_text(json.dumps(request_payload, indent=1), encoding="utf-8")

        stdout_path = run_dir / "runner.stdout.log"
        stderr_path = run_dir / "runner.stderr.log"
        try:
            returncode = run_process(
                [str(settings.python), "-I", str(settings.script), str(request_path)],
                cwd=run_dir,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                timeout_seconds=settings.timeout_seconds,
                terminate_grace_seconds=settings.terminate_grace_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise QibocalRunnerTimeoutError(
                f"Qibocal runner exceeded {settings.timeout_seconds:g} s and was stopped"
            ) from exc

        if hash_tree(settings.platform_dir) != source_hash:
            raise QibocalRunnerError(
                f"Configured platform {settings.platform_dir} changed during the run"
            )

        result_path = run_dir / "result.json"
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise QibocalRunnerError(
                f"Qibocal runner exited with {returncode} without a readable result: "
                f"{exc}\n{_tail(stderr_path)}"
            ) from exc

        if returncode == EXIT_REJECTED or result.get("status") == "rejected":
            raise QibocalPlatformRejectedError(str(result.get("error", "platform rejected")))
        if returncode == EXIT_INVALID or result.get("status") == "invalid":
            raise QibocalRunnerError(f"Invalid Qibocal request: {result.get('error')}")
        if returncode != 0 or result.get("status") != "ok":
            raise QibocalRunnerError(
                f"Qibocal runner failed with exit code {returncode}: "
                f"{result.get('error', '')}\n{_tail(stderr_path)}"
            )

        self._check_result(result, source_hash)
        problems = readback_mismatches(
            result["provenance"].get("applied_parameters", {}), assignments
        )
        if problems:
            raise QibocalRunnerError("Calibration readback mismatch: " + "; ".join(problems))
        # Recheck the model before allowing a result to be adopted.
        self.binding()
        result["provenance"]["simulation_binding"] = binding.model_dump(mode="json")
        result["provenance"]["chip_id"] = self.config["chip_id"]
        result["provenance"]["project_id"] = self.config.get("project_id")
        # Identify the exact runner build: the lock pins every distribution version.
        lock = settings.script.parent / "uv.lock"
        result["provenance"]["runner_script_sha256"] = hashlib.sha256(
            settings.script.read_bytes()
        ).hexdigest()
        result["provenance"]["runner_lock_sha256"] = (
            hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else None
        )
        return QibocalRunResult(
            result=result,
            run_dir=run_dir,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

    @staticmethod
    def _check_result(result: Mapping[str, Any], source_hash: Mapping[str, str]) -> None:
        """Accept only emulator results produced without a platform update."""
        provenance = result.get("provenance")
        if not isinstance(provenance, Mapping) or not isinstance(result.get("fit"), Mapping):
            raise QibocalRunnerError("Qibocal runner result has no fit or provenance")
        controllers = provenance.get("controllers") or []
        if not controllers or any(
            not str(entry).endswith(f"={EMULATOR_CONTROLLER}") for entry in controllers
        ):
            raise QibocalPlatformRejectedError(
                f"Runner reported non-emulator controllers: {controllers}"
            )
        if provenance.get("source") != EMULATOR_SOURCE or provenance.get("synthetic") is not True:
            raise QibocalRunnerError("Runner result is not marked as synthetic emulator data")
        if provenance.get("executor_update") is not False:
            raise QibocalRunnerError("Runner did not run Qibocal with update=False")
        if (
            provenance.get("platform_unchanged") is not True
            or provenance.get("platform_sha256_before") != dict(source_hash)
            or provenance.get("platform_sha256_after") != dict(source_hash)
        ):
            raise QibocalRunnerError(
                "Runner used or changed a platform other than the configured one"
            )
