"""Tests for the CheckCrossResonance and CreateZX90 CR controls.

The Qubex calls are mocked; the calibration note is the real Qubex ``CalibrationNote`` so
putting a rejected fit back and the freshness check run against its timestamp-ordered
merge.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock

import numpy as np
import plotly.graph_objects as go
import pytest
from qubex.experiment.models.calibration_note import CalibrationNote

from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.qubex.two_qubit.check_cross_resonance import (
    CheckCrossResonance,
)
from qdash.workflow.calibtasks.qubex.two_qubit.cr_controls import NOTE_TIMESTAMP_FORMAT
from qdash.workflow.calibtasks.qubex.two_qubit.create_zx90 import CreateZX90

if TYPE_CHECKING:
    from pathlib import Path

    from qdash.workflow.calibtasks.results import PostProcessResult
    from qdash.workflow.engine.backend.qubex import QubexBackend

LABEL = "Q00-Q01"


def _note_time(delta: timedelta) -> str:
    return (datetime.now() + delta).strftime(NOTE_TIMESTAMP_FORMAT)


# calc_control_amplitude(rabi_rate) = 10 * rabi_rate and |f_c - f_t| = 0.1 GHz, so the
# adiabatic cap equals the safety factor (0.75 for the default factor).
FREQUENCIES = {"Q00": 8.0, "Q01": 8.1}

PRIOR_ENTRY = {
    "target": LABEL,
    "duration": 176.0,
    "ramptime": 16.0,
    "cr_amplitude": 0.3,
    "cr_phase": 0.1,
    "cr_beta": 0.01,
    "cancel_amplitude": 0.02,
    "cancel_phase": 0.2,
    "cancel_beta": 0.0,
    "rotary_amplitude": 0.05,
    "zx_rotation_rate": 0.004,
    "timestamp": _note_time(-timedelta(days=3)),
}

ZX90_INPUTS = {
    "cr_duration": 176.0,
    "cr_ramptime": 16.0,
    "cr_amplitude": 0.3,
    "cr_phase": 0.1,
    "cr_beta": 0.01,
    "cancel_amplitude": 0.02,
    "cancel_phase": 0.2,
    "cancel_beta": 0.0,
    "rotary_amplitude": 0.05,
    "zx_rotation_rate": 0.004,
}


def _note(tmp_path: Path, entry: dict[str, Any] = PRIOR_ENTRY) -> Any:
    note: Any = CalibrationNote("test-chip", file_path=tmp_path / "note.json")
    note.update_cr_param(LABEL, dict(entry))
    return note


def _backend(exp: object) -> QubexBackend:
    return cast("QubexBackend", SimpleNamespace(get_instance=lambda: exp))


# ---------------------------------------------------------------------------
# CreateZX90
# ---------------------------------------------------------------------------


class FakeZX90Qubex:
    """Callable standing in for Qubex ``calibrate_zx90`` with scripted outcomes."""

    def __init__(self, note: Any, outcomes: list[dict[str, Any]]) -> None:
        self.note = note
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, control: str, target: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if "raise" in outcome:
            self.note.update_cr_param(LABEL, {"cr_amplitude": 0.99})
            raise outcome["raise"]
        amplitude_range = kwargs.get("amplitude_range")
        scanned = (
            np.asarray(amplitude_range, dtype=float)
            if amplitude_range is not None
            else np.linspace(0.2, 0.4, 50)
        )
        root = outcome.get("root", math.nan)
        if kwargs.get("store_params", True):
            # Qubex stores 1.0 when the final fit has no root.
            stored = outcome.get("stored_amplitude", 1.0 if math.isnan(root) else root)
            self.note.update_cr_param(
                LABEL,
                {
                    "target": LABEL,
                    "duration": outcome.get("duration", kwargs.get("duration", 176.0)),
                    "ramptime": kwargs.get("ramptime", 16.0),
                    "cr_amplitude": stored,
                    "cr_phase": 0.1,
                    "cr_beta": -0.002,
                    "cancel_amplitude": 0.02 * stored / 0.3,
                    "cancel_phase": 0.2,
                    "cancel_beta": 0.0,
                    "rotary_amplitude": 0.06,
                    "zx_rotation_rate": 0.004,
                },
            )
        result = {
            "amplitude_range": scanned,
            "root": root,
            "fig": go.Figure(),
            "n1": {"root": outcome.get("n1_root", root), "fig": go.Figure()},
            "n3": {"root": root, "fig": go.Figure()},
        }
        if outcome.get("no_root_key"):
            del result["root"]
        return result


def _zx90_exp(note: Any, calibrate: Any) -> SimpleNamespace:
    return SimpleNamespace(
        drag_pi_pulse={"Q00": object()},
        get_qubit_label=lambda qid: f"Q0{qid}",
        calibrate_zx90=calibrate,
        calib_note=note,
        qubits={label: SimpleNamespace(frequency=f) for label, f in FREQUENCIES.items()},
        calc_control_amplitude=lambda _qubit, rabi_rate: 10 * rabi_rate,
        zx90=MagicMock(return_value=SimpleNamespace(duration=400.0)),
    )


def _zx90_task(
    run: dict[str, Any] | None = None, inputs: dict[str, Any] | None = None
) -> CreateZX90:
    task = CreateZX90()
    for name, value in {**ZX90_INPUTS, **(inputs or {})}.items():
        task.input_parameters[name] = InputParameterModel(value=value)
    for name, value in (run or {}).items():
        task.run_parameters[name].value = value
    return task


def _run_task(
    task: CreateZX90 | CheckCrossResonance,
    exp: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[PostProcessResult, MagicMock]:
    """Run ``run`` and ``postprocess`` as TaskExecutor does after ``prepare_run``."""
    save = MagicMock()
    monkeypatch.setattr(task, "save_calibration", save)
    backend = _backend(exp)
    run_result = task.run(backend, "0-1")
    return task.postprocess(backend, "exec", run_result, "0-1"), save


def test_zx90_default_forwards_input_ramptime_and_default_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    note = _note(tmp_path)
    calibrate = FakeZX90Qubex(note, [{"root": 0.31}])
    post, save = _run_task(_zx90_task(), _zx90_exp(note, calibrate), monkeypatch)

    (kwargs,) = calibrate.calls
    assert kwargs["ramptime"] == 16.0
    assert kwargs["adiabatic_safe_factor"] == 0.75
    assert kwargs["max_amplitude"] == 1.0
    assert kwargs["store_params"] is True
    for name in ("duration", "amplitude_range", "rotary_multiple", "duration_buffer"):
        assert name not in kwargs
    assert post.validation_error is None
    assert post.output_parameters["cr_amplitude"].value == pytest.approx(0.31)
    save.assert_called_once()


def test_zx90_run_parameters_override_inputs_and_forward(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    note = _note(tmp_path)
    calibrate = FakeZX90Qubex(note, [{"root": 0.31}])
    task = _zx90_task(run={"ramptime": 24.0, "rotary_multiple": 7.0, "duration_buffer": 1.1})
    post, _ = _run_task(task, _zx90_exp(note, calibrate), monkeypatch)

    kwargs = calibrate.calls[0]
    assert kwargs["ramptime"] == 24.0
    assert kwargs["rotary_multiple"] == 7.0
    assert kwargs["duration_buffer"] == 1.1
    assert post.validation_error is None


def test_zx90_inherits_check_cr_bounds_and_accepts_tighter_run_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inherited = {"cr_max_amplitude": 0.6, "cr_adiabatic_safe_factor": 0.5}
    calls = []
    for run in ({}, {"max_amplitude": 0.4}):
        note = _note(tmp_path)
        calibrate = FakeZX90Qubex(note, [{"root": 0.31}])
        task = _zx90_task(run=run, inputs=inherited)
        post, _ = _run_task(task, _zx90_exp(note, calibrate), monkeypatch)
        assert post.validation_error is None
        calls.append(calibrate.calls[0])

    assert calls[0]["max_amplitude"] == 0.6
    assert calls[0]["adiabatic_safe_factor"] == 0.5
    assert calls[1]["max_amplitude"] == 0.4


@pytest.mark.parametrize(
    ("run", "inputs", "message"),
    [
        ({"max_amplitude": 0.7}, {"cr_max_amplitude": 0.6}, "looser than the approved"),
        ({"adiabatic_safe_factor": 0.9}, {"cr_adiabatic_safe_factor": 0.5}, "looser"),
        ({"ramptime": math.nan}, {}, "ramptime must be finite"),
        ({"ramptime": 0.0}, {}, "ramptime must be positive"),
        ({}, {"cr_ramptime": -4.0}, "input cr_ramptime must be positive"),
        ({"duration": 30.0}, {}, "at least 2 \\* ramptime"),
        ({}, {"cr_duration": 24.0}, "at least 2 \\* ramptime"),
        ({"duration": -1.0}, {}, "duration must be positive"),
        ({"adiabatic_safe_factor": 1.5}, {}, "adiabatic_safe_factor must be in"),
        ({"max_amplitude": 0.0}, {}, "max_amplitude must be in"),
        ({"amplitude_range": [0.3, 0.2, 10]}, {}, "0 <= start < stop"),
        ({"amplitude_range": [0.1, 0.3, 2]}, {}, "num must be an integer"),
        ({"amplitude_range": [0.1, 0.8, 10]}, {}, "exceeds the approved CR amplitude cap"),
        ({"rotary_multiple": 0.0}, {}, "rotary_multiple must be positive"),
        ({"duration_buffer": 0.5}, {}, "duration_buffer must be at least 1"),
    ],
)
def test_zx90_validates_controls_before_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run: dict[str, Any],
    inputs: dict[str, Any],
    message: str,
) -> None:
    note = _note(tmp_path)
    calibrate = FakeZX90Qubex(note, [])
    with pytest.raises(ValueError, match=message):
        _run_task(_zx90_task(run=run, inputs=inputs), _zx90_exp(note, calibrate), monkeypatch)
    assert calibrate.calls == []
    assert note.get_cr_param(LABEL) == PRIOR_ENTRY


def test_zx90_input_duration_zero_lets_qubex_derive_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    note = _note(tmp_path)
    calibrate = FakeZX90Qubex(note, [{"root": 0.31}])
    post, _ = _run_task(
        _zx90_task(inputs={"cr_duration": 0.0}), _zx90_exp(note, calibrate), monkeypatch
    )
    assert "duration" not in calibrate.calls[0]
    assert post.validation_error is None


def test_zx90_fixed_duration_scans_only_at_that_duration_within_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    note = _note(tmp_path)
    calibrate = FakeZX90Qubex(note, [{"n1_root": 0.5}, {"root": 0.55}])
    task = _zx90_task(run={"duration": 208.0, "max_amplitude": 0.58})
    post, save = _run_task(task, _zx90_exp(note, calibrate), monkeypatch)

    rough, final = calibrate.calls
    assert rough["duration"] == final["duration"] == 208.0
    assert rough["store_params"] is False
    # Rough stop is min(2 * input cr_amplitude, cap) = min(0.6, 0.58).
    assert rough["amplitude_range"][-1] == pytest.approx(0.58)
    # Fine scan is 0.8x to 1.2x the rough root, capped at 0.58.
    assert final["amplitude_range"][0] == pytest.approx(0.4)
    assert final["amplitude_range"][-1] == pytest.approx(0.58)
    assert final["store_params"] is True
    assert post.validation_error is None
    assert post.output_parameters["cr_duration"].value == 208.0
    save.assert_called_once()


def test_zx90_fixed_duration_fails_without_lengthening_when_rough_has_no_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    note = _note(tmp_path)
    calibrate = FakeZX90Qubex(note, [{"n1_root": math.nan}])
    with pytest.raises(ValueError, match=r"fixed duration 208\.0 ns"):
        _run_task(_zx90_task(run={"duration": 208.0}), _zx90_exp(note, calibrate), monkeypatch)
    assert len(calibrate.calls) == 1
    assert note.get_cr_param(LABEL) == PRIOR_ENTRY


@pytest.mark.parametrize(
    ("run", "outcome", "message"),
    [
        ({}, {"root": math.nan}, "found no root"),
        ({}, {"root": 0.31, "stored_amplitude": 0.32}, "not the fitted root"),
        ({}, {"root": 0.45}, "outside the scanned range"),
        # The fake reports a 0.2-0.4 scan, as if Qubex had scanned past the cap.
        ({"max_amplitude": 0.35}, {"root": 0.38}, "exceeds the approved CR amplitude cap"),
        ({"amplitude_range": [0.2, 0.4, 10]}, {"root": 0.3, "duration": 192.0}, "duration"),
    ],
)
def test_zx90_rejected_fit_is_put_back_and_not_saved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run: dict[str, Any],
    outcome: dict[str, Any],
    message: str,
) -> None:
    note = _note(tmp_path)
    calibrate = FakeZX90Qubex(note, [outcome])
    if "duration" in outcome:
        run = {**run, "duration": 176.0}
    post, save = _run_task(_zx90_task(run=run), _zx90_exp(note, calibrate), monkeypatch)

    assert post.validation_error is not None
    assert message in post.validation_error
    save.assert_not_called()
    assert note.get_cr_param(LABEL) == PRIOR_ENTRY


def test_zx90_accepts_a_fitted_root_of_exactly_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    note = _note(tmp_path)
    calibrate = FakeZX90Qubex(note, [{"root": 1.0}])
    task = _zx90_task(run={"adiabatic_safe_factor": 1.0, "amplitude_range": [0.8, 1.0, 10]})
    post, save = _run_task(task, _zx90_exp(note, calibrate), monkeypatch)

    assert post.validation_error is None
    assert post.output_parameters["cr_amplitude"].value == 1.0
    save.assert_called_once()


@pytest.mark.parametrize(
    ("outcome", "error"),
    [
        ({"raise": RuntimeError("measurement failed")}, RuntimeError),
        ({"root": 0.31, "no_root_key": True}, RuntimeError),
    ],
)
def test_zx90_puts_the_entry_back_when_run_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: dict[str, Any],
    error: type[Exception],
) -> None:
    note = _note(tmp_path)
    calibrate = FakeZX90Qubex(note, [outcome])
    with pytest.raises(error):
        _run_task(_zx90_task(), _zx90_exp(note, calibrate), monkeypatch)
    assert note.get_cr_param(LABEL) == PRIOR_ENTRY


@pytest.mark.parametrize("delta", [timedelta(), timedelta(hours=1)])
def test_zx90_fails_when_qubex_drops_the_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delta: timedelta
) -> None:
    # A same-second or future-dated entry makes the Qubex merge drop the new result.
    incumbent = {**PRIOR_ENTRY, "timestamp": _note_time(delta)}
    note = _note(tmp_path, incumbent)
    calibrate = FakeZX90Qubex(note, [{"root": 0.31}])
    with pytest.raises(RuntimeError, match="did not store fresh CR parameters"):
        _run_task(_zx90_task(), _zx90_exp(note, calibrate), monkeypatch)
    assert note.get_cr_param(LABEL) == incumbent


# ---------------------------------------------------------------------------
# CheckCrossResonance
# ---------------------------------------------------------------------------


class _CRRaw(dict[str, Any]):
    data: dict[str, Any]


def _cr_exp(note: Any, *, fail: bool = False, cr_amplitude: float = 0.4) -> SimpleNamespace:
    raw = _CRRaw(coeffs_history={"IX": np.array([0.001])})
    raw.data = {"figs_history": [{"fig_c": go.Figure(), "fig_t": go.Figure()}]}

    def obtain(control: str, target: str, **kwargs: Any) -> Any:
        note.update_cr_param(
            LABEL,
            {
                "target": LABEL,
                "duration": 0.0,
                "ramptime": kwargs.get("ramptime", 16.0),
                "cr_amplitude": cr_amplitude,
                "cr_phase": 0.2,
                "cr_beta": 0.0,
                "cancel_amplitude": 0.03,
                "cancel_phase": 0.1,
                "cancel_beta": 0.0,
                "rotary_amplitude": 0.0,
                "zx_rotation_rate": 0.005,
            },
        )
        if fail:
            raise RuntimeError("tomography failed")
        return raw

    return SimpleNamespace(
        params=SimpleNamespace(readout_amplitude={}),
        drag_hpi_pulse={"Q00": object(), "Q01": object()},
        get_qubit_label=lambda qid: f"Q0{qid}",
        obtain_cr_params=MagicMock(side_effect=obtain),
        calib_note=note,
    )


def _cr_task(run: dict[str, Any] | None = None) -> CheckCrossResonance:
    task = CheckCrossResonance()
    for role in ("control", "target"):
        task.input_parameters[f"{role}_readout_amplitude"] = InputParameterModel(value=None)
    for name, value in (run or {}).items():
        task.run_parameters[name].value = value
    return task


@pytest.mark.parametrize("ramptime", [None, 24.0])
def test_check_cr_forwards_ramptime_only_when_set_and_publishes_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ramptime: float | None
) -> None:
    note = _note(tmp_path)
    exp = _cr_exp(note)
    task = _cr_task({"ramptime": ramptime, "max_amplitude": 0.6, "adiabatic_safe_factor": 0.5})
    post, save = _run_task(task, exp, monkeypatch)

    kwargs = exp.obtain_cr_params.call_args.kwargs
    assert kwargs.get("ramptime") == ramptime
    assert ("ramptime" in kwargs) is (ramptime is not None)
    assert kwargs["max_amplitude"] == 0.6
    assert post.validation_error is None
    assert post.output_parameters["cr_max_amplitude"].value == 0.6
    assert post.output_parameters["cr_adiabatic_safe_factor"].value == 0.5
    save.assert_called_once()


@pytest.mark.parametrize(
    "run",
    [
        {"ramptime": math.inf},
        {"ramptime": -1.0},
        {"max_amplitude": 1.2},
        {"adiabatic_safe_factor": 0.0},
    ],
)
def test_check_cr_validates_controls_before_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: dict[str, Any]
) -> None:
    note = _note(tmp_path)
    exp = _cr_exp(note)
    with pytest.raises(ValueError):
        _run_task(_cr_task(run), exp, monkeypatch)
    exp.obtain_cr_params.assert_not_called()


def test_check_cr_puts_the_entry_back_when_qubex_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    note = _note(tmp_path)
    with pytest.raises(RuntimeError, match="tomography failed"):
        _run_task(_cr_task(), _cr_exp(note, fail=True), monkeypatch)
    assert note.get_cr_param(LABEL) == PRIOR_ENTRY


def test_check_cr_rejected_result_is_put_back_and_not_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    note = _note(tmp_path)
    post, save = _run_task(_cr_task(), _cr_exp(note, cr_amplitude=math.nan), monkeypatch)
    assert post.validation_error is not None
    save.assert_not_called()
    assert note.get_cr_param(LABEL) == PRIOR_ENTRY


def test_check_cr_fails_when_qubex_drops_the_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    incumbent = {**PRIOR_ENTRY, "timestamp": _note_time(timedelta(hours=1))}
    note = _note(tmp_path, incumbent)
    with pytest.raises(RuntimeError, match="did not store fresh CR parameters"):
        _run_task(_cr_task(), _cr_exp(note), monkeypatch)
    assert note.get_cr_param(LABEL) == incumbent
