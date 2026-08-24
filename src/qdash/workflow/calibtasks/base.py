from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar

from qdash.datamodel.task import (
    InputParameterModel,
    InputParameterSpec,
    OutputParameterModel,
    OutputParameterSpec,
    RunParameterModel,
    RunParameterSpec,
    TaskTypes,
)
from qdash.workflow.calibtasks.results import PostProcessResult, PreProcessResult, RunResult
from qdash.workflow.engine.backend.base import BaseBackend

__all__ = [
    "BaseTask",
    "PostProcessResult",
    "PreProcessResult",
    "RunParameterModel",
    "RunResult",
]


class BaseTask(ABC):
    """Base class for the task.

    Attributes
    ----------
    input_spec : Mapping[str, InputParameterSpec]
        Class-level declarations for calibration dependencies and resolution policy.
    run_spec : Mapping[str, RunParameterSpec]
        Class-level declarations for experiment configuration.
    output_spec : Mapping[str, OutputParameterSpec]
        Class-level declarations for calibration values produced by the task.
    """

    name: str = ""
    task_type: str
    # Class-level parameter declarations
    input_spec: ClassVar[Mapping[str, InputParameterSpec]] = {}
    # Experiment run configuration declarations
    run_spec: ClassVar[Mapping[str, RunParameterSpec]] = {}
    # Calibration output declarations
    output_spec: ClassVar[Mapping[str, OutputParameterSpec]] = {}
    r2_threshold: float = 0.7
    timeout = 60 * 60  # Default timeout of 1 hour
    backend = "qubex"
    registry: ClassVar[dict[str, dict[str, type["BaseTask"]]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
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
        # Calibration input parameters (for provenance)
        self.input_parameters: dict[str, InputParameterModel] = {
            name: declaration.create_model()
            for name, declaration in self.__class__.input_spec.items()
        }
        # Calibration output parameters
        self.output_parameters: dict[str, OutputParameterModel] = {
            name: declaration.create_model()
            for name, declaration in self.__class__.output_spec.items()
        }
        # Experiment run configuration
        self.run_parameters: dict[str, RunParameterModel] = {
            name: declaration.create_model()
            for name, declaration in self.__class__.run_spec.items()
        }
        # Set by TaskExecutor after a complete re-execution snapshot is applied.
        self.input_parameters_from_snapshot = False

        if params is not None:
            self._convert_and_set_parameters(params)

    def r2_is_lower_than_threshold(self, r2: float) -> bool:
        """Check if the R2 value is above the threshold."""
        return r2 <= self.r2_threshold

    def extract_raw_data(self, run_result: RunResult) -> list[Any]:
        """Return raw artifacts to persist before postprocessing.

        Backends that expose persistable raw results can override this hook.
        """
        return []

    def prepare_run(self, backend: BaseBackend, qid: str) -> None:
        """Apply resolved and validated inputs immediately before execution."""

    def extract_batch_raw_data(
        self, backend: BaseBackend, run_result: RunResult, qids: list[str]
    ) -> dict[str, list[Any]]:
        """Return raw artifacts grouped by qid for a batch result."""
        return {qid: [] for qid in qids}

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
        # Handle run_parameters (experiment configuration)
        if "run_parameters" in params:
            self._set_run_parameters(params["run_parameters"])
        # Backward compatibility: old input_parameters -> run_parameters
        elif "input_parameters" in params:
            self._set_run_parameters(params["input_parameters"])

        # Handle input_parameters (calibration inputs for provenance)
        if "calibration_inputs" in params:
            self._set_calibration_inputs(params["calibration_inputs"])

    def _set_run_parameters(self, run_params: dict[str, Any]) -> None:
        """Set run parameters (experiment configuration).

        Args:
        ----
            run_params: Dictionary of run parameters

        """
        for name, param_data in run_params.items():
            if name in self.run_parameters:
                # Parameter already exists - update its value
                value = param_data.get("value")
                if value is not None:
                    value_type = param_data.get("value_type", self.run_parameters[name].value_type)
                    converted_value = self._convert_value_to_type(value, value_type)
                    self.run_parameters[name].value = converted_value
            else:
                # Create new RunParameterModel
                value = param_data.get("value")
                if value is not None:
                    value_type = param_data.get("value_type", "float")
                    unit = param_data.get("unit", "")
                    description = param_data.get("description", "")
                    converted_value = self._convert_value_to_type(value, value_type)

                    self.run_parameters[name] = RunParameterModel(
                        unit=unit,
                        description=description,
                        value=converted_value,
                        value_type=value_type,
                    )

    def _set_calibration_inputs(self, calib_inputs: dict[str, Any]) -> None:
        """Set calibration input parameters (for provenance tracking).

        Args:
        ----
            calib_inputs: Dictionary of calibration input parameters

        """
        for name, param_data in calib_inputs.items():
            if name in self.input_parameters:
                # Update existing parameter
                param = self.input_parameters[name]
                if param is not None:
                    if "value" in param_data:
                        param.value = param_data["value"]
                    if "unit" in param_data:
                        param.unit = param_data["unit"]
                    if "error" in param_data:
                        param.error = param_data["error"]
            else:
                # Create new ParameterModel for calibration input
                self.input_parameters[name] = InputParameterModel(
                    value=param_data.get("value", 0),
                    unit=param_data.get("unit", ""),
                    error=param_data.get("error", 0.0),
                    description=param_data.get("description", ""),
                )

    @abstractmethod
    def preprocess(self, backend: BaseBackend, qid: str) -> PreProcessResult:
        """Preprocess the task. This method is called before the task is executed.

        Args:
        ----
            backend: Backend object for device communication
            qid: qubit id

        """

    @abstractmethod
    def postprocess(
        self, backend: BaseBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Postprocess the task. This method is called after the task is executed.

        Args:
        ----
            backend: Backend object for device communication
            execution_id: execution id
            run_result: RunResult object
            qid: qubit id

        """

    @abstractmethod
    def run(self, backend: BaseBackend, qid: str) -> RunResult:
        """Run the task.

        Args:
        ----
            backend: Backend object for device communication
            qid: qubit id

        """

    @abstractmethod
    def batch_run(self, backend: BaseBackend, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits.

        Args:
        ----
            backend: Backend object for device communication
            qids: list of qubit ids

        """

    def is_valid(self, r2: float) -> None:
        """Diagnose the task. This method is called to check the task status."""
        if self.r2_is_lower_than_threshold(r2):
            raise ValueError(f"R^2 value of {self.name} is too low: {r2}")

    def get_output_parameters(self) -> list[str]:
        """Return the output parameter names of the task."""
        return list(self.output_parameters.keys())

    def get_input_parameters(self) -> list[str]:
        """Return the input parameter names (calibration dependencies) of the task."""
        return list(self.input_parameters.keys())

    def get_run_parameters(self) -> list[str]:
        """Return the run parameter names (experiment configuration) of the task."""
        return list(self.run_parameters.keys())

    def get_name(self) -> str:
        """Return the name of the task."""
        return self.name

    def get_task_type(self) -> str:
        """Return the type of the task."""
        return self.task_type

    def is_global_task(self) -> bool:
        """Return True if the task is a global task."""
        return bool(self.task_type == TaskTypes.GLOBAL)

    def is_qubit_task(self) -> bool:
        """Return True if the task is a qubit task."""
        return bool(self.task_type == TaskTypes.QUBIT)

    def is_coupling_task(self) -> bool:
        """Return True if the task is a coupling task."""
        return bool(self.task_type == TaskTypes.COUPLING)

    def is_system_task(self) -> bool:
        """Return True if the task is a system task."""
        return bool(self.task_type == TaskTypes.SYSTEM)

    def is_mux_task(self) -> bool:
        """Return True if the task is a MUX task."""
        return bool(self.task_type == TaskTypes.MUX)

    def attach_execution_id(self, execution_id: str) -> dict[str, OutputParameterModel]:
        """Attach the execution id to the output parameters."""
        for value in self.output_parameters.values():
            value.execution_id = execution_id
        return self.output_parameters

    def attach_task_id(self, task_id: str) -> dict[str, OutputParameterModel]:
        """Attach the task id to the output parameters."""
        for value in self.output_parameters.values():
            value.task_id = task_id
        return self.output_parameters
