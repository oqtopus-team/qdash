from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class Configure(BaseTask):
    task_name: str = "Configure"
    task_type: str = "global"

    def __init__(self):
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager):
        pass

    def _postprocess(self, exp: Experiment, task_manager: TaskManager):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager):
        exp.state_manager.load(
            chip_id=exp.chip_id, config_dir=exp.config_path, params_dir=exp.params_path
        )
        exp.state_manager.push(box_ids=exp.box_ids, confirm=False)
        exp.calib_note.save(file_path=task_manager.calib_dir)
