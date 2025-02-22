from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal

import plotly.graph_objs as go
from pydantic import BaseModel
from qcflow.subflow.task_manager import Data
from qubex.experiment import Experiment


class OutputParameter(BaseModel):
    """Output parameter class."""

    unit: str = ""
    description: str = ""


class PreProcessResult(BaseModel):
    """Result class."""

    input_parameters: dict


class PostProcessResult(BaseModel):
    """Result class."""

    output_parameters: dict[str, Data]
    figures: list[go.Figure] = []

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


class RunResult(BaseModel):
    """Result class."""

    raw_result: Any


class BaseTask(ABC):
    """Base class for the task."""

    task_name: str = ""
    task_type: Literal["global", "qubit", "coupling"]
    output_parameters: ClassVar[dict[str, OutputParameter]] = {}
    registry: ClassVar[dict] = {}

    def __init_subclass__(cls, **kwargs) -> None:  # noqa: ANN003
        """Register the task class."""
        super().__init_subclass__(**kwargs)
        BaseTask.registry[cls.__name__] = cls

    @abstractmethod
    def __init__(
        self,
    ) -> None:
        pass

    @abstractmethod
    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        """Preprocess the task. This method is called before the task is executed.

        Args:
        ----
            exp: Experiment object
            qid: qubit id

        """

    @abstractmethod
    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        """Postprocess the task. This method is called after the task is executed.

        Args:
        ----
            execution_id: execution id
            run_result: RunResult object
            qid: qubit id

        """

    @abstractmethod
    def run(self, exp: Experiment, qid: str) -> RunResult:
        """Run the task.

        Args:
        ----
            exp: Experiment object
            qid: qubit id

        """

    def get_output_parameters(self) -> list[str]:
        """Return the output parameters of the task."""
        return list(self.output_parameters.keys())

    def get_task_name(self) -> str:
        """Return the name of the task."""
        return self.task_name

    def get_task_type(self) -> Literal["global", "qubit", "coupling"]:
        """Return the type of the task."""
        return self.task_type

    def is_global_task(self) -> bool:
        """Return True if the task is a global task."""
        return self.task_type == "global"

    def is_qubit_task(self) -> bool:
        """Return True if the task is a qubit task."""
        return self.task_type == "qubit"

    def is_coupling_task(self) -> bool:
        """Return True if the task is a coupling task."""
        return self.task_type == "coupling"
