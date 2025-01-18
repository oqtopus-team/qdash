from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from subflow.qubex.manager import TaskManager


class DumpBox(BaseTask):
    task_name: str = "DumpBox"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager):
        for id in exp.box_ids:
            box_info = {}
            box_info[id] = exp.tool.dump_box(id)
            task_manager.put_box_info(box_info)
