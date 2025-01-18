from qcflow.subflow.qubex.manager import TaskManager
from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment


class CheckPIPulse(BaseTask):
    task_name: str = "CheckPIPulse"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager):
        exp.repeat_sequence(
            exp.pi_pulse,
            repetitions=20,
        )
        exp.save_defaults()
