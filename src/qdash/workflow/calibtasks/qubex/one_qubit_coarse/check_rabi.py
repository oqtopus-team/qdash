import logging
import math
from typing import Any, ClassVar

import plotly.graph_objects as go
from qubex.analysis import IQPlotter
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL, DEFAULT_READOUT_DURATION

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend

DEFAULT_READOUT_AMPLITUDE = 0.2
DEFAULT_CONTROL_AMPLITUDE = 0.0125
CONTROL_AMPLITUDE_MIN = 1e-4
CONTROL_AMPLITUDE_MAX = 1.0

logger = logging.getLogger(__name__)


def _extract_rabi_r2_candidates(result: Any, label: str) -> dict[str, float | None]:
    """Extract Rabi R² candidates from data/fit and rabi_params."""
    candidates: dict[str, float | None] = {
        "data_r2": None,
        "fit_r2": None,
        "rabi_params_r2": None,
    }

    data_by_label = getattr(result, "data", None) or {}
    data = data_by_label.get(label) if hasattr(data_by_label, "get") else None
    if data is not None:
        data_r2 = getattr(data, "r2", None)
        if data_r2 is not None:
            candidates["data_r2"] = float(data_r2)
        fit = getattr(data, "fit", None)
        if callable(fit):
            fit_result = fit()
            if isinstance(fit_result, dict):
                fit_r2 = fit_result.get("r2")
                if fit_r2 is not None:
                    candidates["fit_r2"] = float(fit_r2)

    rabi_params = getattr(result, "rabi_params", None) or {}
    rabi_param = rabi_params.get(label) if hasattr(rabi_params, "get") else None
    rabi_params_r2 = getattr(rabi_param, "r2", None)
    if rabi_params_r2 is not None:
        candidates["rabi_params_r2"] = float(rabi_params_r2)

    return candidates


def _extract_rabi_r2(result: Any, label: str) -> float | None:
    """Extract the Rabi fit R² used in the saved fit figure."""
    candidates = _extract_rabi_r2_candidates(result, label)
    return (
        candidates["data_r2"]
        if candidates["data_r2"] is not None
        else candidates["fit_r2"]
        if candidates["fit_r2"] is not None
        else candidates["rabi_params_r2"]
    )


def _finite_rabi_validation_error(value: Any, field_name: str, label: str) -> str | None:
    if value is None:
        return f"CheckRabi produced no {field_name} for {label}"
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        return f"CheckRabi produced non-finite {field_name} for {label}: {value}"
    return None


def _rabi_validation_error(result: Any, label: str) -> str | None:
    rabi_params = getattr(result, "rabi_params", None) or {}
    rabi_param = rabi_params.get(label) if hasattr(rabi_params, "get") else None
    if rabi_param is None:
        return f"CheckRabi produced no rabi_params for {label}"

    frequency = getattr(rabi_param, "frequency", None)
    error = _finite_rabi_validation_error(frequency, "frequency", label)
    if error is not None:
        return error
    if float(frequency) <= 0:
        return f"CheckRabi produced non-positive frequency for {label}: {frequency}"

    for field_name in ("amplitude", "phase", "offset", "angle", "noise", "distance"):
        error = _finite_rabi_validation_error(getattr(rabi_param, field_name, None), field_name, label)
        if error is not None:
            return error
    return None


