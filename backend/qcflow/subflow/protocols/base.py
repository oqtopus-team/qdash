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

    @abstractmethod
    def execute(self, exp: Experiment, task_manager: TaskManager):
        """
        Execute the task. This method must be implemented by all subclasses.
        """
        pass
