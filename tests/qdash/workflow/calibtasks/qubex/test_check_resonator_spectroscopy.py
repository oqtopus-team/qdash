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

    assert result.output_parameters["resonator_frequency"].value == 6.3
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
    assert result.output_parameters["resonator_frequency"].value == 6.2


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
    assert result.output_parameters["resonator_frequency"].value == 6.1
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
    assert result.output_parameters["resonator_frequency"].value == 6.3
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
        "interval",
        "resonator_assignment_order",
        "detection_only",
    }
    assert CheckResonatorSpectroscopy.run_spec["detection_only"].default is False


@pytest.mark.parametrize("assignment_order", [[0, 0, 1, 2], [0, 1, 2]])
@pytest.mark.parametrize("batch", [False, True])
def test_invalid_assignment_order_is_rejected_before_hardware(
    assignment_order: list[int], batch: bool
) -> None:
    task = CheckResonatorSpectroscopy()
    task.run_parameters["resonator_assignment_order"].value = tuple(assignment_order)
    get_experiment = MagicMock()
    task.get_experiment = get_experiment  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="must contain each qubit offset"):
        if batch:
            task.batch_run(MagicMock(), ["0", "1"])
        else:
            task.run(MagicMock(), "0")

    get_experiment.assert_not_called()


def test_measurement_settings_are_forwarded_to_qubex(monkeypatch) -> None:
    task = CheckResonatorSpectroscopy()
    task.run_parameters["shots"].value = 321
    task.run_parameters["interval"].value = 654.0
    exp = MagicMock()
    monkeypatch.setattr(task, "get_experiment", lambda _backend: exp)
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)

    task.run(MagicMock(), "0")

    kwargs = exp.resonator_spectroscopy.call_args.kwargs
    assert kwargs["n_shots"] == 321
    assert kwargs["shot_interval"] == 654.0


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


_CANDIDATE_OUTPUT_NAMES = (
    "resonator_candidate_count",
    *(
        f"resonator_candidate_{index}_{field}"
        for index in range(4)
        for field in ("frequency", "readout_amplitude")
    ),
)


def _postprocess_with_detection(
    frequencies: list[float],
    optimal_powers: list[float],
    *,
    qid: str = "1",
    assignment_order: list[int | float] | None = None,
    detection_only: bool = True,
    analysis_error: Exception | None = None,
):
    task = CheckResonatorSpectroscopy()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task._bare_shift_estimator_type = "config"
    task.run_parameters["detection_only"].value = detection_only
    if assignment_order is not None:
        task.run_parameters["resonator_assignment_order"].value = assignment_order
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
        for i in range(len(frequencies))
    ]
    module = "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
    with (
        patch.object(task, "_prepare_analysis_figure", return_value=raw_fig),
        patch(
            module + "estimate_resonator_frequency_from_figure",
            return_value=(resonances, [], frequencies),
            side_effect=analysis_error,
        ),
        patch(module + "estimate_minimum_usable_power", return_value=-40.0),
        patch(module + "estimate_optimal_powers", return_value=optimal_powers),
        patch(module + "create_marked_figure", return_value=go.Figure(raw_fig)),
    ):
        return task.postprocess(MagicMock(), "exec-1", RunResult(raw_result={"fig": raw_fig}), qid)


def test_detection_only_publishes_unassigned_candidates_with_paired_amplitudes() -> None:
    """Publish every detected peak with the amplitude of its own optimal power."""
    result = _postprocess_with_detection([6.0, 6.1, 6.2, 6.3], [-40.0, -35.0, -30.0, -25.0])

    outputs = result.output_parameters
    assert result.validation_error is None
    assert set(outputs) == set(_CANDIDATE_OUTPUT_NAMES)
    assert outputs["resonator_candidate_count"].value == 4
    for index, (frequency, power) in enumerate(
        zip([6.0, 6.1, 6.2, 6.3], [-40.0, -35.0, -30.0, -25.0], strict=True)
    ):
        assert outputs[f"resonator_candidate_{index}_frequency"].value == frequency
        assert outputs[f"resonator_candidate_{index}_readout_amplitude"].value == pytest.approx(
            10 ** (power / 20)
        )
        assert outputs[f"resonator_candidate_{index}_frequency"].execution_id == "exec-1"


