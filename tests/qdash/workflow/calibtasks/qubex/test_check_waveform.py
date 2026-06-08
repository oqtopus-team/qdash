from unittest.mock import MagicMock

import plotly.graph_objects as go

from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.cw.check_waveform import CheckWaveform


def _make_backend() -> MagicMock:
    backend = MagicMock()
    backend.get_instance.return_value = backend.experiment
    backend.experiment.get_qubit_label.side_effect = lambda qid: f"Q{qid:02d}"
    return backend


def test_run_calls_qubex_check_waveform_for_single_target() -> None:
    task = CheckWaveform()
    backend = _make_backend()
    backend.experiment.check_waveform.return_value = {"ok": True}

    result = task.run(backend, "0")

    backend.experiment.check_waveform.assert_called_once_with(
        targets="Q00",
        n_shots=task.run_parameters["shots"].get_value(),
        shot_interval=task.run_parameters["interval"].get_value(),
        readout_amplitude=None,
        readout_duration=None,
        readout_pre_margin=None,
        readout_post_margin=None,
    )
    assert result.raw_result == {"ok": True}


def test_batch_run_calls_qubex_check_waveform_for_targets() -> None:
    task = CheckWaveform()
    backend = _make_backend()
    backend.experiment.check_waveform.return_value = {"ok": True}

    result = task.batch_run(backend, ["0", "1"])

    backend.experiment.check_waveform.assert_called_once_with(
        targets=["Q00", "Q01"],
        n_shots=task.run_parameters["shots"].get_value(),
        shot_interval=task.run_parameters["interval"].get_value(),
        readout_amplitude=None,
        readout_duration=None,
        readout_pre_margin=None,
        readout_post_margin=None,
    )
    assert result.raw_result == {"ok": True}


def test_postprocess_returns_waveform_figure_when_result_has_plot() -> None:
    task = CheckWaveform()
    backend = _make_backend()
    waveform = MagicMock()
    figure = go.Figure()
    waveform.plot.return_value = figure
    raw_result = MagicMock()
    raw_result.data = {"Q00": waveform}

    result = task.postprocess(backend, "exec-1", RunResult(raw_result=raw_result), "0")

    assert result.output_parameters == {}
    assert result.figures == [figure]
    waveform.plot.assert_called_once_with(return_figure=True)
