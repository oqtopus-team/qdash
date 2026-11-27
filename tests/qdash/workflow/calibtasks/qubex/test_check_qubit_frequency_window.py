"""Tests for CheckQubitFrequencyWindow and CheckQubitSpectroscopy window integration."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from qdash.common.config.backend import get_tasks
from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.qubex.cw.check_qubit_frequency_window import (
    CheckQubitFrequencyWindow,
)
from qdash.workflow.calibtasks.qubex.cw.check_qubit_spectroscopy import (
    CheckQubitSpectroscopy,
)
from qdash.workflow.service.one_qubit_stage_runner import batch_capable_tasks


class _FakeControlBox:
    def __init__(self, default_range: tuple[float, float, float]) -> None:
        self.traits = SimpleNamespace(default_control_frequency_range=default_range)


class _FakeReadoutBox:
    def __init__(self, default_range: tuple[float, float, float]) -> None:
        self.traits = SimpleNamespace(default_readout_frequency_range=default_range)


class _FakeExperiment:
    def __init__(
        self,
        *,
        default_range: tuple[float, float, float] = (6.5, 9.5, 0.005),
        readout_range: tuple[float, float, float] = (9.75, 10.75, 0.002),
        peak_freq: float | None = 8.15,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._peak_freq = peak_freq
        ctrl_box = _FakeControlBox(default_range)
        read_box = _FakeReadoutBox(readout_range)
        self.ctx = SimpleNamespace(
            experiment_system=SimpleNamespace(
                get_control_box_for_qubit=lambda _label: ctrl_box,
                get_readout_box_for_qubit=lambda _label: read_box,
            )
        )

    def get_qubit_label(self, qid: int) -> str:
        return f"Q{qid:02d}"

    def modified_frequencies(self, _overrides: dict[str, float]):
        from contextlib import nullcontext

        return nullcontext()

    def qubit_spectroscopy(self, label: str, **kwargs: Any) -> SimpleNamespace:
        self.calls.append({"label": label, **kwargs})
        freqs = np.asarray(kwargs["frequency_range"], dtype=float)
        powers = np.asarray(kwargs["power_range"], dtype=float)
        rng = np.random.default_rng(42)
        phases = rng.normal(0.0, 0.02, (powers.size, freqs.size))
        if self._peak_freq is not None:
            for idx, power_db in enumerate(powers):
                if power_db >= -15.0:
                    width = 0.04 if power_db < -10.0 else 0.25
                    phases[idx] += 1.8 / (1.0 + ((freqs - self._peak_freq) / width) ** 2)
        return SimpleNamespace(
            data={"frequency_range": freqs, "power_range": powers, "data": phases}
        )


class _FakeBackend:
    def __init__(self, exp: _FakeExperiment) -> None:
        self._exp = exp

    def get_instance(self) -> _FakeExperiment:
        return self._exp

    def get_qubit_label(self, qid: str) -> str:
        return f"Q{int(qid):02d}"


def _prepare_window_task(
    exp: _FakeExperiment,
    *,
    readout_frequency: float = 10.14,
    readout_amplitude: float = 0.015,
) -> tuple[CheckQubitFrequencyWindow, _FakeBackend]:
    task = CheckQubitFrequencyWindow()
    task.input_parameters["readout_frequency"] = InputParameterModel(value=readout_frequency)
    task.input_parameters["readout_amplitude"] = InputParameterModel(value=readout_amplitude)
    backend = _FakeBackend(exp)
    task.resolve_run_parameters(backend, "32")  # type: ignore[arg-type]
    return task, backend


def test_window_task_resolves_coarse_range_and_publishes_narrowed_bounds(monkeypatch) -> None:
    exp = _FakeExperiment(
        default_range=(6.5, 9.5, 0.005),
        readout_range=(9.75, 10.75, 0.002),
        peak_freq=8.15,
    )
    task, backend = _prepare_window_task(exp)
    monkeypatch.setattr(task, "save_calibration", lambda _b: None)

    assert task.run_parameters["frequency_range"].value == (6.5, 9.75, 0.01)

    run_result = task.run(backend, "32")  # type: ignore[arg-type]
    post = task.postprocess(backend, "exec-1", run_result, "32")  # type: ignore[arg-type]

    assert post.validation_error is None
    assert len(post.figures) == 1
    win_min_val = post.output_parameters["qubit_frequency_window_min"].value
    win_max_val = post.output_parameters["qubit_frequency_window_max"].value
    center_val = post.output_parameters["window_center_frequency"].value
    assert win_min_val is not None and win_max_val is not None and center_val is not None
    win_min = float(win_min_val)
    win_max = float(win_max_val)
    center = float(center_val)
    assert center == pytest.approx(8.15, abs=0.02)
    assert win_min < 8.15 < win_max
    assert win_max - win_min == pytest.approx(0.6, abs=1e-6)


def test_window_task_returns_validation_error_when_no_signal(monkeypatch) -> None:
    exp = _FakeExperiment(peak_freq=None)
    task, backend = _prepare_window_task(exp)
    monkeypatch.setattr(task, "save_calibration", lambda _b: None)

    run_result = task.run(backend, "32")  # type: ignore[arg-type]
    post = task.postprocess(backend, "exec-2", run_result, "32")  # type: ignore[arg-type]

    assert post.validation_error is not None
    assert post.output_parameters == {}
    assert len(post.figures) == 1


def test_check_qubit_spectroscopy_uses_stored_window_when_frequency_range_blank() -> None:
    exp = _FakeExperiment(default_range=(6.5, 9.5, 0.005))
    backend = _FakeBackend(exp)
    task = CheckQubitSpectroscopy()
    # Window extends above control box default stop (9.5) into 9.5..9.75 GHz.
    task.input_parameters["qubit_frequency_window_min"] = InputParameterModel(value=9.132)
    task.input_parameters["qubit_frequency_window_max"] = InputParameterModel(value=9.748)

    task.resolve_run_parameters(backend, "32")  # type: ignore[arg-type]

    assert task.run_parameters["frequency_range"].value == (9.13, 9.75, 0.005)


def test_check_qubit_spectroscopy_falls_back_to_full_band_without_window() -> None:
    exp = _FakeExperiment(default_range=(6.5, 9.75, 0.005))
    backend = _FakeBackend(exp)
    task = CheckQubitSpectroscopy()

    task.resolve_run_parameters(backend, "32")  # type: ignore[arg-type]

    assert task.run_parameters["frequency_range"].value == (6.5, 9.75, 0.005)


def test_check_qubit_spectroscopy_keeps_explicit_frequency_range_override() -> None:
    exp = _FakeExperiment(default_range=(6.5, 9.75, 0.005))
    backend = _FakeBackend(exp)
    task = CheckQubitSpectroscopy()
    task.run_parameters["frequency_range"].value = (7.0, 7.5, 0.005)
    task.input_parameters["qubit_frequency_window_min"] = InputParameterModel(value=7.83)
    task.input_parameters["qubit_frequency_window_max"] = InputParameterModel(value=8.45)

    task.resolve_run_parameters(backend, "32")  # type: ignore[arg-type]

    assert tuple(task.run_parameters["frequency_range"].value) == (7.0, 7.5, 0.005)


def test_window_task_is_registered_and_not_batch_capable() -> None:
    assert "CheckQubitFrequencyWindow" in get_tasks("qubex")
    assert batch_capable_tasks("qubex")["CheckQubitFrequencyWindow"] is False
    assert set(CheckQubitFrequencyWindow.run_spec) == {
        "frequency_range",
        "frequency_step",
        "power_range",
        "shots",
        "interval",
        "simultaneous_drive",
        "window_width",
    }
