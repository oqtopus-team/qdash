import copy
from unittest.mock import MagicMock, patch

import plotly.graph_objs as go
import pytest

from qdash.analysis.spectroscopy.estimate_resonator_frequency import Peak, Resonance
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy import (
    CheckResonatorSpectroscopy,
    _guess_sorted_slots_for_partial_mux,
)


def test_postprocess_outputs_optimal_power_from_resonator_analysis() -> None:
    task = CheckResonatorSpectroscopy()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task._bare_shift_estimator_type = "config"
    raw_fig = go.Figure(
        data=[
            go.Heatmap(
                x=[6.0, 6.1, 6.2, 6.3],
                y=[-60.0, -55.0, -50.0, -45.0, -40.0, -35.0, -30.0, -25.0],
                z=[[0.0, 0.0, 0.0, 0.0] for _ in range(8)],
            )
        ]
    )
    resonances = [
        Resonance(high_power_peaks=None, low_power_peak=Peak(x=i, y=6, prominence=1.0))
        for i in range(4)
    ]

    with (
        patch.object(task, "_prepare_analysis_figure", return_value=raw_fig),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
            "estimate_resonator_frequency_from_figure",
            return_value=(resonances, [], [6.0, 6.1, 6.2, 6.3]),
        ),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
            "estimate_minimum_usable_power",
            return_value=-40.0,
        ),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy.create_marked_figure",
            return_value=raw_fig,
        ),
    ):
        result = task.postprocess(
            MagicMock(),
            "exec-1",
            RunResult(raw_result={"fig": raw_fig}),
            "1",
        )

    assert result.output_parameters["readout_frequency"].value == 6.3
    assert result.output_parameters["optimal_power"].value == -35.0
    assert result.output_parameters["readout_amplitude"].value == 10 ** (-35.0 / 20)
    assert result.output_parameters["optimal_power"].execution_id == "exec-1"
    assert result.output_parameters["readout_amplitude"].execution_id == "exec-1"


def test_postprocess_uses_custom_resonator_assignment_order() -> None:
    task = CheckResonatorSpectroscopy()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task._bare_shift_estimator_type = "config"
    task.run_parameters["resonator_assignment_order"].value = [0, 3, 1, 2]
    raw_fig = go.Figure(
        data=[
            go.Heatmap(
                x=[6.0, 6.1, 6.2, 6.3],
                y=[-60.0, -55.0, -50.0, -45.0, -40.0, -35.0, -30.0, -25.0],
                z=[[0.0, 0.0, 0.0, 0.0] for _ in range(8)],
            )
        ]
    )
    resonances = [
        Resonance(high_power_peaks=None, low_power_peak=Peak(x=i, y=6, prominence=1.0))
        for i in range(4)
    ]

    with (
        patch.object(task, "_prepare_analysis_figure", return_value=raw_fig),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
            "estimate_resonator_frequency_from_figure",
            return_value=(resonances, [], [6.0, 6.1, 6.2, 6.3]),
        ),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
            "estimate_minimum_usable_power",
            return_value=-40.0,
        ),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy.create_marked_figure",
            return_value=raw_fig,
        ),
    ):
        result = task.postprocess(
            MagicMock(),
            "exec-1",
            RunResult(raw_result={"fig": raw_fig}),
            "1",
        )

    assert result.validation_error is None
    assert result.output_parameters["readout_frequency"].value == 6.2


def test_postprocess_rejects_invalid_resonator_result_without_outputs() -> None:
    task = CheckResonatorSpectroscopy()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task._bare_shift_estimator_type = "config"
    raw_fig = go.Figure(
        data=[
            go.Heatmap(
                x=[6.0, 6.1, 6.2, 6.3],
                y=[-60.0, -55.0, -50.0, -45.0, -40.0, -35.0, -30.0, -25.0],
                z=[[0.0, 0.0, 0.0, 0.0] for _ in range(8)],
            )
        ]
    )
    resonances = [
        Resonance(high_power_peaks=None, low_power_peak=Peak(x=i, y=6, prominence=1.0))
        for i in range(3)
    ]

    with (
        patch.object(task, "_prepare_analysis_figure", return_value=raw_fig),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
            "estimate_resonator_frequency_from_figure",
            return_value=(resonances, [], [6.0, 6.1, 6.2]),
        ),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
            "estimate_minimum_usable_power",
            return_value=-40.0,
        ),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy.create_marked_figure",
            return_value=raw_fig,
        ),
    ):
        result = task.postprocess(
            MagicMock(),
            "exec-1",
            RunResult(raw_result={"fig": raw_fig}),
            "1",
        )

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert "assignment_order=[3, 0, 2, 1]" in result.validation_error
    assert "detected_slots=[0, 1, 2]" in result.validation_error


