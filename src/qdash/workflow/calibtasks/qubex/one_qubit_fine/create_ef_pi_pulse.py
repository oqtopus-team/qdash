"""Calibrate the EF pi pulse."""

import math
from typing import ClassVar

from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, PI_DURATION
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL

from qdash.datamodel.task import InputParameterSpec, OutputParameterSpec, RunParameterSpec
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import QubexTask, readout_duration_run_parameter
from qdash.workflow.calibtasks.qubex.validation import (
    DEFAULT_RABI_R2_THRESHOLD,
    finite_value_error,
    first_validation_error,
    require_ef_configuration,
)
from qdash.workflow.engine.backend.qubex import QubexBackend


class CreateEFPIPulse(QubexTask):
    """Calibrate and store a flat-top EF pi pulse."""

    name: str = "CreateEFPIPulse"
    task_type: str = "qubit"
    r2_threshold: float = DEFAULT_RABI_R2_THRESHOLD
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "control_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("qubit_frequency",), unit="GHz"
        ),
        "control_frequency_ef": InputParameterSpec.required_database(
            fallback_parameter_names=("ef_frequency",), unit="GHz"
        ),
        "control_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "hpi_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "hpi_duration": InputParameterSpec.required_database(unit="ns"),
        "readout_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "readout_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("resonator_frequency",), unit="GHz"
        ),
        "ef_rabi_amplitude": InputParameterSpec.required_database(
            unit="a.u.", ui_group="EF Rabi normalization", ui_group_collapsed=True
        ),
        "ef_rabi_frequency": InputParameterSpec.required_database(
            unit="MHz", ui_group="EF Rabi normalization", ui_group_collapsed=True
        ),
        "ef_rabi_phase": InputParameterSpec.required_database(
            unit="a.u.", ui_group="EF Rabi normalization", ui_group_collapsed=True
        ),
        "ef_rabi_offset": InputParameterSpec.required_database(
            unit="a.u.", ui_group="EF Rabi normalization", ui_group_collapsed=True
        ),
        "ef_rabi_angle": InputParameterSpec.required_database(
            unit="rad", ui_group="EF Rabi normalization", ui_group_collapsed=True
        ),
        "ef_rabi_noise": InputParameterSpec.required_database(
            unit="a.u.", ui_group="EF Rabi normalization", ui_group_collapsed=True
        ),
        "ef_rabi_distance": InputParameterSpec.required_database(
            unit="a.u.", ui_group="EF Rabi normalization", ui_group_collapsed=True
        ),
        "ef_rabi_reference_phase": InputParameterSpec.required_database(
            unit="a.u.", ui_group="EF Rabi normalization", ui_group_collapsed=True
        ),
        "ef_rabi_r2": InputParameterSpec.required_database(
            ui_group="EF Rabi normalization", ui_group_collapsed=True
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_duration": readout_duration_run_parameter(),
        "ef_pi_duration": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=PI_DURATION,
            description="EF pi pulse duration",
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=CALIBRATION_SHOTS,
            description="Shots per EF pi calibration point",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=DEFAULT_INTERVAL,
            description="Time interval between shots",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "ef_pi_amplitude": OutputParameterSpec(unit="a.u.", description="EF pi amplitude"),
        "ef_pi_duration": OutputParameterSpec(unit="ns", description="EF pi duration"),
    }

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
                ef_label: self._get_calibration_value("control_frequency_ef"),
                exp.ctx.resolve_read_label(label): self._get_calibration_value("readout_frequency"),
            }
        ):
            result = exp.calibrate_ef_pi_pulse(
                targets=label,
                duration=self.run_parameters["ef_pi_duration"].get_value(),
                r2_threshold=self.r2_threshold,
                n_shots=self.run_parameters["shots"].get_value(),
                shot_interval=self.run_parameters["interval"].get_value(),
                plot=False,
            )
        measured_r2 = float(result.data[ef_label].r2)
        r2 = measured_r2 if math.isfinite(measured_r2) else None
        if r2 is not None and r2 > self.r2_threshold:
            self.save_calibration(backend)
        return RunResult(raw_result=result, r2={qid: r2})

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = self.get_experiment(backend)
        ef_label = exp.ctx.resolve_ef_label(self.get_qubit_label(backend, qid))
        data = run_result.raw_result.data[ef_label]
        amplitude = float(data.calib_value)
        duration = float(self.run_parameters["ef_pi_duration"].get_value())
        self.output_parameters["ef_pi_amplitude"].value = amplitude
        self.output_parameters["ef_pi_duration"].value = duration
        r2 = float(data.r2)
        r2_error = finite_value_error(r2, f"EF pi R² for {ef_label}", maximum=1.0)
        if r2_error is None and r2 <= self.r2_threshold:
            r2_error = f"EF pi R² must exceed {self.r2_threshold}: {r2}"
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id),
            figures=[data.fit()["fig"]],
            validation_error=first_validation_error(
                r2_error,
                finite_value_error(
                    amplitude, f"EF pi amplitude for {ef_label}", minimum=0, maximum=1
                ),
                finite_value_error(duration, f"EF pi duration for {ef_label}", minimum=0),
            ),
        )
