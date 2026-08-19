import logging
import math
from typing import Any, ClassVar

import plotly.graph_objects as go
from qubex.analysis import IQPlotter
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL, DEFAULT_READOUT_DURATION

from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
)
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend

DEFAULT_READOUT_AMPLITUDE = 0.2
DEFAULT_CONTROL_AMPLITUDE = 0.0125
CONTROL_AMPLITUDE_MIN = 1e-4
CONTROL_AMPLITUDE_MAX = 1.0

logger = logging.getLogger(__name__)


def _store_rabi_params(exp: Any, result: Any) -> None:
    """Store fitted Rabi parameters after converting NumPy scalars for JSON."""
    rabi_params = result.rabi_params
    float_fields = (
        "frequency",
        "amplitude",
        "phase",
        "offset",
        "noise",
        "angle",
        "distance",
        "r2",
        "reference_phase",
    )
    for rabi_param in rabi_params.values():
        for field_name in float_fields:
            value = getattr(rabi_param, field_name, None)
            if value is not None:
                setattr(rabi_param, field_name, float(value))
    exp.ctx.store_rabi_params(rabi_params)


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
    assert frequency is not None
    if float(frequency) <= 0:
        return f"CheckRabi produced non-positive frequency for {label}: {frequency}"

    for field_name in ("amplitude", "phase", "offset", "angle", "noise", "distance"):
        error = _finite_rabi_validation_error(
            getattr(rabi_param, field_name, None), field_name, label
        )
        if error is not None:
            return error

    r2 = getattr(rabi_param, "r2", None)
    error = _finite_rabi_validation_error(r2, "r2", label)
    if error is not None:
        return error
    assert r2 is not None
    if float(r2) < 0.6:
        return f"CheckRabi produced rabi_r2 below 0.6 for {label}: {r2}"
    return None


class CheckRabi(QubexTask):
    """Task to check the Rabi oscillation."""

    name: str = "CheckRabi"
    task_type: str = "qubit"
    r2_threshold: float = 0.6
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "qubit_frequency": InputParameterSpec.required_database(),
        "control_amplitude": InputParameterSpec.database_or_default(
            default=DEFAULT_CONTROL_AMPLITUDE,
            greater_than=CONTROL_AMPLITUDE_MIN,
            less_than=CONTROL_AMPLITUDE_MAX,
            unit="a.u.",
            description="Control pulse amplitude",
        ),
        "readout_frequency": InputParameterSpec.required_database(),
        "readout_amplitude": InputParameterSpec.database_or_default(
            default=DEFAULT_READOUT_AMPLITUDE,
            unit="a.u.",
            description="Readout amplitude",
        ),
        "readout_length": InputParameterSpec.database_or_default(
            default=DEFAULT_READOUT_DURATION,
            unit="ns",
            description="Readout pulse length",
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "time_range": RunParameterSpec(
            unit="ns",
            value_type="range",
            default=(0, 401, 8),
            description="Time range for Rabi oscillation",
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=CALIBRATION_SHOTS,
            description="Number of shots for Rabi oscillation",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="int",
            default=DEFAULT_INTERVAL,
            description="Time interval for Rabi oscillation",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "rabi_amplitude": OutputParameterSpec(
            unit="a.u.", description="Rabi oscillation amplitude"
        ),
        "rabi_frequency": OutputParameterSpec(unit="MHz", description="Rabi oscillation frequency"),
        "rabi_phase": OutputParameterSpec(unit="a.u.", description="Rabi oscillation phase"),
        "rabi_offset": OutputParameterSpec(unit="a.u.", description="Rabi oscillation offset"),
        "rabi_angle": OutputParameterSpec(unit="degree", description="Rabi angle (in degree)"),
        "rabi_noise": OutputParameterSpec(unit="a.u.", description="Rabi oscillation noise"),
        "rabi_distance": OutputParameterSpec(unit="a.u.", description="Rabi distance"),
        "rabi_reference_phase": OutputParameterSpec(
            unit="a.u.", description="Rabi reference phase"
        ),
        "rabi_r2": OutputParameterSpec(unit="", description="Rabi fit R²"),
        "control_amplitude": OutputParameterSpec(
            unit="a.u.", description="Control pulse amplitude"
        ),
        "maximum_rabi_frequency": OutputParameterSpec(
            unit="MHz/a.u.", description="Maximum Rabi frequency per unit control amplitude"
        ),
    }

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
        self.output_parameters["rabi_r2"].value = result.rabi_params[label].r2
        control_amplitude_param = self.input_parameters["control_amplitude"]
        assert control_amplitude_param is not None
        default_amp = control_amplitude_param.value
        rabi_frequency = self.output_parameters["rabi_frequency"].value
        if default_amp is None or rabi_frequency is None:
            raise ValueError("Rabi parameters were not resolved during preprocessing")
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
        return PostProcessResult(
            output_parameters=output_parameters,
            figures=figures,
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
            store_params=False,
        )

        _store_rabi_params(exp, result)
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
