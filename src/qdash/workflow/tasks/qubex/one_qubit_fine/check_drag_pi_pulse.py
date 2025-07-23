from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)


class CheckDRAGPIPulse(BaseTask):
    """Task to check the DRAG PI pulse."""

    name: str = "CheckDRAGPIPulse"
    backend: str = "qubex"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "repetitions": InputParameterModel(
            unit="a.u.",
            value_type="int",
            value=20,
            description="Number of repetitions for the PI pulse",
        )
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = session.get_session()
        label = exp.get_qubit_label(int(qid))
        result = run_result.raw_result
        figures = [result.data[label].plot(normalize=True, return_figure=True)]
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id), figures=figures
        )

    def run(self, session: QubexSession, qid: str) -> RunResult:
        exp = session.get_session()
        labels = [exp.get_qubit_label(int(qid))]
        drag_pi_pulse = {qubit: exp.drag_pi_pulse[qubit] for qubit in labels}
        result = exp.repeat_sequence(
            sequence=drag_pi_pulse,
            repetitions=self.input_parameters["repetitions"].get_value(),
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)

    def batch_run(self, session: QubexSession, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
