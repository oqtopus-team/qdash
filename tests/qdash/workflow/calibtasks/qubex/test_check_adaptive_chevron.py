from contextlib import nullcontext
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import plotly.graph_objects as go
import pytest

from qdash.datamodel.task import InputParameterModel as ParameterModel
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_adaptive_chevron import (
    DEFAULT_MINIMUM_PEAK_BACKGROUND_RMS_RATIO,
    CheckAdaptiveChevron,
)

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend
else:
    QubexBackend = Any


def test_adaptive_chevron_uses_operational_frequency_with_legacy_fallback() -> None:
    frequency_spec = CheckAdaptiveChevron.input_spec["control_frequency"]

    assert frequency_spec.fallback_parameter_names == ("coarse_qubit_frequency",)


def test_chevron_control_amplitude_requires_database_value() -> None:
    spec = CheckAdaptiveChevron.input_spec["coarse_control_amplitude"]

    assert spec.resolution == "database_required"
    assert spec.default is None


@pytest.mark.parametrize("value", [1e-4, 0.07, 1.0])
def test_chevron_control_amplitude_accepts_inclusive_bounds(value: float) -> None:
    CheckAdaptiveChevron.input_spec["coarse_control_amplitude"].validate_effective_value(
        "coarse_control_amplitude", value
    )


@pytest.mark.parametrize(
    "value", [0.000099, 1.000001, float("nan"), float("inf"), None, True, "0.5"]
)
def test_chevron_control_amplitude_rejects_invalid_values(value: Any) -> None:
    with pytest.raises(ValueError, match="coarse_control_amplitude"):
        CheckAdaptiveChevron.input_spec["coarse_control_amplitude"].validate_effective_value(
            "coarse_control_amplitude", value
        )


class _DummyExperiment:
    def __init__(self) -> None:
        self.params = SimpleNamespace(readout_amplitude={"Q00": 0.0})
        self.modified_frequency_calls: list[dict[str, float]] = []

    def get_qubit_label(self, qid: int) -> str:
        assert qid == 0
        return "Q00"

    def modified_frequencies(self, frequencies: dict[str, float]):
        self.modified_frequency_calls.append(frequencies)
        return nullcontext()


def test_check_chevron_run_uses_adaptive_helper(monkeypatch) -> None:
    task = CheckAdaptiveChevron()
    task.input_parameters["control_frequency"] = ParameterModel(value=4.25, unit="GHz")
    task.input_parameters["readout_frequency"] = ParameterModel(value=6.1, unit="GHz")
    task.input_parameters["readout_amplitude"] = ParameterModel(value=0.031, unit="a.u.")
    task.input_parameters["coarse_control_amplitude"] = ParameterModel(value=0.07, unit="a.u.")

    exp = _DummyExperiment()
    captured: dict[str, object] = {}

    def fake_get_experiment(_backend):
        return exp

    def fake_save_calibration(_backend):
        return None

    def fake_estimate_qubit_frequency_from_chevron_adaptive(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            data={
                "resonant_frequencies": {"Q00": 4.321},
                "target_amplitudes": {"Q00": 0.086},
                "peak_background_rms_ratios": {"Q00": 8.5},
                "results": {
                    "Q00": {
                        "omega_q": 4.321,
                        "omega_rabi": 0.011,
                        "peak_background_rms_ratio": 8.5,
                        "frequency_used": 4.25,
                        "amplitude_used": 0.082,
                    }
                },
                "search_results": {
                    "Q00": {
                        "omega_q": 4.3,
                        "omega_rabi": 0.0105,
                        "peak_background_rms_ratio": 7.0,
                        "frequency_used": 4.25,
                        "amplitude_used": 0.07,
                    }
                },
            },
            figures={
                "Q00_search_measurement": go.Figure(),
                "Q00_search_transform": go.Figure(),
                "Q00_measurement": go.Figure(),
                "Q00_transform": go.Figure(),
            },
        )

    monkeypatch.setattr(task, "get_experiment", fake_get_experiment)
    monkeypatch.setattr(task, "save_calibration", fake_save_calibration)
    monkeypatch.setattr(
        "qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_adaptive_chevron."
        "estimate_qubit_frequency_from_chevron_adaptive",
        fake_estimate_qubit_frequency_from_chevron_adaptive,
    )

    result = task.run(backend=cast("QubexBackend", object()), qid="0")

    assert captured["exp"] is exp
    assert captured["targets"] == ["Q00"]
    assert captured["frequencies"] == {"Q00": 4.25}
    assert captured["amplitudes"] == {"Q00": 0.07}
    assert captured["n_shots"] == 256
    assert captured["shot_interval"] == 153600.0
    assert "peak_background_rms_threshold" not in captured
    assert exp.modified_frequency_calls == [{"Q00": 4.25, "RQ00": 6.1}]
    assert captured["plot"] is False
    assert captured["save_image"] is False
    assert result.raw_result["resonant_frequencies"]["Q00"] == 4.321
    assert result.raw_result["target_amplitudes"]["Q00"] == 0.086
    assert "control_amplitude_used" not in result.raw_result
    assert result.raw_result["readout_amplitude_used"] == 0.031


