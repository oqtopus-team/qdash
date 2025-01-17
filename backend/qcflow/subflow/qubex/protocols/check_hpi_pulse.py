from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from subflow.qubex.manager import TaskManager


class CheckHPIPulse(BaseTask):
    task_name = "CheckHPIPulse"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager, task_name: str):
        exp.repeat_sequence(
            exp.hpi_pulse,
            repetitions=20,
        )
        exp.save_defaults()