def test_postprocess_allows_partial_mux_success_when_qid_slot_is_available() -> None:
    task = CheckResonatorSpectroscopy()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task._bare_shift_estimator_type = "config"
    raw_fig = go.Figure(
        data=[
            go.Heatmap(
                x=[6.0, 6.1, 6.2, 6.3],
                y=[-60.0, -55.0, -50.0, -45.0, -40.0, -35.0, -30.0, -25.0],
                z=[[0.0, 0.0, 0.0, 0.0] for _ in range(8)],
            )
        ]
    )
    resonances = [
        Resonance(high_power_peaks=None, low_power_peak=Peak(x=i, y=6, prominence=1.0))
        for i in range(3)
    ]

    with (
        patch.object(task, "_prepare_analysis_figure", return_value=raw_fig),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
            "estimate_resonator_frequency_from_figure",
            return_value=(resonances, [], [6.0, 6.1, 6.2]),
        ),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
            "estimate_minimum_usable_power",
            return_value=-40.0,
        ),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy.create_marked_figure",
            return_value=raw_fig,
        ),
    ):
        result = task.postprocess(
            MagicMock(),
            "exec-1",
            RunResult(raw_result={"fig": raw_fig}),
            "0",
        )

    assert result.validation_error is None
    assert result.output_parameters["readout_frequency"].value == 6.1
    assert result.output_parameters["optimal_power"].value == -35.0


def test_postprocess_rejects_partial_mux_when_qid_slot_is_missing() -> None:
    task = CheckResonatorSpectroscopy()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task._bare_shift_estimator_type = "config"
    raw_fig = go.Figure(
        data=[
            go.Heatmap(
                x=[6.0, 6.1, 6.2, 6.3],
                y=[-60.0, -55.0, -50.0, -45.0, -40.0, -35.0, -30.0, -25.0],
                z=[[0.0, 0.0, 0.0, 0.0] for _ in range(8)],
            )
        ]
    )
    resonances = [
        Resonance(high_power_peaks=None, low_power_peak=Peak(x=i, y=6, prominence=1.0))
        for i in range(3)
    ]

    with (
        patch.object(task, "_prepare_analysis_figure", return_value=raw_fig),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
            "estimate_resonator_frequency_from_figure",
            return_value=(resonances, [], [6.0, 6.1, 6.2]),
        ),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
            "estimate_minimum_usable_power",
            return_value=-40.0,
        ),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy.create_marked_figure",
            return_value=raw_fig,
        ),
    ):
        result = task.postprocess(
            MagicMock(),
            "exec-1",
            RunResult(raw_result={"fig": raw_fig}),
            "1",
        )

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert "assigned_slot=3" in result.validation_error
    assert "detected_slots=[0, 1, 2]" in result.validation_error


def test_postprocess_preserves_analysis_exception_in_validation_error() -> None:
    task = CheckResonatorSpectroscopy()
    task._bare_shift_estimator_type = "config"
    raw_fig = go.Figure(go.Heatmap(x=[6.0, 6.1], y=[-30.0], z=[[1.0, 2.0]]))

    with (
        patch.object(task, "_prepare_analysis_figure", return_value=raw_fig),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
            "estimate_resonator_frequency_from_figure",
            side_effect=ValueError("peak grouping failed"),
        ),
    ):
        result = task.postprocess(
            MagicMock(),
            "exec-1",
            RunResult(raw_result={"fig": raw_fig}),
            "4",
        )

    assert result.output_parameters == {}
    assert result.validation_error == (
        "Resonator analysis failed for qid=4: ValueError: peak grouping failed"
    )


def test_guess_sorted_slots_for_partial_mux_prefers_left_edge_missing_for_right_cluster() -> None:
    sorted_slots, mode = _guess_sorted_slots_for_partial_mux(
        xs=[6.0, 6.1, 6.2, 6.3],
        frequencies=[6.1, 6.2, 6.3],
    )

    assert sorted_slots == [1, 2, 3]
    assert mode == "left-edge-missing-cluster-right"


def test_postprocess_allows_left_edge_missing_partial_mux_when_qid_slot_is_available() -> None:
    task = CheckResonatorSpectroscopy()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task._bare_shift_estimator_type = "config"
    raw_fig = go.Figure(
        data=[
            go.Heatmap(
                x=[6.0, 6.1, 6.2, 6.3],
                y=[-60.0, -55.0, -50.0, -45.0, -40.0, -35.0, -30.0, -25.0],
                z=[[0.0, 0.0, 0.0, 0.0] for _ in range(8)],
            )
        ]
    )
    resonances = [
        Resonance(high_power_peaks=None, low_power_peak=Peak(x=i + 1, y=6, prominence=1.0))
        for i in range(3)
    ]

    with (
        patch.object(task, "_prepare_analysis_figure", return_value=raw_fig),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
            "estimate_resonator_frequency_from_figure",
            return_value=(resonances, [], [6.1, 6.2, 6.3]),
        ),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
            "estimate_minimum_usable_power",
            return_value=-40.0,
        ),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy.create_marked_figure",
            return_value=raw_fig,
        ),
    ):
        result = task.postprocess(
            MagicMock(),
            "exec-1",
            RunResult(raw_result={"fig": raw_fig}),
            "1",
        )

    assert result.validation_error is None
    assert result.output_parameters["readout_frequency"].value == 6.3
    annotations = result.figures[0].layout.annotations
    texts = [annotation["text"] for annotation in annotations]
    assert "left-edge-missing-cluster-right" in texts
    assert "Q00 / s1" in texts
    assert "Q02 / s2" in texts
    assert "Q01 / s3" in texts


