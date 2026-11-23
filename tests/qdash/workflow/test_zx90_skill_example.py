"""Code facts the ZX90 search skill (qdash-zx90-optimization) relies on.

The skill tells the model which run keys it searches and which CR controls it leaves unset,
that CreateZX90 inherits the CheckCR amplitude bounds and ramp time, that qubex clips every
CreateZX90 sweep to that cap, and that QDash rejects the amplitude 1.0 qubex stores when the
final fit finds no root. These tests pin those statements to the QDash tasks and to the
locked qubex implementation, so a change in either fails here before the skill misleads a
hardware run.

Tests named ``test_upstream_*`` exercise qubex ``CalibrationService.calibrate_zx90`` alone and
document upstream behavior. Tests named ``test_createzx90_*`` run the QDash ``CreateZX90`` task
on top of that same upstream code and pin the QDash wrapper contract.
"""

from __future__ import annotations

import copy
import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock

import numpy as np
import plotly.graph_objects as go
import pytest
from qubex.analysis import fitting
from qubex.experiment.experiment import Experiment
from qubex.experiment.models.calibration_note import CalibrationNote
from qubex.experiment.services.calibration_service import CalibrationService

from qdash.datamodel.calibration_pipeline import CalibrationPipelineSpec
from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.qubex.benchmark.zx90_interleaved_randoized_benchmarking import (
    ZX90InterleavedRandomizedBenchmarking,
)
from qdash.workflow.calibtasks.qubex.two_qubit.check_bell_state import CheckBellState
from qdash.workflow.calibtasks.qubex.two_qubit.check_bell_state_tomography import (
    CheckBellStateTomography,
)
from qdash.workflow.calibtasks.qubex.two_qubit.check_cross_resonance import CheckCrossResonance
from qdash.workflow.calibtasks.qubex.two_qubit.check_zx90 import CheckZX90
from qdash.workflow.calibtasks.qubex.two_qubit.cr_controls import NOTE_TIMESTAMP_FORMAT
from qdash.workflow.calibtasks.qubex.two_qubit.create_zx90 import CreateZX90

if TYPE_CHECKING:
    from qdash.workflow.calibtasks.results import PostProcessResult
    from qdash.workflow.engine.backend.qubex import QubexBackend

SKILL = (
    Path(__file__).resolve().parents[3]
    / "packages/pi-qdash/skills/qdash-zx90-optimization/SKILL.md"
)
TASKS = {
    task.name: task
    for task in (
        CheckCrossResonance,
        CreateZX90,
        CheckZX90,
        CheckBellState,
        CheckBellStateTomography,
        ZX90InterleavedRandomizedBenchmarking,
    )
}
SEARCH_KEYS = {"adiabatic_safe_factor", "max_amplitude", "max_time_range"}
# CR controls the skill names as existing but leaves unset during the search.
UNSEARCHED_CHECKCR_KEYS = {"ramptime"}
UNSEARCHED_CREATEZX90_KEYS = {
    "duration",
    "ramptime",
    "amplitude_range",
    "adiabatic_safe_factor",
    "max_amplitude",
    "rotary_multiple",
    "duration_buffer",
}
# Measurement settings; the skill lets a stage set only CreateZX90 shots.
CREATEZX90_MEASUREMENT_KEYS = {"readout_duration", "shots", "interval"}

LABEL = "Q00-Q01"
CONTROL, TARGET = LABEL.split("-")


def _example_specs() -> list[dict[str, Any]]:
    text = SKILL.read_text(encoding="utf-8")
    return [json.loads(block) for block in re.findall(r"```json\n(.*?)```", text, re.DOTALL)]


