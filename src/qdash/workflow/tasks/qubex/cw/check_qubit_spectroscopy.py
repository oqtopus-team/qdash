from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.calibration.util import qid_to_label
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)


class CheckQubitSpectroscopy(BaseTask):
    """Task to check the qubit frequencies."""

    name: str = "CheckQubitSpectroscopy"
    backend: str = "qubex"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:  # noqa: ARG002
        """Preprocess the task."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        """Process the results of the task."""
        label = qid_to_label(qid)
        result = run_result.raw_result
        figures = [result[label]["fig"]]
        output_parameters = self.attach_execution_id(execution_id)
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        """Run the task."""
        label = qid_to_label(qid)
        exp = session.get_session()
        result = exp.qubit_spectroscopy(label)
        exp.calib_note.save()
        return RunResult(raw_result=result)

    def batch_run(self, session: QubexSession, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits."""
        labels = [qid_to_label(qid) for qid in qids]
        results = {}
        exp = session.get_session()
        for label in labels:
            result = exp.qubit_spectroscopy(label)
            results[label] = result
        exp.calib_note.save()
        return RunResult(raw_result=results)
