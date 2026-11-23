"""Code facts the ZX90 search skill (qdash-zx90-optimization) relies on.

The skill tells the model which run keys exist, that CreateZX90 does not inherit the CheckCR
amplitude cap, how far CreateZX90's amplitude scan can reach, and that a failed final fit stores
amplitude 1.0. These tests pin those statements to the QDash tasks and to the locked qubex
implementation, so a change in either fails here before the skill misleads a hardware run.
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock

import numpy as np
import pytest
from qubex.analysis import fitting
from qubex.experiment.services.calibration_service import CalibrationService

from qdash.datamodel.calibration_pipeline import CalibrationPipelineSpec
from qdash.workflow.calibtasks.qubex.benchmark.zx90_interleaved_randoized_benchmarking import (
    ZX90InterleavedRandomizedBenchmarking,
)
from qdash.workflow.calibtasks.qubex.two_qubit.check_bell_state import CheckBellState
from qdash.workflow.calibtasks.qubex.two_qubit.check_bell_state_tomography import (
    CheckBellStateTomography,
)
from qdash.workflow.calibtasks.qubex.two_qubit.check_cross_resonance import CheckCrossResonance
from qdash.workflow.calibtasks.qubex.two_qubit.check_zx90 import CheckZX90
from qdash.workflow.calibtasks.qubex.two_qubit.create_zx90 import CreateZX90

if TYPE_CHECKING:
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
            # CreateZX90 reuses a stored nonzero cr_duration unless CheckCR runs before it.
            assert names.index("CheckCrossResonance") < names.index("CreateZX90")
            for call in calls:
                assert call.input is None, "the search changes run conditions only"
                if call.run:
                    assert set(call.run) <= set(TASKS[call.name].run_spec), call
            checkcr = next(call for call in calls if call.name == "CheckCrossResonance")
            assert len(set(checkcr.run or {}) & SEARCH_KEYS) == 1, "one key per experiment"


def test_search_keys_are_checkcr_run_keys_and_createzx90_exposes_no_shape_keys() -> None:
    assert set(CheckCrossResonance.run_spec) >= SEARCH_KEYS
    assert "cr_amplitude" not in CheckCrossResonance.run_spec
    assert set(CreateZX90.run_spec) == {"readout_duration", "shots", "interval"}
    defaults = {key: CheckCrossResonance.run_spec[key].default for key in SEARCH_KEYS}
    assert defaults == {
        "adiabatic_safe_factor": 0.75,
        "max_amplitude": 1.0,
        "max_time_range": 4096,
    }


def test_createzx90_calls_qubex_without_the_checkcr_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    # The skill's scan check rests on this: CreateZX90 falls back to qubex's own 0.75 and 1.0.
    task = CreateZX90()
    calibrate_zx90 = MagicMock(
        return_value={"n1": {"fig": object()}, "n3": {"fig": object()}, "fig": object()}
    )
    cr_param = {
        "duration": 128.0,
        "cr_amplitude": 0.27,
        "cr_phase": 0.0,
        "cr_beta": 0.0,
        "cancel_amplitude": 0.03,
        "cancel_phase": 0.0,
        "cancel_beta": 0.0,
        "rotary_amplitude": 0.06,
        "zx_rotation_rate": 0.004,
        "ramptime": 32.0,
    }
    exp = SimpleNamespace(
        drag_pi_pulse={"Q00": object()},
        get_qubit_label=lambda qid: f"Q0{qid}",
        calibrate_zx90=calibrate_zx90,
        calib_note=SimpleNamespace(get_cr_param=lambda _label: cr_param),
        zx90=MagicMock(return_value=SimpleNamespace(duration=160.0)),
    )
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)

    task.run(cast("QubexBackend", SimpleNamespace(get_instance=lambda: exp)), "0-1")

    passed = calibrate_zx90.call_args.kwargs
    for key in ("adiabatic_safe_factor", "max_amplitude", "duration", "amplitude_range"):
        assert passed.get(key) is None, key


class _FakeCalibration:
    """Just enough of CalibrationService for its real calibrate_zx90 to run without hardware."""

    def __init__(self, cr_amplitude: float, delta_ghz: float, amp_per_ghz: float) -> None:
        self.stored: dict[str, Any] = {}
        self.sweeps: list[np.ndarray] = []
        self.cr_param = {
            "duration": 0.0,  # as CheckCR leaves it
            "cr_amplitude": cr_amplitude,
            "cr_phase": 0.0,
            "cancel_amplitude": 0.02,
            "cancel_phase": 0.0,
            "zx_rotation_rate": 0.01,
        }
        qubits = {
            "Q00": SimpleNamespace(frequency=8.0),
            "Q01": SimpleNamespace(frequency=8.0 + delta_ghz),
        }

        def calc_control_amplitude(target: str, rabi_rate: float) -> float:
            return amp_per_ghz * rabi_rate

        def sweep_parameter(_sequence: Any, *, sweep_range: Any, **_kwargs: Any) -> Any:
            sweep = np.asarray(sweep_range, dtype=float)
            self.sweeps.append(sweep)
            return SimpleNamespace(data={"Q01": SimpleNamespace(normalized=np.zeros(len(sweep)))})

        self.ctx = SimpleNamespace(
            qubits=qubits,
            calib_note=SimpleNamespace(
                get_cr_param=lambda _label: self.cr_param,
                update_cr_param=lambda _label, value: self.stored.update(value),
            ),
        )
        self.pulse = SimpleNamespace(
            calc_control_amplitude=calc_control_amplitude, x180=lambda _q: object()
        )
        self.measurement_service = SimpleNamespace(sweep_parameter=sweep_parameter)

    def _ramptime(self, _control: str, _target: str) -> float:
        return 32.0

    def _adiabatic_safe_factor(self, control: str, target: str) -> float:
        return CalibrationService._adiabatic_safe_factor(cast("Any", self), control, target)

    def calc_zx90_coherence_limit(self, _control: str, _target: str) -> Any:
        raise KeyError("no coherence data")


def _run_calibrate_zx90(
    monkeypatch: pytest.MonkeyPatch, fake: _FakeCalibration, roots: list[float]
) -> None:
    """Run qubex's calibrate_zx90 with each polynomial fit returning the next root fraction.

    A root is given as a fraction of the swept range (nan for no root), so it always lies in the
    range, as qubex's fit_polynomial guarantees.
    """
    pending = list(roots)

    def fit_polynomial(*, x: Any, **_kwargs: Any) -> dict[str, float]:
        fraction = pending.pop(0) if pending else 0.5
        low, high = float(np.min(x)), float(np.max(x))
        return {"root": float("nan") if np.isnan(fraction) else low + fraction * (high - low)}

    # calibration_service calls fitting.fit_polynomial through this same module object.
    monkeypatch.setattr(fitting, "fit_polynomial", fit_polynomial)
    CalibrationService.calibrate_zx90(cast("Any", fake), "Q00", "Q01", plot=False)


def test_createzx90_scan_exceeds_the_checkcr_cap_but_stays_within_min_c_and_2_4a(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # CheckCR ran with max_amplitude 0.3 and realized a = 0.3. CreateZX90's own ceiling is
    # C = min(amp_per_ghz x 0.75 x delta, 1.0) = min(2 x 0.75 x 0.4, 1.0) = 0.6.
    a, ceiling = 0.3, 0.6
    fake = _FakeCalibration(cr_amplitude=a, delta_ghz=0.4, amp_per_ghz=2.0)
    # Rough root near the top of its range, then a final root inside the fine range.
    _run_calibrate_zx90(monkeypatch, fake, roots=[0.95, 0.5, 0.5, 0.9])

    scan_max = max(float(sweep.max()) for sweep in fake.sweeps)
    assert scan_max <= min(ceiling, 2.4 * a) + 1e-12
    assert scan_max > a, "the scan is not bounded by the CheckCR cap"
    assert fake.stored["cr_amplitude"] <= scan_max
    assert fake.stored["cr_amplitude"] > a


def test_createzx90_stores_amplitude_one_when_the_final_fit_finds_no_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeCalibration(cr_amplitude=0.2, delta_ghz=0.4, amp_per_ghz=2.0)
    _run_calibrate_zx90(monkeypatch, fake, roots=[0.5, 0.5, 0.5, float("nan")])

    assert max(float(sweep.max()) for sweep in fake.sweeps) < 1.0
    assert fake.stored["cr_amplitude"] == 1.0, "a value no sweep measured, passed as finite"


def test_createzx90_retries_a_longer_duration_when_the_rough_fit_finds_no_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _FakeCalibration(cr_amplitude=0.2, delta_ghz=0.4, amp_per_ghz=2.0)
    _run_calibrate_zx90(monkeypatch, first, roots=[0.5])
    retried = _FakeCalibration(cr_amplitude=0.2, delta_ghz=0.4, amp_per_ghz=2.0)
    _run_calibrate_zx90(monkeypatch, retried, roots=[float("nan"), 0.5])

    # 1.05 / (8 x 0.01 x 0.2) + 32 = 97.6 ns, rounded up to 16 ns.
    assert first.stored["duration"] == 112.0
    assert retried.stored["duration"] > first.stored["duration"]
    assert np.array_equal(retried.sweeps[0], retried.sweeps[1]), "the retry sweeps the same range"
