from qcflow.subflow.manager import ExecutionManager
from qcflow.subflow.protocols.base import BaseTask
from qubex.experiment import Experiment


class DumpBox(BaseTask):
    task_name: str = "DumpBox"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, execution_manager: ExecutionManager):
        for id in exp.box_ids:
            box_info = {}
            box_info[id] = exp.tool.dump_box(id)
            execution_manager.put_box_info(box_info)
