from abc import ABC, abstractmethod

from qcflow.subflow.qubex.manager import TaskManager
from qubex.experiment import Experiment


class BaseTask(ABC):
    task_name: str = ""

    def __init__(
        self,
    ):
        pass

    @abstractmethod
    def execute(self, exp: Experiment, task_manager: TaskManager):
        """
        Execute the task. This method must be implemented by all subclasses.
        """
        pass
