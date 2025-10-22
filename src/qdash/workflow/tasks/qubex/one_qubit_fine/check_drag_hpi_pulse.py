from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.tasks.qubex.base import QubexTask


class CheckDRAGHPIPulse(QubexTask):
    """Task to check the DRAG HPI pulse."""

    name: str = "CheckDRAGHPIPulse"
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

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(session)
        label = self.get_qubit_label(session, qid)
        result = run_result.raw_result
        figures = [result.data[label].plot(normalize=True, return_figure=True)]
        return PostProcessResult(output_parameters=self.attach_execution_id(execution_id), figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        exp = self.get_experiment(session)
        labels = [exp.get_qubit_label(int(qid))]
        drag_hpi_pulse = {qubit: exp.drag_hpi_pulse[qubit] for qubit in labels}
        result = exp.repeat_sequence(
            sequence=drag_hpi_pulse,
            repetitions=self.input_parameters["repetitions"].get_value(),
        )
        self.save_calibration(session)
        return RunResult(raw_result=result)