def test_example_spec_validates_and_changes_one_search_key() -> None:
    specs = _example_specs()
    assert specs, "the skill should show one runnable spec"
    for raw in specs:
        spec = CalibrationPipelineSpec.model_validate(raw)
        for step in spec.steps:
            calls = getattr(step, "tasks", None) or []
            names = [call.name for call in calls]
            # CreateZX90 reads this run's bounds and cr_duration = 0 only after CheckCR.
            assert names.index("CheckCrossResonance") < names.index("CreateZX90")
            for call in calls:
                assert call.input is None, "the search changes run conditions only"
                if call.run:
                    assert set(call.run) <= set(TASKS[call.name].run_spec), call
            checkcr = next(call for call in calls if call.name == "CheckCrossResonance")
            assert set(checkcr.run or {}) <= SEARCH_KEYS, "only search keys on CheckCR"
            assert len(set(checkcr.run or {})) == 1, "one key per experiment"
            createzx90 = next(call for call in calls if call.name == "CreateZX90")
            # Any bound or duration key would stop CreateZX90 inheriting the CheckCR run.
            assert set(createzx90.run or {}) <= {"shots"}, createzx90


def test_run_keys_match_the_skill_contract() -> None:
    assert set(CheckCrossResonance.run_spec) >= SEARCH_KEYS | UNSEARCHED_CHECKCR_KEYS
    assert "cr_amplitude" not in CheckCrossResonance.run_spec
    defaults = {key: CheckCrossResonance.run_spec[key].default for key in SEARCH_KEYS}
    assert defaults == {
        "adiabatic_safe_factor": 0.75,
        "max_amplitude": 1.0,
        "max_time_range": 4096,
    }
    # A new CreateZX90 key needs a skill review: searched, left unset, or a measurement setting.
    assert set(CreateZX90.run_spec) == UNSEARCHED_CREATEZX90_KEYS | CREATEZX90_MEASUREMENT_KEYS
    for key in UNSEARCHED_CREATEZX90_KEYS:
        assert CreateZX90.run_spec[key].default is None, f"unset {key} must keep inheriting"
    text = SKILL.read_text(encoding="utf-8")
    for key in UNSEARCHED_CREATEZX90_KEYS | UNSEARCHED_CHECKCR_KEYS:
        assert f"`{key}`" in text, f"the skill should name the {key} control"


def test_checkcr_publishes_the_bounds_createzx90_inherits() -> None:
    for name in ("cr_max_amplitude", "cr_adiabatic_safe_factor"):
        assert CheckCrossResonance.output_spec[name].qid_role == "coupling"
        assert CreateZX90.input_spec[name].parameter_name == name
        assert CreateZX90.input_spec[name].qid_role == "coupling"


# ---------------------------------------------------------------------------
# Upstream qubex calibrate_zx90, driven without hardware
# ---------------------------------------------------------------------------


def _note_time(delta: timedelta) -> str:
    return (datetime.now() + delta).strftime(NOTE_TIMESTAMP_FORMAT)


def _checkcr_entry(cr_amplitude: float, ramptime: float = 16.0) -> dict[str, Any]:
    """A CR note entry as CheckCR leaves it: cr_duration 0, dated before this run."""
    return {
        "target": LABEL,
        "duration": 0.0,
        "ramptime": ramptime,
        "cr_amplitude": cr_amplitude,
        "cr_phase": 0.1,
        "cr_beta": 0.0,
        "cancel_amplitude": 0.02,
        "cancel_phase": 0.2,
        "cancel_beta": 0.0,
        "rotary_amplitude": 0.0,
        "zx_rotation_rate": 0.01,
        "timestamp": _note_time(-timedelta(days=1)),
    }


