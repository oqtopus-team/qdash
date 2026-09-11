"""Tests that downstream tasks pass resolved pulse waveforms explicitly to Qubex."""

from contextlib import nullcontext
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock

import pytest

from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.qubex.benchmark.x180_interleaved_randoized_benchmarking import (
    X180InterleavedRandomizedBenchmarking,
)
from qdash.workflow.calibtasks.qubex.benchmark.zx90_interleaved_randoized_benchmarking import (
    ZX90InterleavedRandomizedBenchmarking,
)
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_t2_echo import CheckT2Echo
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_t2_echo_average import (
    CheckT2EchoAverage,
)
from qdash.workflow.calibtasks.qubex.two_qubit.check_bell_state import CheckBellState
from qdash.workflow.calibtasks.qubex.two_qubit.check_bell_state_tomography import (
    CheckBellStateTomography,
)
from qdash.workflow.calibtasks.qubex.two_qubit.check_cross_resonance import (
    CheckCrossResonance,
)
from qdash.workflow.calibtasks.qubex.two_qubit.check_zx90 import CheckZX90
from qdash.workflow.calibtasks.qubex.two_qubit.create_zx90 import CreateZX90

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend


def _backend_for(exp: object) -> Any:
    return SimpleNamespace(get_instance=lambda: exp)


_ZX90_CR_KWARGS = {
    "cr_duration": 100.0,
    "cr_ramptime": 16.0,
    "cr_amplitude": 0.2,
    "cr_phase": 0.1,
    "cr_beta": 0.01,
    "cancel_amplitude": 0.02,
    "cancel_phase": 0.3,
    "cancel_beta": 0.04,
    "rotary_amplitude": 0.05,
}


def _set_zx90_cr_inputs(task: Any) -> None:
    for name, value in _ZX90_CR_KWARGS.items():
        task.input_parameters[name] = InputParameterModel(value=value)


def _assert_explicit_zx90_call(zx90: MagicMock, control_x180: object) -> None:
    kwargs = zx90.call_args.kwargs
    assert kwargs["x180"] == {"Q00": control_x180}
    assert {name: kwargs[name] for name in _ZX90_CR_KWARGS} == _ZX90_CR_KWARGS


@pytest.mark.parametrize("task_type", [CheckT2Echo, CheckT2EchoAverage])
def test_t2_echo_passes_resolved_pi_pulse_as_cpmg(
    task_type: type[CheckT2Echo] | type[CheckT2EchoAverage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = task_type()
    pi = MagicMock()
    pi_y180 = object()
    pi.shifted.return_value = pi_y180
    datum = SimpleNamespace(t2=10.0, t2_err=0.1, r2=0.99)
    t2_experiment = MagicMock(return_value=SimpleNamespace(data={"Q01": datum}))
    exp = SimpleNamespace(
        params=SimpleNamespace(readout_amplitude={}),
        pi_pulse={"Q01": pi},
        get_qubit_label=lambda _qid: "Q01",
        t2_experiment=t2_experiment,
    )
    task.input_parameters["readout_amplitude"] = InputParameterModel(value=0.2)
    if isinstance(task, CheckT2EchoAverage):
        task.run_parameters["n_runs"].value = 1
    monkeypatch.setattr(task, "_apply_frequency_override", lambda *_args: nullcontext())
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)

    task.run(cast("QubexBackend", _backend_for(exp)), "1")

    assert task_type.input_spec["pi_amplitude"].resolution == "database_required"
    assert task_type.input_spec["pi_duration"].resolution == "database_required"
    pi.shifted.assert_called_once_with(pytest.approx(1.5707963267948966))
    assert t2_experiment.call_args.kwargs["pi_cpmg"] is pi_y180


def test_x180_irb_passes_resolved_x90_and_x180_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = X180InterleavedRandomizedBenchmarking()
    x90 = object()
    x180 = object()
    interleaved_rb = MagicMock(return_value={"Q01": {"rb_fit_result": {"r2": 0.99}}})
    exp = SimpleNamespace(
        params=SimpleNamespace(readout_amplitude={}),
        drag_hpi_pulse={"Q01": x90},
        drag_pi_pulse={"Q01": x180},
        get_qubit_label=lambda _qid: "Q01",
        interleaved_randomized_benchmarking=interleaved_rb,
    )
    task.input_parameters["readout_amplitude"] = InputParameterModel(value=0.2)
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)

    task.run(cast("QubexBackend", _backend_for(exp)), "1")

    kwargs = interleaved_rb.call_args.kwargs
    assert kwargs["x90"] == {"Q01": x90}
    assert kwargs["interleaved_waveform"] == {"Q01": x180}
    assert {
        "drag_hpi_amplitude",
        "drag_hpi_duration",
        "drag_hpi_beta",
        "drag_pi_amplitude",
        "drag_pi_duration",
        "drag_pi_beta",
    } <= task.input_spec.keys()


