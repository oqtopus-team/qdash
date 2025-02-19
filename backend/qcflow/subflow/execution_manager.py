import json
from enum import Enum
from pathlib import Path

import pendulum
from pydantic import BaseModel
from qcflow.subflow.constant import COMPLETED, FAILED, RUNNING, SCHDULED
from qcflow.subflow.system_info import SystemInfo
from qcflow.subflow.task_manager import CalibData, TaskResult


class ExecutionStatus(str, Enum):
    """Enum class for execution status.

    Attributes
    ----------
        SCHEDULED (str): The execution is scheduled.
        RUNNING (str): The execution is running.
        COMPLETED (str): The execution is completed.
        FAILED (str): The execution is failed.

    """

    SCHEDULED = SCHDULED
    RUNNING = RUNNING
    COMPLETED = COMPLETED
    FAILED = FAILED


class ExecutionManager(BaseModel):
    """Execution manager class.

    Attributes
    ----------
        execution_id (str): The execution id.
        calib_data_path (str): The calibration data path.
        qubex_version (str): The qubex version.
        status (ExecutionStatus): The execution status.
        task_result (TaskResult): The task result.
        created_at (str): The created time.
        updated_at (str): The updated time.
        tags (list[str]): The tags.
        controller_info (list[dict]): The controller information.
        fridge_info (float): The fridge information.
        chip_id (str): The chip id.
        start_at (str): The start time.
        end_at (str): The end time.
        elapsed_time (str): The elapsed time.
        calib_data (CalibData): The calibration data.

    """

    execution_id: str = ""
    calib_data_path: str = ""
    qubex_version: str = ""
    status: ExecutionStatus = ExecutionStatus.SCHEDULED
    task_results: dict[str, TaskResult] = {}
    tags: list[str] = []
    controller_info: list[dict] = []
    fridge_info: dict = {}
    chip_id: str = ""
    start_at: str = ""
    end_at: str = ""
    elapsed_time: str = ""
    calib_data: CalibData = CalibData(qubit={}, coupling={})
    system_info: SystemInfo = SystemInfo()

    def __init__(
        self,
        execution_id: str,
        calib_data_path: str,
        tags: list[str] = [],
        fridge_info: dict = {},
        chip_id: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.calib_data_path = calib_data_path
        self.execution_id = execution_id
        self.fridge_info = fridge_info
        self.tags = tags
        self.chip_id = chip_id
        self.save()

    def update_execution_status_to_running(self) -> None:
        """Update the execution status to running."""
        self.status = ExecutionStatus.RUNNING
        self.system_info.update_time()
        self.save()

    def update_execution_status_to_completed(self) -> None:
        """Update the execution status to success."""
        self.status = ExecutionStatus.COMPLETED
        self.system_info.update_time()
        self.save()

    def update_execution_status_to_failed(self) -> None:
        """Update the execution status to failed."""
        self.status = ExecutionStatus.FAILED
        self.system_info.update_time()
        self.save()

    def put_controller_info(self, box_info: dict) -> None:
        """Put the box information to the task manager."""
        self.controller_info.append(box_info)
        self.save()

    def save(self) -> None:
        """Save the task manager to a file."""
        from pathlib import Path

        save_path = Path(f"{self.calib_data_path}/execution_note.json")
        with save_path.open("w") as f:
            f.write(json.dumps(self.model_dump(), indent=2))

    @classmethod
    def load_from_file(cls, calib_data_path: str) -> "ExecutionManager":
        """Load the task manager from a file."""
        save_path = Path(f"{calib_data_path}/execution_note.json")
        return cls.model_validate_json(save_path.read_text())

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
        return end_time.diff_for_humans(start_time, absolute=True)

    def start_execution(self) -> None:
        """Start all the process."""
        self.start_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
        self.save()

    def end_execution(self) -> None:
        """End all the process."""
        self.end_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
        self.elapsed_time = self.calculate_elapsed_time(self.start_at, self.end_at)
        # self.pending_task_all()
        self.save()
