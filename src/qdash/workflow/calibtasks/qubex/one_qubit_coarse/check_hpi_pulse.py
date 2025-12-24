from typing import ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckHPIPulse(QubexTask):
    """Task to check the HPI pulse."""

    name: str = "CheckHPIPulse"
    task_type: str = "qubit"
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "repetitions": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=20,
            description="Number of repetitions for the HPI pulse",
        )
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {}

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
        hpi_pulse = {qubit: exp.hpi_pulse[qubit] for qubit in labels}
        result = exp.repeat_sequence(
            sequence=hpi_pulse,
            repetitions=self.run_parameters["repetitions"].get_value(),
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)
