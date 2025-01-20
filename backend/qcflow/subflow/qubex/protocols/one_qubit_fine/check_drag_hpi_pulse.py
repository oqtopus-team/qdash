from qcflow.subflow.qubex.manager import ExecutionManager
from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment


class CheckDRAGHPIPulse(BaseTask):
    task_name: str = "CheckDRAGHPIPulse"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, execution_manager: ExecutionManager):
        exp.repeat_sequence(
            exp.drag_hpi_pulse,
            repetitions=20,
        )
        exp.save_defaults()
