import math
import uuid
from copy import deepcopy
from datetime import datetime, timedelta
from enum import Enum
from typing import Annotated, Any, Final, Literal, Self

import numpy as np
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    WithJsonSchema,
    field_serializer,
    field_validator,
    model_validator,
)

from qdash.common.utils.datetime import format_elapsed_time, format_iso, now, parse_elapsed_time
from qdash.datamodel.system_info import SystemInfoModel

SCHDULED = "scheduled"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
PENDING = "pending"
SKIPPED = "skipped"
CANCELLED = "cancelled"

# Task type definitions
TaskType = Literal["qubit", "coupling", "global", "system", "mux"]


class TaskTypes:
    """Constants for task types."""

    QUBIT: Final[TaskType] = "qubit"
    COUPLING: Final[TaskType] = "coupling"
    GLOBAL: Final[TaskType] = "global"
    SYSTEM: Final[TaskType] = "system"
    MUX: Final[TaskType] = "mux"


class ParameterSpec(BaseModel):
    """Common metadata declared for a task parameter."""

    unit: str = ""
    value_type: str = "float"
    description: str = ""


class RunParameterModel(BaseModel):
    """Run parameter class for experiment configuration (e.g., shots, ranges).

    This was previously named InputParameterModel. It handles experiment settings
    that are passed to measurement functions, NOT calibration parameters.
    """

    unit: str = ""
    value_type: str = "float"
    value: tuple[int | float, ...] | list[int | float] | int | float | str | None = None
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
            if self.value is None:
                raise ValueError("Cannot convert None to int")
            if isinstance(self.value, (tuple, list)):
                raise ValueError("Cannot convert tuple/list to int")
            return int(self.value)
        elif self.value_type == "float":
            if self.value is None:
                raise ValueError("Cannot convert None to float")
            if isinstance(self.value, (tuple, list)):
                raise ValueError("Cannot convert tuple/list to float")
            return float(self.value)
        elif self.value_type == "str":
            return str(self.value)
        elif self.value_type == "list":
            if not isinstance(self.value, (list, tuple)):
                raise ValueError("Cannot convert non-iterable to list")
            return list(self.value)
        return self.value


class RunParameterSpec(ParameterSpec):
    """Class-level declaration for experiment run configuration."""

    default: tuple[int | float, ...] | list[int | float] | int | float | str | None = None

    def create_model(self) -> RunParameterModel:
        """Create an independent runtime model from this declaration."""
        return RunParameterModel(
            unit=self.unit,
            value_type=self.value_type,
            value=deepcopy(self.default),
            description=self.description,
        )


class InputParameterSpec(ParameterSpec):
    """Declaration describing how a task calibration input is resolved."""

    resolution: Literal["database_required", "database_or_default", "default_only"]
    user_override: Literal["allowed", "forbidden"]
    default: float | int | None
    parameter_name: str = ""
    qid_role: Literal["self", "control", "target", "coupling"] = "self"
    greater_than: float | None = None
    less_than: float | None = None

    @classmethod
    def required_database(
        cls,
        *,
        user_override: Literal["allowed", "forbidden"] = "allowed",
        **metadata: Any,
    ) -> Self:
        """Declare a calibration input that must exist in the database."""
        return cls(
            resolution="database_required",
            user_override=user_override,
            default=None,
            **metadata,
        )

    @classmethod
    def database_or_default(
        cls,
        *,
        default: float | int,
        user_override: Literal["allowed", "forbidden"] = "allowed",
        **metadata: Any,
    ) -> Self:
        """Declare a database input with an explicit missing-value fallback."""
        return cls(
            resolution="database_or_default",
            user_override=user_override,
            default=default,
            **metadata,
        )

    @classmethod
    def default_only(
        cls,
        *,
        default: float | int,
        user_override: Literal["allowed", "forbidden"] = "allowed",
        **metadata: Any,
    ) -> Self:
        """Declare an input that never reads calibration state."""
        return cls(
            resolution="default_only",
            user_override=user_override,
            default=default,
            **metadata,
        )

    @model_validator(mode="after")
    def validate_resolution_default(self) -> "InputParameterSpec":
        """Reject contradictory resolution and default declarations."""
        if self.resolution == "database_required" and self.default is not None:
            raise ValueError("database_required must not declare a default")
        if self.resolution != "database_required" and self.default is None:
            raise ValueError(f"{self.resolution} requires a default")
        if (
            self.greater_than is not None
            and self.less_than is not None
            and self.greater_than >= self.less_than
        ):
            raise ValueError("greater_than must be less than less_than")
        return self

    def validate_effective_value(self, name: str, value: Any) -> None:
        """Validate a resolved value without changing it or applying a fallback."""
        if value is None:
            raise ValueError(f"Input parameter '{name}' was not resolved")
        if self.greater_than is None and self.less_than is None:
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Input parameter '{name}' must be numeric, got {value!r}")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError(f"Input parameter '{name}' must be finite, got {value!r}")
        if self.greater_than is not None and numeric <= self.greater_than:
            raise ValueError(
                f"Input parameter '{name}' must be greater than {self.greater_than}, got {value!r}"
            )
        if self.less_than is not None and numeric >= self.less_than:
            raise ValueError(
                f"Input parameter '{name}' must be less than {self.less_than}, got {value!r}"
            )

    def create_model(self) -> "InputParameterModel":
        """Create an independent runtime model from this declaration."""
        return InputParameterModel(
            parameter_name=self.parameter_name,
            qid_role=self.qid_role,
            value=self.default,
            value_type=self.value_type,
            unit=self.unit,
            description=self.description,
        )


