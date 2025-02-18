from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class DumpBox(BaseTask):
    task_name: str = "DumpBox"
    task_type: str = "global"

    def __init__(self):
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager):
        pass

    def _postprocess(self, exp: Experiment, task_manager: TaskManager):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager):
        for id in exp.box_ids:
            box_info = {}
            box_info[id] = exp.tool.dump_box(id)
            # execution_manager.put_box_info(box_info)
