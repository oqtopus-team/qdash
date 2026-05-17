import copy
from unittest.mock import MagicMock, patch

import plotly.graph_objs as go

from qdash.analysis.spectroscopy.estimate_resonator_frequency import Peak, Resonance
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy import (
    CheckResonatorSpectroscopy,
    _guess_sorted_slots_for_partial_mux,
)


def test_postprocess_outputs_optimal_power_from_resonator_analysis() -> None:
    task = CheckResonatorSpectroscopy()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task.run_parameters["bare_shift_estimator_type"].value = "config"
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


def test_postprocess_rejects_invalid_resonator_result_without_outputs() -> None:
    task = CheckResonatorSpectroscopy()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task.run_parameters["bare_shift_estimator_type"].value = "config"
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


def test_postprocess_allows_partial_mux_success_when_qid_slot_is_available() -> None:
    task = CheckResonatorSpectroscopy()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task.run_parameters["bare_shift_estimator_type"].value = "config"
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
    task.run_parameters["bare_shift_estimator_type"].value = "config"
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
    task.run_parameters["bare_shift_estimator_type"].value = "config"
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
    annotations = result.figures[1].layout.annotations
    texts = [annotation["text"] for annotation in annotations]
    assert "left-edge-missing-cluster-right" in texts
    assert "Q00 / s1" in texts
    assert "Q02 / s2" in texts
    assert "Q01 / s3" in texts


def test_postprocess_rejects_left_edge_missing_partial_mux_when_qid_slot_is_missing() -> None:
    task = CheckResonatorSpectroscopy()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task.run_parameters["bare_shift_estimator_type"].value = "config"
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
