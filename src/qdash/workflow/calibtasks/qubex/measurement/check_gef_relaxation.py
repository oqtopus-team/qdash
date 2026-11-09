"""Continuous-time GEF relaxation characterization task."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from numbers import Real
from typing import TYPE_CHECKING, Any, ClassVar, cast

import numpy as np
import numpy.typing as npt
from qubex.core import DataModel
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL

from qdash.datamodel.task import InputParameterSpec, OutputParameterSpec, RunParameterSpec
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import QubexTask, readout_duration_run_parameter
from qdash.workflow.calibtasks.qubex.validation import require_ef_configuration
from qdash.workflow.engine.progress import ProgressPlan

if TYPE_CHECKING:
    import plotly.graph_objects as go

    from qdash.workflow.engine.backend.qubex import QubexBackend


DEFAULT_MEASUREMENT_SHOTS = 4096
DEFAULT_CALIBRATION_SHOTS = 8192
_NS_TO_US = 1e-3
# QDash metric names mapped to the Qubex ``derived_times_ns`` keys they publish.
# Qubex names directional times ``t1_<from>_to_<to>``; QDash keeps the existing ``t1``
# metric and uses ``t1_fe``/``t1_fg``. The stored artifact keeps the Qubex key names.
_OUTPUT_TO_QUBEX = {
    "t1": "t1_e_to_g",
    "t1_fe": "t1_f_to_e",
    "t1_fg": "t1_f_to_g",
}


class GEFRelaxationData(DataModel):
    """NetCDF artifact containing processed GEF relaxation measurements and fit results."""

    target: str
    time_ns: npt.NDArray[Any]
    measurements: dict[str, Any]
    analysis: dict[str, Any]
    measurement_options: dict[str, Any]
    analysis_options: dict[str, Any]


@dataclass(frozen=True)
class _GEFRelaxationRunPayload:
    """Qubex result paired with the resolved target used by this task."""

    result: Any
    target: str


class CheckGEFRelaxation(QubexTask):
    """Characterize continuous-time transitions in the GEF manifold."""

    name: str = "CheckGEFRelaxation"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "control_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("qubit_frequency",),
            unit="GHz",
            greater_than=0,
            description="Calibrated GE control frequency",
        ),
        "control_frequency_ef": InputParameterSpec.required_database(
            fallback_parameter_names=("ef_frequency",),
            unit="GHz",
            greater_than=0,
            description="Calibrated EF control frequency",
        ),
        "readout_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("resonator_frequency",),
            unit="GHz",
            greater_than=0,
            description="Calibrated readout frequency",
        ),
        "readout_amplitude": InputParameterSpec.required_database(
            unit="a.u.",
            greater_than=0,
            less_than_or_equal=1,
            description="Calibrated readout amplitude",
        ),
        "pi_amplitude": InputParameterSpec.required_database(
            unit="a.u.",
            greater_than=0,
            description="Calibrated GE pi-pulse amplitude",
        ),
        "pi_duration": InputParameterSpec.required_database(
            parameter_aliases=("pi_length",),
            unit="ns",
            greater_than=0,
            description="Calibrated GE pi-pulse duration",
        ),
        "ef_pi_amplitude": InputParameterSpec.required_database(
            unit="a.u.",
            greater_than=0,
            description="Calibrated EF pi-pulse amplitude",
        ),
        "ef_pi_duration": InputParameterSpec.required_database(
            unit="ns",
            greater_than=0,
            description="Calibrated EF pi-pulse duration",
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_duration": readout_duration_run_parameter(),
        "time_range": RunParameterSpec(
            unit="ns",
            value_type="np.logspace",
            default=(np.log10(200.0), np.log10(200_000.0), 18),
            description="Positive GEF relaxation delays; zero is added automatically",
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=DEFAULT_MEASUREMENT_SHOTS,
            description="Shots for each GEF population measurement",
        ),
        "calibration_shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=DEFAULT_CALIBRATION_SHOTS,
            description="Shots for each shared GEF calibration configuration",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=DEFAULT_INTERVAL,
            description="Interval between shots",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "t1": OutputParameterSpec(
            unit="μs",
            description="Directional e-to-g relaxation time from the GEF model",
        ),
        "t1_fe": OutputParameterSpec(
            unit="μs",
            description="Inverse direct f-to-e transition rate",
        ),
        "t1_fg": OutputParameterSpec(
            unit="μs",
            description="Inverse direct f-to-g transition rate",
        ),
    }

    def _run_kwargs(self) -> dict[str, Any]:
        """Return validated options passed directly to Qubex."""
        supplied_time = self.run_parameters["time_range"].get_value()
        object_time = np.asarray(supplied_time, dtype=object)
        if object_time.ndim != 1 or any(
            isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
            for value in object_time
        ):
            raise TypeError("time_range must be a one-dimensional sequence of real numbers")
        positive_time_range = np.asarray(supplied_time, dtype=np.float64)
        if (
            positive_time_range.size < 4
            or not np.all(np.isfinite(positive_time_range))
            or np.any(positive_time_range <= 0.0)
            or np.any(np.diff(positive_time_range) <= 0.0)
        ):
            raise ValueError(
                "time_range must contain at least four strictly increasing finite, "
                "strictly positive values; zero is added automatically"
            )
        time_range = np.concatenate(([0.0], positive_time_range))
        shots = int(self.run_parameters["shots"].get_value())
        calibration_shots = int(self.run_parameters["calibration_shots"].get_value())
        interval = float(self.run_parameters["interval"].get_value())
        if shots < 2:
            raise ValueError("shots must be at least two")
        if calibration_shots < 2:
            raise ValueError("calibration_shots must be at least two")
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("interval must be finite and positive")
        return {
            "time_range": time_range.tolist(),
            "gef_measurement_n_shots": shots,
            "gef_calibration_n_shots": calibration_shots,
            "shot_interval": interval,
            "plot": False,
        }

    def get_progress_plan(self) -> ProgressPlan:
        """Count the GEF calibration and population-acquisition sweeps."""
        return ProgressPlan(2, 2)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run one-target continuous-time GEF relaxation characterization."""
        from qubex.contrib import characterize_gef_relaxation

        run_options = self._run_kwargs()
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        require_ef_configuration(exp, label)
        exp.params.readout_amplitude[label] = self._get_calibration_value("readout_amplitude")
        with exp.modified_frequencies(
            {
                exp.ctx.resolve_ge_label(label): self._get_calibration_value("control_frequency"),
                exp.ctx.resolve_ef_label(label): self._get_calibration_value(
                    "control_frequency_ef"
                ),
                exp.ctx.resolve_read_label(label): self._get_calibration_value("readout_frequency"),
            }
        ):
            result = characterize_gef_relaxation(
                exp,
                targets=[label],
                **run_options,
            )
        return RunResult(raw_result=_GEFRelaxationRunPayload(result=result, target=label))

    @staticmethod
    def _payload(run_result: RunResult) -> _GEFRelaxationRunPayload:
        """Return the validated task-specific run payload."""
        payload = run_result.raw_result
        if not isinstance(payload, _GEFRelaxationRunPayload):
            raise TypeError("Unsupported GEF relaxation run payload")
        return payload

    @staticmethod
    def _mapping(value: Any, name: str) -> Mapping[str, Any]:
        """Return a required Qubex result mapping."""
        if not isinstance(value, Mapping):
            raise TypeError(f"GEF relaxation result field {name!r} must be a mapping")
        return value

    @staticmethod
    def _dataclass_mapping(value: Any, name: str) -> dict[str, Any]:
        """Convert one processed Qubex dataclass to a serializable mapping."""
        if isinstance(value, type) or not is_dataclass(value):
            raise TypeError(f"GEF relaxation result field {name!r} must be a dataclass")
        return asdict(cast("Any", value))

    def extract_raw_data(self, run_result: RunResult) -> list[Any]:
        """Store processed measurements and fits while excluding raw IQ."""
        payload = self._payload(run_result)
        data = self._mapping(payload.result.data, "data")
        measurements_by_target = self._mapping(data["measurements"], "measurements")
        analysis_by_target = self._mapping(data["analysis"], "analysis")
        measurements = self._dataclass_mapping(
            measurements_by_target[payload.target], "measurements[target]"
        )
        artifact = GEFRelaxationData(
            target=payload.target,
            time_ns=np.asarray(measurements["time_ns"]),
            measurements=measurements,
            analysis=self._dataclass_mapping(
                analysis_by_target[payload.target], "analysis[target]"
            ),
            measurement_options=dict(
                self._mapping(data["measurement_options"], "measurement_options")
            ),
            analysis_options=dict(self._mapping(data["analysis_options"], "analysis_options")),
        )
        return [artifact]

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Publish three directional times only when the complete fit is usable."""
        del backend, qid
        payload = self._payload(run_result)
        result = payload.result
        data = self._mapping(result.data, "data")
        analysis_by_target = self._mapping(data["analysis"], "analysis")
        fit = analysis_by_target[payload.target]

        figures_by_name = result.figures or {}
        populations_figure = figures_by_name.get(f"{payload.target}/populations")
        if populations_figure is None:
            populations_figure = result.figure
        figures: list[go.Figure] = [
            figure
            for figure in (
                populations_figure,
                figures_by_name.get(f"{payload.target}/rates"),
            )
            if figure is not None
        ]

        validation_error = self._fit_validation_error(fit)
        if validation_error is not None:
            return PostProcessResult(
                output_parameters={},
                figures=figures,
                validation_error=validation_error,
            )

        for output_name, qubex_name in _OUTPUT_TO_QUBEX.items():
            estimate = fit.derived_times_ns[qubex_name]
            self.output_parameters[output_name].value = float(estimate.value) * _NS_TO_US
            self.output_parameters[output_name].error = float(estimate.standard_error) * _NS_TO_US
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id),
            figures=figures,
        )

    @staticmethod
    def _fit_validation_error(fit: Any) -> str | None:
        """Return the first reason a fit cannot publish all requested metrics."""
        if not fit.success:
            return f"GEF relaxation fit failed: {fit.message}"
        for output_name, qubex_name in _OUTPUT_TO_QUBEX.items():
            name = f"{output_name} (Qubex {qubex_name})"
            estimate = fit.derived_times_ns.get(qubex_name)
            if estimate is None:
                return f"GEF relaxation {name} is missing"
            if not estimate.estimable:
                return f"GEF relaxation {name} is not estimable"
            if not math.isfinite(float(estimate.value)):
                return f"GEF relaxation {name} is non-finite"
            if estimate.value <= 0:
                return f"GEF relaxation {name} must be positive"
            if estimate.standard_error is None:
                return f"GEF relaxation {name} standard error is missing"
            if not math.isfinite(float(estimate.standard_error)):
                return f"GEF relaxation {name} standard error is non-finite"
            if estimate.standard_error < 0:
                return f"GEF relaxation {name} standard error must be nonnegative"
        return None