class ParameterModel(BaseModel):
    """Common persisted metadata for resolved calibration parameters.

    Attributes
    ----------
        parameter_name: The actual DB parameter name. If empty, the dict key is used.
        source: Explicit source for dependency resolution. ``"database"`` declares
            that the value must be loaded from calibration state.
        required: Whether resolution must fail when the declared source has no value.
        qid_role: The qid role for 2-qubit tasks. One of:
            - "" or "self": Use task's qid as-is (default, for 1-qubit tasks)
            - "control": Use control qubit's qid (for 2-qubit tasks)
            - "target": Use target qubit's qid (for 2-qubit tasks)
            - "coupling": Use coupling qid as-is (for 2-qubit tasks)
        value: The parameter value.
        value_type: The type of the value (default: "float").
        error: The error/uncertainty of the value.
        unit: The unit of measurement.
        description: Description of the parameter.
        calibrated_at: When the calibration was performed.
        execution_id: The execution that produced this value.
        task_id: The task that produced this value.

    """

    parameter_name: str = ""
    qid_role: str = ""
    source: Literal["database"] | None = None
    required: bool = False
    value: float | int | None = 0
    value_type: str = "float"
    error: float = 0
    unit: str = ""
    description: str = ""
    calibrated_at: datetime = Field(
        default_factory=now,
        description="The time when the calibration was performed",
    )
    execution_id: str = ""
    task_id: str = ""

    @field_validator("value", mode="before")
    @classmethod
    def replace_nan_with_zero(cls, v: float | int | None) -> float | int | None:
        """Replace NaN values with zero."""
        if isinstance(v, float) and math.isnan(v):
            return 0
        return v


class InputParameterModel(ParameterModel):
    """Resolved input parameter used by one task instance."""


class OutputParameterModel(ParameterModel):
    """Output parameter produced by one task instance."""


class TaskResultParameterModel(BaseModel):
    """Flexible parameter persisted in task-result history."""

    parameter_name: str = ""
    qid_role: str = ""
    source: Literal["database"] | None = None
    required: bool = False
    value: Any = None
    value_type: str = ""
    error: float = 0
    unit: str = ""
    description: str = ""
    calibrated_at: datetime | None = None
    execution_id: str = ""
    task_id: str = ""

    model_config = ConfigDict(extra="allow")


class TaskResultInputParameterModel(TaskResultParameterModel):
    """Input parameter persisted in task-result history."""


class TaskResultOutputParameterModel(TaskResultParameterModel):
    """Output parameter persisted in task-result history with DB comparison metadata."""

    previous_database_value: Any = None
    database_updated: bool = False


def _validate_task_result_input_parameter(value: Any) -> Any:
    """Validate a history input parameter while retaining dictionary compatibility."""
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if not isinstance(value, dict):
        return value
    return TaskResultInputParameterModel.model_validate(value).model_dump(exclude_unset=True)


def _validate_task_result_output_parameter(value: Any) -> Any:
    """Validate a history parameter while retaining dictionary compatibility."""
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if not isinstance(value, dict):
        return value
    return TaskResultOutputParameterModel.model_validate(value).model_dump(exclude_unset=True)


TaskResultOutputParameter = Annotated[
    Any,
    BeforeValidator(_validate_task_result_output_parameter),
    WithJsonSchema(TaskResultOutputParameterModel.model_json_schema()),
]

TaskResultInputParameter = Annotated[
    Any,
    BeforeValidator(_validate_task_result_input_parameter),
    WithJsonSchema(TaskResultInputParameterModel.model_json_schema()),
]


