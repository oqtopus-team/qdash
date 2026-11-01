from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from qdash.workflow.engine.backend.fake import FakeBackend
from qdash.workflow.engine.backend.fake_qubex.simulation import FakeExperiment


def test_fake_ramsey_fit_exposes_qubex_compatible_fields() -> None:
    exp = FakeExperiment()

    result = exp.ramsey_experiment(
        targets=["Q00"],
        time_range=np.arange(0.0, 1000.0, 100.0),
        detuning=0.001,
        plot=False,
    )

    fit = result.data["Q00"].fit()

    assert fit["f"] == 0.001
    assert fit["f_err"] == 0.0
    assert fit["tau_err"] == 0.0


def test_fake_default_t1_and_t2_echo_lifetimes_have_small_variation() -> None:
    exp = FakeExperiment()

    t1_result = exp.t1_experiment(
        targets=["Q00", "Q01"],
        time_range=np.geomspace(100.0, 10_000.0, 5),
        plot=False,
    )
    t2_result = exp.t2_experiment(
        targets=["Q00", "Q01"],
        time_range=np.geomspace(300.0, 10_000.0, 5),
        plot=False,
    )

    assert t1_result.data["Q00"].t1 != t2_result.data["Q00"].t2
    assert t1_result.data["Q00"].t1 != t1_result.data["Q01"].t1
    assert t2_result.data["Q00"].t2 != t2_result.data["Q01"].t2


def test_fake_default_coherence_lifetimes_and_time_scale_vary_between_runs(
    monkeypatch,
) -> None:
    values = iter(
        [
            0.0,
            0.0,
            -0.020,
            0.030,
            0.0,
            0.020,
            0.0,
            0.0,
            -0.015,
            0.0,
            0.025,
            0.015,
        ]
    )
    monkeypatch.setattr(
        "qdash.workflow.engine.backend.fake_qubex.simulation.random.uniform",
        lambda *_: next(values),
    )
    exp = FakeExperiment()

    first_t1 = exp.t1_experiment(
        targets=["Q00"],
        time_range=np.geomspace(100.0, 10_000.0, 5),
        plot=False,
    )
    second_t1 = exp.t1_experiment(
        targets=["Q00"],
        time_range=np.geomspace(100.0, 10_000.0, 5),
        plot=False,
    )
    first_t2 = exp.t2_experiment(
        targets=["Q00"],
        time_range=np.geomspace(300.0, 10_000.0, 5),
        plot=False,
    )
    second_t2 = exp.t2_experiment(
        targets=["Q00"],
        time_range=np.geomspace(300.0, 10_000.0, 5),
        plot=False,
    )

    assert first_t1.data["Q00"].t1 != second_t1.data["Q00"].t1
    assert not np.array_equal(first_t1.data["Q00"].sweep_range, second_t1.data["Q00"].sweep_range)
    assert first_t2.data["Q00"].t2 != second_t2.data["Q00"].t2
    assert not np.array_equal(first_t2.data["Q00"].sweep_range, second_t2.data["Q00"].sweep_range)


def test_fake_explicit_lifetimes_are_preserved() -> None:
    exp = FakeExperiment(qubit_lifetimes=((11.0, 12.0), (21.0, 22.0)))

    assert exp._qubit_lifetime(0) == (11.0, 12.0)
    assert exp._qubit_lifetime(1) == (21.0, 22.0)


def test_fake_zx90_accepts_explicit_cr_parameters_and_x180(monkeypatch) -> None:
    exp = FakeExperiment()
    x180 = object()
    monkeypatch.setattr(
        "qdash.workflow.engine.backend.fake_qubex.simulation._simulation_dependencies",
        lambda: (_ for _ in ()).throw(ImportError),
    )

    schedule = exp.zx90(
        "Q00",
        "Q01",
        cr_duration=100.0,
        cr_ramptime=16.0,
        cr_amplitude=0.2,
        cr_phase=0.1,
        cr_beta=0.01,
        cancel_amplitude=0.02,
        cancel_phase=0.3,
        cancel_beta=0.04,
        rotary_amplitude=0.05,
        x180={"Q00": x180},
    )

    assert schedule.duration == 100.0
    assert exp._resolve_zx90_x180("Q00", {"Q00": x180}) is x180


def test_fake_backend_passes_session_configuration_to_experiment(monkeypatch) -> None:
    experiment = MagicMock()
    factory = MagicMock(return_value=experiment)
    monkeypatch.setattr(
        "qdash.workflow.engine.backend.fake_qubex.FakeExperiment",
        factory,
    )
    backend = FakeBackend(
        {
            "task_type": "qubit",
            "qids": ["0"],
            "chip_id": "chip-1",
            "readout_duration": 2048.0,
            "configuration_mode": "ge-ef-fh",
        }
    )

    backend.connect()

    assert factory.call_args.kwargs["readout_duration"] == 2048.0
    assert factory.call_args.kwargs["configuration_mode"] == "ge-ef-fh"
    experiment.connect.assert_called_once_with()


def test_fake_default_control_amplitude_drives_a_pi_rotation_in_pi_duration() -> None:
    exp = FakeExperiment()

    rate = exp.calc_rabi_rate("Q00")

    assert rate == pytest.approx(1.0 / (2.0 * exp.pi_duration))
    assert exp.control_params.get_control_amplitude("Q00") == exp.CONTROL_AMPLITUDE_SCALE


