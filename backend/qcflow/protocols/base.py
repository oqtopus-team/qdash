from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal

import numpy as np
import plotly.graph_objs as go
from datamodel.task import DataModel
from pydantic import BaseModel
from qubex.experiment import Experiment


class InputParameter(BaseModel):
    """Input parameter class."""

    unit: str = ""
    value_type: str = "float"
    value: tuple | int | float | None = None
    description: str = ""

    def get_value(self) -> Any:
        """Get the actual value based on value_type.

        Returns
        -------
            The converted value based on value_type

        """
        if self.value_type == "np.linspace":
            if not isinstance(self.value, (list, tuple)) or len(self.value) != 3:
                raise ValueError("np.linspace requires a tuple/list of (start, stop, num)")
            start, stop, num = self.value
            return np.linspace(float(start), float(stop), int(num))
        elif self.value_type == "np.logspace":
            if not isinstance(self.value, (list, tuple)) or len(self.value) != 3:
                raise ValueError("np.logspace requires a tuple/list of (start, stop, num)")
            start, stop, num = self.value
            return np.logspace(float(start), float(stop), int(num))
        elif self.value_type == "np.arange":
            if not isinstance(self.value, (list, tuple)) or len(self.value) != 3:
                raise ValueError("np.arange requires a tuple/list of (start, stop, step)")
            start, stop, step = self.value
            return np.arange(float(start), float(stop), float(step))
        elif self.value_type == "range":
            if not isinstance(self.value, (list, tuple)) or len(self.value) != 3:
                raise ValueError("range requires a tuple/list of (start, stop, step)")
            start, stop, step = self.value
            return range(int(start), int(stop), int(step))
        elif self.value_type == "int":
            if isinstance(self.value, str) and "*" in self.value:
                # Handle expressions like "150 * 1024"
                parts = [int(p.strip()) for p in self.value.split("*")]
                result = 1
                for p in parts:
                    result *= p
                return result
            return int(self.value)
        elif self.value_type == "float":
            return float(self.value)
        return self.value


class OutputParameter(BaseModel):
    """Output parameter class."""

    unit: str = ""
    description: str = ""


class PreProcessResult(BaseModel):
    """Result class."""

    input_parameters: dict


class PostProcessResult(BaseModel):
    """Result class."""

    output_parameters: dict[str, DataModel]
    figures: list[go.Figure] = []
    raw_data: list[Any] = []

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


class RunResult(BaseModel):
    """Result class."""

    raw_result: Any


class BaseTask(ABC):
    """Base class for the task."""

    name: str = ""
    task_type: Literal["global", "qubit", "coupling"]
    input_parameters: ClassVar[dict[str, InputParameter]] = {}
    output_parameters: ClassVar[dict[str, OutputParameter]] = {}
    registry: ClassVar[dict] = {}

    def __init_subclass__(cls, **kwargs) -> None:  # noqa: ANN003
        """Register the task class."""
        super().__init_subclass__(**kwargs)
        BaseTask.registry[cls.__name__] = cls

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        """Initialize task with parameters.

        Args:
        ----
            params: Optional dictionary containing task parameters

        """
        if params is not None:
            self._convert_and_set_parameters(params)

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
                        value_type = param_data.get(
                            "value_type", self.input_parameters[name].value_type
                        )
                        converted_value = self._convert_value_to_type(value, value_type)
                        self.input_parameters[name].value = converted_value

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

    def get_name(self) -> str:
        """Return the name of the task."""
        return self.name

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
