import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar

from qdash.datamodel.task import (
    SWEEP_VALUE_TYPES,
    InputParameterModel,
    InputParameterSpec,
    OutputParameterModel,
    OutputParameterSpec,
    RunParameterModel,
    RunParameterSpec,
    TaskTypes,
    compatible_value_type,
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


logger = logging.getLogger(__name__)


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
    timeout = 60 * 120  # Default timeout of 2 hours
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
        # Explicit calibration input overrides; TaskExecutor applies them after
        # preprocess so they replace the database or snapshot baseline.
        self.input_overrides: dict[str, Any] = {}
        # Explicit run parameter values; TaskExecutor applies them on top of a
        # re-execution snapshot, which otherwise replaces every run parameter.
        self.run_overrides: dict[str, Any] = {}

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

    def resolve_run_parameters(self, backend: BaseBackend, qid: str) -> None:
        """Resolve backend-dependent defaults before run parameters are recorded."""

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
        elif value_type == "list":
            if not isinstance(value, (list, tuple)):
                raise ValueError(f"list requires a JSON array, got {value!r}")
            return list(value)
        return value

    def _convert_and_set_parameters(self, params: dict[str, Any]) -> None:
        """Convert and set parameters from dictionary.

        Args:
        ----
            params: Dictionary containing task parameters

        """
        # Handle run_parameters (shared experiment configuration fallbacks)
        if "run_parameters" in params:
            self._set_run_parameters(params["run_parameters"])
        # Backward compatibility: old input_parameters -> run_parameters
        elif "input_parameters" in params:
            self._set_run_parameters(params["input_parameters"])
        # Explicit run parameter values set for this task
        if "run" in params:
            self._set_run_overrides(params["run"])

        # Calibration input overrides. ``calibration_inputs`` is the legacy key.
        if "calibration_inputs" in params:
            self._set_input_overrides(params["calibration_inputs"])
        if "input" in params:
            self._set_input_overrides(params["input"])

    def _set_run_parameters(self, run_params: dict[str, Any]) -> None:
        """Set run parameters (experiment configuration).

        Only parameters the task declares in ``run_spec`` are set. A task reads
        its run parameters by name, so a value under any other name (a flow's
        shared default meant for another task, a stale template entry) would
        never be used, and recording it would misstate the task's settings.

        Args:
        ----
            run_params: Dictionary of run parameters

        """
        for name, param_data in run_params.items():
            if name not in self.run_parameters:
                logger.debug(
                    "%s ignores run parameter %r: not declared in run_spec",
                    self.__class__.__name__,
                    name,
                )
                continue
            value = param_data.get("value")
            if value is not None:
                value_type = self._resolve_run_value_type(name, param_data.get("value_type"))
                converted_value = self._convert_value_to_type(value, value_type)
                self.run_parameters[name].value = converted_value
                self.run_parameters[name].value_type = value_type

    def _set_run_overrides(self, overrides: Mapping[str, Any]) -> None:
        """Set and record explicit run parameter values.

        Unlike ``_set_run_parameters``, an undeclared name fails because the value
        was set for this task specifically.

        Args:
        ----
            overrides: Run parameter names mapped to a value or ``{"value": ...}``

        """
        for name, data in overrides.items():
            if name not in self.run_parameters:
                raise ValueError(f"{self.name} does not declare run parameter {name!r}")
            param_data = data if isinstance(data, Mapping) else {"value": data}
            value = param_data.get("value")
            if value is None:
                raise ValueError(f"Run parameter {name!r} for {self.name} needs a value")
            value_type = self._resolve_run_value_type(name, param_data.get("value_type"))
            converted_value = self._convert_value_to_type(value, value_type)
            self.run_parameters[name].value = converted_value
            self.run_parameters[name].value_type = value_type
            self.run_overrides[name] = converted_value

    def _resolve_run_value_type(self, name: str, requested: Any) -> str:
        """Return the ``value_type`` a run value sets on the parameter ``name``.

        A parameter declared with a sweep constructor takes any sweep constructor or
        explicit ``list`` values, and the parameter then records the type it ran
        with. A scalar parameter keeps its declared type: a scalar type hint is
        informational, and a sweep for a scalar (or a scalar for a sweep) fails.
        """
        declared = self.run_parameters[name].value_type
        if not compatible_value_type(declared, requested):
            raise ValueError(
                f"{self.name}.{name} declares {declared!r} and cannot take a {requested!r} value"
            )
        if declared in SWEEP_VALUE_TYPES and requested is not None:
            return str(requested)
        return declared

    def _set_input_overrides(self, overrides: Mapping[str, Any]) -> None:
        """Record explicit calibration input overrides.

        Values are validated against ``input_spec`` here, so an undeclared name or a
        forbidden override fails when the task is created rather than being dropped.
        TaskExecutor applies the recorded values after preprocess.

        Args:
        ----
            overrides: Input names mapped to a value or ``{"value": ...}``

        """
        for name, data in overrides.items():
            declaration = self.__class__.input_spec.get(name)
            if declaration is None:
                raise ValueError(f"{self.name} does not declare calibration input {name!r}")
            value = data.get("value") if isinstance(data, Mapping) else data
            if value is None:
                raise ValueError(f"Input override {name!r} for {self.name} needs a value")
            self.input_overrides[name] = declaration.coerce_override(name, value)

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
