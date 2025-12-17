from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.caltasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.caltasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckZX90(QubexTask):
    """Task to check ZX90 pulse."""

    name: str = "CheckZX90"
    task_type: str = "coupling"
    timeout: int = 60 * 25  # 25 minutes
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
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = self.get_experiment(backend)
        control, target = (
            exp.get_qubit_label(int(q)) for q in qid.split("-")
        )  # e.g., "0-1" → "Q00","Q01"
        result = run_result.raw_result
        figures = [
            result.data[control].plot(normalize=True, return_figure=True),
            result.data[target].plot(normalize=True, return_figure=True),
        ]
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id), figures=figures
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        control, target = (
            exp.get_qubit_label(int(q)) for q in qid.split("-")
        )  # e.g., "0-1" → "Q00","Q01"
        zx90_pulse = exp.zx90(control, target)
        result = exp.repeat_sequence(
            sequence=zx90_pulse,
            repetitions=self.input_parameters["repetitions"].get_value(),
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)
