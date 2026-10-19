"""Measure and persist EF Rabi parameters."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, ClassVar

from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL

from qdash.datamodel.task import InputParameterSpec, OutputParameterSpec, RunParameterSpec
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import (
    QubexTask,
    readout_duration_run_parameter,
    required_rabi_normalization_inputs,
)
from qdash.workflow.calibtasks.qubex.validation import (
    DEFAULT_RABI_R2_THRESHOLD,
    finite_value_error,
    first_validation_error,
    require_ef_configuration,
)

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckEFRabi(QubexTask):
    """Measure the EF Rabi oscillation using the Qubex session's GE pulses."""

    name: str = "CheckEFRabi"
    task_type: str = "qubit"
    r2_threshold: float = DEFAULT_RABI_R2_THRESHOLD

    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        **required_rabi_normalization_inputs(),
        "control_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("qubit_frequency",), unit="GHz"
        ),
        "ef_frequency": InputParameterSpec.required_database(unit="GHz"),
        "hpi_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "hpi_duration": InputParameterSpec.required_database(unit="ns"),
        "readout_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "readout_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("resonator_frequency",), unit="GHz"
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_duration": readout_duration_run_parameter(),
        "time_range": RunParameterSpec(
            unit="ns",
            value_type="range",
            default=(0, 401, 8),
            description="EF Rabi drive-time sweep",
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=CALIBRATION_SHOTS,
            description="Shots per EF Rabi point",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=DEFAULT_INTERVAL,
            description="Time interval between shots",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "ef_rabi_amplitude": OutputParameterSpec(unit="a.u.", description="EF Rabi amplitude"),
        "ef_rabi_frequency": OutputParameterSpec(unit="MHz", description="EF Rabi frequency"),
        "ef_rabi_phase": OutputParameterSpec(unit="a.u.", description="EF Rabi phase"),
        "ef_rabi_offset": OutputParameterSpec(unit="a.u.", description="EF Rabi offset"),
        "ef_rabi_angle": OutputParameterSpec(unit="rad", description="EF Rabi angle"),
        "ef_rabi_noise": OutputParameterSpec(unit="a.u.", description="EF Rabi fit noise"),
        "ef_rabi_distance": OutputParameterSpec(unit="a.u.", description="EF IQ distance"),
        "ef_rabi_reference_phase": OutputParameterSpec(
            unit="a.u.", description="EF Rabi reference phase"
        ),
        "ef_rabi_r2": OutputParameterSpec(unit="", description="EF Rabi fit R²"),
    }

    def _validation_error(self, rabi_param: object, label: str) -> str | None:
        values = {
            name: getattr(rabi_param, name)
            for name in (
                "amplitude",
                "frequency",
                "phase",
                "offset",
                "angle",
                "noise",
                "distance",
                "reference_phase",
                "r2",
            )
        }
        error = first_validation_error(
            *(
                finite_value_error(value, f"EF Rabi {name} for {label}")
                for name, value in values.items()
            )
        )
        if error is not None:
            return error
        if float(values["frequency"]) <= 0:
            return f"EF Rabi frequency must be positive for {label}: {values['frequency']}"
        if float(values["r2"]) <= self.r2_threshold:
            return f"EF Rabi R² must exceed {self.r2_threshold} for {label}: {values['r2']}"
        return None

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        require_ef_configuration(exp, label)
        exp.params.control_amplitude[label] = self._get_calibration_value("control_amplitude")
        exp.params.readout_amplitude[label] = self._get_calibration_value("readout_amplitude")
        ef_label = exp.ctx.resolve_ef_label(label)
        with exp.modified_frequencies(
            {
                exp.ctx.resolve_ge_label(label): self._get_calibration_value("control_frequency"),
                ef_label: self._get_calibration_value("ef_frequency"),
                exp.ctx.resolve_read_label(label): self._get_calibration_value("readout_frequency"),
            }
        ):
            # TODO(qubex): expose explicit GE preparation waveforms through
            # obtain_ef_rabi_params() and ef_rabi_experiment(). The current API
            # prepares |e> with x180(), which prefers stored DRAG PI, PI, then
            # DRAG HPI over the HPI restored from this task's recorded inputs.
            # Once supported, pass a FlatTop built from hpi_amplitude,
            # hpi_duration, and HPI_RAMPTIME, repeated twice. Do not clear note
            # entries or patch x180(): those mutate shared session state.
            result = exp.obtain_ef_rabi_params(
                targets=label,
                time_range=self.run_parameters["time_range"].get_value(),
                n_shots=self.run_parameters["shots"].get_value(),
                shot_interval=self.run_parameters["interval"].get_value(),
                plot=False,
            )
        rabi_param = result.rabi_params[ef_label]
        r2 = float(rabi_param.r2) if math.isfinite(float(rabi_param.r2)) else None
        if self._validation_error(rabi_param, ef_label) is None:
            self.save_calibration(backend)
        return RunResult(raw_result=result, r2={qid: r2})

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = self.get_experiment(backend)
        ef_label = exp.ctx.resolve_ef_label(self.get_qubit_label(backend, qid))
        result = run_result.raw_result
        param = result.rabi_params[ef_label]
        values = {
            "ef_rabi_amplitude": param.amplitude,
            "ef_rabi_frequency": 1000.0 * param.frequency,
            "ef_rabi_phase": param.phase,
            "ef_rabi_offset": param.offset,
            "ef_rabi_angle": param.angle,
            "ef_rabi_noise": param.noise,
            "ef_rabi_distance": param.distance,
            "ef_rabi_reference_phase": param.reference_phase,
            "ef_rabi_r2": param.r2,
        }
        for name, value in values.items():
            self.output_parameters[name].value = float(value)
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id),
            figures=[result.data[ef_label].fit()["fig"]],
            validation_error=self._validation_error(param, ef_label),
        )
