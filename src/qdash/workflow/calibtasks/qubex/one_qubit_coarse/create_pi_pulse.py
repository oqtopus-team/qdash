from typing import ClassVar

from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, PI_DURATION
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
from qdash.workflow.calibtasks.qubex.validation import finite_value_error
from qdash.workflow.engine.backend.qubex import QubexBackend


class CreatePIPulse(QubexTask):
    """Task to create the pi pulse."""

    name: str = "CreatePIPulse"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "qubit_frequency": InputParameterSpec.required_database(),
        "control_amplitude": InputParameterSpec.required_database(),
        "readout_amplitude": InputParameterSpec.required_database(),
        "readout_frequency": InputParameterSpec.required_database(),
        "readout_length": InputParameterSpec.database_or_default(
            default=DEFAULT_READOUT_DURATION,
            unit="ns",
            description="Readout pulse length",
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "pi_duration": RunParameterSpec(
            unit="ns", value_type="int", default=PI_DURATION, description="PI pulse length"
        ),
        "shots": RunParameterSpec(
            unit="",
            value_type="int",
            default=CALIBRATION_SHOTS,
            description="Number of shots for calibration",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="int",
            default=DEFAULT_INTERVAL,
            description="Time interval for calibration",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "pi_amplitude": OutputParameterSpec(unit="", description="PI pulse amplitude"),
        "pi_length": OutputParameterSpec(
            default=PI_DURATION, unit="ns", description="PI pulse length"
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["pi_amplitude"].value = result.data[label].calib_value
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.data[label].fit()["fig"]]
        validation_error = finite_value_error(
            self.output_parameters["pi_amplitude"].value,
            f"CreatePIPulse pi_amplitude for {label}",
            minimum=0.0,
            maximum=1.0,
        )
        return PostProcessResult(
            output_parameters=output_parameters,
            figures=figures,
            validation_error=validation_error,
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        labels = [exp.get_qubit_label(int(qid))]
        readout_amp_param = self.input_parameters["readout_amplitude"]
        if readout_amp_param is not None:
            exp.params.readout_amplitude[labels[0]] = readout_amp_param.value
        control_amp_param = self.input_parameters["control_amplitude"]
        if control_amp_param is not None:
            exp.params.control_amplitude[labels[0]] = control_amp_param.value
        result = exp.calibrate_pi_pulse(
            targets=labels,
            n_rotations=1,
            duration=self.run_parameters["pi_duration"].get_value(),
            n_shots=self.run_parameters["shots"].get_value(),
            shot_interval=self.run_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        r2 = result.data[exp.get_qubit_label(int(qid))].r2
        return RunResult(raw_result=result, r2={qid: r2})
