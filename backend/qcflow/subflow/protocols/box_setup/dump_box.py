from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class DumpBox(BaseTask):
    """DumpBox class to dump the box information."""

    task_name: str = "DumpBox"
    task_type: str = "global"

    def __init__(self) -> None:
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager) -> None:
        pass

    def _postprocess(self, exp: Experiment, task_manager: TaskManager) -> None:
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager) -> None:
        for _id in exp.box_ids:
            box_info = {}
            box_info[_id] = exp.tool.dump_box(_id)
            task_manager.put_controller_info(box_info)
