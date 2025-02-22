from typing import Any, ClassVar

from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import Data, TaskManager
from qcflow.subflow.util import convert_label
from qubex.experiment import Experiment


class ReadoutClassification(BaseTask):
    """Task to classify the readout."""

    task_name: str = "ReadoutClassification"
    task_type: str = "qubit"

    output_parameters: ClassVar[list[str]] = [
        "average_readout_fidelity",
        "readout_fidelity_0",
        "readout_fidelity_1",
    ]

    def __init__(self) -> None:
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        pass

    def _postprocess(
        self, exp: Experiment, task_manager: TaskManager, result: Any, qid: str
    ) -> None:
        label = convert_label(qid)
        output_param = {
            "average_readout_fidelity": Data(
                value=result["average_readout_fidelity"][label],
                execution_id=task_manager.execution_id,
            ),
            "readout_fidelity_0": Data(
                value=result["readout_fidelties"][label][0], execution_id=task_manager.execution_id
            ),
            "readout_fidelity_1": Data(
                value=result["readout_fidelties"][label][1], execution_id=task_manager.execution_id
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
