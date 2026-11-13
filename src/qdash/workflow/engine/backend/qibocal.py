"""Backend that runs Qibocal protocols on a Qibolab emulator in an isolated runner.

QDash does not import Qibocal or Qibolab. Their pinned dependencies conflict with qubex
(``cma<4`` against ``cma>=4``), so they live in their own environment under
``tools/qibocal-runner`` and run as a subprocess. This module owns that boundary:

* settings come from ``config/app/qibocal.yaml``, separate from the Qibolab platform files;
* every run gets its own artifact directory and its own copy of the platform, so the
  configured platform stays unchanged and concurrent runs never share files;
* the runner is started without a shell, in its own process group, and is stopped on
  timeout, cancellation, or any other exception;
* the runner result is accepted only when it reports an emulator-only platform, an
  executor with ``update=False``, and an unchanged platform.

The backend is limited to emulators. Its results are synthetic and are never written to
accepted calibration state; see ``QibocalTask``.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import shutil
import signal
import subprocess
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from qdash.common.config.loader import ConfigLoader
from qdash.workflow.engine.backend.base import BaseBackend

logger = logging.getLogger(__name__)

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
        # and the runner is installed under /app/tools/qibocal-runner).
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
class RabiAmplitudeRequest:
    """Parameters of one Qibocal ``rabi_amplitude`` run."""

    qubit: int
    min_amp: float
    max_amp: float
    step_amp: float
    nshots: int
    relaxation_time: float
    seed: int
    pulse_length: float | None = None


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
                + ". Run `uv sync --frozen` in tools/qibocal-runner."
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

    def artifact_root(self) -> Path:
        """Directory below which each run gets its own folder."""
        calib_dir = self._config.get("calib_data_path")
        if not calib_dir:
            note_path = self._config.get("note_path")
            if not note_path:
                raise QibocalRunnerError("Backend config has no calib_data_path")
            calib_dir = str(Path(str(note_path)).parent.parent)
        return Path(str(calib_dir)) / "qibocal"

    def run_rabi_amplitude(self, request: RabiAmplitudeRequest, label: str) -> QibocalRunResult:
        """Run Qibocal ``rabi_amplitude`` and return the accepted result.

        Raises ``QibocalPlatformRejectedError`` when the platform is not an emulator,
        ``QibocalRunnerTimeoutError`` on timeout, and ``QibocalRunnerError`` for every
        other failure, including a changed platform.
        """
        settings = self.settings
        run_dir = self.artifact_root() / f"{label}_{uuid.uuid4().hex[:12]}"
        run_dir.mkdir(parents=True, exist_ok=False)

        source_hash = hash_tree(settings.platform_dir)
        platforms_copy = run_dir / "platforms"
        shutil.copytree(
            settings.platform_dir,
            platforms_copy / settings.platform,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        request_payload = {
            **asdict(request),
            "platform": settings.platform,
            "platforms_dir": str(platforms_copy),
            "output_dir": str(run_dir),
        }
        request_path = run_dir / "request.json"
        request_path.write_text(json.dumps(request_payload, indent=1), encoding="utf-8")

        stdout_path = run_dir / "runner.stdout.log"
        stderr_path = run_dir / "runner.stderr.log"
        returncode = self._run_subprocess(
            [str(settings.python), "-I", str(settings.script), str(request_path)],
            run_dir,
            stdout_path,
            stderr_path,
            settings,
        )

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

    @staticmethod
    def _run_subprocess(
        command: list[str],
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        settings: QibocalRunnerSettings,
    ) -> int:
        """Run the runner without a shell and stop its process group on any exit path."""
        env = {
            "PATH": os.defpath,
            "HOME": os.environ.get("HOME", str(cwd)),
            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),  # noqa: S108
            "LANG": "C.UTF-8",
            "MPLBACKEND": "Agg",
            "JAX_PLATFORMS": "cpu",
        }
        logger.info("Starting Qibocal runner: %s", " ".join(command))
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                command,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                shell=False,
                start_new_session=True,
            )
            try:
                return process.wait(timeout=settings.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                QibocalBackend._stop(process, settings.terminate_grace_seconds)
                raise QibocalRunnerTimeoutError(
                    f"Qibocal runner exceeded {settings.timeout_seconds:g} s and was stopped"
                ) from exc
            except BaseException:
                # Cancellation (Prefect termination, KeyboardInterrupt) or any other error:
                # never leave the emulator running.
                QibocalBackend._stop(process, settings.terminate_grace_seconds)
                raise

    @staticmethod
    def _stop(process: subprocess.Popen[bytes], grace_seconds: float) -> None:
        """Terminate the runner's process group, then kill it after ``grace_seconds``."""
        if process.poll() is not None:
            return
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(process.pid, sig)
            try:
                process.wait(timeout=grace_seconds)
                return
            except subprocess.TimeoutExpired:
                continue
        logger.error("Qibocal runner pid=%s did not exit after SIGKILL", process.pid)
