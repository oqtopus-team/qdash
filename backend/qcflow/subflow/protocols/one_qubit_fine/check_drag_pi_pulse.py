from typing import Any, ClassVar

from qcflow.subflow.protocols.base import BaseTask, OutputParameter
from qcflow.subflow.task_manager import TaskManager
from qcflow.subflow.util import convert_label
from qubex.experiment import Experiment


class CheckDRAGPIPulse(BaseTask):
    """Task to check the DRAG PI pulse."""

    task_name: str = "CheckDRAGPIPulse"
    task_type: str = "qubit"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {}

    def __init__(self) -> None:
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        pass

    def _postprocess(
        self, exp: Experiment, task_manager: TaskManager, result: Any, qid: str
    ) -> None:
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        labels = [convert_label(qid)]
        drag_pi_pulse = {qubit: exp.drag_pi_pulse[qubit] for qubit in labels}
        exp.repeat_sequence(
            sequence=drag_pi_pulse,
            repetitions=20,
        )
        exp.calib_note.save()
