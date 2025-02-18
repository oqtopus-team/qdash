import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel
from qcflow.subflow.constant import COMPLETED, FAILED, RUNNING, SCHDULED
from qcflow.subflow.system_info import SystemInfo
from qcflow.subflow.task_manager import CalibData, TaskResult


class ExecutionStatus(str, Enum):
    """
    Execution status enum.

    Attributes:
        SCHEDULED (str): The execution
        RUNNING (str): The execution
        COMPLETED (str): The execution
        FAILED (str): The execution
    """

    SCHEDULED = SCHDULED
    RUNNING = RUNNING
    COMPLETED = COMPLETED
    FAILED = FAILED


class ExecutionManager(BaseModel):
    """
    Execution manager class.

    Attributes:
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
    task_result: TaskResult = TaskResult()
    tags: list[str] = []
    controller_info: list[dict] = []
    fridge_info: float = 0.0
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
        tags: list[str],
        **kargs,
    ):
        super().__init__(**kargs)
        self.calib_data_path = calib_data_path
        self.execution_id = execution_id
        self.tags = tags
        self.save()

    def update_execution_status_to_running(self) -> None:
        """
        Update the execution status to running.
        """
        self.status = ExecutionStatus.RUNNING
        self.system_info.update_time()
        self.save()

    def update_execution_status_to_completed(self) -> None:
        """
        Update the execution status to success.
        """
        self.status = ExecutionStatus.COMPLETED
        self.system_info.update_time()
        self.save()

    def update_execution_status_to_failed(self) -> None:
        """
        Update the execution status to failed.
        """
        self.status = ExecutionStatus.FAILED
        self.system_info.update_time()
        self.save()

    def put_controller_info(self, box_info: dict) -> None:
        """
        Put the box information to the task manager.
        """
        self.controller_info.append(box_info)
        self.save()

    def save(self):
        """
        Save the task manager to a file.
        """
        save_path = f"{self.calib_data_path}/calib_note.json"
        with open(save_path, "w") as f:
            f.write(json.dumps(self.model_dump(), indent=4))

    # def start_task(self, task_name: str) -> None:
    #     """
    #     Start the task.
    #     """
    #     if task_name in self.tasks:
    #         self.tasks[task_name].start_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    #         self.save()
    #     else:
    #         raise ValueError(f"Task '{task_name}' not found.")

    # def end_task(self, task_name: str) -> None:
    #     """
    #     End the task.
    #     """
    #     if task_name in self.tasks:
    #         self.tasks[task_name].end_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    #         self.tasks[task_name].elapsed_time = self.tasks[task_name].calculate_elapsed_time(
    #             self.tasks[task_name].start_at, self.tasks[task_name].end_at
    #         )
    #     else:
    #         raise ValueError(f"Task '{task_name}' not found.")

    def calculate_elapsed_time(self, start_at: str, end_at: str):
        """
        Calculate the elapsed time.
        """
        start_time = datetime.strptime(start_at, "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(end_at, "%Y-%m-%d %H:%M:%S")
        elapsed_time = end_time - start_time
        return str(elapsed_time)

    def start_execution(self) -> None:
        """
        Start all the process.
        """
        self.start_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save()

    # def pending_task_all(self) -> None:
    #     """
    #     Update all the task status to pending.
    #     """
    #     for task_name in self.tasks.keys():
    #         if self.tasks[task_name].status == TaskStatus.SCHEDULED:
    #             self.update_task_status_to_pending(task_name)
    #             self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    #             self.save()

    def end_execution(self) -> None:
        """
        End all the process.
        """
        self.end_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.elapsed_time = self.calculate_elapsed_time(self.start_at, self.end_at)
        # self.pending_task_all()
        self.save()