class CheckRabi(QubexTask):
    """Task to check the Rabi oscillation."""

    name: str = "CheckRabi"
    task_type: str = "qubit"
    r2_threshold: float = 0.6
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        "qubit_frequency": None,
        "control_amplitude": None,
        "readout_frequency": None,
        "readout_amplitude": ParameterModel(
            value=DEFAULT_READOUT_AMPLITUDE, unit="a.u.", description="Readout amplitude"
        ),
        "readout_length": ParameterModel(
            value=DEFAULT_READOUT_DURATION, unit="ns", description="Readout pulse length"
        ),
    }
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "time_range": RunParameterModel(
            unit="ns",
            value_type="range",
            value=(0, 401, 8),
            description="Time range for Rabi oscillation",
        ),
        "shots": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots for Rabi oscillation",
        ),
        "interval": RunParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for Rabi oscillation",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "rabi_amplitude": ParameterModel(unit="a.u.", description="Rabi oscillation amplitude"),
        "rabi_frequency": ParameterModel(unit="MHz", description="Rabi oscillation frequency"),
        "rabi_phase": ParameterModel(unit="a.u.", description="Rabi oscillation phase"),
        "rabi_offset": ParameterModel(unit="a.u.", description="Rabi oscillation offset"),
        "rabi_angle": ParameterModel(unit="degree", description="Rabi angle (in degree)"),
        "rabi_noise": ParameterModel(unit="a.u.", description="Rabi oscillation noise"),
        "rabi_distance": ParameterModel(unit="a.u.", description="Rabi distance"),
        "rabi_reference_phase": ParameterModel(unit="a.u.", description="Rabi reference phase"),
        "control_amplitude": ParameterModel(unit="a.u.", description="Control pulse amplitude"),
        "maximum_rabi_frequency": ParameterModel(
            unit="MHz/a.u.", description="Maximum Rabi frequency per unit control amplitude"
        ),
    }

    def preprocess(self, backend: QubexBackend, qid: str) -> PreProcessResult:
        """Preprocess with control_amplitude validation."""
        result = super().preprocess(backend, qid)
        param = self.input_parameters.get("control_amplitude")
        value = param.value if param is not None else None
        if (
            value is None
            or not isinstance(value, (int, float))
            or math.isnan(value)
            or value <= CONTROL_AMPLITUDE_MIN
            or value >= CONTROL_AMPLITUDE_MAX
        ):
            print(
                f"control_amplitude={value} is out of range "
                f"({CONTROL_AMPLITUDE_MIN}, {CONTROL_AMPLITUDE_MAX}), "
                f"using default={DEFAULT_CONTROL_AMPLITUDE}"
            )
            if param is None:
                self.input_parameters["control_amplitude"] = ParameterModel(
                    value=DEFAULT_CONTROL_AMPLITUDE,
                    unit="a.u.",
                    description="Control pulse amplitude (default)",
                )
            else:
                param.value = DEFAULT_CONTROL_AMPLITUDE
        return result

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["rabi_amplitude"].value = result.rabi_params[label].amplitude
        self.output_parameters["rabi_amplitude"].error = result.data[label].fit()["amplitude_err"]
        self.output_parameters["rabi_frequency"].value = (
            result.rabi_params[label].frequency * 1000
        )  # convert to MHz
        self.output_parameters["rabi_frequency"].error = (
            result.data[label].fit()["frequency_err"] * 1000
        )
        self.output_parameters["rabi_phase"].value = result.rabi_params[label].phase
        self.output_parameters["rabi_phase"].error = result.data[label].fit()["phase_err"]
        self.output_parameters["rabi_offset"].value = result.rabi_params[label].offset
        self.output_parameters["rabi_offset"].error = result.data[label].fit()["offset_err"]
        self.output_parameters["rabi_angle"].value = result.rabi_params[label].angle
        self.output_parameters["rabi_noise"].value = result.rabi_params[label].noise
        self.output_parameters["rabi_distance"].value = result.rabi_params[label].distance
        self.output_parameters["rabi_reference_phase"].value = result.rabi_params[
            label
        ].reference_phase
        control_amplitude_param = self.input_parameters["control_amplitude"]
        assert control_amplitude_param is not None
        default_amp = control_amplitude_param.value
        rabi_frequency = self.output_parameters["rabi_frequency"].value
        print("rabi frequency (MHz): ", self.output_parameters["rabi_frequency"].value)
        print("default amplitude (a.u.): ", control_amplitude_param.value)
        maximum_rabi_frequency = rabi_frequency / default_amp
        ratio = maximum_rabi_frequency / 1000
        self.output_parameters["control_amplitude"].value = min(0.0125 / ratio, 0.99)
        self.output_parameters["maximum_rabi_frequency"].value = maximum_rabi_frequency
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.data[label].fit()["fig"]]
        exp = self.get_experiment(backend)
        iq_plotter = IQPlotter(state_centers=exp.state_centers)
        iq_plotter.update({label: result.data[label].data})
        figures.append(go.Figure(iq_plotter._widget.to_dict()))
        raw_data = [result.data[label].data]
        return PostProcessResult(
            output_parameters=output_parameters,
            figures=figures,
            raw_data=raw_data,
            validation_error=_rabi_validation_error(result, label),
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)

        control_amplitude_param = self.input_parameters["control_amplitude"]
        qubit_frequency_param = self.input_parameters["qubit_frequency"]
        readout_amplitude_param = self.input_parameters["readout_amplitude"]
        assert control_amplitude_param is not None
        assert qubit_frequency_param is not None
        assert readout_amplitude_param is not None

        # Get readout_amplitude from input_parameters (loaded from DB)
        readout_amp = readout_amplitude_param.value
        exp.params.readout_amplitude[label] = readout_amp

        print(
            f"[run] CheckRabi params for {label}: "
            f"control_amplitude={control_amplitude_param.value}, "
            f"qubit_frequency={qubit_frequency_param.value}, "
            f"readout_amplitude={readout_amp}"
        )

        result = exp.obtain_rabi_params(
            amplitudes={label: control_amplitude_param.value},
            frequencies={label: qubit_frequency_param.value},
            time_range=self.run_parameters["time_range"].get_value(),
            n_shots=self.run_parameters["shots"].get_value(),
            shot_interval=self.run_parameters["interval"].get_value(),
            targets=label,
        )

        self.save_calibration(backend)
        r2_candidates = _extract_rabi_r2_candidates(result, label)
        r2 = _extract_rabi_r2(result, label)
        logger.warning(
            "CheckRabi R² candidates for qid=%s label=%s threshold=%.4f "
            "selected=%s data_r2=%s fit_r2=%s rabi_params_r2=%s",
            qid,
            label,
            self.r2_threshold,
            r2,
            r2_candidates["data_r2"],
            r2_candidates["fit_r2"],
            r2_candidates["rabi_params_r2"],
        )
        return RunResult(raw_result=result, r2={qid: r2})