def test_check_chevron_postprocess_handles_adaptive_search_figures(monkeypatch) -> None:
    task = CheckAdaptiveChevron()
    task.input_parameters["readout_amplitude"] = ParameterModel(value=0.031, unit="a.u.")

    monkeypatch.setattr(task, "get_experiment", lambda _backend: object())
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")

    run_result = RunResult(
        raw_result={
            "resonant_frequencies": {"Q00": 4.321},
            "peak_background_rms_ratios": {"Q00": 8.5},
            "target_amplitudes": {"Q00": 0.086},
            "readout_amplitude_used": 0.031,
            "figures": {
                "Q00_measurement": go.Figure(),
                "Q00_transform": go.Figure(),
                "Q00_search_measurement": go.Figure(),
                "Q00_search_transform": go.Figure(),
            },
        }
    )

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=run_result,
        qid="0",
    )

    assert result.output_parameters["qubit_frequency"].value == 4.321
    assert result.output_parameters["control_amplitude"].value == 0.086
    assert "readout_amplitude" not in result.output_parameters
    assert len(result.figures) == 5
    assert result.validation_error is None


@pytest.mark.parametrize(
    ("ratios", "expected_error"),
    [
        ({"Q00": 4.99}, "peak/background RMS ratio for Q00 is below minimum 5.0"),
        ({}, "peak/background RMS ratio for Q00 is missing"),
        ({"Q00": float("nan")}, "peak/background RMS ratio for Q00 is non-finite"),
        ({"Q00": "invalid"}, "peak/background RMS ratio for Q00 is not numeric"),
    ],
)
def test_check_chevron_postprocess_rejects_invalid_peak_background_rms_ratio(
    monkeypatch: pytest.MonkeyPatch,
    ratios: dict[str, object],
    expected_error: str,
) -> None:
    task = CheckAdaptiveChevron()
    monkeypatch.setattr(task, "get_experiment", lambda _backend: object())
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(
            raw_result={
                "resonant_frequencies": {"Q00": 4.321},
                "peak_background_rms_ratios": ratios,
                "target_amplitudes": {"Q00": 0.086},
            }
        ),
        qid="0",
    )

    assert result.validation_error is not None
    assert expected_error in result.validation_error


def test_check_chevron_postprocess_accepts_peak_background_rms_ratio_at_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = CheckAdaptiveChevron()
    monkeypatch.setattr(task, "get_experiment", lambda _backend: object())
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(
            raw_result={
                "resonant_frequencies": {"Q00": 4.321},
                "peak_background_rms_ratios": {"Q00": DEFAULT_MINIMUM_PEAK_BACKGROUND_RMS_RATIO},
                "target_amplitudes": {"Q00": 0.086},
            }
        ),
        qid="0",
    )

    assert result.validation_error is None


def test_check_chevron_postprocess_uses_configured_peak_background_rms_ratio_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = CheckAdaptiveChevron()
    task.run_parameters["minimum_peak_background_rms_ratio"].value = 8.0
    monkeypatch.setattr(task, "get_experiment", lambda _backend: object())
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(
            raw_result={
                "resonant_frequencies": {"Q00": 4.321},
                "peak_background_rms_ratios": {"Q00": 7.9},
                "target_amplitudes": {"Q00": 0.086},
            }
        ),
        qid="0",
    )

    assert result.validation_error is not None
    assert "below minimum 8.0" in result.validation_error


@pytest.mark.parametrize("threshold", [-0.1, float("nan"), float("inf"), "invalid"])
def test_check_chevron_postprocess_rejects_invalid_peak_background_rms_ratio_threshold(
    monkeypatch: pytest.MonkeyPatch,
    threshold: object,
) -> None:
    task = CheckAdaptiveChevron()
    task.run_parameters["minimum_peak_background_rms_ratio"].value = cast("Any", threshold)
    monkeypatch.setattr(task, "get_experiment", lambda _backend: object())
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(
            raw_result={
                "resonant_frequencies": {"Q00": 4.321},
                "peak_background_rms_ratios": {"Q00": 8.5},
                "target_amplitudes": {"Q00": 0.086},
            }
        ),
        qid="0",
    )

    assert result.validation_error is not None
    assert "minimum_peak_background_rms_ratio" in result.validation_error


@pytest.mark.parametrize("target_amplitudes", [{}, {"Q00": float("nan")}, {"Q00": "invalid"}])
def test_check_chevron_postprocess_rejects_invalid_target_control_amplitude(
    monkeypatch: pytest.MonkeyPatch,
    target_amplitudes: dict[str, object],
) -> None:
    task = CheckAdaptiveChevron()
    monkeypatch.setattr(task, "get_experiment", lambda _backend: object())
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(
            raw_result={
                "resonant_frequencies": {"Q00": 4.321},
                "peak_background_rms_ratios": {"Q00": 8.5},
                "target_amplitudes": target_amplitudes,
            }
        ),
        qid="0",
    )

    assert result.output_parameters["control_amplitude"].value is None
    assert result.validation_error is not None
    assert "target control amplitude for Q00" in result.validation_error


def test_check_chevron_run_requires_db_readout_amplitude(monkeypatch) -> None:
    task = CheckAdaptiveChevron()
    task.input_parameters["control_frequency"] = ParameterModel(value=4.25, unit="GHz")
    task.input_parameters["readout_frequency"] = ParameterModel(value=6.1, unit="GHz")
    task.input_parameters["readout_amplitude"] = ParameterModel(value=None)

    monkeypatch.setattr(task, "get_experiment", lambda _backend: _DummyExperiment())

    with pytest.raises(ValueError, match="readout_amplitude input parameter is required"):
        task.run(backend=cast("QubexBackend", object()), qid="0")
