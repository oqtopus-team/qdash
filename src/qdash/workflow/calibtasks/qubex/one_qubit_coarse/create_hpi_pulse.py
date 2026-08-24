from typing import ClassVar

from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, HPI_DURATION
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL, DEFAULT_READOUT_DURATION

from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
)
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.calibtasks.qubex.validation import finite_value_error
from qdash.workflow.engine.backend.qubex import QubexBackend


class CreateHPIPulse(QubexTask):
    """Task to create the HPI pulse."""

    name: str = "CreateHPIPulse"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "qubit_frequency": InputParameterSpec.required_database(),
        "control_amplitude": InputParameterSpec.required_database(),
        "readout_amplitude": InputParameterSpec.required_database(),
        "readout_frequency": InputParameterSpec.required_database(),
        "rabi_amplitude": InputParameterSpec.required_database(),
        "rabi_phase": InputParameterSpec.required_database(),
        "rabi_offset": InputParameterSpec.required_database(),
        "rabi_angle": InputParameterSpec.required_database(),
        "rabi_noise": InputParameterSpec.required_database(),
        "rabi_distance": InputParameterSpec.required_database(),
        "rabi_reference_phase": InputParameterSpec.required_database(),
        "rabi_r2": InputParameterSpec.required_database(),
        "maximum_rabi_frequency": InputParameterSpec.required_database(),
        "readout_duration": InputParameterSpec.database_or_default(
            default=DEFAULT_READOUT_DURATION,
            unit="ns",
            description="Readout pulse duration",
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "hpi_duration": RunParameterSpec(
            unit="ns", value_type="int", default=HPI_DURATION, description="HPI pulse duration"
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
        "hpi_amplitude": OutputParameterSpec(unit="", description="HPI pulse amplitude"),
        "hpi_duration": OutputParameterSpec(
            default=HPI_DURATION, unit="ns", description="HPI pulse duration"
        ),
    }

    def preprocess(self, backend: QubexBackend, qid: str) -> PreProcessResult:
        """Load and explicitly validate every input needed to restore Rabi context."""
        result = super().preprocess(backend, qid)
        missing = [
            name for name, parameter in self.input_parameters.items() if parameter.value is None
        ]
        if missing:
            raise ValueError(
                "CreateHPIPulse requires resolved calibration inputs: " + ", ".join(missing)
            )
        return result

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["hpi_amplitude"].value = result.data[label].calib_value
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.data[label].fit()["fig"]]
        validation_error = finite_value_error(
            self.output_parameters["hpi_amplitude"].value,
            f"CreateHPIPulse hpi_amplitude for {label}",
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
        label = labels[0]
        readout_amp_param = self.input_parameters["readout_amplitude"]
        if readout_amp_param is not None:
            exp.params.readout_amplitude[labels[0]] = readout_amp_param.value
        control_amp_param = self.input_parameters["control_amplitude"]
        if control_amp_param is not None:
            exp.params.control_amplitude[label] = control_amp_param.value

        self._restore_rabi_context(backend, qid)
        result = exp.calibrate_hpi_pulse(
            targets=labels,
            n_rotations=1,
            duration=self.run_parameters["hpi_duration"].get_value(),
            n_shots=self.run_parameters["shots"].get_value(),
            shot_interval=self.run_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        r2 = result.data[exp.get_qubit_label(int(qid))].r2
        return RunResult(raw_result=result, r2={qid: r2})
