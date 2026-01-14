from typing import ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckQubitFrequencies(QubexTask):
    """Task to check the qubit frequencies."""

    name: str = "CheckQubitFrequencies"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {}
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {}
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "coarse_qubit_frequency": ParameterModel(unit="GHz", description="Coarse qubit frequency"),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        figures = [result[label]["fig"]]
        coarse_qubit_frequency = 0
        if result[label]["frequency_guess"]["f_ge"] is not None:
            coarse_qubit_frequency = result[label]["frequency_guess"]["f_ge"]
        self.output_parameters["coarse_qubit_frequency"].value = coarse_qubit_frequency
        output_parameters = self.attach_execution_id(execution_id)
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = exp.scan_qubit_frequencies(label)
        self.save_calibration(backend)
        return RunResult(raw_result=result)

    def batch_run(self, backend: QubexBackend, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits."""
        exp = self.get_experiment(backend)
        labels = [self.get_qubit_label(backend, qid) for qid in qids]
        results = {}
        for label in labels:
            result = exp.scan_qubit_frequencies(label)
            results[label] = result
        self.save_calibration(backend)
        return RunResult(raw_result=results)
