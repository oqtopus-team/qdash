from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.engine.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.tasks.qubex.base import QubexTask


class CheckQubitSpectroscopy(QubexTask):
    """Task to check the qubit frequencies."""

    name: str = "CheckQubitSpectroscopy"
    task_type: str = "qubit"
    timeout: int = 60 * 120
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        label = self.get_qubit_label(session, qid)
        result = run_result.raw_result
        figures = [result[label]["fig"]]
        output_parameters = self.attach_execution_id(execution_id)
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(session)
        label = self.get_qubit_label(session, qid)
        result = exp.qubit_spectroscopy(label)
        self.save_calibration(session)
        return RunResult(raw_result=result)

    def batch_run(self, session: QubexSession, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits."""
        exp = self.get_experiment(session)
        labels = [self.get_qubit_label(session, qid) for qid in qids]
        results = {}
        for label in labels:
            result = exp.qubit_spectroscopy(label)
            results[label] = result
        self.save_calibration(session)
        return RunResult(raw_result=results)
