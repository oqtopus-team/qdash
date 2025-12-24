from typing import ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckQubitSpectroscopy(QubexTask):
    """Task to check the qubit frequencies."""

    name: str = "CheckQubitSpectroscopy"
    task_type: str = "qubit"
    timeout: int = 60 * 120
    input_parameters: ClassVar[dict[str, ParameterModel]] = {}
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {}
    output_parameters: ClassVar[dict[str, ParameterModel]] = {}

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        figures = [result[label]["fig"]]
        output_parameters = self.attach_execution_id(execution_id)
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        results = {}

        # Apply parameter overrides if provided via task_details
        # Supports: qubit_frequency, readout_amplitude, control_amplitude, readout_frequency
        with self._apply_parameter_overrides(backend, qid):
            result = exp.qubit_spectroscopy(label)
            results[label] = result

        self.save_calibration(backend)

        return RunResult(raw_result=results)

    def batch_run(self, backend: QubexBackend, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits.

        Note: batch_run does not support parameter overrides via task_details.
        Use individual run() calls if you need per-qubit parameter customization.
        """
        exp = self.get_experiment(backend)
        labels = [self.get_qubit_label(backend, qid) for qid in qids]
        results = {}
        for label in labels:
            result = exp.qubit_spectroscopy(label)
            results[label] = result
        self.save_calibration(backend)
        return RunResult(raw_result=results)
