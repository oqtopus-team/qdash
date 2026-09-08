from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np
import plotly.graph_objects as go
import pytest
import qubex
from qubex.contrib.experiment.readout_parameters_characterization import (
    characterize_coarse_readout_parameters,
)

from qdash.datamodel.task import InputParameterModel, TaskStatusModel
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_coarse_readout_params import (
    CheckCoarseReadoutParams,
)
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_rabi import CheckRabi
from qdash.workflow.engine.backend.plugins.qubex_progress import (
    ReportingTqdm,
    capture_qubex_progress,
)
from qdash.workflow.engine.progress import ProgressPlan, TaskProgress
from qdash.workflow.engine.task.executor import TaskExecutor
from qdash.workflow.engine.task.state_manager import TaskStateManager


@pytest.fixture
def coarse_readout(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    task = CheckCoarseReadoutParams()
    task.input_parameters["qubit_frequency"] = InputParameterModel(value=5.1, unit="GHz")
    task.input_parameters["control_amplitude"] = InputParameterModel(value=0.03, unit="a.u.")
    task.input_parameters["readout_frequency"] = InputParameterModel(value=6.0, unit="GHz")
    task.input_parameters["readout_amplitude"] = InputParameterModel(value=0.1, unit="a.u.")
    # Qubex flattens a (2 amplitudes, 3 frequencies) scan in amplitude-major order.
    # The selected point is index 4, not the last scan or the point with highest R².
    rabi_results = [
        SimpleNamespace(rabi_params={"Q00": SimpleNamespace(r2=0.99)}) for _ in range(6)
    ]
    result = SimpleNamespace(
        data={
            "frequency_range": np.array([6.0, 6.01, 6.02]),
            "readout_amplitudes": np.array([0.0, 0.1]),
            "optimal_readout_frequency": 6.01,
            "optimal_readout_amplitude": 0.1,
            "rabi_results": rabi_results,
        },
        figure=go.Figure(),
    )
    params = SimpleNamespace(control_amplitude={"Q00": 0.01}, readout_amplitude={"Q00": 0.2})
    qubit = SimpleNamespace(frequency=5.0)

    @contextmanager
    def modified_frequencies(frequencies: dict[str, float]) -> Iterator[None]:
        original = qubit.frequency
        qubit.frequency = frequencies["Q00"]
        try:
            yield
        finally:
            qubit.frequency = original

    experiment = SimpleNamespace(
        params=params,
        ctx=SimpleNamespace(params=params),
        experiment_system=SimpleNamespace(
            control_params=SimpleNamespace(
                get_readout_amplitude=lambda label: params.readout_amplitude[label],
                get_control_amplitude=lambda label: params.control_amplitude[label],
            ),
            quantum_system=SimpleNamespace(get_qubit=lambda _label: qubit),
        ),
        modified_frequencies=modified_frequencies,
        rabi_experiment=MagicMock(),
    )
    backend = cast("Any", SimpleNamespace(name="qubex", update_note=MagicMock()))
    save_calibration = MagicMock()
    characterize = MagicMock(return_value=result)
    monkeypatch.setattr(task, "get_experiment", lambda _backend: experiment)
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    monkeypatch.setattr(task, "save_calibration", save_calibration)
    monkeypatch.setattr(task, "prepare_run", lambda *_args: None)
    monkeypatch.setattr(task, "preprocess", lambda *_args: None)
    monkeypatch.setattr(qubex.contrib, "characterize_coarse_readout_parameters", characterize)
    return SimpleNamespace(
        task=task,
        backend=backend,
        result=result,
        rabi_results=rabi_results,
        save_calibration=save_calibration,
        characterize=characterize,
        experiment=experiment,
        qubit=qubit,
    )


def test_selected_r2_ignores_unselected_poor_fits(coarse_readout: SimpleNamespace) -> None:
    for result in coarse_readout.rabi_results:
        result.rabi_params["Q00"].r2 = np.nan
    coarse_readout.rabi_results[4].rabi_params["Q00"].r2 = np.float64(0.61)

    run_result = coarse_readout.task.run(coarse_readout.backend, "0")
    postprocess = coarse_readout.task.postprocess(coarse_readout.backend, "exec-1", run_result, "0")

    assert coarse_readout.task.r2_threshold == CheckRabi.r2_threshold == 0.6
    assert run_result.r2 == {"0": 0.61}
    assert postprocess.validation_error is None
    assert postprocess.output_parameters["readout_frequency"].value == 6.01
    assert postprocess.output_parameters["readout_amplitude"].value == 0.1
    coarse_readout.save_calibration.assert_called_once()


@pytest.mark.parametrize(
    ("amplitude", "frequency_range", "ratio_range", "n_sweeps"),
    [
        (0.1, (-0.015, 0.015, 13), (0.8, 1.2, 5), 65),
        (1.0, (-0.015, 0.015, 13), (0.8, 1.2, 5), 39),
        (0.1, (-0.005, 0.005, 3), (0.9, 1.1, 3), 9),
        (0.1, (0, 0, 3), (1, 1, 3), 1),
    ],
)
def test_progress_plan_counts_the_effective_scan_grid(
    coarse_readout: SimpleNamespace,
    amplitude: float,
    frequency_range: tuple[float, float, int],
    ratio_range: tuple[float, float, int],
    n_sweeps: int,
) -> None:
    task = coarse_readout.task
    task.input_parameters["readout_amplitude"].value = amplitude
    task.run_parameters["detuning_range"].value = frequency_range
    task.run_parameters["readout_amplitude_ratio_range"].value = ratio_range

    assert TaskExecutor._progress_plan(task) == ProgressPlan(n_sweeps, n_sweeps)
    coarse_readout.characterize.assert_not_called()


@pytest.mark.parametrize(("amplitude", "n_sweeps"), [(0.1, 65), (1.0, 39)])
def test_real_readout_search_reports_all_sweeps_from_the_first_measurement(
    coarse_readout: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    amplitude: float,
    n_sweeps: int,
) -> None:
    task = coarse_readout.task
    task.input_parameters["readout_amplitude"].value = amplitude
    exp = coarse_readout.experiment
    exp.ctx.resolve_qubit_label = lambda target: target
    exp.ctx.resonators = {"Q00": SimpleNamespace(label="RQ00", frequency=6.5)}
    events: list[TaskProgress] = []

    def rabi_experiment(**kwargs: Any) -> SimpleNamespace:
        # Each real Rabi experiment opens one disabled parameter-sweep tqdm.
        list(
            ReportingTqdm(
                kwargs["time_range"],
                desc="Sweeping parameters",
                disable=True,
                file=StringIO(),
            )
        )
        return SimpleNamespace(
            data={"Q00": SimpleNamespace(data=np.array([0j, 1j, -1j]))},
            rabi_params={"Q00": SimpleNamespace(r2=0.95)},
        )

    def characterize(sweep_exp: Any, **kwargs: Any) -> Any:
        return characterize_coarse_readout_parameters(
            sweep_exp, plot=False, save_image=False, **kwargs
        )

    monkeypatch.setattr(exp, "rabi_experiment", rabi_experiment)
    monkeypatch.setattr(qubex.contrib, "characterize_coarse_readout_parameters", characterize)
    with capture_qubex_progress(
        events.append, task_name=task.name, plan=TaskExecutor._progress_plan(task)
    ):
        task.run(coarse_readout.backend, "0")

    assert events[0].phase == 1
    assert events[0].current == 0
    assert events[-1].phase == n_sweeps
    assert events[-1].current == events[-1].total == 26
    assert all(event.has_multiple_phases for event in events)
    assert all(event.phase_total_min == event.phase_total_max == n_sweeps for event in events)
    assert all(event.description == "Readout parameter search" for event in events)
    fractions = []
    for event in events:
        assert event.total is not None
        fractions.append((event.phase - 1 + event.current / event.total) / n_sweeps)
    assert fractions == sorted(fractions)
    assert fractions[0] == 0
    assert fractions[-1] == 1
    assert all(
        fraction < 1
        for event, fraction in zip(events, fractions, strict=True)
        if event.phase < n_sweeps
    )


@pytest.mark.parametrize("r2", [0.59, 0.6, None, np.nan, np.inf, -np.inf, 1.1])
def test_rejected_selected_fit_preserves_figure_and_blocks_outputs(
    coarse_readout: SimpleNamespace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    r2: float | None,
) -> None:
    coarse_readout.rabi_results[4].rabi_params["Q00"].r2 = r2
    state = TaskStateManager(qids=["0"])
    saver = MagicMock()
    saver.save_figures.return_value = (["heatmap.png"], ["heatmap.json"])
    executor = TaskExecutor(
        state_manager=state,
        calib_dir=str(tmp_path),
        execution_id="exec-1",
        username="test",
        task_manager_id="tm-1",
        data_saver=saver,
    )

    with pytest.raises(ValueError, match="R²"):
        executor.execute_task(coarse_readout.task, coarse_readout.backend, "0")

    model = state.get_task(coarse_readout.task.name, "qubit", "0")
    assert model.status == TaskStatusModel.FAILED
    assert model.output_parameters == {}
    assert state.get_qubit_calib_data("0") == {}
    saver.save_figures.assert_called_once()
    assert saver.save_figures.call_args.args[0] == [coarse_readout.result.figure]
    coarse_readout.save_calibration.assert_not_called()

    # Even a forced backend save cannot publish the rejected candidate after rollback.
    qubit_repo = MagicMock()
    coupling_repo = MagicMock()
    update_params = MagicMock()
    monkeypatch.setattr("qdash.repository.MongoQubitCalibrationRepository", lambda: qubit_repo)
    monkeypatch.setattr(
        "qdash.repository.MongoCouplingCalibrationRepository", lambda: coupling_repo
    )
    executor._backend_saver._force_update_params = True
    monkeypatch.setattr(executor._backend_saver, "_update_backend_params", update_params)
    executor._backend_saver.save(
        coarse_readout.task,
        cast("Any", SimpleNamespace(chip_id="chip", project_id="project", execution_id="exec-1")),
        "0",
        coarse_readout.backend,
        False,
    )
    qubit_repo.update_calib_data.assert_not_called()
    coupling_repo.update_calib_data.assert_not_called()
    update_params.assert_not_called()


@pytest.mark.parametrize("missing", ["rabi_results", "frequency_range", "readout_amplitudes"])
def test_missing_selection_metadata_fails_after_postprocess(
    coarse_readout: SimpleNamespace, missing: str
) -> None:
    del coarse_readout.result.data[missing]
    run_result = coarse_readout.task.run(coarse_readout.backend, "0")
    postprocess = coarse_readout.task.postprocess(coarse_readout.backend, "exec-1", run_result, "0")

    assert run_result.r2 == {"0": None}
    assert postprocess.validation_error == "Selected readout point R² is missing"
    assert postprocess.figures == [coarse_readout.result.figure]
    coarse_readout.save_calibration.assert_not_called()


def test_selected_result_must_belong_to_requested_qubit(coarse_readout: SimpleNamespace) -> None:
    coarse_readout.rabi_results[4].rabi_params = {"Q01": SimpleNamespace(r2=0.99)}
    run_result = coarse_readout.task.run(coarse_readout.backend, "0")

    assert run_result.r2 == {"0": None}
    coarse_readout.save_calibration.assert_not_called()


@pytest.mark.parametrize("time_range", [(0, 101, 4), (0, 401, 10)])
def test_rabi_time_range_is_passed_to_qubex(
    coarse_readout: SimpleNamespace, time_range: tuple[int, int, int]
) -> None:
    coarse_readout.task.run_parameters["time_range"].value = time_range
    coarse_readout.task.run_parameters["shots"].value = 4096
    coarse_readout.task.run(coarse_readout.backend, "0")

    kwargs = coarse_readout.characterize.call_args.kwargs
    np.testing.assert_array_equal(kwargs["time_range"], np.arange(*time_range))
    assert kwargs["n_shots"] == 4096


def test_default_sweep_is_local_and_uses_half_the_shots(coarse_readout: SimpleNamespace) -> None:
    coarse_readout.task.run(coarse_readout.backend, "0")
    kwargs = coarse_readout.characterize.call_args.kwargs

    np.testing.assert_allclose(kwargs["frequency_range"], np.linspace(5.985, 6.015, 13))
    np.testing.assert_allclose(kwargs["readout_amplitudes"], [0.08, 0.09, 0.1, 0.11, 0.12])
    assert kwargs["frequency_range"][6] == 6.0
    assert kwargs["readout_amplitudes"][2] == 0.1
    assert kwargs["n_shots"] == 1024
    np.testing.assert_array_equal(kwargs["time_range"], np.arange(0, 101, 4))


def test_sweep_respects_effective_inputs_and_run_overrides(
    coarse_readout: SimpleNamespace,
) -> None:
    task = coarse_readout.task
    task.input_parameters["readout_frequency"].value = 7.0
    task.input_parameters["readout_amplitude"].value = 0.2
    task.run_parameters["detuning_range"].value = (-0.025, 0.025, 21)
    task.run_parameters["readout_amplitude_ratio_range"].value = (0.5, 1.5, 7)
    task.run(coarse_readout.backend, "0")
    kwargs = coarse_readout.characterize.call_args.kwargs

    np.testing.assert_allclose(kwargs["frequency_range"], np.linspace(6.975, 7.025, 21))
    np.testing.assert_allclose(kwargs["readout_amplitudes"], np.linspace(0.1, 0.3, 7))
    assert task.input_parameters["readout_amplitude"].value == 0.2


def test_sweep_caps_amplitude_without_duplicate_measurements(
    coarse_readout: SimpleNamespace,
) -> None:
    coarse_readout.task.input_parameters["readout_amplitude"].value = 1.0
    coarse_readout.task.run(coarse_readout.backend, "0")
    np.testing.assert_allclose(
        coarse_readout.characterize.call_args.kwargs["readout_amplitudes"], [0.8, 0.9, 1.0]
    )
    assert coarse_readout.task.input_parameters["readout_amplitude"].value == 1.0


@pytest.mark.parametrize("amplitude", [None, 0.0, -0.1, 1.1, np.nan, np.inf])
def test_invalid_reference_amplitude_stops_before_measurement(
    coarse_readout: SimpleNamespace, amplitude: float | None
) -> None:
    coarse_readout.task.input_parameters["readout_amplitude"].value = amplitude
    with pytest.raises(ValueError, match="readout_amplitude"):
        coarse_readout.task.run(coarse_readout.backend, "0")
    coarse_readout.characterize.assert_not_called()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("detuning_range", (-0.01, 0.01, 0)),
        ("detuning_range", (-8.0, -7.0, 3)),
        ("readout_amplitude_ratio_range", (-0.5, 0.5, 3)),
        ("readout_amplitude_ratio_range", (0.8, 1.2, 0)),
    ],
)
def test_invalid_scan_stops_before_measurement(
    coarse_readout: SimpleNamespace, name: str, value: tuple[float, float, int]
) -> None:
    coarse_readout.task.run_parameters[name].value = value
    with pytest.raises(ValueError):
        coarse_readout.task.run(coarse_readout.backend, "0")
    coarse_readout.characterize.assert_not_called()


