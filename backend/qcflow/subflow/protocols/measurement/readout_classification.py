from typing import Any, ClassVar

from qcflow.subflow.protocols.base import BaseTask, OutputParameter
from qcflow.subflow.task_manager import Data, TaskManager
from qcflow.subflow.util import convert_label
from qubex.experiment import Experiment


class ReadoutClassification(BaseTask):
    """Task to classify the readout."""

    task_name: str = "ReadoutClassification"
    task_type: str = "qubit"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "average_readout_fidelity": OutputParameter(
            unit="GHz",
            description="Average readout fidelity",
        ),
        "readout_fidelity_0": OutputParameter(
            unit="GHz",
            description="Readout fidelity with preparation state 0",
        ),
        "readout_fidelity_1": OutputParameter(
            unit="GHz",
            description="Readout fidelity with preparation state 1",
        ),
    }

    def __init__(self) -> None:
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        pass

    def _postprocess(
        self, exp: Experiment, task_manager: TaskManager, result: Any, qid: str
    ) -> None:
        label = convert_label(qid)
        op = self.output_parameters
        output_param = {
            "average_readout_fidelity": Data(
                value=result["average_readout_fidelity"][label],
                unit=op["average_readout_fidelity"].unit,
                description=op["average_readout_fidelity"].description,
                execution_id=task_manager.execution_id,
            ),
            "readout_fidelity_0": Data(
                value=result["readout_fidelties"][label][0],
                unit=op["readout_fidelity_0"].unit,
                description=op["readout_fidelity_0"].description,
                execution_id=task_manager.execution_id,
            ),
            "readout_fidelity_1": Data(
                value=result["readout_fidelties"][label][1],
                unit=op["readout_fidelity_1"].unit,
                description=op["readout_fidelity_1"].description,
                execution_id=task_manager.execution_id,
            ),
        }
        task_manager.put_output_parameters(
            self.task_name,
            output_param,
            self.task_type,
            qid=qid,
        )

    def execute(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        label = convert_label(qid)
        result = exp.build_classifier(targets=label)
        exp.calib_note.save()
        self._postprocess(exp, task_manager, result, qid=qid)
