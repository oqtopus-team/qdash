"""Readout measurement-induced state-transition characterization task."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

import numpy as np
import numpy.typing as npt
from qubex.core import DataModel
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL

from qdash.datamodel.task import InputParameterSpec, OutputParameterSpec, RunParameterSpec
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.calibtasks.qubex.validation import require_ef_configuration
from qdash.workflow.engine.progress import ProgressPlan

if TYPE_CHECKING:
    import plotly.graph_objects as go

    from qdash.workflow.engine.backend.qubex import QubexBackend


DEFAULT_MEASUREMENT_SHOTS = 4096
DEFAULT_CALIBRATION_SHOTS = 8192


class ReadoutMISTData(DataModel):
    """NetCDF artifact containing processed MIST measurements and fit results."""

    target: str
    repetition_counts: npt.NDArray[Any]
    measurements: dict[str, Any]
    analysis: dict[str, Any]
    measurement_options: dict[str, Any]
    analysis_options: dict[str, Any]
    readout_cycle_timing: dict[str, Any]


@dataclass(frozen=True)
class _ReadoutMISTRunPayload:
    """Qubex result paired with the resolved target omitted from its data."""

    result: Any
    target: str


class CheckReadoutMIST(QubexTask):
    """Characterize effective GEF transitions caused by a readout cycle."""

    name: str = "CheckReadoutMIST"
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
        "cycle_gap": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=0.0,
            description="Trailing gap appended to each configured readout cycle",
        ),
        "measure_reference": RunParameterSpec(
            unit="a.u.",
            value_type="bool",
            default=True,
            description="Measure and fit a duration-matched blank reference cycle",
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
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {}

    def _run_kwargs(self) -> dict[str, Any]:
        """Return validated options passed directly to Qubex."""
        cycle_gap = float(self.run_parameters["cycle_gap"].get_value())
        measure_reference = self.run_parameters["measure_reference"].get_value()
        shots = int(self.run_parameters["shots"].get_value())
        calibration_shots = int(self.run_parameters["calibration_shots"].get_value())
        interval = float(self.run_parameters["interval"].get_value())
        if not math.isfinite(cycle_gap) or cycle_gap < 0:
            raise ValueError("cycle_gap must be finite and nonnegative")
        if not isinstance(measure_reference, bool):
            raise TypeError("measure_reference must be boolean")
        if shots < 2:
            raise ValueError("shots must be at least two")
        if calibration_shots < 2:
            raise ValueError("calibration_shots must be at least two")
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("interval must be finite and positive")
        return {
            "cycle_gap_ns": cycle_gap,
            "measure_reference": measure_reference,
            "gef_measurement_n_shots": shots,
            "gef_calibration_n_shots": calibration_shots,
            "shot_interval": interval,
            "plot": False,
        }

    def get_progress_plan(self) -> ProgressPlan:
        """Count the GEF calibration and population-acquisition sweeps."""
        return ProgressPlan(2, 2)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run one-target readout MIST characterization."""
        from qubex.contrib import characterize_readout_mist

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
            result = characterize_readout_mist(
                exp,
                target=label,
                **run_options,
            )
        return RunResult(raw_result=_ReadoutMISTRunPayload(result=result, target=label))

    @staticmethod
    def _payload(run_result: RunResult) -> _ReadoutMISTRunPayload:
        """Return the validated task-specific run payload."""
        payload = run_result.raw_result
        if not isinstance(payload, _ReadoutMISTRunPayload):
            raise TypeError("Unsupported readout MIST run payload")
        return payload

    @staticmethod
    def _mapping(value: Any, name: str) -> Mapping[str, Any]:
        """Return a required Qubex result mapping."""
        if not isinstance(value, Mapping):
            raise TypeError(f"Readout MIST result field {name!r} must be a mapping")
        return value

    @staticmethod
    def _dataclass_mapping(value: Any, name: str) -> dict[str, Any]:
        """Convert one processed Qubex dataclass to a serializable mapping."""
        if isinstance(value, type) or not is_dataclass(value):
            raise TypeError(f"Readout MIST result field {name!r} must be a dataclass")
        return asdict(cast("Any", value))

    def extract_raw_data(self, run_result: RunResult) -> list[Any]:
        """Store processed measurements and fits while excluding raw IQ and schedules."""
        payload = self._payload(run_result)
        data = self._mapping(payload.result.data, "data")
        measurements = self._dataclass_mapping(data["measurements"], "measurements")
        artifact = ReadoutMISTData(
            target=payload.target,
            repetition_counts=np.asarray(measurements["repetition_counts"]),
            measurements=measurements,
            analysis=self._dataclass_mapping(data["analysis"], "analysis"),
            measurement_options=dict(
                self._mapping(data["measurement_options"], "measurement_options")
            ),
            analysis_options=dict(self._mapping(data["analysis_options"], "analysis_options")),
            readout_cycle_timing=dict(
                self._mapping(data["readout_cycle_timing"], "readout_cycle_timing")
            ),
        )
        return [artifact]

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Retain both diagnostic figures and require all requested fits to succeed."""
        del backend, execution_id, qid
        result = self._payload(run_result).result
        data = self._mapping(result.data, "data")
        analysis = data["analysis"]
        validation_error = None
        if not analysis.actual.success:
            validation_error = f"Readout MIST actual fit failed: {analysis.actual.message}"
        elif analysis.reference is not None and not analysis.reference.success:
            validation_error = f"Readout MIST reference fit failed: {analysis.reference.message}"

        figures_by_name = result.figures or {}
        populations = figures_by_name.get("populations")
        if populations is None:
            populations = result.figure
        transition_matrix = figures_by_name.get("transition_matrix")
        figures: list[go.Figure] = [
            figure for figure in (populations, transition_matrix) if figure is not None
        ]
        return PostProcessResult(
            output_parameters={},
            figures=figures,
            validation_error=validation_error,
        )
