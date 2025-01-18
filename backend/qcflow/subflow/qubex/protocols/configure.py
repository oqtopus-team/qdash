from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from subflow.qubex.manager import TaskManager


class Configure(BaseTask):
    task_name: str = "Configure"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager):
        exp.state_manager.load(
            chip_id=exp.chip_id, config_dir=exp.config_path, params_dir=exp.params_path
        )
        exp.state_manager.push(box_ids=exp.box_ids, confirm=False)
        exp.save_defaults()
