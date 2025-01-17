from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from subflow.qubex.manager import TaskManager


class CheckPIPulse(BaseTask):
    task_name = "CheckPIPulse"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager, task_name: str):
        exp.repeat_sequence(
            exp.pi_pulse,
            repetitions=20,
        )
        exp.save_defaults()
