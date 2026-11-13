"""Shared helpers for qibocal backend tests.

``write_fake_runner`` writes a stand-in for ``tools/qibocal-runner/run_rabi_amplitude.py``
that runs under the test interpreter. It exercises the real subprocess boundary of
``QibocalBackend`` (no shell, own process group, artifacts, result checks) without the
Qibocal environment. ``run_task_through_executor`` runs a task through the real
``TaskExecutor`` with in-memory repositories and fails if any calibration write-back
path is reached.
"""

from __future__ import annotations

import json
import shutil
import sys
import textwrap
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

from qdash.repository.inmemory import (
    InMemoryChipHistoryRepository,
    InMemoryChipRepository,
    InMemoryExecutionRepository,
    InMemoryTaskResultHistoryRepository,
)
from qdash.workflow.engine.backend.qibocal import QibocalBackend
from qdash.workflow.engine.execution.service import ExecutionService
from qdash.workflow.engine.task.context import TaskContext
from qdash.workflow.engine.task.history_recorder import TaskHistoryRecorder

REPO_ROOT = Path(__file__).resolve().parents[3]
UPSTREAM_PLATFORMS = REPO_ROOT / "config" / "domain" / "qibocal" / "platforms"
RUNNER_PYTHON = REPO_ROOT / "tools" / "qibocal-runner" / ".venv" / "bin" / "python"
RUNNER_SCRIPT = REPO_ROOT / "tools" / "qibocal-runner" / "run_rabi_amplitude.py"
EMULATOR = "qibolab._core.instruments.emulator.emulator.EmulatorController"

FAKE_RUNNER = textwrap.dedent(
    """
    import hashlib, json, math, os, sys, time
    from pathlib import Path

    SCENARIO = {scenario!r}
    OVERRIDES = json.loads({overrides!r})

    def tree(root):
        return {{
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts
        }}

    request = json.loads(Path(sys.argv[1]).read_text())
    out = Path(request["output_dir"])
    platform_dir = Path(request["platforms_dir"]) / request["platform"]
    Path(out, "env.json").write_text(json.dumps(dict(os.environ)))
    Path(out, "pid").write_text(str(os.getpid()))
    if SCENARIO == "sleep":
        import subprocess
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        Path(out, "child_pid").write_text(str(child.pid))
        time.sleep(60)
    if SCENARIO == "watchdog":
        # The real runner's parent watchdog, loaded from tools/qibocal-runner.
        import importlib.util
        spec = importlib.util.spec_from_file_location("qdash_runner", OVERRIDES["runner"])
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        runner._exit_with_parent(0.1)
        time.sleep(60)
        sys.exit(0)
    if SCENARIO == "crash":
        print("boom from runner", file=sys.stderr)
        sys.exit(1)
    if SCENARIO == "no_result":
        sys.exit(0)
    if SCENARIO == "rejected":
        Path(out, "result.json").write_text(json.dumps(
            {{"status": "rejected", "error": "Instrument 'dummy' is DummyInstrument"}}))
        sys.exit(3)
    if SCENARIO == "touch_original":
        Path(OVERRIDES["original"], "parameters.json").write_text("{{}}")
    amps = [0.01 * (i + 1) for i in range(50)]
    prob = [0.5 - 0.5 * math.cos(math.pi * a / 0.127) for a in amps]
    Path(out, "figure_0.json").write_text(json.dumps(
        {{"data": [{{"type": "scatter", "x": amps, "y": prob}}], "layout": {{}}}}))
    digest = tree(platform_dir)
    result = {{
        "status": "ok",
        "protocol": "rabi_amplitude",
        "qubit": request["qubit"],
        "request": request,
        "fit": {{
            "status": "ok", "errors": [], "pi_amplitude": 0.127,
            "pi_amplitude_error": 0.0002, "chi2": 0.7, "chi2_error": 0.2,
            "pulse_length": 40.0, "fitted_parameters": [0.5, 0.5, 0.25, 3.1],
        }},
        "data": {{"amplitude": amps, "probability": prob, "error": [0.01] * len(amps)}},
        "figures": [str(out / "figure_0.json")],
        "fit_report_html": "",
        "provenance": {{
            "source": "qibolab-emulator", "synthetic": True,
            "controllers": ["dummy={emulator}"], "platform": request["platform"],
            "platform_sha256_before": digest, "platform_sha256_after": digest,
            "platform_unchanged": True, "rx_before": {{}}, "rx_after": {{}},
            "executor_update": False, "seed": request["seed"],
            "versions": {{"qibocal": "0.2.6", "qibolab": "0.2.16", "qibo": "0.3.3"}},
            "qibocal_output_dir": str(out / "qibocal"), "python_executable": sys.executable,
        }},
        "elapsed_seconds": 0.0,
    }}
    for key, value in OVERRIDES.get("fit", {{}}).items():
        result["fit"][key] = value
    for key, value in OVERRIDES.get("provenance", {{}}).items():
        result["provenance"][key] = value
    Path(out, "result.json").write_text(json.dumps(result))
    """
)


def copy_platforms(tmp_path: Path) -> Path:
    """Copy the upstream platforms to ``tmp_path`` and return the copy's directory."""
    target = tmp_path / "platforms"
    shutil.copytree(UPSTREAM_PLATFORMS, target)
    return target


def write_fake_runner(
    tmp_path: Path, scenario: str = "ok", overrides: dict[str, Any] | None = None
) -> Path:
    path = tmp_path / f"fake_runner_{scenario}.py"
    path.write_text(
        FAKE_RUNNER.format(
            scenario=scenario,
            overrides=json.dumps(overrides or {}),
            emulator=EMULATOR,
        ),
        encoding="utf-8",
    )
    return path