@pytest.mark.parametrize("fail", [False, True])
def test_real_qubex_helper_uses_resolved_rabi_inputs_and_restores_context(
    coarse_readout: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    fail: bool,
) -> None:
    task = coarse_readout.task
    exp = coarse_readout.experiment
    task.input_parameters["qubit_frequency"].value = 5.4
    task.input_parameters["control_amplitude"].value = 0.04
    task.input_parameters["readout_duration"].value = 2300
    exp.ctx.resolve_qubit_label = lambda target: target
    exp.ctx.resonators = {"Q00": SimpleNamespace(label="RQ00", frequency=6.5)}
    observed: list[dict[str, Any]] = []

    def rabi_experiment(**kwargs: Any) -> SimpleNamespace:
        assert coarse_readout.qubit.frequency == 5.4
        assert kwargs["amplitudes"] == {"Q00": 0.04}
        assert kwargs["readout_duration"] == 2300
        assert kwargs["n_shots"] == 1024
        assert kwargs["store_params"] is False
        observed.append(kwargs)
        if fail:
            raise RuntimeError("measurement failed")
        return SimpleNamespace(
            data={
                "Q00": SimpleNamespace(
                    data=np.array([0j, 1j, -1j]) * exp.params.readout_amplitude["Q00"]
                )
            },
            rabi_params={"Q00": SimpleNamespace(r2=0.95)},
        )

    def characterize(sweep_exp: Any, **kwargs: Any) -> Any:
        return characterize_coarse_readout_parameters(
            sweep_exp, plot=False, save_image=False, **kwargs
        )

    monkeypatch.setattr(exp, "rabi_experiment", rabi_experiment)
    monkeypatch.setattr(qubex.contrib, "characterize_coarse_readout_parameters", characterize)
    if fail:
        with pytest.raises(RuntimeError, match="measurement failed"):
            task.run(coarse_readout.backend, "0")
        coarse_readout.save_calibration.assert_not_called()
    else:
        result = task.run(coarse_readout.backend, "0")
        assert result.r2 == {"0": 0.95}
        assert len(observed) == 65
        np.testing.assert_allclose(
            [kwargs["frequencies"]["RQ00"] for kwargs in observed[:13]],
            np.linspace(5.985, 6.015, 13),
        )

    assert coarse_readout.qubit.frequency == 5.0
    assert exp.params.control_amplitude == {"Q00": 0.01}
    assert exp.params.readout_amplitude == {"Q00": 0.2}
    assert task.input_parameters["readout_duration"].value == 2300


@pytest.mark.parametrize("duration", [0, -1, np.nan, np.inf])
def test_invalid_readout_duration_stops_before_measurement(
    coarse_readout: SimpleNamespace, duration: float
) -> None:
    coarse_readout.task.input_parameters["readout_duration"].value = duration
    with pytest.raises(ValueError, match="readout_duration"):
        coarse_readout.task.run(coarse_readout.backend, "0")
    coarse_readout.characterize.assert_not_called()
