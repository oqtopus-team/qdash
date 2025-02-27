import uuid
from copy import deepcopy
from enum import Enum
from typing import Literal

import numpy as np
import pendulum
from datamodel.system_info import SystemInfoModel
from pydantic import BaseModel, Field

SCHDULED = "scheduled"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
PENDING = "pending"


class TaskStatusModel(str, Enum):
    """Task status enum.

    Attributes
    ----------
        SCHEDULED (str): The task is scheduled.
        RUNNING (str): The task is running.
        COMPLETED (str): The task is completed.
        FAILED (str): The task is failed.
        PENDING (str): The task is pending

    """

    SCHEDULED = SCHDULED
    RUNNING = RUNNING
    COMPLETED = COMPLETED
    FAILED = FAILED
    PENDING = PENDING


class DataModel(BaseModel):
    """Data model.

    Attributes
    ----------
        qubit (dict[str, dict[str, float | int]]): The calibration data for qubits.
        coupling (dict[str, dict[str, float | int]]): The calibration data for couplings.

    """

    value: float | int = 0
    unit: str = ""
    description: str = ""
    calibrated_at: str = Field(
        default_factory=lambda: pendulum.now(tz="Asia/Tokyo").to_iso8601_string(),
        description="The time when the system information was created",
    )
    execution_id: str = ""


class CalibDataModel(BaseModel):
    """Calibration data model.

    Attributes
    ----------
        qubit (dict[str, dict[str, Data]]): The calibration data for qubits.
        coupling (dict[str, dict[str, Data]]): The calibration data for couplings.

    """

    qubit: dict[str, dict[str, DataModel]] = Field(default_factory=dict)
    coupling: dict[str, dict[str, DataModel]] = Field(default_factory=dict)

    def put_qubit_data(self, qid: str, parameter_name: str, data: DataModel) -> None:
        self.qubit[qid][parameter_name] = data

    def put_coupling_data(self, qid: str, parameter_name: str, data: DataModel) -> None:
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

    name: str = Field(..., description="The name of the task")
    description: str = Field(..., description="Detailed description of the task")
    task_type: str = Field(..., description="The type of the task")
