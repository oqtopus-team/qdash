from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.tasks.qubex.base import QubexTask


class CheckQubitFrequencies(QubexTask):
    """Task to check the qubit frequencies."""

    name: str = "CheckQubitFrequencies"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "coarse_qubit_frequency": OutputParameterModel(unit="GHz", description="Coarse qubit frequency"),
    }

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:  # noqa: ARG002
        """Preprocess the task."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        label = self.get_qubit_label(session, qid)
        result = run_result.raw_result
        figures = [result[label]["fig"]]
        coarse_qubit_frequency = 0
        if result[label]["frequency_guess"]["f_ge"] is not None:
            coarse_qubit_frequency = result[label]["frequency_guess"]["f_ge"]
        self.output_parameters["coarse_qubit_frequency"].value = coarse_qubit_frequency
        output_parameters = self.attach_execution_id(execution_id)
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(session)
        label = self.get_qubit_label(session, qid)
        result = exp.scan_qubit_frequencies(label)
        self.save_calibration(session)
        return RunResult(raw_result=result)

    def batch_run(self, session: QubexSession, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits."""
        exp = self.get_experiment(session)
        labels = [self.get_qubit_label(session, qid) for qid in qids]
        results = {}
        for label in labels:
            result = exp.scan_qubit_frequencies(label)
            results[label] = result
        self.save_calibration(session)
        return RunResult(raw_result=results)
