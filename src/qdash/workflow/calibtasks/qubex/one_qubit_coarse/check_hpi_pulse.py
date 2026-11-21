from typing import ClassVar

from qubex.experiment.experiment_constants import DEFAULT_SHOTS
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL

from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
    TaskDocumentation,
)
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import (
    QubexTask,
    readout_duration_run_parameter,
    required_rabi_normalization_inputs,
)
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckHPIPulse(QubexTask):
    """Task to check the HPI pulse."""

    name: str = "CheckHPIPulse"
    task_type: str = "qubit"
    documentation: ClassVar[TaskDocumentation] = TaskDocumentation(
        description=(
            "Applies the stored half-pi pulse repeatedly (20 times by default) and plots the "
            "normalized signal after each repetition. It writes no calibration values."
        ),
        when_to_use=(
            "Run it after CreateHPIPulse to see amplitude error accumulate: a correct pulse "
            "returns to the same state every four repetitions."
        ),
        prerequisites=(
            (
                "Rabi parameters from a CheckRabi run under the current readout_duration, with "
                "rabi_r2 at or above the R² threshold; they normalize the IQ data."
            ),
            "hpi_amplitude and hpi_duration stored by CreateHPIPulse.",
            (
                "control_frequency (or qubit_frequency), readout_frequency (or "
                "resonator_frequency), and readout_amplitude are stored for the qubit."
            ),
        ),
    )
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        # RabiParam normalizes measured IQ values; its readout duration is validated.
        **required_rabi_normalization_inputs(),
        "control_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("qubit_frequency",)
        ),
        "hpi_amplitude": InputParameterSpec.required_database(),
        "hpi_duration": InputParameterSpec.required_database(),
        "readout_amplitude": InputParameterSpec.required_database(),
        "readout_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("resonator_frequency",)
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_duration": readout_duration_run_parameter(),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=DEFAULT_SHOTS,
            description="Number of shots for pulse verification",
        ),
        "repetitions": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=20,
            description="Number of repetitions for the HPI pulse",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="int",
            default=DEFAULT_INTERVAL,
            description="Time interval",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {}

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        figures = [result.data[label].plot(normalize=True, return_figure=True)]
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id), figures=figures
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        labels = [exp.get_qubit_label(int(qid))]
        readout_amp_param = self.input_parameters["readout_amplitude"]
        if readout_amp_param is not None:
            exp.params.readout_amplitude[labels[0]] = readout_amp_param.value
        hpi_pulse = {qubit: exp.hpi_pulse[qubit] for qubit in labels}
        result = exp.repeat_sequence(
            sequence=hpi_pulse,
            repetitions=self.run_parameters["repetitions"].get_value(),
            n_shots=self.run_parameters["shots"].get_value(),
            shot_interval=self.run_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)
