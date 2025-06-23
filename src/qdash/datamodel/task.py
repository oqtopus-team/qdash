import math
import uuid
from copy import deepcopy
from enum import Enum
from typing import Any, Literal

import numpy as np
import pendulum
from pydantic import BaseModel, Field, field_validator
from qdash.datamodel.system_info import SystemInfoModel

SCHDULED = "scheduled"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
PENDING = "pending"
SKIPPED = "skipped"


class InputParameterModel(BaseModel):
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
        elif self.value_type == "str":
            return str(self.value)
        elif self.value_type == "list":
            return list(self.value)
        return self.value


class OutputParameterModel(BaseModel):
    """Data model.

    Attributes
    ----------
        qubit (dict[str, dict[str, float | int]]): The calibration data for qubits.
        coupling (dict[str, dict[str, float | int]]): The calibration data for couplings.

    """

    value: float | int = 0
    value_type: str = "float"
    error: float = 0
    unit: str = ""
    description: str = ""
    calibrated_at: str = Field(
        default_factory=lambda: pendulum.now(tz="Asia/Tokyo").to_iso8601_string(),
        description="The time when the system information was created",
    )
    execution_id: str = ""

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

    qubit: dict[str, dict[str, OutputParameterModel]] = Field(default_factory=dict)
    coupling: dict[str, dict[str, OutputParameterModel]] = Field(default_factory=dict)

    def put_qubit_data(self, qid: str, parameter_name: str, data: OutputParameterModel) -> None:
        self.qubit[qid][parameter_name] = data

    def put_coupling_data(self, qid: str, parameter_name: str, data: OutputParameterModel) -> None:
        self.coupling[qid][parameter_name] = data

    def __getitem__(self, key: str) -> dict:
        """Get the item by key."""
        if key in ("qubit", "coupling"):
            return getattr(self, key)  # type: ignore #noqa: PGH003
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
        start_at (str): The time when the task started.
        end_at (str): The time when the task ended.
        elapsed_time (str): The elapsed time of the task.
        task_type (str): The type of the task.
        system_info (SystemInfoModel): The system information.

    """

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    upstream_id: str = ""
    status: TaskStatusModel = TaskStatusModel.SCHEDULED
    message: str = ""
    input_parameters: dict = {}
    output_parameters: dict = {}
    output_parameter_names: list[str] = []
    note: dict = {}
    figure_path: list[str] = []
    json_figure_path: list[str] = []
    raw_data_path: list[str] = []
    start_at: str = ""
    end_at: str = ""
    elapsed_time: str = ""
    task_type: str = "global"
    system_info: SystemInfoModel = SystemInfoModel()

    def diagnose(self) -> None:
        """Diagnose the task result and raise an error if the task failed."""
        if self.status == TaskStatusModel.FAILED:
            raise RuntimeError(f"Task {self.name} failed with message: {self.message}")

    def put_input_parameter(self, input_parameters: dict) -> None:
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

    def put_output_parameter(self, output_parameters: dict) -> None:
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

    def put_note(self, note: dict) -> None:
        """Put a note to the task result.

        Args:
        ----
            note (str): The note to put.

        """
        self.note = note

    def calculate_elapsed_time(self, start_at: str, end_at: str) -> str:
        """Calculate the elapsed time.

        Args:
        ----
            start_at (str): The start time.
            end_at (str): The end time.

        """
        try:
            start_time = pendulum.parse(start_at)
            end_time = pendulum.parse(end_at)
        except Exception as e:
            error_message = f"Failed to parse the time. {e}"
            raise ValueError(error_message)
        return end_time.diff_for_humans(start_time, absolute=True)  # type: ignore #noqa: PGH003


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


class TaskResultModel(BaseModel):
    """Task result class.

    Attributes
    ----------
        global_tasks (list[GlobalTask]): The global tasks.
        qubit_tasks (dict[str, list[QubitTask]]): The qubit tasks.
        coupling_tasks (dict[str, list[CouplingTask]]): The coupling tasks.

    """

    system_tasks: list[SystemTaskModel] = []
    global_tasks: list[GlobalTaskModel] = []
    qubit_tasks: dict[str, list[QubitTaskModel]] = {}
    coupling_tasks: dict[str, list[CouplingTaskModel]] = {}


class TaskModel(BaseModel):
    """Task model.

    Attributes
    ----------
        name (str): The name of the task. e.g. "CheckT1" ,"CheckT2Echo" ".
        description (str): Detailed description of the task.
        task_type (str): The type of the task. e.g. "global", "qubit", "coupling".

    """

    username: str = Field(..., description="The username of the user who created the task")
    name: str = Field(..., description="The name of the task")
    backend: str | None = Field(None, description="The backend of the task")
    description: str = Field(..., description="Detailed description of the task")
    task_type: str = Field(..., description="The type of the task")
    input_parameters: dict = Field(..., description="The input parameters of the task")
    output_parameters: dict = Field(..., description="The output parameters of the task")
