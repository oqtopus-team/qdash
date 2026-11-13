"""QibocalRabiAmplitude stays measurement-only and records its emulator provenance."""

from __future__ import annotations

import itertools
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from qdash.datamodel.task import ParameterModel, validate_task_result_output_parameters
from qdash.workflow.calibtasks.base import BaseTask
from qdash.workflow.calibtasks.qibocal import QibocalRabiAmplitude
from qdash.workflow.calibtasks.qibocal.base import EMULATOR_MEASUREMENT_ONLY_REASON
from qdash.workflow.engine.config import CalibConfig
from qdash.workflow.engine.orchestrator import CalibOrchestrator
from qdash.workflow.engine.task.backend_saver import BackendSaver
from tests.qdash.workflow.qibocal_helpers import fake_backend, run_task_through_executor

TASK = "QibocalRabiAmplitude"
OUTPUTS = {"qibocal_pi_amplitude", "qibocal_pi_duration", "qibocal_rabi_chi2"}
WRITEBACK_SETTINGS = list(
    itertools.product(
        [True, False],  # update_calibration_parameters
        [True, False],  # force_update_params
        ["qubex", "fake", "qibocal"],  # DEFAULT_BACKEND
    )
)


def _final_history(history_repo: Any) -> Any:
    entries = history_repo.get_all()
    assert entries, "the executor must record the task"
    return entries[-1]


class TestRegistration:
    def test_task_is_registered_only_for_the_qibocal_backend(self) -> None:
        assert BaseTask.registry["qibocal"][TASK] is QibocalRabiAmplitude
        assert TASK not in BaseTask.registry.get("qubex", {})
        assert TASK not in BaseTask.registry.get("fake", {})

    def test_qdash_never_imports_qibocal_or_qibolab(self) -> None:
        import qdash.workflow.calibtasks  # noqa: F401

        assert "qibocal" not in sys.modules
        assert "qibolab" not in sys.modules

    def test_outputs_cannot_be_confused_with_qubex_parameters(self) -> None:
        assert set(QibocalRabiAmplitude.output_spec) == OUTPUTS
        assert all(not spec.publish_targets for spec in QibocalRabiAmplitude.output_spec.values())
        assert QibocalRabiAmplitude.measurement_only_reason is None


class TestRequest:
    def test_default_sweep_starts_above_zero(self) -> None:
        from qdash.common.qibocal_platform import load_platform_template, template_values

        task = QibocalRabiAmplitude()
        for name, value in template_values(load_platform_template().parameters(), 0).items():
            task.input_parameters[name].value = value
        request = task.build_request("0")

        assert request.parameters["min_amp"] == 0.01
        assert request.parameters["max_amp"] == 0.5
        assert request.parameters["step_amp"] == 0.01
        assert request.parameters["nshots"] == 1024
        assert request.seed == 1234
        assert request.qubit == 0

    @pytest.mark.parametrize(
        ("run", "message"),
        [
            ({"min_amp": 0.0}, "greater than 0"),
            ({"min_amp": -0.1}, "greater than 0"),
            ({"max_amp": 0.01}, "greater than min_amp"),
            ({"step_amp": 0.0}, "at least 5"),
            ({"step_amp": 0.2}, "at least 5"),
            ({"nshots": 0}, "nshots"),
            ({"relaxation_time": -1.0}, "relaxation_time"),
            ({"max_amp": float("nan")}, "finite"),
        ],
    )
    def test_invalid_sweep_is_rejected_before_the_runner_starts(
        self, run: dict[str, Any], message: str, tmp_path: Path
    ) -> None:
        task = QibocalRabiAmplitude({"run": run})
        backend = fake_backend(tmp_path)

        with pytest.raises(ValueError, match=message):
            task.run(backend, "0")
        assert not (tmp_path / "calib" / "qibocal").exists()