def fake_backend(
    tmp_path: Path,
    scenario: str = "ok",
    overrides: dict[str, Any] | None = None,
    **settings: Any,
) -> QibocalBackend:
    """A ``QibocalBackend`` whose runner is the fake runner under the test interpreter."""
    platforms = settings.pop("platforms_dir", None) or copy_platforms(tmp_path)
    calib_dir = tmp_path / "calib"
    calib_dir.mkdir(parents=True, exist_ok=True)
    return QibocalBackend(
        {
            "calib_data_path": str(calib_dir),
            "runner_python": sys.executable,
            "runner_script": str(write_fake_runner(tmp_path, scenario, overrides)),
            "platforms_dir": str(platforms),
            "platform": "qubit",
            **settings,
        }
    )


def real_backend(tmp_path: Path, **settings: Any) -> QibocalBackend:
    """A ``QibocalBackend`` running the real runner from ``tools/qibocal-runner``."""
    calib_dir = tmp_path / "calib"
    calib_dir.mkdir(parents=True, exist_ok=True)
    return QibocalBackend({"calib_data_path": str(calib_dir), **settings})


class WriteBackReachedError(AssertionError):
    """A calibration write-back path was reached."""


def _forbid(name: str) -> Any:
    def fail(*args: Any, **kwargs: Any) -> Any:
        raise WriteBackReachedError(f"{name} must not be reached for measurement-only output")

    return fail


def run_task_through_executor(
    task: Any,
    backend: QibocalBackend,
    calib_dir: Path,
    *,
    qid: str = "0",
    update_calibration_parameters: bool = True,
    force_update_params: bool = False,
) -> tuple[Any, InMemoryTaskResultHistoryRepository, TaskContext]:
    """Run ``task`` through the real ``TaskExecutor`` with in-memory repositories.

    Returns the ``TaskExecutionResult``, or the exception the executor raised after it
    recorded the failed task, together with the history repository and the context.

    The calibration repositories, the backend params updater, and calibration-note
    updates raise ``WriteBackReachedError`` if anything tries to use them.
    """
    history_repo = InMemoryTaskResultHistoryRepository()
    recorder = TaskHistoryRecorder(
        task_result_history_repo=history_repo,  # type: ignore[arg-type]
        chip_repo=InMemoryChipRepository(),
        chip_history_repo=InMemoryChipHistoryRepository(),
    )
    context = TaskContext(
        username="alice",
        execution_id="20261113-000",
        qids=[qid],
        calib_dir=str(calib_dir),
        history_recorder=recorder,
        force_update_params=force_update_params,
        update_calibration_parameters=update_calibration_parameters,
    )
    execution_service = ExecutionService.create(
        username="alice",
        execution_id="20261113-000",
        calib_data_path=str(calib_dir),
        chip_id="emulator",
        project_id="proj-1",
        repository=InMemoryExecutionRepository(),
    )
    execution_service.save()
    with ExitStack() as stack:
        stack.enter_context(
            patch("qdash.repository.MongoQubitCalibrationRepository", _forbid("qubit DB"))
        )
        stack.enter_context(
            patch("qdash.repository.MongoCouplingCalibrationRepository", _forbid("coupling DB"))
        )
        stack.enter_context(
            patch(
                "qdash.workflow.engine.task.backend_saver.get_params_updater",
                _forbid("params updater"),
            )
        )
        stack.enter_context(patch.object(backend, "update_note", _forbid("calibration note")))
        try:
            _, result = context.executor.execute(task, backend, qid, execution_service)
        except WriteBackReachedError:
            raise
        except Exception as exc:
            return exc, history_repo, context
    return result, history_repo, context


def run_task_through_orchestrator(
    tmp_path: Path,
    monkeypatch: Any,
    backend_settings: dict[str, Any],
    *,
    call_parameters: dict[str, Any] | None = None,
    task_parameters: dict[str, Any] | None = None,
    force_update_params: bool = True,
) -> tuple[Any, Any]:
    """Run ``QibocalRabiAmplitude`` through ``CalibOrchestrator.run_task``.

    Requires the ``init_db`` fixture (mongomock). Prefect is stubbed by the test suite, so
    the Prefect task wrapper is called in-process. ``backend_settings`` are merged into
    the backend config the orchestrator builds, to point it at a test runner.
    Returns the orchestrator and the ``run_task`` result or exception.
    """
    from qdash.workflow.engine import orchestrator as orchestrator_module
    from qdash.workflow.engine import task_runner
    from qdash.workflow.engine.backend.factory import create_backend as real_create_backend
    from qdash.workflow.engine.config import CalibConfig

    monkeypatch.setattr(
        orchestrator_module,
        "create_backend",
        lambda backend, config: real_create_backend(backend, {**config, **backend_settings}),
    )
    wrapped = task_runner.execute_dynamic_task_by_qid_service
    monkeypatch.setattr(
        task_runner,
        "execute_dynamic_task_by_qid_service",
        type("PrefectTaskStub", (), {"with_options": staticmethod(lambda **_: wrapped)}),
    )
    config = CalibConfig(
        username="alice",
        chip_id="emulator",
        qids=["0"],
        execution_id="20261113-000",
        project_id="proj-1",
        backend_name="qibocal",
        enable_github_pull=False,
        force_update_params=force_update_params,
        task_parameters=task_parameters or {},
    )
    config.calib_data_path = str(tmp_path / "calib")
    config.classifier_dir = str(tmp_path / "classifier")
    orchestrator = orchestrator_module.CalibOrchestrator(config)
    orchestrator.initialize()
    try:
        outcome: Any = orchestrator.run_task("QibocalRabiAmplitude", "0", call_parameters)
    except Exception as exc:
        outcome = exc
    orchestrator.complete()
    return orchestrator, outcome
