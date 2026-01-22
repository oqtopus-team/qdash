import math
import uuid
from copy import deepcopy
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Final, Literal

import numpy as np
from pydantic import BaseModel, Field, field_serializer, field_validator
from qdash.common.datetime_utils import format_elapsed_time, now, parse_elapsed_time
from qdash.datamodel.system_info import SystemInfoModel

SCHDULED = "scheduled"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
PENDING = "pending"
SKIPPED = "skipped"

# Task type definitions
TaskType = Literal["qubit", "coupling", "global", "system", "mux"]


class TaskTypes:
    """Constants for task types."""

    QUBIT: Final[TaskType] = "qubit"
    COUPLING: Final[TaskType] = "coupling"
    GLOBAL: Final[TaskType] = "global"
    SYSTEM: Final[TaskType] = "system"
    MUX: Final[TaskType] = "mux"


class RunParameterModel(BaseModel):
    """Run parameter class for experiment configuration (e.g., shots, ranges).

    This was previously named InputParameterModel. It handles experiment settings
    that are passed to measurement functions, NOT calibration parameters.
    """

    unit: str = ""
    value_type: str = "float"
    value: tuple[int | float, ...] | list[int | float] | int | float | None = None
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


class ParameterModel(BaseModel):
    """Calibration parameter model.

    Used for both input_parameters (calibration dependencies) and
    output_parameters (calibration outputs) in tasks.

    Attributes
    ----------
        parameter_name: The actual DB parameter name. If empty, the dict key is used.
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
    value: float | int = 0
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
    def replace_nan_with_zero(cls, v: float) -> float:
        """Replace NaN values with zero."""
        if isinstance(v, float) and math.isnan(v):
            return 0
        return v


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
    input_parameters: dict[str, Any] = {}
    output_parameters: dict[str, Any] = {}
    output_parameter_names: list[str] = []
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
        return v.isoformat() if v else None

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