def test_check_cross_resonance_passes_control_and_target_x90_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = CheckCrossResonance()
    control_x90 = object()
    target_x90 = object()
    raw_result = MagicMock()
    raw_result.data = {"figs_history": []}
    raw_result.__getitem__.side_effect = {"coeffs_history": []}.__getitem__
    obtain_cr_params = MagicMock(return_value=raw_result)
    cr_params = {
        "duration": 100.0,
        "cr_amplitude": 0.2,
        "cr_phase": 0.1,
        "cr_beta": 0.0,
        "cancel_amplitude": 0.01,
        "cancel_phase": 0.0,
        "cancel_beta": 0.0,
        "rotary_amplitude": 0.02,
        "zx_rotation_rate": 0.003,
        "ramptime": 16.0,
    }
    exp = SimpleNamespace(
        drag_hpi_pulse={"Q00": control_x90, "Q01": target_x90},
        get_qubit_label=lambda qid: f"Q0{qid}",
        obtain_cr_params=obtain_cr_params,
        calib_note=SimpleNamespace(get_cr_param=lambda _label: cr_params),
    )
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)

    task.run(cast("QubexBackend", _backend_for(exp)), "0-1")

    assert obtain_cr_params.call_args.kwargs["x90"] == {
        "Q00": control_x90,
        "Q01": target_x90,
    }
    for role in ("control", "target"):
        assert task.input_spec[f"{role}_drag_hpi_duration"].resolution == "database_required"


def test_create_zx90_uses_calibrated_cr_values_and_resolved_control_x180(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = CreateZX90()
    _set_zx90_cr_inputs(task)
    control_x180 = object()
    calibrate_zx90 = MagicMock(
        return_value={
            "n1": {"fig": object()},
            "n3": {"fig": object()},
            "fig": object(),
        }
    )
    cr_params = {
        "duration": 128.0,
        "cr_amplitude": 0.27,
        "cr_phase": 0.12,
        "cr_beta": 0.013,
        "cancel_amplitude": 0.031,
        "cancel_phase": 0.4,
        "cancel_beta": 0.05,
        "rotary_amplitude": 0.06,
        "zx_rotation_rate": 0.004,
        "ramptime": 24.0,
    }
    zx90 = MagicMock(return_value=SimpleNamespace(duration=120.0))
    exp = SimpleNamespace(
        drag_pi_pulse={"Q00": control_x180},
        get_qubit_label=lambda qid: f"Q0{qid}",
        calibrate_zx90=calibrate_zx90,
        calib_note=SimpleNamespace(get_cr_param=lambda _label: cr_params),
        zx90=zx90,
    )
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)

    task.run(cast("QubexBackend", _backend_for(exp)), "0-1")

    assert calibrate_zx90.call_args.kwargs["x180"] == {"Q00": control_x180}
    assert zx90.call_args.kwargs == {
        "control_qubit": "Q00",
        "target_qubit": "Q01",
        "x180": {"Q00": control_x180},
        "cr_duration": 128.0,
        "cr_ramptime": 24.0,
        "cr_amplitude": 0.27,
        "cr_phase": 0.12,
        "cr_beta": 0.013,
        "cancel_amplitude": 0.031,
        "cancel_phase": 0.4,
        "cancel_beta": 0.05,
        "rotary_amplitude": 0.06,
    }
    assert {
        "control_drag_pi_amplitude",
        "control_drag_pi_duration",
        "control_drag_pi_beta",
    } <= task.input_spec.keys()


