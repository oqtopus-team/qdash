from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.engine.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.tasks.qubex.base import QubexTask


class CheckElectricalDelay(QubexTask):
    """Task to check the electrical delay."""

    name: str = "CheckElectricalDelay"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "electrical_delay": OutputParameterModel(unit="ns", description="Electrical delay", value_type="float")
    }

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        result = run_result.raw_result
        self.output_parameters["electrical_delay"].value = result
        output_parameters = self.attach_execution_id(execution_id)
        return PostProcessResult(output_parameters=output_parameters)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(session)
        label = self.get_qubit_label(session, qid)
        result = exp.measure_electrical_delay(target=label)
        self.save_calibration(session)
        return RunResult(raw_result=result)