class OutputParameterSpec(ParameterSpec):
    """Class-level declaration for a calibration output."""

    default: float | int | None = 0
    qid_role: str = ""

    def create_model(self) -> OutputParameterModel:
        """Create an independent runtime model from this declaration."""
        return OutputParameterModel(
            qid_role=self.qid_role,
            value=self.default,
            value_type=self.value_type,
            unit=self.unit,
            description=self.description,
        )


class TaskStatusModel(str, Enum):
    """Task status enum.

    Attributes
    ----------
        SCHEDULED (str): The task is scheduled.
        RUNNING (str): The task is running.
        COMPLETED (str): The task is completed.
        FAILED (str): The task is failed.
        PENDING (str): The task is pending
        SKIPPED (str): The task is skipped

    """

    SCHEDULED = SCHDULED
    RUNNING = RUNNING
    COMPLETED = COMPLETED
    FAILED = FAILED
    PENDING = PENDING
    SKIPPED = SKIPPED
    CANCELLED = CANCELLED


class CalibDataModel(BaseModel):
    """Calibration data model.

    Attributes
    ----------
        qubit (dict[str, dict[str, Data]]): The calibration data for qubits.
        coupling (dict[str, dict[str, Data]]): The calibration data for couplings.

    """

    qubit: dict[str, dict[str, ParameterModel]] = Field(default_factory=dict)
    coupling: dict[str, dict[str, ParameterModel]] = Field(default_factory=dict)

    def put_qubit_data(self, qid: str, parameter_name: str, data: ParameterModel) -> None:
        if qid not in self.qubit:
            self.qubit[qid] = {}
        self.qubit[qid][parameter_name] = data

    def put_coupling_data(self, qid: str, parameter_name: str, data: ParameterModel) -> None:
        if qid not in self.coupling:
            self.coupling[qid] = {}
        self.coupling[qid][parameter_name] = data

    def __getitem__(self, key: str) -> dict[str, dict[str, ParameterModel]]:
        """Get the item by key."""
        if key in ("qubit", "coupling"):
            return getattr(self, key)  # type: ignore
        raise KeyError(f"Invalid key: {key}")


class BaseTaskResultModel(BaseModel):
    """Base class for task results.

    Attributes
    ----------
        id (str): The unique identifier of the task result.
        name (str): The name of the task.
        upstream_id (str): The unique identifier of the upstream task.
        status (TaskStatus): The status of the task. e.g. "scheduled", "running", "completed", "failed".
        message (str): The message of the task.
        input_parameters (dict): The input parameters of the task.
        output_parameters (dict): The output parameters of the task.
        note (str): The note of the task.
        figure_path (list[str]): The path of the figure.
        start_at (datetime): The time when the task started.
        end_at (datetime): The time when the task ended.
        elapsed_time (timedelta): The elapsed time of the task.
        task_type (str): The type of the task.
        system_info (SystemInfoModel): The system information.

    """

    project_id: str | None = Field(default=None, description="Owning project identifier")
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    upstream_id: str = ""
    status: TaskStatusModel = TaskStatusModel.SCHEDULED
    message: str = ""
    stack_trace: str = ""
    input_parameters: dict[str, Any] = {}
    output_parameters: dict[str, Any] = {}
    output_parameter_names: list[str] = []
    run_parameters: dict[str, Any] = {}
    quality_metrics: dict[str, float] = {}
    note: dict[str, Any] = {}
    figure_path: list[str] = []
    json_figure_path: list[str] = []
    raw_data_path: list[str] = []
    start_at: datetime | None = None
    end_at: datetime | None = None
    elapsed_time: timedelta | None = None
    task_type: str = "global"
    system_info: SystemInfoModel = SystemInfoModel()

    @field_validator("elapsed_time", mode="before")
    @classmethod
    def _parse_elapsed_time(cls, v: Any) -> timedelta | None:
        """Parse elapsed_time from various formats including human-readable strings."""
        return parse_elapsed_time(v)

    @field_serializer("start_at", "end_at")
    @classmethod
    def _serialize_datetime(cls, v: datetime | None) -> str | None:
        """Serialize datetime to ISO format for JSON compatibility."""
        return format_iso(v)

    @field_serializer("elapsed_time")
    @classmethod
    def _serialize_elapsed_time(cls, v: timedelta | None) -> str | None:
        """Serialize elapsed_time to H:MM:SS format."""
        return format_elapsed_time(v) if v else None

    def diagnose(self) -> None:
        """Diagnose the task result and raise an error if the task failed."""
        if self.status == TaskStatusModel.FAILED:
            raise RuntimeError(f"Task {self.name} failed with message: {self.message}")

    def put_input_parameter(self, input_parameters: dict[str, Any]) -> None:
        """Put a parameter to the task result."""
        copied_parameters = deepcopy(input_parameters)
        # Process the copied_parameters
        for key, item in copied_parameters.items():
            if isinstance(item, np.ndarray):
                copied_parameters[key] = str(item.tolist())
            elif isinstance(item, range):
                copied_parameters[key] = str(list(item))
            else:
                copied_parameters[key] = item
        self.input_parameters = copied_parameters

    def put_run_parameter(self, run_parameters: dict[str, Any]) -> None:
        """Put run parameters to the task result."""
        self.run_parameters = deepcopy(run_parameters)

    def put_output_parameter(self, output_parameters: dict[str, Any]) -> None:
        import numpy as np

        """
        put a parameter to the task result.
        """
        copied_parameters = deepcopy(output_parameters)
        # Process the copied_parameters
        for key, item in copied_parameters.items():
            if isinstance(item, np.ndarray):
                copied_parameters[key] = str(item.tolist())
            elif isinstance(item, range):
                copied_parameters[key] = str(list(item))
            else:
                copied_parameters[key] = item
            self.output_parameter_names.append(key)
        self.output_parameters = copied_parameters

    def put_note(self, note: dict[str, Any]) -> None:
        """Put a note to the task result.

        Args:
        ----
            note (str): The note to put.

        """
        self.note = note

    def calculate_elapsed_time(self, start_at: datetime, end_at: datetime) -> timedelta:
        """Calculate the elapsed time.

        Args:
        ----
            start_at (datetime): The start time.
            end_at (datetime): The end time.

        Returns:
        -------
            timedelta: The elapsed time.

        """
        return end_at - start_at


