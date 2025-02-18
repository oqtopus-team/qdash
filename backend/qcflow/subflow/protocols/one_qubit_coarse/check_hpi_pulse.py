from typing import Any

from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class CheckHPIPulse(BaseTask):
    task_name: str = "CheckHPIPulse"
    task_type: str = "qubit"

    def __init__(self):
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager):
        pass

    def _postprocess(self, exp: Experiment, task_manager: TaskManager, result: Any):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager):
        exp.repeat_sequence(
            exp.hpi_pulse,
            repetitions=20,
        )
        exp.calib_note.save()