def _assert_control_drag_pi_inputs(task: Any) -> None:
    assert {
        "control_drag_pi_amplitude",
        "control_drag_pi_duration",
        "control_drag_pi_beta",
    } <= task.input_spec.keys()


def _assert_target_drag_hpi_inputs(task: Any) -> None:
    assert {
        "target_drag_hpi_amplitude",
        "target_drag_hpi_duration",
        "target_drag_hpi_beta",
    } <= task.input_spec.keys()


def test_check_zx90_builds_pulse_with_resolved_control_x180(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = CheckZX90()
    _set_zx90_cr_inputs(task)
    control_x180 = object()
    zx90_pulse = object()
    zx90 = MagicMock(return_value=zx90_pulse)
    repeat_sequence = MagicMock(return_value=object())
    exp = SimpleNamespace(
        drag_pi_pulse={"Q00": control_x180},
        get_qubit_label=lambda qid: f"Q0{qid}",
        zx90=zx90,
        repeat_sequence=repeat_sequence,
    )
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)

    task.run(cast("QubexBackend", _backend_for(exp)), "0-1")

    _assert_explicit_zx90_call(zx90, control_x180)
    assert repeat_sequence.call_args.kwargs["sequence"] is zx90_pulse
    _assert_control_drag_pi_inputs(task)


@pytest.mark.parametrize(
    ("task_type", "method_name"),
    [
        (CheckBellState, "measure_bell_state"),
        (CheckBellStateTomography, "bell_state_tomography"),
    ],
)
def test_bell_tasks_pass_explicit_zx90_built_with_resolved_x180(
    task_type: type[CheckBellState] | type[CheckBellStateTomography],
    method_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = task_type()
    control_x180 = object()
    _set_zx90_cr_inputs(task)
    zx90_pulse = object()
    zx90 = MagicMock(return_value=zx90_pulse)
    method = MagicMock(return_value={})
    exp = SimpleNamespace(
        drag_pi_pulse={"Q00": control_x180},
        get_qubit_label=lambda qid: f"Q0{qid}",
        zx90=zx90,
        **{method_name: method},
    )
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)

    task.run(cast("QubexBackend", _backend_for(exp)), "0-1")

    _assert_explicit_zx90_call(zx90, control_x180)
    assert method.call_args.kwargs["zx90"] is zx90_pulse
    _assert_control_drag_pi_inputs(task)
    _assert_target_drag_hpi_inputs(task)


def test_zx90_irb_passes_explicit_zx90_built_with_resolved_x180(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ZX90InterleavedRandomizedBenchmarking()
    _set_zx90_cr_inputs(task)
    control_x90 = object()
    target_x90 = object()
    control_x180 = object()
    zx90_pulse = object()
    zx90 = MagicMock(return_value=zx90_pulse)
    interleaved_rb = MagicMock(return_value={"Q00-Q01": {"rb_fit_result": {"r2": 0.99}}})
    exp = SimpleNamespace(
        drag_hpi_pulse={"Q00": control_x90, "Q01": target_x90},
        drag_pi_pulse={"Q00": control_x180},
        get_qubit_label=lambda qid: f"Q0{qid}",
        zx90=zx90,
        interleaved_randomized_benchmarking=interleaved_rb,
    )
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)

    task.run(cast("QubexBackend", _backend_for(exp)), "0-1")

    expected = {"Q00-Q01": zx90_pulse}
    _assert_explicit_zx90_call(zx90, control_x180)
    assert interleaved_rb.call_args.kwargs["zx90"] == expected
    assert interleaved_rb.call_args.kwargs["interleaved_waveform"] == expected
    assert interleaved_rb.call_args.kwargs["x90"] == {
        "Q00": control_x90,
        "Q01": target_x90,
    }
    _assert_control_drag_pi_inputs(task)
    _assert_target_drag_hpi_inputs(task)