class _UpstreamCalibration:
    """Just enough of CalibrationService for its real calibrate_zx90 to run without hardware.

    The calibration note is the real qubex ``CalibrationNote``. ``amp_per_ghz`` is the
    control amplitude per GHz of Rabi rate.
    """

    def __init__(self, note: Any, delta_ghz: float, amp_per_ghz: float) -> None:
        self.sweeps: list[np.ndarray] = []
        self.qubits = {
            CONTROL: SimpleNamespace(frequency=8.0),
            TARGET: SimpleNamespace(frequency=8.0 + delta_ghz),
        }
        self.amp_per_ghz = amp_per_ghz

        def calc_control_amplitude(target: str, rabi_rate: float) -> float:
            return amp_per_ghz * rabi_rate

        def sweep_parameter(_sequence: Any, *, sweep_range: Any, **_kwargs: Any) -> Any:
            sweep = np.asarray(sweep_range, dtype=float)
            self.sweeps.append(sweep)
            return SimpleNamespace(data={TARGET: SimpleNamespace(normalized=np.zeros(len(sweep)))})

        self.ctx = SimpleNamespace(qubits=self.qubits, calib_note=note)
        self.pulse = SimpleNamespace(
            calc_control_amplitude=calc_control_amplitude,
            x180=lambda _q: object(),
            zx90=lambda *_args, **_kwargs: SimpleNamespace(plot=lambda **_kw: None),
        )
        self.measurement_service = SimpleNamespace(sweep_parameter=sweep_parameter)

    def _ramptime(self, _control: str, _target: str) -> float:
        return 32.0

    def _adiabatic_safe_factor(self, control: str, target: str) -> float:
        return CalibrationService._adiabatic_safe_factor(cast("Any", self), control, target)

    def calc_zx90_coherence_limit(self, _control: str, _target: str) -> Any:
        raise KeyError("no coherence data")

    def calibrate_zx90(self, **kwargs: Any) -> Any:
        # Experiment.calibrate_zx90 passes the qubit labels as keywords.
        return CalibrationService.calibrate_zx90(cast("Any", self), **kwargs)


def _script_roots(monkeypatch: pytest.MonkeyPatch, roots: list[float]) -> None:
    """Make each qubex polynomial fit return the next root fraction of its swept range.

    A root is given as a fraction of the swept range (nan for no root), so it always lies in
    the range, as qubex's fit_polynomial guarantees.
    """
    pending = list(roots)

    def fit_polynomial(*, x: Any, **_kwargs: Any) -> dict[str, Any]:
        fraction = pending.pop(0) if pending else 0.5
        low, high = float(np.min(x)), float(np.max(x))
        root = float("nan") if np.isnan(fraction) else low + fraction * (high - low)
        return {"root": root, "fig": go.Figure()}

    # calibration_service calls fitting.fit_polynomial through this same module object.
    monkeypatch.setattr(fitting, "fit_polynomial", fit_polynomial)


def _upstream(
    tmp_path: Path, cr_amplitude: float, delta_ghz: float = 0.4, amp_per_ghz: float = 2.0
) -> _UpstreamCalibration:
    note: Any = CalibrationNote("test-chip", file_path=tmp_path / "note.json")
    note.update_cr_param(LABEL, _checkcr_entry(cr_amplitude))
    return _UpstreamCalibration(note, delta_ghz=delta_ghz, amp_per_ghz=amp_per_ghz)


def test_upstream_calibrate_zx90_clips_every_sweep_retry_included_to_the_passed_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Cap = min(max_amplitude, amp_per_ghz x factor x delta) = min(0.25, 2 x 0.75 x 0.4).
    fake = _upstream(tmp_path, cr_amplitude=0.2)
    # No rough root forces the duration retry; then a rough root near the top of its range.
    _script_roots(monkeypatch, [math.nan, 0.95, 0.5, 0.5, 0.9])
    CalibrationService.calibrate_zx90(
        cast("Any", fake), CONTROL, TARGET, max_amplitude=0.25, adiabatic_safe_factor=0.75
    )

    assert len(fake.sweeps) == 4, "rough, retried rough, n1, n3"
    for sweep in fake.sweeps:
        assert float(sweep.max()) <= 0.25 + 1e-12
    # Without the cap the rough scan would reach 2 x 0.2 = 0.4.
    assert float(fake.sweeps[0].max()) == pytest.approx(0.25)


def test_upstream_calibrate_zx90_stores_amplitude_one_when_the_final_fit_finds_no_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _upstream(tmp_path, cr_amplitude=0.2)
    _script_roots(monkeypatch, [0.5, 0.5, 0.5, math.nan])
    CalibrationService.calibrate_zx90(cast("Any", fake), CONTROL, TARGET, plot=False)

    assert max(float(sweep.max()) for sweep in fake.sweeps) < 1.0
    stored = fake.ctx.calib_note.get_cr_param(LABEL)
    assert stored["cr_amplitude"] == 1.0, "a value no sweep measured, passed as finite"