class TestMeasurementOnly:
    @pytest.fixture(autouse=True)
    def legacy_policy(self, monkeypatch):
        # Previously recorded tasks retain their unconditional measurement-only policy.
        monkeypatch.setattr(
            QibocalRabiAmplitude, "measurement_only_reason", EMULATOR_MEASUREMENT_ONLY_REASON
        )

    @pytest.mark.parametrize(("update", "force", "default_backend"), WRITEBACK_SETTINGS)
    def test_every_setting_records_history_without_write_back(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        update: bool,
        force: bool,
        default_backend: str,
    ) -> None:
        monkeypatch.setenv("DEFAULT_BACKEND", default_backend)
        backend = fake_backend(tmp_path)

        result, history_repo, _ = run_task_through_executor(
            QibocalRabiAmplitude(),
            backend,
            tmp_path / "calib",
            update_calibration_parameters=update,
            force_update_params=force,
        )

        assert not isinstance(result, Exception), result
        assert result.success
        entry = _final_history(history_repo)
        assert entry.status == "completed"
        assert set(entry.output_parameters) == OUTPUTS
        stored = validate_task_result_output_parameters(entry.output_parameters)
        amplitude = stored["qibocal_pi_amplitude"]
        assert amplitude["value"] == pytest.approx(0.127)
        assert amplitude["error"] == pytest.approx(0.0002)
        assert stored["qibocal_rabi_chi2"]["value"] == pytest.approx(0.7)
        for parameter in stored.values():
            assert parameter["database_updated"] is False
            assert all(not update["updated"] for update in parameter["database_updates"])
            assert parameter["measurement_only_reason"] == EMULATOR_MEASUREMENT_ONLY_REASON
            provenance = parameter["provenance"]
            assert provenance["source"] == "qibolab-emulator"
            assert provenance["synthetic"] is True
            assert provenance["executor_update"] is False
            assert provenance["versions"]["qibocal"] == "0.2.6"
            assert Path(provenance["run_dir"]).is_dir()
        assert [Path(p).suffix for p in entry.json_figure_path] == [".json"]
        assert all(Path(p).exists() for p in entry.figure_path + entry.json_figure_path)
        assert len(entry.raw_data_path) == 2
        assert all(Path(p).exists() for p in entry.raw_data_path)

    @pytest.mark.parametrize("default_backend", ["qubex", "fake", "qibocal"])
    @pytest.mark.parametrize(
        ("call", "configured"),
        [
            (None, None),
            ({"update_calibration_parameters": True}, None),
            (None, {"update_calibration_parameters": True}),
            ({"update_calibration_parameters": True}, {"update_calibration_parameters": True}),
            ({"update_calibration_parameters": False}, None),
        ],
    )
    def test_orchestrator_resolves_write_back_to_false(
        self,
        monkeypatch: pytest.MonkeyPatch,
        default_backend: str,
        call: dict[str, Any] | None,
        configured: dict[str, Any] | None,
    ) -> None:
        monkeypatch.setenv("DEFAULT_BACKEND", default_backend)
        orchestrator = CalibOrchestrator(
            CalibConfig(
                username="alice",
                chip_id="emulator",
                qids=["0"],
                execution_id="exec-1",
                project_id="project-1",
                backend_name="qibocal",
                force_update_params=True,
                task_parameters={TASK: configured} if configured else {},
            )
        )

        assert orchestrator._should_update_calibration_parameters(TASK, call) is False

    def test_orchestrator_keeps_qubex_write_back_unchanged(self) -> None:
        orchestrator = CalibOrchestrator(
            CalibConfig(
                username="alice",
                chip_id="chip-1",
                qids=["0"],
                execution_id="exec-1",
                project_id="project-1",
                backend_name="fake",
            )
        )

        assert orchestrator._should_update_calibration_parameters("CheckRabi", None) is True

    @pytest.mark.parametrize(("update", "force"), list(itertools.product([True, False], repeat=2)))
    @pytest.mark.parametrize("success", [True, False])
    def test_backend_saver_never_writes_back(
        self, update: bool, force: bool, success: bool
    ) -> None:
        task_model = SimpleNamespace(
            output_parameters={"qibocal_pi_amplitude": ParameterModel(value=0.127)}
        )
        state_manager = MagicMock()
        state_manager.get_task.return_value = task_model
        saver = BackendSaver(
            state_manager=state_manager,
            username="alice",
            calib_dir="/tmp/calib",
            task_manager_id="tm-1",
            force_update_params=force,
            update_calibration_parameters=update,
        )
        task = QibocalRabiAmplitude()
        task.output_provenance = {"source": "qibolab-emulator", "synthetic": True}
        backend = MagicMock()
        execution_service: Any = SimpleNamespace(
            execution_id="exec-1", chip_id="emulator", project_id="proj-1"
        )

        with (
            patch("qdash.repository.MongoQubitCalibrationRepository") as qubit_repo,
            patch("qdash.repository.MongoCouplingCalibrationRepository") as coupling_repo,
            patch("qdash.workflow.engine.task.backend_saver.get_params_updater") as updater,
        ):
            saver.save(task, execution_service, "0", backend, success)
            saver.save_mux_qid(task, execution_service, "0", backend)

        qubit_repo.assert_not_called()
        coupling_repo.assert_not_called()
        updater.assert_not_called()
        backend.update_note.assert_not_called()
        stored = task_model.output_parameters["qibocal_pi_amplitude"]
        assert stored["database_updated"] is False
        assert stored["measurement_only_reason"] == EMULATOR_MEASUREMENT_ONLY_REASON
        assert stored["provenance"]["source"] == "qibolab-emulator"


