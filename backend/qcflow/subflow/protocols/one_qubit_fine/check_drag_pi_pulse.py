from typing import Any

from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class CheckDRAGPIPulse(BaseTask):
    task_name: str = "CheckDRAGPIPulse"
    task_type: str = "qubit"

    def __init__(self):
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager):
        pass

    def _postprocess(self, exp: Experiment, task_manager: TaskManager, result: Any):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager):
        exp.repeat_sequence(
            {qubit: exp.drag_pi_pulse[qubit] for qubit in exp.qubit_labels},
            repetitions=20,
        )
        exp.save_defaults()