def test_upstream_calibrate_zx90_retries_a_longer_duration_when_the_rough_fit_finds_no_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _upstream(tmp_path / "first", cr_amplitude=0.2)
    _script_roots(monkeypatch, [0.5])
    CalibrationService.calibrate_zx90(cast("Any", first), CONTROL, TARGET, plot=False)
    retried = _upstream(tmp_path / "retried", cr_amplitude=0.2)
    _script_roots(monkeypatch, [math.nan, 0.5])
    CalibrationService.calibrate_zx90(cast("Any", retried), CONTROL, TARGET, plot=False)

    first_duration = first.ctx.calib_note.get_cr_param(LABEL)["duration"]
    retried_duration = retried.ctx.calib_note.get_cr_param(LABEL)["duration"]
    # 1.05 / (8 x 0.01 x 0.2) + 32 = 97.6 ns, rounded up to 16 ns.
    assert first_duration == 112.0
    assert retried_duration > first_duration
    assert np.array_equal(retried.sweeps[0], retried.sweeps[1]), "the retry sweeps the same range"


# ---------------------------------------------------------------------------
# QDash CreateZX90 on top of the upstream code
# ---------------------------------------------------------------------------

# Complete CreateZX90 CR inputs as a same-step CheckCR publishes them.
_CHECKCR_OUTPUTS = {
    "cr_duration": 0.0,
    "cr_phase": 0.1,
    "cr_beta": 0.0,
    "cancel_amplitude": 0.02,
    "cancel_phase": 0.2,
    "cancel_beta": 0.0,
    "rotary_amplitude": 0.0,
    "zx_rotation_rate": 0.01,
}


def _run_createzx90(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    max_amplitude: float,
    adiabatic_safe_factor: float,
    roots: list[float],
    ramptime: float = 24.0,
) -> tuple[_UpstreamCalibration, MagicMock, dict[str, Any], PostProcessResult, MagicMock]:
    """Run CreateZX90 with no run keys after a CheckCR that used the given bounds.

    CheckCR fixes its drive at min(max_amplitude, amp_per_ghz x factor x delta), so the
    note entry and the cr_amplitude input carry that realized amplitude.
    """
    delta_ghz, amp_per_ghz = 0.4, 2.0
    realized = min(max_amplitude, amp_per_ghz * adiabatic_safe_factor * delta_ghz)
    note: Any = CalibrationNote("test-chip", file_path=tmp_path / "note.json")
    note.update_cr_param(LABEL, _checkcr_entry(realized, ramptime=ramptime))
    previous = copy.deepcopy(dict(note.get_cr_param(LABEL)))
    upstream = _UpstreamCalibration(note, delta_ghz=delta_ghz, amp_per_ghz=amp_per_ghz)
    _script_roots(monkeypatch, roots)

    def calibrate_zx90(control: str, target: str, **kwargs: Any) -> Any:
        # The real Experiment wrapper, so n_shots and shot_interval map as on hardware.
        holder = SimpleNamespace(calibration_service=upstream)
        return Experiment.calibrate_zx90(cast("Any", holder), control, target, **kwargs)

    spy = MagicMock(side_effect=calibrate_zx90)
    exp = SimpleNamespace(
        drag_pi_pulse={CONTROL: object()},
        get_qubit_label=lambda qid: f"Q0{qid}",
        calibrate_zx90=spy,
        calib_note=note,
        qubits=upstream.qubits,
        calc_control_amplitude=lambda _qubit, rabi_rate: amp_per_ghz * rabi_rate,
        zx90=MagicMock(return_value=SimpleNamespace(duration=200.0)),
    )

    task = CreateZX90()
    inputs = {
        **_CHECKCR_OUTPUTS,
        "cr_amplitude": realized,
        "cr_ramptime": ramptime,
        "cr_max_amplitude": max_amplitude,
        "cr_adiabatic_safe_factor": adiabatic_safe_factor,
    }
    for name, value in inputs.items():
        task.input_parameters[name] = InputParameterModel(value=value)
    save = MagicMock()
    monkeypatch.setattr(task, "save_calibration", save)
    backend = cast("QubexBackend", SimpleNamespace(get_instance=lambda: exp))
    run_result = task.run(backend, "0-1")
    post = task.postprocess(backend, "exec", run_result, "0-1")
    return upstream, spy, previous, post, save