class TestFailures:
    @pytest.mark.parametrize(
        ("fit", "message"),
        [
            (
                {
                    "status": "failed",
                    "errors": ["Qibocal fit produced no pi-pulse amplitude"],
                    "pi_amplitude": None,
                },
                "no pi-pulse amplitude",
            ),
            (
                {
                    "status": "failed",
                    "errors": ["Qibocal pi-pulse amplitude or its error is not finite"],
                    "pi_amplitude": float("nan"),
                },
                "not finite",
            ),
            ({"pi_amplitude": 0.9}, "outside the swept range"),
        ],
    )
    def test_unusable_fit_fails_but_keeps_figure_and_raw_data(
        self, tmp_path: Path, fit: dict[str, Any], message: str
    ) -> None:
        backend = fake_backend(tmp_path, overrides={"fit": fit})

        error, history_repo, _ = run_task_through_executor(
            QibocalRabiAmplitude(), backend, tmp_path / "calib"
        )

        assert isinstance(error, ValueError)
        assert message in str(error)
        entry = _final_history(history_repo)
        assert entry.status == "failed"
        assert message in (entry.message or "")
        assert entry.output_parameters == {}
        assert entry.json_figure_path
        assert len(entry.raw_data_path) == 2

    @pytest.mark.parametrize(
        ("scenario", "message"),
        [("crash", "boom from runner"), ("rejected", "DummyInstrument")],
    )
    def test_runner_failure_fails_the_task_with_its_reason(
        self, tmp_path: Path, scenario: str, message: str
    ) -> None:
        backend = fake_backend(tmp_path, scenario)

        error, history_repo, _ = run_task_through_executor(
            QibocalRabiAmplitude(), backend, tmp_path / "calib"
        )

        assert isinstance(error, Exception)
        entry = _final_history(history_repo)
        assert entry.status == "failed"
        assert message in (entry.message or "")
        assert entry.output_parameters == {}

    def test_runner_timeout_fails_the_task(self, tmp_path: Path) -> None:
        backend = fake_backend(tmp_path, "sleep", timeout_seconds=1, terminate_grace_seconds=1)

        error, history_repo, _ = run_task_through_executor(
            QibocalRabiAmplitude(), backend, tmp_path / "calib"
        )

        assert isinstance(error, Exception)
        assert "exceeded 1 s" in (_final_history(history_repo).message or "")