def test_detection_only_assigns_nothing_to_the_qid() -> None:
    """Publish no resonator, readout frequency, power, or amplitude for any qid."""
    result = _postprocess_with_detection([6.0, 6.1, 6.2, 6.3], [-40.0, -35.0, -30.0, -25.0])

    assert not {"resonator_frequency", "optimal_power", "readout_amplitude"} & set(
        result.output_parameters
    )


def test_detection_only_sorts_candidates_by_frequency_and_keeps_power_pairing() -> None:
    """Sort candidates by frequency without separating a peak from its power."""
    result = _postprocess_with_detection([6.3, 6.0, 6.2, 6.1], [-25.0, -40.0, -30.0, -35.0])

    outputs = result.output_parameters
    assert [outputs[f"resonator_candidate_{i}_frequency"].value for i in range(4)] == [
        6.0,
        6.1,
        6.2,
        6.3,
    ]
    assert [
        outputs[f"resonator_candidate_{i}_readout_amplitude"].value for i in range(4)
    ] == pytest.approx([10 ** (power / 20) for power in (-40.0, -35.0, -30.0, -25.0)])


@pytest.mark.parametrize("qid", ["0", "1", "2", "3"])
def test_detection_only_result_is_identical_for_every_qid_and_assignment_order(qid) -> None:
    """Give every qid of the MUX the same candidate set whatever the assignment order."""
    reference = _postprocess_with_detection(
        [6.0, 6.1, 6.2], [-40.0, -35.0, -30.0], qid="0", assignment_order=[3, 0, 2, 1]
    )
    other = _postprocess_with_detection(
        [6.0, 6.1, 6.2], [-40.0, -35.0, -30.0], qid=qid, assignment_order=[0, 1, 2, 3]
    )

    assert other.validation_error is None
    assert reference.output_parameters.keys() == other.output_parameters.keys()
    for name, value in reference.output_parameters.items():
        assert other.output_parameters[name].value == value.value


def test_detection_only_uses_all_peaks_when_assignment_would_fail() -> None:
    """Publish a partial detection that the per-qid assignment would reject for this qid."""
    legacy = _postprocess_with_detection(
        [6.0, 6.1, 6.2], [-40.0, -35.0, -30.0], qid="1", detection_only=False
    )
    detection = _postprocess_with_detection([6.0, 6.1, 6.2], [-40.0, -35.0, -30.0], qid="1")

    assert legacy.validation_error is not None
    outputs = detection.output_parameters
    assert detection.validation_error is None
    assert outputs["resonator_candidate_count"].value == 3
    assert outputs["resonator_candidate_2_frequency"].value == 6.2
    assert "resonator_candidate_3_frequency" not in outputs
    assert "resonator_candidate_3_readout_amplitude" not in outputs


@pytest.mark.parametrize(
    ("frequencies", "powers", "analysis_error"),
    [
        ([6.0, 6.1, 6.2, 6.3], [-40.0, float("nan"), -30.0, -25.0], None),
        ([], [], None),
        ([6.0, 6.1, 6.2, 6.3, 6.4], [-40.0, -35.0, -30.0, -25.0, -20.0], None),
        ([6.0], [-40.0], RuntimeError("analysis broke")),
    ],
)
@pytest.mark.parametrize("qid", ["0", "2"])
def test_detection_only_fails_without_outputs_for_an_unusable_set(
    frequencies, powers, analysis_error, qid
) -> None:
    """Fail every qid explicitly instead of publishing an empty or partial candidate set."""
    result = _postprocess_with_detection(
        frequencies, powers, qid=qid, analysis_error=analysis_error
    )

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert result.figures


def test_default_mode_publishes_no_candidates() -> None:
    """Keep the default per-qid assignment outputs unchanged."""
    result = _postprocess_with_detection(
        [6.0, 6.1, 6.2, 6.3], [-40.0, -35.0, -30.0, -25.0], detection_only=False
    )

    assert result.validation_error is None
    assert set(result.output_parameters) == {
        "resonator_frequency",
        "optimal_power",
        "readout_amplitude",
    }


def test_default_mode_publishes_nothing_when_assignment_fails() -> None:
    """Keep the existing failure semantics: a failed qid publishes no outputs."""
    result = _postprocess_with_detection(
        [6.0, 6.1, 6.2], [-40.0, -35.0, -30.0], qid="1", detection_only=False
    )

    assert result.validation_error is not None
    assert result.output_parameters == {}
