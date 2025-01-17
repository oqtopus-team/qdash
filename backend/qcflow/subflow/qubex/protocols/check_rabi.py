from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from subflow.qubex.manager import TaskManager


class CheckRabi(BaseTask):
    task_name = "CheckRabi"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager, task_name: str):
        rabi_result = exp.check_rabi()
        exp.save_defaults()
        rabi_params = {key: value.rabi_param.__dict__ for key, value in rabi_result.data.items()}
        task_manager.put_output_parameter(task_name, "rabi_params", rabi_params)
