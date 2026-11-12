"""QMAmplitudeRabi: run parameter validation, fitting, result mapping and persistence.

These tests need no QM SDK. Results are built from ``SyntheticRabiResponse``, a
made-up qubit response; see ``test_qm_rabi_sdk.py`` for checks against the real
``qm-qua`` and ``qualang-tools`` packages.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from qdash.common.raw_data import PreFitRawData
from qdash.datamodel.task import QubitTaskModel, TaskStatusModel
from qdash.datamodel.task_call import TaskCall
from qdash.repository import FilesystemCalibDataSaver
from qdash.workflow.calibtasks.base import BaseTask, RunResult
from qdash.workflow.calibtasks.qm import qm_amplitude_rabi
from qdash.workflow.calibtasks.qm.qm_amplitude_rabi import (
    QMAmplitudeRabi,
    simulator_run_parameters,
)
from qdash.workflow.calibtasks.qm.rabi_experiment import (
    RabiFit,
    RabiIQResult,
    RabiSimulationResult,
    RabiSweep,
    covered_magnitude_range,
    fit_amplitude_rabi,
    project_iq,
    simulate_rabi,
)
from qdash.workflow.engine.params_updater import get_params_updater
from qdash.workflow.engine.task.backend_saver import BackendSaver
from qdash.workflow.engine.task.executor import TaskExecutor
from tests.qdash.workflow.qm_helpers import (
    StubQuantumMachinesManager,
    SyntheticRabiResponse,
    connected_backend,
)

if TYPE_CHECKING:
    from pathlib import Path

SCALES = np.linspace(0.0, 1.5, 51)


def _hardware_result(response: SyntheticRabiResponse | None = None) -> RunResult:
    response = response or SyntheticRabiResponse()
    iq = response.iq(SCALES)
    measurement = RabiIQResult(
        qid="0",
        target="qubit",
        amplitude_scales=SCALES,
        iq=iq,
        magnitude=np.abs(iq),
        phase=np.angle(iq),
    )
    fit = fit_amplitude_rabi(SCALES, project_iq(iq))
    return RunResult(raw_result={"measurement": measurement, "fit": fit}, r2={"0": fit.r2})


def _simulation_result(samples: np.ndarray | None = None) -> RunResult:
    if samples is None:
        samples = np.concatenate([np.zeros(16), 0.2 * np.ones(40), np.zeros(16)])
    return RunResult(
        raw_result=RabiSimulationResult(
            qid="0",
            qubit_element="qubit",
            amplitude_scales=SCALES,
            duration_ns=40_000,
            shots=1,
            iteration_ns=51 * (40 + 200 + 100),
            analog={"con1:1": samples, "con1:2": np.zeros_like(samples)},
            analog_sampling_rate={"con1:1": 1e9, "con1:2": 1e9},
        )
    )


class TestRegistration:
    def test_task_is_registered_for_qm_backend_only(self) -> None:
        assert BaseTask.registry["qm"]["QMAmplitudeRabi"] is QMAmplitudeRabi
        assert "QMAmplitudeRabi" not in BaseTask.registry["qubex"]
        assert "QMAmplitudeRabi" not in BaseTask.registry["fake"]

    def test_default_sweep_converts_cooldown_to_clock_cycles(self) -> None:
        sweep = QMAmplitudeRabi().sweep()

        np.testing.assert_allclose(sweep.amplitude_scales, SCALES)
        assert sweep.shots == 1000
        assert sweep.cooldown_clock_cycles == 25_000

    def test_simulator_preset_is_a_short_sweep_with_drive(self) -> None:
        call = TaskCall(name="QMAmplitudeRabi", run=simulator_run_parameters())
        sweep = QMAmplitudeRabi(call.settings()).sweep()

        np.testing.assert_allclose(sweep.amplitude_scales, [0.0, 0.5, 1.0, 1.5])
        assert np.count_nonzero(sweep.amplitude_scales) == 3
        assert (sweep.shots, sweep.cooldown_ns) == (1, 1000)
        assert sweep.iteration_duration_ns(40, 200) == 4960

    def test_run_overrides_are_validated(self) -> None:
        task = QMAmplitudeRabi(
            {"run": {"amplitude_scale_range": {"value": [0.0, 2.5, 11]}, "shots": 10}}
        )

        with pytest.raises(ValueError, match=r"\[-2, 2\)"):
            task.sweep()


class TestSweepValidation:
    @pytest.mark.parametrize(
        ("scales", "message"),
        [
            ([0.0, 0.1], "at least 3"),
            ([0.0, 0.1, 0.3], "evenly spaced"),
            ([0.3, 0.2, 0.1], "evenly spaced"),
            ([0.0, 1.0, 2.0], r"\[-2, 2\)"),
            ([-2.1, 0.0, 2.1], r"\[-2, 2\)"),
            ([0.0, np.nan, 1.0], "finite"),
        ],
    )
    def test_rejects_invalid_scales(self, scales: list[float], message: str) -> None:
        with pytest.raises(ValueError, match=message):
            RabiSweep.create(scales, 10, 1000)

    @pytest.mark.parametrize("shots", [0, -1, 1.5, True])
    def test_rejects_invalid_shots(self, shots: Any) -> None:
        with pytest.raises(ValueError, match="shots"):
            RabiSweep.create(SCALES, shots, 1000)

    @pytest.mark.parametrize("cooldown", [12, 1002, 10.5])
    def test_rejects_invalid_cooldown(self, cooldown: Any) -> None:
        with pytest.raises(ValueError, match="cooldown_time"):
            RabiSweep.create(SCALES, 10, cooldown)


class TestCoveredMagnitudes:
    @pytest.mark.parametrize(
        ("scales", "expected"),
        [
            ([0.0, 0.5, 1.0], (0.0, 1.0)),
            ([0.5, 1.0, 1.5], (0.5, 1.5)),
            ([-1.0, 0.0, 1.0], (0.0, 1.0)),
            ([-0.6, 0.2, 1.0], (0.0, 1.0)),
            ([-1.5, -1.0, -0.5], (0.5, 1.5)),
        ],
    )
    def test_interval(self, scales: list[float], expected: tuple[float, float]) -> None:
        assert covered_magnitude_range(np.array(scales)) == pytest.approx(expected)


class TestFit:
    def test_recovers_pi_scale_from_synthetic_response(self) -> None:
        signal = project_iq(SyntheticRabiResponse(pi_amplitude_scale=0.6).iq(SCALES))

        fit = fit_amplitude_rabi(SCALES, signal)

        assert fit.pi_amplitude_scale == pytest.approx(0.6, rel=1e-4)
        assert fit.r2 > 0.999

    def test_tolerates_noise(self) -> None:
        response = SyntheticRabiResponse(pi_amplitude_scale=0.45, noise=5e-4)

        fit = fit_amplitude_rabi(SCALES, project_iq(response.iq(SCALES)))

        assert fit.pi_amplitude_scale == pytest.approx(0.45, rel=0.02)
        assert fit.r2 > 0.95
        assert 0 < fit.pi_amplitude_scale_error < 0.02

    def test_projection_sign_does_not_matter(self) -> None:
        signal = project_iq(SyntheticRabiResponse().iq(SCALES))

        assert fit_amplitude_rabi(SCALES, -signal).pi_amplitude_scale == pytest.approx(
            fit_amplitude_rabi(SCALES, signal).pi_amplitude_scale
        )

    def test_noise_only_gives_low_r2(self) -> None:
        signal = np.random.default_rng(1).standard_normal(SCALES.size)

        assert fit_amplitude_rabi(SCALES, signal).r2 < 0.7


class TestRun:
    def test_simulator_mode_simulates_and_reports_no_r2(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = connected_backend(StubQuantumMachinesManager(), mode="simulator")
        expected = _simulation_result().raw_result
        calls: list[Any] = []

        def simulate(*args: Any) -> Any:
            calls.append(args)
            return expected

        monkeypatch.setattr(qm_amplitude_rabi, "simulate_rabi", simulate)
        monkeypatch.setattr(
            qm_amplitude_rabi,
            "run_rabi_on_hardware",
            MagicMock(side_effect=AssertionError("hardware must not run")),
        )

        result = QMAmplitudeRabi().run(backend, "0")

        assert result.raw_result is expected
        assert result.r2 is None
        assert calls[0][1] == "0"

    def test_hardware_mode_fits_measurement(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = connected_backend(StubQuantumMachinesManager(), mode="hardware")
        measurement = _hardware_result().raw_result["measurement"]
        monkeypatch.setattr(qm_amplitude_rabi, "run_rabi_on_hardware", lambda *_: measurement)
        monkeypatch.setattr(
            qm_amplitude_rabi,
            "simulate_rabi",
            MagicMock(side_effect=AssertionError("simulator must not run")),
        )

        result = QMAmplitudeRabi().run(backend, "0")

        assert result.r2 is not None
        assert (result.r2["0"] or 0.0) > 0.999
        assert result.raw_result["fit"].pi_amplitude_scale == pytest.approx(0.6, rel=1e-4)


class TestSimulationCoverage:
    def test_sweep_without_headroom_is_refused_before_simulating(self) -> None:
        manager = StubQuantumMachinesManager()
        session = connected_backend(manager, mode="simulator").get_instance()
        # 3 * (40 + 200 + 10300) = 31620 ns fits in 40 us but not with the headroom.
        sweep = RabiSweep.create([0.5, 1.0, 1.5], shots=1, cooldown_ns=10_300)

        with pytest.raises(ValueError, match=r"31620 ns \(40525 ns with scheduling headroom\)"):
            simulate_rabi(session, "0", sweep)
        assert manager.simulated == []


class TestPostprocess:
    def test_hardware_result_publishes_pi_scale(self) -> None:
        backend = connected_backend(StubQuantumMachinesManager(), mode="hardware")

        result = QMAmplitudeRabi().postprocess(backend, "exec-1", _hardware_result(), "0")

        output = result.output_parameters["qm_pi_amplitude_scale"]
        assert output.value == pytest.approx(0.6, rel=1e-4)
        assert output.unit == "a.u."
        assert output.execution_id == "exec-1"
        assert result.validation_error is None
        assert "hardware" in result.figures[0].layout.title.text

    def test_pi_scale_outside_sweep_fails_validation(self) -> None:
        backend = connected_backend(StubQuantumMachinesManager(), mode="hardware")
        scales = np.linspace(0.0, 0.75, 51)
        iq = SyntheticRabiResponse(pi_amplitude_scale=1.4).iq(scales)
        run_result = _hardware_result()
        run_result.raw_result["measurement"].amplitude_scales = scales
        run_result.raw_result["measurement"].iq = iq
        run_result.raw_result["fit"] = fit_amplitude_rabi(scales, project_iq(iq))

        result = QMAmplitudeRabi().postprocess(backend, "exec-1", run_result, "0")

        assert result.output_parameters == {}
        assert result.validation_error is not None
        assert "outside the swept range" in result.validation_error
        assert result.figures

    @staticmethod
    def _postprocess_sweep(scales: np.ndarray, pi_scale: float) -> Any:
        backend = connected_backend(StubQuantumMachinesManager(), mode="hardware")
        iq = SyntheticRabiResponse(pi_amplitude_scale=pi_scale).iq(scales)
        run_result = _hardware_result()
        run_result.raw_result["measurement"].amplitude_scales = scales
        run_result.raw_result["measurement"].iq = iq
        run_result.raw_result["fit"] = fit_amplitude_rabi(scales, project_iq(iq))
        return QMAmplitudeRabi().postprocess(backend, "exec-1", run_result, "0")

    def test_pi_scale_below_nonzero_start_fails_validation(self) -> None:
        # The fit extrapolates a pi scale of 0.3 from a sweep that starts at 0.5.
        result = self._postprocess_sweep(np.linspace(0.5, 1.5, 41), pi_scale=0.3)

        assert result.output_parameters == {}
        assert result.validation_error is not None
        assert "from 0.5 to 1.5" in result.validation_error

    def test_pi_scale_inside_nonzero_start_sweep_is_published(self) -> None:
        result = self._postprocess_sweep(np.linspace(0.5, 1.5, 41), pi_scale=0.8)

        assert result.validation_error is None
        value = result.output_parameters["qm_pi_amplitude_scale"].value
        assert value == pytest.approx(0.8, rel=1e-4)

    @pytest.mark.parametrize(
        ("pi_scale", "accepted"),
        [
            (0.5, True),  # first point
            (1.5, True),  # last point
            (1.5 * (1 + 1e-9), True),  # float noise at the edge
            (0.5 * (1 - 1e-3), False),
            (1.5 * (1 + 1e-3), False),
        ],
    )
    def test_swept_interval_is_inclusive(self, pi_scale: float, accepted: bool) -> None:
        backend = connected_backend(StubQuantumMachinesManager(), mode="hardware")
        run_result = _hardware_result()
        run_result.raw_result["measurement"].amplitude_scales = np.linspace(0.5, 1.5, 41)
        run_result.raw_result["fit"] = RabiFit(
            amplitude=1.0, frequency=0.5 / pi_scale, offset=0.0, r2=1.0, frequency_error=0.0
        )

        result = QMAmplitudeRabi().postprocess(backend, "exec-1", run_result, "0")

        assert (result.validation_error is None) is accepted
        assert ("qm_pi_amplitude_scale" in result.output_parameters) is accepted

    def test_signed_sweep_covers_magnitudes_on_both_sides(self) -> None:
        result = self._postprocess_sweep(np.linspace(-1.0, 1.0, 81), pi_scale=0.7)

        assert result.validation_error is None
        value = result.output_parameters["qm_pi_amplitude_scale"].value
        assert value == pytest.approx(0.7, rel=1e-4)

    def test_negative_sweep_uses_magnitudes(self) -> None:
        inside = self._postprocess_sweep(np.linspace(-1.5, -0.5, 41), pi_scale=0.8)
        below = self._postprocess_sweep(np.linspace(-1.5, -0.5, 41), pi_scale=0.3)

        assert inside.validation_error is None
        assert inside.output_parameters["qm_pi_amplitude_scale"].value == pytest.approx(
            0.8, rel=1e-4
        )
        assert below.output_parameters == {}
        assert below.validation_error is not None
        assert "from 0.5 to 1.5" in below.validation_error

    def test_simulation_never_publishes_outputs(self) -> None:
        backend = connected_backend(StubQuantumMachinesManager(), mode="simulator")

        result = QMAmplitudeRabi().postprocess(backend, "exec-1", _simulation_result(), "0")

        assert result.output_parameters == {}
        assert result.validation_error is None
        assert "SIMULATED" in result.figures[0].layout.title.text
        assert "does not model the qubit" in result.figures[0].layout.annotations[0].text

    def test_simulation_reports_iteration_coverage(self) -> None:
        backend = connected_backend(StubQuantumMachinesManager(), mode="simulator")
        run_result = _simulation_result()
        run_result.raw_result.shots = 1000

        result = QMAmplitudeRabi().postprocess(backend, "exec-1", run_result, "0")

        assert result.validation_error is None
        assert "about 2 of 1000 iterations in 40000 ns" in result.figures[0].layout.title.text

    def test_simulation_shorter_than_one_sweep_fails_validation(self) -> None:
        backend = connected_backend(StubQuantumMachinesManager(), mode="simulator")
        run_result = _simulation_result()
        run_result.raw_result.iteration_ns = 50_000

        result = QMAmplitudeRabi().postprocess(backend, "exec-1", run_result, "0")

        assert result.output_parameters == {}
        assert result.validation_error is not None
        assert "do not cover one sweep" in result.validation_error

    def test_silent_simulation_fails_validation(self) -> None:
        backend = connected_backend(StubQuantumMachinesManager(), mode="simulator")

        result = QMAmplitudeRabi().postprocess(
            backend, "exec-1", _simulation_result(np.zeros(64)), "0"
        )

        assert result.output_parameters == {}
        assert result.validation_error is not None
        assert "no analog output" in result.validation_error

    def test_hardware_result_is_rejected_in_simulator_mode(self) -> None:
        backend = connected_backend(StubQuantumMachinesManager(), mode="simulator")

        with pytest.raises(RuntimeError, match="simulator mode"):
            QMAmplitudeRabi().postprocess(backend, "exec-1", _hardware_result(), "0")


class TestRawData:
    def test_hardware_raw_data_round_trips_through_netcdf(self, tmp_path: Path) -> None:
        artifacts = QMAmplitudeRabi().extract_raw_data(_hardware_result())

        assert len(artifacts) == 1
        artifact = artifacts[0]
        assert isinstance(artifact, PreFitRawData)
        assert artifact.source_type == "qualang_tools.QUA_calibrations.Rabi"
        np.testing.assert_allclose(artifact.axes["amplitude_scale"], SCALES)

        paths = FilesystemCalibDataSaver(str(tmp_path)).save_raw_data(
            artifacts, "QMAmplitudeRabi", "qubit", "0"
        )
        assert len(paths) == 1
        loaded = PreFitRawData.load_netcdf(paths[0])
        np.testing.assert_allclose(loaded.data, artifact.data)

    def test_simulation_raw_data_is_labelled_as_simulator_output(self) -> None:
        artifacts = QMAmplitudeRabi().extract_raw_data(_simulation_result())

        assert [a.target for a in artifacts] == ["con1:1", "con1:2"]
        assert {a.source_type for a in artifacts} == {"qm.simulator.analog_samples"}
        np.testing.assert_allclose(artifacts[0].axes["time_ns"][:3], [0.0, 1.0, 2.0])


def _task_model(output_parameters: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(output_parameters=output_parameters)


def _qm_task() -> MagicMock:
    task = MagicMock()
    task.backend = "qm"
    task.get_name.return_value = "QMAmplitudeRabi"
    task.get_task_type.return_value = "qubit"
    task.is_qubit_task.return_value = True
    task.is_coupling_task.return_value = False
    return task


class TestPersistence:
    def test_simulator_outputs_are_never_written(self) -> None:
        state_manager = MagicMock()
        task_model = _task_model({"qm_pi_amplitude_scale": {"value": 0.5}})
        state_manager.get_task.return_value = task_model
        backend = connected_backend(StubQuantumMachinesManager(), mode="simulator")
        saver = BackendSaver(state_manager, "alice", "/tmp/calib", "tm-1")
        execution_service = cast(
            "Any", SimpleNamespace(execution_id="e", chip_id="c", project_id="p")
        )

        with (
            patch("qdash.repository.MongoQubitCalibrationRepository") as qubit_repo,
            patch("qdash.workflow.engine.task.backend_saver.get_params_updater") as updater,
        ):
            saver.save(_qm_task(), execution_service, "0", backend, success=True)

        qubit_repo.assert_not_called()
        updater.assert_not_called()
        saved = task_model.output_parameters["qm_pi_amplitude_scale"]
        assert saved["database_updated"] is False

    def test_hardware_outputs_are_written_to_calibration_database(self) -> None:
        state_manager = MagicMock()
        outputs = {"qm_pi_amplitude_scale": {"value": 0.6, "unit": "a.u."}}
        state_manager.get_task.return_value = _task_model(dict(outputs))
        backend = connected_backend(StubQuantumMachinesManager(), mode="hardware")
        saver = BackendSaver(state_manager, "alice", "/tmp/calib", "tm-1")
        execution_service = cast(
            "Any", SimpleNamespace(execution_id="e", chip_id="c", project_id="p")
        )

        with (
            patch("qdash.repository.MongoQubitCalibrationRepository") as qubit_repo,
            patch("qdash.repository.MongoCouplingCalibrationRepository"),
        ):
            qubit_repo.return_value.get_calibration_data_for_update.return_value = {}
            saver.save(_qm_task(), execution_service, "0", backend, success=True)

        qubit_repo.return_value.update_calib_data.assert_called_once_with(
            username="alice", qid="0", chip_id="c", output_parameters=outputs, project_id="p"
        )

    def test_qm_backend_has_no_qubex_params_updater(self) -> None:
        backend = connected_backend(StubQuantumMachinesManager(), mode="hardware")

        assert get_params_updater(backend, "chip-1") is None


class TestExecutor:
    @pytest.fixture
    def executor(self) -> TaskExecutor:
        state_manager = MagicMock()
        state_manager.get_task.return_value = QubitTaskModel(
            name="QMAmplitudeRabi", qid="0", task_id="task-1", status=TaskStatusModel.RUNNING
        )
        data_saver = MagicMock()
        data_saver.save_figures.return_value = ([], [])
        data_saver.save_raw_data.return_value = ["raw.nc"]
        executor = TaskExecutor(
            state_manager=state_manager,
            calib_dir="/tmp/calib",
            execution_id="exec-1",
            task_manager_id="tm-1",
            data_saver=data_saver,
        )
        executor.history_recorder = MagicMock()
        return executor

    def test_simulator_run_completes_without_calibration_writes(
        self, executor: TaskExecutor, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = connected_backend(StubQuantumMachinesManager(), mode="simulator")
        monkeypatch.setattr(
            qm_amplitude_rabi, "simulate_rabi", lambda *_: _simulation_result().raw_result
        )
        execution_service = MagicMock(project_id="p", chip_id="c")
        execution_service.merge_calib_data.return_value = execution_service

        with (
            patch("qdash.repository.MongoQubitCalibrationRepository") as qubit_repo,
            patch("qdash.repository.MongoCouplingCalibrationRepository") as coupling_repo,
        ):
            _, result = executor.execute(QMAmplitudeRabi(), backend, "0", execution_service)

        assert result.success
        assert result.r2 is None
        qubit_repo.return_value.update_calib_data.assert_not_called()
        coupling_repo.return_value.update_calib_data.assert_not_called()
        cast("MagicMock", executor.state_manager).put_output_parameters.assert_not_called()
        cast("MagicMock", executor.data_saver).save_raw_data.assert_called_once()
        cast("MagicMock", executor.data_saver).save_figures.assert_called_once()
