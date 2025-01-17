from abc import ABC, abstractmethod

from qubex.experiment import Experiment
from subflow.qubex.manager import TaskManager


class BaseTask(ABC):
    task_name = ""

    def __init__(
        self,
    ):
        pass

    @abstractmethod
    def execute(self, exp: Experiment, task_manager: TaskManager, task_name: str):
        """
        Execute the task. This method must be implemented by all subclasses.
        """
        pass
