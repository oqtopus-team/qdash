from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal

import plotly.graph_objs as go
from pydantic import BaseModel
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.base import BaseSession


class PreProcessResult(BaseModel):
    """Result class."""

    input_parameters: dict


class PostProcessResult(BaseModel):
    """Result class."""

    output_parameters: dict[str, OutputParameterModel]
    figures: list[go.Figure | go.FigureWidget] = []
    raw_data: list[Any] = []

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


class RunResult(BaseModel):
    """Result class."""

    raw_result: Any
    r2: dict[str, float] | None = None

    def has_r2(self) -> bool:
        """Check if the result has R2 value."""
        return self.r2 is not None


class BaseTask(ABC):
    """Base class for the task."""

    name: str = ""
    task_type: Literal["global", "qubit", "coupling", "system"]
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}
    r2_threshold: float = 0.7
    timeout = 60 * 60  # Default timeout of 1 hour
    backend = "qubex"
    registry: ClassVar[dict[str, dict[str, type["BaseTask"]]]] = {}

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        backend = getattr(cls, "backend", None)
        if backend is None:
            raise ValueError(f"{cls.__name__} に backend を定義してください")
        task_name = getattr(cls, "name", cls.__name__)

        # Skip registration for intermediate base classes (those with empty name)
        # Only concrete task implementations should be registered
        if task_name:
            BaseTask.registry.setdefault(backend, {})[task_name] = cls

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        """Initialize task with parameters.

        Args:
        ----
            params: Optional dictionary containing task parameters

        """
        if params is not None:
            self._convert_and_set_parameters(params)

    def r2_is_lower_than_threshold(self, r2: float) -> bool:
        """Check if the R2 value is above the threshold."""
        return r2 <= self.r2_threshold

    def _convert_value_to_type(self, value: Any, value_type: str) -> Any:
        """Convert value to the specified type.

        Args:
        ----
            value: Value to convert
            value_type: Target type

        Returns:
        -------
            Converted value

        """
        if value_type in ["np.linspace", "np.logspace", "np.arange", "range"]:
            if isinstance(value, (list, tuple)) and len(value) == 3:
                return tuple(value)  # Convert to tuple for storage
            raise ValueError(f"{value_type} requires a tuple/list of 3 values")
        elif value_type == "int":
            if isinstance(value, str) and "*" in value:
                # Handle expressions like "150 * 1024"
                parts = [int(p.strip()) for p in value.split("*")]
                result = 1
                for p in parts:
                    result *= p
                return result
            return int(value)
        elif value_type == "float":
            return float(value)
        return value

    def _convert_and_set_parameters(self, params: dict[str, Any]) -> None:
        """Convert and set parameters from dictionary.

        Args:
        ----
            params: Dictionary containing task parameters

        """
        if "input_parameters" in params:
            input_params = params["input_parameters"]
            for name, param_data in input_params.items():
                if name in self.input_parameters:
                    value = param_data.get("value")
                    if value is not None:
                        value_type = param_data.get("value_type", self.input_parameters[name].value_type)
                        converted_value = self._convert_value_to_type(value, value_type)
                        self.input_parameters[name].value = converted_value

    @abstractmethod
    def preprocess(self, session: BaseSession, qid: str) -> PreProcessResult:
        """Preprocess the task. This method is called before the task is executed.

        Args:
        ----
            session: Session object
            qid: qubit id

        """

    @abstractmethod
    def postprocess(
        self, session: BaseSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Postprocess the task. This method is called after the task is executed.

        Args:
        ----
            session: Session object
            execution_id: execution id
            run_result: RunResult object
            qid: qubit id

        """

    @abstractmethod
    def run(self, session: BaseSession, qid: str) -> RunResult:
        """Run the task.

        Args:
        ----
            session: Session object
            qid: qubit id

        """

    @abstractmethod
    def batch_run(self, session: BaseSession, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits.

        Args:
        ----
            session: Session object
            qids: list of qubit ids

        """

    def is_valid(self, r2: float) -> None:
        """Diagnose the task. This method is called to check the task status."""
        if self.r2_is_lower_than_threshold(r2):
            raise ValueError(f"R^2 value of {self.name} is too low: {r2}")

    def get_output_parameters(self) -> list[str]:
        """Return the output parameters of the task."""
        return list(self.output_parameters.keys())

    def get_name(self) -> str:
        """Return the name of the task."""
        return self.name

    def get_task_type(self) -> Literal["global", "qubit", "coupling", "system"]:
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

    def is_system_task(self) -> bool:
        """Return True if the task is a system task."""
        return self.task_type == "system"

    def attach_execution_id(self, execution_id: str) -> dict[str, OutputParameterModel]:
        """Attach the execution id to the output parameters."""
        for value in self.output_parameters.values():
            value.execution_id = execution_id
        return self.output_parameters
