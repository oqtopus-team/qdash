from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from qdash.workflow.calibtasks.qubex.box_setup.correct_capture_delay import CorrectCaptureDelay

SAMPLING_NS = 8.0
SAMPLES = 192
DURATION_NS = 1024.0


class _FakeQuel1:
    """Capture a rectangular pulse shifted by the temporarily applied delay."""

    sampling_ns = SAMPLING_NS
    samples = SAMPLES

    def __init__(self, arrival_ns: float, *, restore: bool = True) -> None:
        self.arrival_ns = arrival_ns
        self.restore = restore
        self.applied_ns: float | None = None
        self.frequencies: list[dict[str, float]] = []
        self.active_frequencies = {"RQ00": 8.1}
        self.captured: list[list[str]] = []
        self.delays: dict[int, float] = {0: 7, 1: 8}
        self.words = {0: 0, 1: 0}
        self.qubit_labels = ["Q00", "Q01", "Q02", "Q03", "Q04"]
        system = SimpleNamespace(
            get_mux_by_qubit=lambda label: SimpleNamespace(index=int(label[1:]) // 4),
            resolve_read_label=lambda label: f"R{label}",
            control_params=SimpleNamespace(
                get_capture_delay=self.delays.__getitem__,
                get_capture_delay_word=self.words.__getitem__,
            ),
        )
        self.system_manager = SimpleNamespace(
            backend_kind="quel1",
            experiment_system=system,
            modified_capture_delay=self._modified_capture_delay,
        )
        box = SimpleNamespace(
            traits=SimpleNamespace(default_readout_frequency_range=(9.75, 10.75, 0.002))
        )
        self.ctx = SimpleNamespace(
            experiment_system=SimpleNamespace(get_readout_box_for_qubit=lambda _: box)
        )
        self.readout_duration = DURATION_NS

    def get_qubit_label(self, qid: int) -> str:
        return f"Q{qid:02d}"

    @contextmanager
    def modified_frequencies(self, frequencies):
        self.frequencies.append(dict(frequencies))
        original = dict(self.active_frequencies)
        self.active_frequencies.update(frequencies)
        try:
            yield
        finally:
            self.active_frequencies = original

    @contextmanager
    def _modified_capture_delay(self, delays):
        (self.applied_ns,) = delays.values()
        if not self.restore:
            self.delays[0] = 99
        try:
            yield
        finally:
            self.applied_ns = None

    def check_waveform(
        self, *, targets, readout_amplitude, readout_duration, n_shots, add_pump_pulses, plot
    ):
        # These conditions must hold for sweeps, verification, and the final check
        # on both backends, even with other active qubits in the same MUX.
        assert len(targets) == 1
        assert readout_amplitude == 1.0
        assert n_shots == 1024
        assert not add_pump_pulses
        assert not plot
        assert self.applied_ns is not None
        self.captured.append(list(targets))
        rng = np.random.default_rng(round(self.applied_ns * 10))
        time = np.arange(self.samples) * self.sampling_ns
        start = self.arrival_ns - self.applied_ns
        envelope = 0.5 * (
            np.tanh((time - start) / 6) - np.tanh((time - start - readout_duration) / 6)
        )
        data = {}
        for target in targets:
            shape = (4, self.samples)
            noise = rng.normal(size=shape) + 1j * rng.normal(size=shape)
            raw = envelope * (0.3 + 0.4j) + 0.005 * noise
            data[target] = SimpleNamespace(raw=raw, sampling_period=self.sampling_ns)
        return SimpleNamespace(data=data)


class _FakeQuel3(_FakeQuel1):
    """QuEL-3 captures at 0.8 ns, in the low band, without a word offset."""

    sampling_ns = 0.8
    samples = 1920

    def __init__(self, arrival_ns: float) -> None:
        super().__init__(arrival_ns)
        self.system_manager.backend_kind = "quel3"
        self.delays.update({0: 700.0, 1: 700.0})

        def unsupported_word(mux: int) -> int:
            raise ValueError(f"Capture delay word is not supported for mux {mux}")

        params = self.system_manager.experiment_system.control_params
        params.get_capture_delay_word = unsupported_word
        box = self.ctx.experiment_system.get_readout_box_for_qubit("Q00")
        box.traits.default_readout_frequency_range = (5.75, 6.75, 0.002)


def _backend(experiment: _FakeQuel1) -> MagicMock:
    backend = MagicMock()
    backend.get_instance.return_value = experiment
    return backend


def _run(task: CorrectCaptureDelay, backend: MagicMock, qid: str = "0"):
    task.resolve_run_parameters(backend, qid)
    return task.run(backend, qid)


@pytest.mark.parametrize(("arrival_ns", "expected"), [(1400.0, (9, 0)), (1430.0, (9, 4))])
def test_run_publishes_centered_delay_for_the_mux(arrival_ns, expected):
    experiment = _FakeQuel1(arrival_ns)
    backend = _backend(experiment)
    task = CorrectCaptureDelay()

    run_result = _run(task, backend)
    result = task.postprocess(backend, "exec-1", run_result, "0")

    assert run_result.raw_result.target == "Q00"
    assert result.validation_error is None
    assert result.output_parameters["capture_delay"].value == expected[0]
    assert result.output_parameters["capture_delay_word"].value == expected[1]
    assert result.output_parameters["capture_delay"].execution_id == "exec-1"
    assert len(result.figures) == 3
    # Only the representative qubit is captured, at the fixed tone.
    assert task.run_parameters["readout_frequency"].value == pytest.approx(11.0)
    assert all(f == {"RQ00": 11.0} for f in experiment.frequencies)
    assert all(captured == ["Q00"] for captured in experiment.captured)


def test_postprocess_rejects_when_no_pulse_is_found():
    experiment = _FakeQuel1(arrival_ns=100_000.0)
    backend = _backend(experiment)
    task = CorrectCaptureDelay()

    result = task.postprocess(backend, "exec-1", _run(task, backend), "0")

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert "coarse sweep" in result.validation_error


def test_run_rejects_unaligned_word_sweep():
    backend = _backend(_FakeQuel1(1400.0))
    task = CorrectCaptureDelay()
    task.run_parameters["capture_delay_word_range"].value = (0, 16, 2)

    with pytest.raises(ValueError, match="multiples of 4"):
        _run(task, backend)


def test_run_rejects_unsupported_backend():
    experiment = _FakeQuel1(1400.0)
    experiment.system_manager.backend_kind = "other"
    task = CorrectCaptureDelay()

    with pytest.raises(ValueError, match="QuEL-1 and QuEL-3"):
        _run(task, _backend(experiment))


def test_quel3_publishes_capture_delay_in_ns_without_word():
    experiment = _FakeQuel3(arrival_ns=1430.0)
    backend = _backend(experiment)
    task = CorrectCaptureDelay()

    run_result = _run(task, backend)
    result = task.postprocess(backend, "exec-1", run_result, "0")

    assert result.validation_error is None
    assert set(result.output_parameters) == {"capture_delay"}
    capture_delay = result.output_parameters["capture_delay"]
    assert capture_delay.unit == "ns"
    assert isinstance(capture_delay.value, float)
    steps = capture_delay.value / 32.0
    assert steps == pytest.approx(round(steps), abs=1e-6)
    # Calibration uses the same 32 ns grid and ±16 ns tolerance as QuEL-1.
    midpoint = 1430.0 - capture_delay.value + DURATION_NS / 2
    assert midpoint == pytest.approx(1920 * 0.8 / 2, abs=16.0)
    # One ns sweep without a word sweep: delay sweep and final capture figures.
    assert all(captured == ["Q00"] for captured in experiment.captured)
    assert experiment.applied_ns is None
    assert experiment.delays == {0: 700.0, 1: 700.0}
    assert run_result.raw_result.fine == []
    assert len(result.figures) == 2
    assert task.run_parameters["readout_frequency"].value == pytest.approx(7.0)


def test_quel3_rejects_sweep_off_the_sampling_grid():
    task = CorrectCaptureDelay()
    task.run_parameters["capture_delay_ns_range"].value = (0, 1000, 100.5)

    with pytest.raises(ValueError, match=r"multiples of 0\.8"):
        _run(task, _backend(_FakeQuel3(1430.0)))


def test_run_fails_when_delay_is_not_restored():
    task = CorrectCaptureDelay()

    with pytest.raises(RuntimeError, match="not restored"):
        _run(task, _backend(_FakeQuel1(1400.0, restore=False)))


def test_default_tone_sits_above_low_band_spectroscopy_range():
    experiment = _FakeQuel1(1400.0)
    box = experiment.ctx.experiment_system.get_readout_box_for_qubit("Q00")
    box.traits.default_readout_frequency_range = (5.75, 6.75, 0.002)
    task = CorrectCaptureDelay()

    task.resolve_run_parameters(_backend(experiment), "0")

    assert task.run_parameters["readout_frequency"].value == pytest.approx(7.0)


def test_explicit_tone_is_kept():
    task = CorrectCaptureDelay()
    task.run_parameters["readout_frequency"].value = 10.9

    task.resolve_run_parameters(_backend(_FakeQuel1(1400.0)), "0")

    assert task.run_parameters["readout_frequency"].value == 10.9


def test_run_explains_inactive_qubits_without_frequencies():
    experiment = _FakeQuel1(1400.0)
    experiment.qubit_labels = ["Q00", "Q01", "Q02", "Q03"]
    task = CorrectCaptureDelay()

    with pytest.raises(ValueError, match="readout_frequency"):
        _run(task, _backend(experiment), qid="4")


@pytest.mark.parametrize("experiment_class", [_FakeQuel1, _FakeQuel3])
def test_capture_failure_restores_frequency_and_delay(experiment_class, monkeypatch):
    experiment = experiment_class(1430.0)
    task = CorrectCaptureDelay()

    def fail_capture(**kwargs):
        assert kwargs["targets"] == ["Q00"]
        assert kwargs["readout_amplitude"] == 1.0
        assert experiment.applied_ns is not None
        raise RuntimeError("capture failed")

    monkeypatch.setattr(experiment, "check_waveform", fail_capture)
    with pytest.raises(RuntimeError, match="capture failed"):
        _run(task, _backend(experiment))

    assert experiment.applied_ns is None
    assert experiment.active_frequencies == {"RQ00": 8.1}