@pytest.mark.parametrize(
    ("max_amplitude", "adiabatic_safe_factor", "cap"),
    [
        (0.3, 0.75, 0.3),  # max_amplitude binds; qubex's own 1.0 would allow 0.6
        (1.0, 0.25, 0.2),  # the factor binds; qubex's own 0.75 would allow 0.6
    ],
)
def test_createzx90_inherits_the_checkcr_caps_and_ramptime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    max_amplitude: float,
    adiabatic_safe_factor: float,
    cap: float,
) -> None:
    upstream, spy, _, post, save = _run_createzx90(
        tmp_path,
        monkeypatch,
        max_amplitude=max_amplitude,
        adiabatic_safe_factor=adiabatic_safe_factor,
        roots=[0.9, 0.5, 0.5, 0.5],
    )

    (call,) = spy.call_args_list
    assert call.kwargs["max_amplitude"] == max_amplitude
    assert call.kwargs["adiabatic_safe_factor"] == adiabatic_safe_factor
    assert call.kwargs["ramptime"] == 24.0, "the input cr_ramptime, not qubex's own 32 ns"
    assert "duration" not in call.kwargs
    assert "amplitude_range" not in call.kwargs
    # The cap equals the realized CheckCR amplitude, so no sweep goes above it.
    for sweep in upstream.sweeps:
        assert float(sweep.max()) <= cap + 1e-12
    assert post.validation_error is None
    amplitude = post.output_parameters["cr_amplitude"].value
    assert amplitude is not None
    assert 0 < amplitude <= cap
    # 1.05 / (8 x 0.01 x cap) + 24 ns, rounded up to 16 ns: the qubex duration behavior.
    expected = math.ceil((1.05 / (8 * 0.01 * cap) + 24.0) / 16.0) * 16.0
    assert post.output_parameters["cr_duration"].value == expected
    assert post.output_parameters["cr_ramptime"].value == 24.0
    stored = upstream.ctx.calib_note.get_cr_param(LABEL)
    assert stored["cr_amplitude"] == amplitude
    assert stored["ramptime"] == 24.0
    save.assert_called_once()


def test_createzx90_publishes_a_retried_duration_longer_than_the_formula(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The skill detects the unflagged qubex retry from cr_duration alone.
    _, _, _, post, _ = _run_createzx90(
        tmp_path,
        monkeypatch,
        max_amplitude=0.3,
        adiabatic_safe_factor=0.75,
        roots=[math.nan, 0.9, 0.5, 0.5, 0.5],
    )

    formula = math.ceil((1.05 / (8 * 0.01 * 0.3) + 24.0) / 16.0) * 16.0
    assert post.validation_error is None
    duration = post.output_parameters["cr_duration"].value
    assert duration is not None
    assert duration > formula


def test_createzx90_rejects_the_upstream_amplitude_one_and_puts_the_checkcr_entry_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    upstream, _, previous, post, save = _run_createzx90(
        tmp_path,
        monkeypatch,
        max_amplitude=0.3,
        adiabatic_safe_factor=0.75,
        roots=[0.9, 0.5, 0.5, math.nan],
    )

    assert post.validation_error is not None
    assert "found no root" in post.validation_error
    save.assert_not_called()
    # The entry from just before the call is this step's CheckCR result, not an incumbent.
    assert upstream.ctx.calib_note.get_cr_param(LABEL) == previous
    assert previous["duration"] == 0.0