def test_postprocess_rejects_left_edge_missing_partial_mux_when_qid_slot_is_missing() -> None:
    task = CheckResonatorSpectroscopy()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task._bare_shift_estimator_type = "config"
    raw_fig = go.Figure(
        data=[
            go.Heatmap(
                x=[6.0, 6.1, 6.2, 6.3],
                y=[-60.0, -55.0, -50.0, -45.0, -40.0, -35.0, -30.0, -25.0],
                z=[[0.0, 0.0, 0.0, 0.0] for _ in range(8)],
            )
        ]
    )
    resonances = [
        Resonance(high_power_peaks=None, low_power_peak=Peak(x=i + 1, y=6, prominence=1.0))
        for i in range(3)
    ]

    with (
        patch.object(task, "_prepare_analysis_figure", return_value=raw_fig),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
            "estimate_resonator_frequency_from_figure",
            return_value=(resonances, [], [6.1, 6.2, 6.3]),
        ),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
            "estimate_minimum_usable_power",
            return_value=-40.0,
        ),
        patch(
            "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy.create_marked_figure",
            return_value=raw_fig,
        ),
    ):
        result = task.postprocess(
            MagicMock(),
            "exec-1",
            RunResult(raw_result={"fig": raw_fig}),
            "3",
        )

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert "assigned_slot=0" in result.validation_error
    assert "detected_slots=[1, 2, 3]" in result.validation_error


def test_frequency_range_is_resolved_from_readout_box_when_unset(monkeypatch) -> None:
    task = CheckResonatorSpectroscopy()
    backend = MagicMock()
    exp = MagicMock()
    readout_box = exp.ctx.experiment_system.get_readout_box_for_qubit.return_value
    readout_box.traits.default_readout_frequency_range = (5.75, 6.75, 0.002)
    monkeypatch.setattr(task, "get_experiment", lambda _backend: exp)
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")

    task.resolve_run_parameters(backend, "0")

    assert task.run_parameters["frequency_range"].value == (5.75, 6.75, 0.002)
    exp.ctx.experiment_system.get_readout_box_for_qubit.assert_called_once_with("Q00")


def test_run_parameters_only_expose_measurement_and_assignment_settings() -> None:
    assert set(CheckResonatorSpectroscopy.run_spec) == {
        "frequency_range",
        "power_range",
        "shots",
        "resonator_assignment_order",
    }


def test_frequency_range_can_be_overridden_per_task() -> None:
    task = CheckResonatorSpectroscopy()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task.run_parameters["frequency_range"].value = (5.8, 6.15, 0.1)

    assert list(task._frequency_range()) == pytest.approx([5.8, 5.9, 6.0, 6.1])


def test_explicit_frequency_range_is_not_resolved_from_readout_box() -> None:
    task = CheckResonatorSpectroscopy()
    task.run_parameters["frequency_range"].value = (5.8, 6.15, 0.1)
    backend = MagicMock()

    task.resolve_run_parameters(backend, "0")

    backend.get_experiment.assert_not_called()


def test_prepare_analysis_figure_ignores_spike_ranges_outside_custom_sweep() -> None:
    task = CheckResonatorSpectroscopy()
    raw_fig = go.Figure(
        go.Heatmap(
            x=[5.7, 5.8, 5.9],
            y=[-30.0],
            z=[[1.0, 2.0, 3.0]],
        )
    )

    analysis_fig = task._prepare_analysis_figure(raw_fig)

    assert list(analysis_fig.data[0].z[0]) == [1.0, 2.0, 3.0]


def test_prepare_analysis_figure_ignores_spike_ranges_not_sampled_by_custom_step() -> None:
    task = CheckResonatorSpectroscopy()
    raw_fig = go.Figure(
        go.Heatmap(
            x=[5.95, 5.96, 5.97, 5.98, 5.99, 6.0, 6.01],
            y=[-30.0],
            z=[[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]],
        )
    )

    analysis_fig = task._prepare_analysis_figure(raw_fig)

    assert list(analysis_fig.data[0].z[0]) == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
