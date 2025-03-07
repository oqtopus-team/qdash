from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal

import plotly.graph_objs as go
from pydantic import BaseModel
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qubex.experiment import Experiment


class PreProcessResult(BaseModel):
    """Result class."""

    input_parameters: dict


class PostProcessResult(BaseModel):
    """Result class."""

    output_parameters: dict[str, OutputParameterModel]
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
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}
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
