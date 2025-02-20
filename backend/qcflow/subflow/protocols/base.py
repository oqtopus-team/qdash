from abc import ABC, abstractmethod
from typing import Literal

from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class BaseTask(ABC):
    """Base class for the task."""

    task_name: str = ""
    task_type: Literal["global", "qubit", "coupling"]
    output_parameters: list[str] = []

    def __init__(
        self,
    ) -> None:
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager) -> None:
        """Preprocess the task. This method is called before the task is executed.

        Args:
        ----
            exp: Experiment object
            task_manager: TaskManager object

        """

    def _postprocess(self, exp: Experiment, task_manager: TaskManager, result) -> None:
        """Postprocess the task. This method is called after the task is executed.

        Args:
        ----
            exp: Experiment object
            task_manager: TaskManager object
            result: The result of the task

        """

    @abstractmethod
    def execute(self, exp: Experiment, task_manager: TaskManager) -> None:
        """Execute the task. This method must be implemented by all subclasses.

        Args:
        ----
            exp: Experiment object
            task_manager: TaskManager object

        """

    def get_output_parameters(self) -> list[str]:
        """Return the output parameters of the task."""
        return self.output_parameters

    def get_task_name(self) -> str:
        """Return the name of the task."""
        return self.task_name

    def get_task_type(self) -> Literal["global", "qubit", "coupling"]:
        """Return the type of the task."""
        return self.task_type
