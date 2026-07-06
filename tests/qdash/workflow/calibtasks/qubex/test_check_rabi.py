import math
from types import SimpleNamespace

import plotly.graph_objects as go
import pytest

import qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_rabi as check_rabi_module
from qdash.datamodel.task import ParameterModel
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_rabi import CheckRabi
from qdash.workflow.engine.task.result_processor import R2ValidationError, TaskResultProcessor


def test_check_rabi_uses_r2_threshold_0_6() -> None:
    task = CheckRabi()
    processor = TaskResultProcessor()

    assert task.r2_threshold == 0.6
    assert processor.validate_r2({"0": 0.61}, "0", task.r2_threshold) is True
    with pytest.raises(R2ValidationError):
        processor.validate_r2({"0": 0.59}, "0", task.r2_threshold)


def test_check_rabi_run_uses_data_fit_r2_for_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    task = CheckRabi()
    task.input_parameters["qubit_frequency"] = ParameterModel(value=5.0, unit="GHz")
    task.input_parameters["control_amplitude"] = ParameterModel(value=0.01, unit="a.u.")
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)

    class DummyData:
        r2 = 0.127

    result = SimpleNamespace(
        data={"Q01": DummyData()},
        rabi_params={"Q01": SimpleNamespace(r2=0.95)},
    )
    exp = SimpleNamespace(
        params=SimpleNamespace(readout_amplitude={}),
        get_qubit_label=lambda _qid: "Q01",
        obtain_rabi_params=lambda **_kwargs: result,
    )
    backend = SimpleNamespace(get_instance=lambda: exp)

    run_result = task.run(backend, "1")

    assert run_result.r2 == {"1": 0.127}


def test_check_rabi_postprocess_marks_non_finite_frequency_failed_after_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = CheckRabi()
    task.input_parameters["control_amplitude"] = ParameterModel(value=0.0125, unit="a.u.")

    class DummyIQPlotter:
        def __init__(self, state_centers):
            self._widget = go.Figure()

        def update(self, data):
            return None

    class DummyData:
        data = {"iq": [0.0, 1.0]}

        def fit(self):
            return {
                "amplitude_err": 0.0,
                "frequency_err": 0.0,
                "phase_err": 0.0,
                "offset_err": 0.0,
                "fig": go.Figure(),
            }

    monkeypatch.setattr(check_rabi_module, "IQPlotter", DummyIQPlotter)
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q01")
    monkeypatch.setattr(
        task,
        "get_experiment",
        lambda _backend: SimpleNamespace(state_centers={}),
    )

    raw_result = SimpleNamespace(
        data={"Q01": DummyData()},
        rabi_params={
            "Q01": SimpleNamespace(
                amplitude=1.0,
                frequency=math.nan,
                phase=0.0,
                offset=0.0,
                angle=180.0,
                noise=0.0,
                distance=1.0,
                reference_phase=0.0,
            )
        },
    )

    result = task.postprocess(
        SimpleNamespace(),
        "exec-1",
        RunResult(raw_result=raw_result, r2={"1": 0.95}),
        "1",
    )

    assert result.figures
    assert result.raw_data
    assert result.validation_error == "CheckRabi produced non-finite frequency for Q01: nan"
