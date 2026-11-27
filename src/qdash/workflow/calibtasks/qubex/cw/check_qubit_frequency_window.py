"""Fast coarse few-power qubit spectroscopy to narrow the 2D spectroscopy window."""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np

from qdash.analysis.spectroscopy import (
    DEFAULT_MIN_RESPONSE_SCORE,
    DEFAULT_MIN_WINDOW_GHZ,
    DEFAULT_WINDOW_MARGIN_GHZ,
    create_qubit_frequency_window_figure,
    estimate_qubit_frequency_window,
)
from qdash.common.visualization.figure_metadata import set_figure_role
from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
    TaskDocumentation,
)
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import QubexTask

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend

DEFAULT_WINDOW_FREQUENCY_STEP = 0.010
DEFAULT_WINDOW_POWER_RANGE = (-25, 0, 10)
DEFAULT_WINDOW_SHOTS = 512
DEFAULT_WINDOW_INTERVAL = 1024.0


class CheckQubitFrequencyWindow(QubexTask):
    """Fast coarse few-power sweep to narrow the downstream 2D spectroscopy band.

    Runs a coarse frequency sweep (default 10 MHz step) at a few medium drive
    powers (default ``[-25, -15, -5] dB``) on the qubit's mapped resonator, then
    publishes ``qubit_frequency_window_min`` and ``qubit_frequency_window_max``.
    ``CheckQubitSpectroscopy`` consumes those bounds when ``frequency_range`` is
    left blank, cutting 2D spectroscopy runtime several-fold while keeping full
    fallback compatibility when no window is stored.
    """

    name: str = "CheckQubitFrequencyWindow"
    task_type: str = "qubit"
    documentation: ClassVar[TaskDocumentation] = TaskDocumentation(
        description=(
            "Fast coarse few-power qubit spectroscopy that locates the qubit response "
            "and publishes a narrowed [qubit_frequency_window_min, qubit_frequency_window_max] "
            "search range for downstream 2D CheckQubitSpectroscopy."
        ),
        when_to_use=(
            "Run after CheckResonatorQubitMapping (or CheckResonatorSpectroscopy) and before "
            "CheckQubitSpectroscopy to avoid scanning empty frequencies across the full 2D grid."
        ),
        prerequisites=(
            "readout_frequency (or resonator_frequency) and readout_amplitude are stored.",
        ),
    )
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "readout_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("resonator_frequency",)
        ),
        "readout_amplitude": InputParameterSpec.required_database(),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "frequency_range": RunParameterSpec(
            unit="GHz",
            value_type="np.arange",
            default=None,
            description=(
                "Drive frequency range as [start, stop, step] in GHz. Leave blank to use "
                "the connected control box's qubex default band with frequency_step."
            ),
        ),
        "frequency_step": RunParameterSpec(
            unit="GHz",
            value_type="float",
            default=DEFAULT_WINDOW_FREQUENCY_STEP,
            description=("Coarse drive frequency step in GHz used when frequency_range is blank."),
        ),
        "power_range": RunParameterSpec(
            unit="dB",
            value_type="np.arange",
            default=DEFAULT_WINDOW_POWER_RANGE,
            description=(
                "Few-power sweep as [start, stop, step] in dB (stop is exclusive). "
                "Default [-25, 0, 10] measures -25, -15, and -5 dB."
            ),
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=DEFAULT_WINDOW_SHOTS,
            description="Number of shots per drive frequency and power point",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=DEFAULT_WINDOW_INTERVAL,
            description="Time interval between shots",
        ),
        "simultaneous_drive": RunParameterSpec(
            unit="a.u.",
            value_type="bool",
            default=True,
            description=(
                "Whether control and readout pulses start together. "
                "False starts readout after the control pulse ends."
            ),
        ),
        "margin_ghz": RunParameterSpec(
            unit="GHz",
            value_type="float",
            default=DEFAULT_WINDOW_MARGIN_GHZ,
            description="Padding in GHz added to each side of the detected response cluster",
        ),
        "min_window_ghz": RunParameterSpec(
            unit="GHz",
            value_type="float",
            default=DEFAULT_MIN_WINDOW_GHZ,
            description=(
                "Minimum search window width in GHz so downstream 2D CheckQubitSpectroscopy "
                "retains enough off-resonant background"
            ),
        ),
        "min_response_score": RunParameterSpec(
            unit="a.u.",
            value_type="float",
            default=DEFAULT_MIN_RESPONSE_SCORE,
            description="Minimum trace score required to accept a power row's response",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "qubit_frequency_window_min": OutputParameterSpec(
            unit="GHz",
            description="Lower bound of the narrowed search range for CheckQubitSpectroscopy",
        ),
        "qubit_frequency_window_max": OutputParameterSpec(
            unit="GHz",
            description="Upper bound of the narrowed search range for CheckQubitSpectroscopy",
        ),
        "window_center_frequency": OutputParameterSpec(
            unit="GHz",
            description="Peak drive frequency of the dominant response cluster in the coarse sweep",
        ),
    }

    def _frequency_range(self) -> Any:
        parameter = self.run_parameters["frequency_range"]
        return None if parameter.value is None else parameter.get_value()

    def resolve_run_parameters(self, backend: QubexBackend, qid: str) -> None:
        """Populate the coarse drive sweep from the connected control box."""
        super().resolve_run_parameters(backend, qid)
        parameter = self.run_parameters["frequency_range"]
        if parameter.value is not None:
            return
        step = float(self.run_parameters["frequency_step"].get_value())
        if not math.isfinite(step) or step <= 0.0:
            raise ValueError(f"frequency_step must be finite and positive, got {step}")

        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        system = exp.ctx.experiment_system
        box = system.get_control_box_for_qubit(label)
        start, stop, _default_step = box.traits.default_control_frequency_range
        effective_stop = float(stop)
        get_readout_box = getattr(system, "get_readout_box_for_qubit", None)
        if callable(get_readout_box):
            readout_box = get_readout_box(label)
            readout_start = float(readout_box.traits.default_readout_frequency_range[0])
            if math.isfinite(readout_start):
                effective_stop = max(effective_stop, readout_start)
        parameter.value = (float(start), effective_stop, step)

    @staticmethod
    def _as_phase(values: Any) -> np.ndarray:
        array = np.asarray(values)
        if np.iscomplexobj(array):
            return np.asarray(np.angle(array), dtype=float)
        return np.asarray(array, dtype=float)

    @classmethod
    def _extract_2d_traces(
        cls,
        result: Any,
        expected_powers: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return ``(frequencies, powers, phase_rows)`` from ``qubit_spectroscopy``."""
        data = getattr(result, "data", result)
        if not isinstance(data, Mapping):
            raise ValueError("qubit_spectroscopy returned no data mapping")
        frequencies = np.asarray(data["frequency_range"], dtype=float).ravel()
        powers = (
            np.asarray(data["power_range"], dtype=float).ravel()
            if "power_range" in data
            else np.asarray(expected_powers, dtype=float).ravel()
        )
        if "data" in data:
            phase_rows = np.atleast_2d(cls._as_phase(data["data"]))
        elif "phases" in data:
            phase_rows = np.atleast_2d(cls._as_phase(data["phases"]))
        else:
            raise ValueError("qubit_spectroscopy result has no phase data")
        if phase_rows.shape != (powers.size, frequencies.size):
            raise ValueError(
                f"qubit_spectroscopy returned shape {phase_rows.shape}, "
                f"expected ({powers.size}, {frequencies.size})"
            )
        return frequencies, powers, phase_rows

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the fast few-power coarse spectroscopy sweep."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)

        readout_freq_param = self.input_parameters["readout_frequency"]
        if readout_freq_param is None or readout_freq_param.value is None:
            raise ValueError("readout_frequency input parameter is required")

        power_range = np.asarray(
            self.run_parameters["power_range"].get_value(), dtype=float
        ).ravel()
        if power_range.size == 0 or not np.all(np.isfinite(power_range)):
            raise ValueError("power_range must contain at least one finite power value")

        with self._modified_qubit_readout_frequencies(
            exp,
            qubit_label=label,
            frequency_overrides={"R" + label: float(readout_freq_param.value)},
        ):
            raw = exp.qubit_spectroscopy(
                label,
                simultaneous_drive=self.run_parameters["simultaneous_drive"].get_value(),
                frequency_range=self._frequency_range(),
                power_range=power_range,
                readout_amplitude=self._get_readout_amplitude_value(),
                readout_frequency=readout_freq_param.value,
                n_shots=self.run_parameters["shots"].get_value(),
                shot_interval=self.run_parameters["interval"].get_value(),
                plot=False,
                save_image=False,
            )

        frequencies, powers, phase_rows = self._extract_2d_traces(raw, power_range)
        self.save_calibration(backend)
        return RunResult(
            raw_result={
                "label": label,
                "frequencies": frequencies,
                "powers": powers,
                "phase_rows": phase_rows,
                "spectroscopy": raw,
            }
        )

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Estimate the narrowed search window and build the review figure."""
        del backend
        raw = run_result.raw_result
        label = str(raw["label"])
        frequencies = raw["frequencies"]
        powers = raw["powers"]
        phase_rows = raw["phase_rows"]

        window = estimate_qubit_frequency_window(
            frequencies,
            powers,
            phase_rows,
            margin_ghz=float(self.run_parameters["margin_ghz"].get_value()),
            min_window_ghz=float(self.run_parameters["min_window_ghz"].get_value()),
            min_response_score=float(self.run_parameters["min_response_score"].get_value()),
        )
        figure = create_qubit_frequency_window_figure(
            frequencies, powers, phase_rows, window, label
        )
        set_figure_role(figure, "marked")

        if (
            not window.succeeded
            or window.window_min is None
            or window.window_max is None
            or window.center_frequency is None
        ):
            error_msg = f"Failed to locate qubit frequency window for qid={qid}: {window.reason}"
            print(f"[ERROR] {error_msg}")
            return PostProcessResult(
                output_parameters={},
                figures=[figure],
                validation_error=error_msg,
            )

        output_parameters = copy.deepcopy(self.output_parameters)
        output_parameters["qubit_frequency_window_min"].value = window.window_min
        output_parameters["qubit_frequency_window_max"].value = window.window_max
        output_parameters["window_center_frequency"].value = window.center_frequency
        for parameter in output_parameters.values():
            parameter.execution_id = execution_id

        print(f"[{self.name}] qid={qid} {window.reason}")
        return PostProcessResult(output_parameters=output_parameters, figures=[figure])
