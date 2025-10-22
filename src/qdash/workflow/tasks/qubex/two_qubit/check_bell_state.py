from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.tasks.qubex.base import QubexTask


class CheckBellState(QubexTask):
    """Task to check the bell state."""

    name: str = "CheckBellState"
    task_type: str = "coupling"
    timeout: int = 60 * 25  # 25 minutes
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        result = run_result.raw_result
        output_parameters = self.attach_execution_id(execution_id)
        figures: list = [result["figure"]]
        raw_data: list = []
        return PostProcessResult(output_parameters=output_parameters, figures=figures, raw_data=raw_data)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        exp = self.get_experiment(session)
        control, target = (exp.get_qubit_label(int(q)) for q in qid.split("-"))  # e.g., "0-1" → "Q00","Q01"
        result = exp.measure_bell_state(control, target)
        self.save_calibration(session)
        return RunResult(raw_result=result)