class SystemTaskModel(BaseTaskResultModel):
    """System task result class.

    Attributes
    ----------
        task_type (str): The type of the task. e.g. "system".

    """

    task_type: Literal["system"] = "system"


class GlobalTaskModel(BaseTaskResultModel):
    """Global task result class.

    Attributes
    ----------
        task_type (str): The type of the task. e.g. "global".

    """

    task_type: Literal["global"] = "global"


class QubitTaskModel(BaseTaskResultModel):
    """Qubit task result class.

    Attributes
    ----------
        task_type (str): The type of the task. e.g. "qubit".
        qid (str): The qubit id.

    """

    task_type: Literal["qubit"] = "qubit"
    qid: str


class CouplingTaskModel(BaseTaskResultModel):
    """Coupling task result class.

    Attributes
    ----------
        task_type (str): The type of the task. e.g. "coupling".
        qid (str): The qubit id.

    """

    task_type: Literal["coupling"] = "coupling"
    qid: str


class MuxTaskModel(BaseTaskResultModel):
    """MUX task result class.

    For tasks that operate on a MUX (multiplexer) unit,
    typically affecting multiple qubits simultaneously.

    Attributes
    ----------
        task_type (str): The type of the task. e.g. "mux".
        mux_id (int): The MUX identifier.

    """

    task_type: Literal["mux"] = "mux"
    mux_id: int


class TaskResultModel(BaseModel):
    """Task result class.

    Attributes
    ----------
        global_tasks (list[GlobalTask]): The global tasks.
        qubit_tasks (dict[str, list[QubitTask]]): The qubit tasks.
        coupling_tasks (dict[str, list[CouplingTask]]): The coupling tasks.
        mux_tasks (dict[int, list[MuxTask]]): The MUX tasks keyed by mux_id.

    """

    system_tasks: list[SystemTaskModel] = []
    global_tasks: list[GlobalTaskModel] = []
    qubit_tasks: dict[str, list[QubitTaskModel]] = {}
    coupling_tasks: dict[str, list[CouplingTaskModel]] = {}
    mux_tasks: dict[int, list[MuxTaskModel]] = {}


class TaskModel(BaseModel):
    """Task model.

    Attributes
    ----------
        name (str): The name of the task. e.g. "CheckT1" ,"CheckT2Echo" ".
        description (str): Detailed description of the task.
        task_type (str): The type of the task. e.g. "global", "qubit", "coupling".

    """

    project_id: str | None = Field(None, description="Owning project identifier")
    username: str = Field(..., description="The username of the user who created the task")
    name: str = Field(..., description="The name of the task")
    backend: str | None = Field(None, description="The backend of the task")
    description: str = Field(..., description="Detailed description of the task")
    task_type: str = Field(..., description="The type of the task")
    input_parameters: dict[str, Any] = Field(..., description="The input parameters of the task")
    output_parameters: dict[str, Any] = Field(..., description="The output parameters of the task")
