"""Tests that QDash passes available pulse arguments explicitly to Qubex."""

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock

import pytest

from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.qubex.benchmark.randomized_benchmarking import (
    RandomizedBenchmarking,
)
from qdash.workflow.calibtasks.qubex.benchmark.x90_interleaved_randomized_benchmarking import (
    X90InterleavedRandomizedBenchmarking,
)

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend


def _backend_for(exp: object) -> Any:
    return SimpleNamespace(get_instance=lambda: exp)


@pytest.mark.parametrize(
    ("task", "method_name"),
    [
        (RandomizedBenchmarking(), "randomized_benchmarking"),
        (X90InterleavedRandomizedBenchmarking(), "interleaved_randomized_benchmarking"),
    ],
)
def test_single_qubit_rb_passes_restored_x90_explicitly(
    task: RandomizedBenchmarking | X90InterleavedRandomizedBenchmarking,
    method_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waveform = object()
    result = {
        "Q01": {
            "r2": 0.99,
            "rb_fit_result": {"r2": 0.99},
        }
    }
    method = MagicMock(return_value=result)
    exp = SimpleNamespace(
        params=SimpleNamespace(readout_amplitude={}),
        drag_hpi_pulse={"Q01": waveform},
        get_qubit_label=lambda _qid: "Q01",
        **{method_name: method},
    )
    task.input_parameters["readout_amplitude"] = InputParameterModel(value=0.2)
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)

    task.run(cast("QubexBackend", _backend_for(exp)), "1")

    kwargs = method.call_args.kwargs
    assert kwargs["x90"] == {"Q01": waveform}
    if method_name == "interleaved_randomized_benchmarking":
        assert kwargs["interleaved_waveform"] == {"Q01": waveform}