def test_fake_rabi_oscillation_carries_shot_noise_and_decay() -> None:
    exp = FakeExperiment()

    result = exp.obtain_rabi_params(["Q00"], time_range=np.arange(0.0, 401.0, 8.0), plot=False)
    param = result.rabi_params["Q00"]
    normalized = np.asarray(result.data["Q00"].normalized, dtype=float)

    assert param.frequency == pytest.approx(1.0 / (2.0 * exp.pi_duration))
    assert 0.0 < param.noise < 0.1
    assert 0.95 < param.r2 < 1.0
    # Several periods fit in the sweep, so the signal changes sign many times.
    assert np.count_nonzero(np.diff(np.sign(normalized))) >= 8


def test_fake_pulse_calibration_returns_the_amplitude_for_the_requested_angle() -> None:
    exp = FakeExperiment()

    hpi = exp.calibrate_hpi_pulse(["Q00"]).data["Q00"]
    pi = exp.calibrate_pi_pulse(["Q00"]).data["Q00"]

    assert hpi.calib_value == pytest.approx(exp.CONTROL_AMPLITUDE_SCALE / 2.0)
    assert pi.calib_value == pytest.approx(exp.CONTROL_AMPLITUDE_SCALE)
    assert 0.95 < hpi.r2 < 1.0
    assert hpi.fit()["fig"] is not None


def test_fake_drive_sweep_follows_the_rabi_formula() -> None:
    """A sweep of plain drive pulses, as qubex's chevron measurement issues, oscillates on
    resonance and loses contrast off resonance."""
    from qxpulse import Rect

    exp = FakeExperiment()
    amplitude = exp.CONTROL_AMPLITUDE_SCALE
    durations = np.arange(0.0, 97.0, 4.0)

    def resonant(duration: float) -> dict[str, Rect]:
        return {"Q00": Rect(duration=float(duration), amplitude=amplitude)}

    def detuned(duration: float) -> dict[str, Rect]:
        return {"Q00": Rect(duration=float(duration), amplitude=amplitude).detuned(0.05)}

    on = exp.sweep_parameter(resonant, sweep_range=durations, n_shots=4096, plot=False)
    off = exp.sweep_parameter(detuned, sweep_range=durations, n_shots=4096, plot=False)

    on_signal = np.real(np.asarray(on.data["Q00"].data))
    off_signal = np.real(np.asarray(off.data["Q00"].data))
    # One pi rotation takes pi_duration, so the signal crosses zero around 12 ns and again
    # around 36 ns; off resonance by 50 MHz the excitation stays small.
    assert on_signal[0] < -0.9
    assert on_signal.max() > 0.9
    assert np.ptp(off_signal) < 0.3


def test_fake_ramsey_x_and_y_axes_rotate_counter_clockwise() -> None:
    """The second pi/2 pulse about Y reads cos, about X reads -sin, so the (X, Y) pair
    advances counter-clockwise for a positive detuning and clockwise for a negative one."""
    exp = FakeExperiment()
    time_range = np.arange(0.0, 1001.0, 50.0)

    def xy(detuning: float) -> tuple[np.ndarray, np.ndarray]:
        y = exp.ramsey_experiment(
            targets=["Q00"],
            time_range=time_range,
            detuning=detuning,
            second_rotation_axis="Y",
            plot=False,
        )
        x = exp.ramsey_experiment(
            targets=["Q00"],
            time_range=time_range,
            detuning=detuning,
            second_rotation_axis="X",
            plot=False,
        )
        return (
            np.asarray(x.data["Q00"].normalized, dtype=float),
            np.asarray(y.data["Q00"].normalized, dtype=float),
        )

    x_pos, y_pos = xy(0.001)
    cross = x_pos[:-1] * y_pos[1:] - x_pos[1:] * y_pos[:-1]
    assert np.all(cross > 0), "positive detuning must rotate counter-clockwise"
    assert y_pos[0] == pytest.approx(1.0, abs=0.1)
    assert abs(x_pos[0]) < 0.1

    x_neg, y_neg = xy(-0.001)
    cross_neg = x_neg[:-1] * y_neg[1:] - x_neg[1:] * y_neg[:-1]
    assert np.all(cross_neg < 0), "negative detuning must rotate clockwise"


def test_fake_repeated_pulse_check_drifts_and_carries_noise() -> None:
    """Repeating a calibrated pi/2 pulse alternates 1, 0, -1, 0 with a small, deterministic
    rotation error and shot noise instead of an exact pattern."""
    exp = FakeExperiment()
    exp.calibrate_hpi_pulse(["Q00"])

    result = exp.repeat_sequence({"Q00": exp.hpi_pulse["Q00"]}, repetitions=20, plot=False)
    again = exp.repeat_sequence({"Q00": exp.hpi_pulse["Q00"]}, repetitions=20, plot=False)
    signal = 2.0 * np.imag(np.asarray(result.data["Q00"].data, dtype=complex))

    assert signal[0] == pytest.approx(1.0, abs=0.1)
    assert signal[2] == pytest.approx(-1.0, abs=0.15)
    assert abs(signal[1]) < 0.2
    assert not np.allclose(np.abs(signal[::2]), 1.0, atol=1e-6)
    # The noise is seeded per target; only the simulator's lifetime jitter differs between runs.
    repeated = 2.0 * np.imag(np.asarray(again.data["Q00"].data, dtype=complex))
    assert np.allclose(signal, repeated, atol=0.05)
