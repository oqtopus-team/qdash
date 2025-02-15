from qcflow.subflow.manager import ExecutionManager
from qcflow.subflow.protocols.base import BaseTask
from qubex.experiment import Experiment


class CheckDRAGPIPulse(BaseTask):
    task_name: str = "CheckDRAGPIPulse"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, execution_manager: ExecutionManager):
        exp.repeat_sequence(
            {qubit: exp.drag_pi_pulse[qubit] for qubit in exp.qubit_labels},
            repetitions=20,
        )
        exp.save_defaults()
