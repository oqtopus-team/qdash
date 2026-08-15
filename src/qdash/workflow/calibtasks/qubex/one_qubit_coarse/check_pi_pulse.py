from typing import ClassVar

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


class CheckPIPulse(QubexTask):
    """Task to check the PI pulse."""

    name: str = "CheckPIPulse"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "qubit_frequency": InputParameterSpec.required_database(),
        "pi_amplitude": InputParameterSpec.required_database(),
        "pi_length": InputParameterSpec.required_database(),
        "readout_amplitude": InputParameterSpec.required_database(),
        "readout_frequency": InputParameterSpec.required_database(),
        "readout_length": InputParameterSpec.database_or_default(
            default=DEFAULT_READOUT_DURATION,
            unit="ns",
            description="Readout pulse length",
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "repetitions": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=20,
            description="Number of repetitions for the PI pulse",
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
        pi_pulse = {qubit: exp.pi_pulse[qubit] for qubit in labels}
        result = exp.repeat_sequence(
            sequence=pi_pulse,
            repetitions=self.run_parameters["repetitions"].get_value(),
            shot_interval=self.run_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)
