"""End-to-end runs of QibocalRabiAmplitude with the real Qibocal and Qibolab emulator.

These tests start the real runner environment from ``tools/qibocal-runner`` and take
about a minute. They run only when ``QDASH_QIBOCAL_INTEGRATION=1`` and the runner
environment exists::

    (cd tools/qibocal-runner && uv sync --frozen)
    QDASH_QIBOCAL_INTEGRATION=1 uv run pytest -m qibocal_emulator

They cover the path that unit tests replace with a stand-in runner: acquisition and fit
by Qibocal on the upstream emulator platform, conversion into task outputs, figure, raw
data and measurement-only history, and rejection of a ``DummyInstrument`` platform by the
instantiated controller before acquisition.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from qdash.datamodel.task import validate_task_result_output_parameters
from qdash.workflow.calibtasks.qibocal import QibocalRabiAmplitude
from qdash.workflow.calibtasks.qibocal.base import EMULATOR_MEASUREMENT_ONLY_REASON
from qdash.workflow.engine.backend.qibocal import QibocalPlatformRejectedError, hash_tree
from tests.qdash.workflow.qibocal_helpers import (
    EMULATOR,
    RUNNER_PYTHON,
    UPSTREAM_PLATFORMS,
    real_backend,
    run_task_through_executor,
)

pytestmark = [
    pytest.mark.qibocal_emulator,
    pytest.mark.skipif(
        os.environ.get("QDASH_QIBOCAL_INTEGRATION") != "1" or not RUNNER_PYTHON.exists(),
        reason="set QDASH_QIBOCAL_INTEGRATION=1 and run `uv sync --frozen` in tools/qibocal-runner",
    ),
]

DUMMY_PLATFORM = """
from qibolab._core.dummy.platform import create_dummy


def create():
    return create_dummy()
"""


def _run(tmp_path: Path, **kwargs: Any) -> tuple[Any, Any]:
    backend = real_backend(tmp_path)
    result, history_repo, _ = run_task_through_executor(
        QibocalRabiAmplitude(), backend, tmp_path / "calib", **kwargs
    )
    return result, history_repo.get_all()[-1]


def test_rabi_amplitude_runs_on_the_emulator_and_stays_measurement_only(
    tmp_path: Path,
) -> None:
    upstream_hash = hash_tree(UPSTREAM_PLATFORMS / "qubit")

    result, entry = _run(
        tmp_path / "a", update_calibration_parameters=True, force_update_params=True
    )
    repeated, repeated_entry = _run(tmp_path / "b")

    assert not isinstance(result, Exception), result
    assert not isinstance(repeated, Exception), repeated
    assert entry.status == "completed"
    stored = validate_task_result_output_parameters(entry.output_parameters)
    amplitude = stored["qibocal_pi_amplitude"]
    # The upstream platform's native RX amplitude is 0.12698.
    assert amplitude["value"] == pytest.approx(0.127, abs=0.005)
    assert 0 < amplitude["error"] < 0.01
    assert stored["qibocal_rabi_chi2"]["value"] > 0
    # Same seed, same result.
    repeated_stored = validate_task_result_output_parameters(repeated_entry.output_parameters)
    assert repeated_stored["qibocal_pi_amplitude"]["value"] == amplitude["value"]

    for parameter in stored.values():
        assert parameter["database_updated"] is False
        assert parameter["measurement_only_reason"] == EMULATOR_MEASUREMENT_ONLY_REASON
        provenance = parameter["provenance"]
        assert provenance["source"] == "qibolab-emulator"
        assert provenance["controllers"] == [f"dummy={EMULATOR}"]
        assert provenance["executor_update"] is False
        assert provenance["platform_sha256"] == upstream_hash
        versions = provenance["versions"]
        assert (versions["qibocal"], versions["qibolab"], versions["qibo"]) == (
            "0.2.6",
            "0.2.16",
            "0.3.3",
        )
        assert versions["python"].startswith("3.11.")
        lock = RUNNER_PYTHON.parents[2] / "uv.lock"
        assert provenance["runner_lock_sha256"] == hash_tree(lock.parent)["uv.lock"]

    run_dir = Path(stored["qibocal_pi_amplitude"]["provenance"]["run_dir"])
    assert (run_dir / "qibocal" / "meta.json").exists()
    assert (run_dir / "result.json").exists()
    assert entry.figure_path and entry.json_figure_path
    assert all(Path(path).exists() for path in entry.figure_path + entry.json_figure_path)
    assert len(entry.raw_data_path) == 2
    assert hash_tree(UPSTREAM_PLATFORMS / "qubit") == upstream_hash


def test_dummy_instrument_platform_is_rejected_before_acquisition(tmp_path: Path) -> None:
    platforms = tmp_path / "platforms"
    (platforms / "dummy").mkdir(parents=True)
    (platforms / "dummy" / "platform.py").write_text(DUMMY_PLATFORM, encoding="utf-8")
    backend = real_backend(tmp_path, platforms_dir=str(platforms), platform="dummy")

    with pytest.raises(QibocalPlatformRejectedError, match="DummyInstrument"):
        backend.run_rabi_amplitude(QibocalRabiAmplitude().build_request("0"), label="dummy")

    (run_dir,) = (tmp_path / "calib" / "qibocal").iterdir()
    # Executor.open creates this folder; rejection happens before it.
    assert not (run_dir / "qibocal").exists()


def test_orchestrator_run_task_on_the_emulator_writes_history_only(
    init_db: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``CalibOrchestrator.run_task`` with Mongo history (mongomock) and the real runner."""
    from qdash.dbmodel.qubit import QubitDocument
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
    from tests.qdash.workflow.qibocal_helpers import run_task_through_orchestrator

    monkeypatch.setenv("DEFAULT_BACKEND", "qibocal")
    _, outcome = run_task_through_orchestrator(
        tmp_path,
        monkeypatch,
        {},
        call_parameters={"update_calibration_parameters": True},
    )

    assert not isinstance(outcome, Exception), outcome
    (document,) = TaskResultHistoryDocument.find({"name": "QibocalRabiAmplitude"}).run()
    assert document.status == "completed"
    amplitude = document.output_parameters["qibocal_pi_amplitude"]
    assert amplitude["value"] == pytest.approx(0.127, abs=0.005)
    assert amplitude["database_updated"] is False
    assert amplitude["provenance"]["versions"]["qibocal"] == "0.2.6"
    assert document.figure_path and document.json_figure_path and document.raw_data_path
    assert QubitDocument.find({}).count() == 0
