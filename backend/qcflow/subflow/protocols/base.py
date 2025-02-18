from abc import ABC, abstractmethod
from typing import Literal

from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class BaseTask(ABC):
    task_name: str = ""
    task_type: Literal["global", "qubit", "coupling"]

    def __init__(
        self,
    ):
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager):
        """
        Preprocess the task. This method is called before the task is executed

        Args:
            exp: Experiment object
            task_manager: TaskManager object
        """
        pass

    def _postprocess(self, exp: Experiment, task_manager: TaskManager, result):
        """
        Postprocess the task. This method is called after the task is executed

        Args:
            exp: Experiment object
            task_manager: TaskManager object
            result: The result of the task
        """
        pass

    @abstractmethod
    def execute(self, exp: Experiment, task_manager: TaskManager):
        """
        Execute the task. This method must be implemented by all subclasses.

        Args:
            exp: Experiment object
            task_manager: TaskManager object
        """
        pass
