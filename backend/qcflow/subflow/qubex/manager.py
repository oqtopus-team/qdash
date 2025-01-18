import json
from copy import deepcopy
from datetime import datetime
from enum import Enum
from typing import Optional

import numpy as np
from pydantic import BaseModel, Field

SCHDULED = "scheduled"
RUNNING = "running"
SUCCESS = "success"
FAILED = "failed"


class TaskStatus(str, Enum):
    SCHEDULED = SCHDULED
    RUNNING = RUNNING
    SUCCESS = SUCCESS
    FAILED = FAILED


class ExecutionStatus(str, Enum):
    SCHEDULED = SCHDULED
    RUNNING = RUNNING
    SUCCESS = SUCCESS
    FAILED = FAILED


class TaskHistoryModel(BaseModel):
    execution_id: str = Field(..., description="Execution ID for the process")
    task_name: str = Field(..., description="Name of the task")
    status: str = Field(..., description="Status of the task (e.g., SUCCESS, FAILED)")
    start_at: datetime = Field(..., description="Start time of the task")
    end_at: Optional[datetime] = Field(None, description="End time of the task")
    elapsed_time: Optional[str] = Field(None, description="Elapsed time of the task")
    input_parameters: dict = Field(
        default_factory=dict, description="Input parameters for the task"
    )
    output_parameters: dict = Field(
        default_factory=dict, description="Output parameters for the task"
    )


class ExecutionHistoryModel(BaseModel):
    execution_id: str = Field(..., description="Execution ID for the process")
    chip_id: str = Field(..., description="Chip ID used in the process")
    start_at: datetime = Field(..., description="Start time of the process")
    end_at: Optional[datetime] = Field(None, description="End time of the process")
    elapsed_time: Optional[str] = Field(None, description="Elapsed time of the process")
    tags: list[str] = Field(default_factory=list, description="Tags associated with the process")
    tasks: list[str] = Field(..., description="List of task names executed in this process")
    status: str = Field(..., description="Overall status of the process")


class TaskResult(BaseModel):
    name: str
    upstream_task: str
    status: TaskStatus = TaskStatus.SCHEDULED
    message: str
    input_parameters: dict = {}
    output_parameters: dict = {}
    figure_path: str = ""
    start_at: str = ""
    end_at: str = ""
    elapsed_time: str = ""

    def diagnose(self):
        """
        diagnose the task result and raise an error if the task failed.
        """
        if self.status == TaskStatus.FAILED:
            raise RuntimeError(f"Task {self.name} failed with message: {self.message}")

    def put_input_parameter(self, key: str, value: dict):
        """
        put a parameter to the task result.
        """
        self.input_parameters[key] = value

    def put_output_parameter(self, key: str, value: dict):
        """
        put a parameter to the task result.
        """
        self.output_parameters[key] = value

    def calculate_elapsed_time(self, start_at: str, end_at: str):
        """
        Calculate the elapsed time.
        """
        start_time = datetime.strptime(start_at, "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(end_at, "%Y-%m-%d %H:%M:%S")
        elapsed_time = end_time - start_time
        return str(elapsed_time)


class ExecutionManager(BaseModel):
    calib_data_path: str = ""
    qubex_version: str = ""
    execution_id: str = ""
    status: ExecutionStatus = ExecutionStatus.SCHEDULED
    tasks: dict[str, TaskResult] = {}
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = []
    box_infos: list[dict] = []
    fridge_temperature: float = 0.0
    chip_id: str = ""
    start_at: str = ""
    end_at: str = ""
    elapsed_time: str = ""

    def __init__(
        self,
        execution_id: str,
        calib_data_path: str,
        task_names: list[str],
        tags: list[str],
        **kargs,
    ):
        super().__init__(**kargs)
        if not task_names or not isinstance(task_names, list):
            raise ValueError("task_names must be a non-empty list of strings.")
        self.calib_data_path = calib_data_path
        self.execution_id = execution_id
        self.tasks = {
            name: TaskResult(
                name=name,
                upstream_task=task_names[i - 1] if i > 0 else "",
                status=TaskStatus.SCHEDULED,
                message="",
                input_parameters={},
                output_parameters={},
                start_at="",
                end_at="",
                elapsed_time="",
            )
            for i, name in enumerate(task_names)
        }
        self.tags = tags
        self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save()

    def update_execution_status_to_running(self) -> None:
        """
        Update the execution status to running.
        """
        self.status = ExecutionStatus.RUNNING
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save()

    def update_execution_status_to_success(self) -> None:
        """
        Update the execution status to success.
        """
        self.status = ExecutionStatus.SUCCESS
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save()

    def update_execution_status_to_failed(self) -> None:
        """
        Update the execution status to failed.
        """
        self.status = ExecutionStatus.FAILED
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save()

    def update_task_status_to_running(self, task_name: str) -> None:
        """
        Update the task status to running.
        """
        if task_name in self.tasks:
            self.tasks[task_name].status = TaskStatus.RUNNING
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()
        else:
            raise ValueError(f"Task '{task_name}' not found.")

    def update_task_status_to_success(self, task_name: str, message: str = "") -> None:
        """
        Update the task status to success.
        """
        if task_name in self.tasks:
            self.tasks[task_name].status = TaskStatus.SUCCESS
            self.tasks[task_name].message = message
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()
        else:
            raise ValueError(f"Task '{task_name}' not found.")

    def update_task_status_to_failed(self, task_name: str, message: str = "") -> None:
        """
        Update the task status to failed.
        """
        if task_name in self.tasks:
            self.tasks[task_name].status = TaskStatus.FAILED
            self.tasks[task_name].message = message
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()
        else:
            raise ValueError(f"Task '{task_name}' not found.")

    def put_input_parameter(self, task_name: str, key: str, value: dict) -> None:
        """
        Put a parameter to the task result.
        """
        if task_name in self.tasks:
            self.tasks[task_name].input_parameters[key] = value
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()
        else:
            raise ValueError(f"Task '{task_name}' not found")

    def put_input_parameters(self, task_name: str, input_parameters: dict) -> None:
        """
        Put a parameter to the task result.
        """

        copied_parameters = deepcopy(input_parameters)
        # Process the copied_parameters
        for key, item in copied_parameters.items():
            if isinstance(item, np.ndarray):
                copied_parameters[key] = str(item.tolist())
            elif isinstance(item, range):
                copied_parameters[key] = str(list(item))

        # Update the task with the modified parameters
        if task_name in self.tasks:
            self.tasks[task_name].input_parameters = copied_parameters
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()
        else:
            raise ValueError(f"Task '{task_name}' not found")

    def put_output_parameter(self, task_name: str, key: str, value: dict) -> None:
        """
        Put a parameter to the task result.
        """
        if task_name in self.tasks:
            self.tasks[task_name].output_parameters[key] = value
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()
        else:
            raise ValueError(f"Task '{task_name}' not found.")

    def put_output_parameters(self, task_name: str, output_parameters: dict) -> None:
        """
        Put a parameter to the task result.
        """

        copied_parameters = deepcopy(output_parameters)
        # Process the copied_parameters
        for key, item in copied_parameters.items():
            if isinstance(item, np.ndarray):
                copied_parameters[key] = str(item.tolist())
            elif isinstance(item, range):
                copied_parameters[key] = str(list(item))

        # Update the task with the modified parameters
        if task_name in self.tasks:
            self.tasks[task_name].output_parameters = copied_parameters
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()
        else:
            raise ValueError(f"Task '{task_name}' not found")

    def get_task(self, task_name: str) -> TaskResult:
        """
        Get the task result by task name.
        """
        if task_name in self.tasks:
            return self.tasks[task_name]
        else:
            raise ValueError(f"Task '{task_name}' not found.")

    def put_box_info(self, box_info: dict) -> None:
        """
        Put the box information to the task manager.
        """
        self.box_infos.append(box_info)
        self.save()

    def save(self):
        """
        Save the task manager to a file.
        """
        save_path = f"{self.calib_data_path}/calib_data.json"
        with open(save_path, "w") as f:
            f.write(json.dumps(self.model_dump(), indent=4))

    def start_task(self, task_name: str) -> None:
        """
        Start the task.
        """
        if task_name in self.tasks:
            self.tasks[task_name].start_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()
        else:
            raise ValueError(f"Task '{task_name}' not found.")

    def end_task(self, task_name: str) -> None:
        """
        End the task.
        """
        if task_name in self.tasks:
            self.tasks[task_name].end_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.tasks[task_name].elapsed_time = self.tasks[task_name].calculate_elapsed_time(
                self.tasks[task_name].start_at, self.tasks[task_name].end_at
            )
        else:
            raise ValueError(f"Task '{task_name}' not found.")

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

    def end_execution(self) -> None:
        """
        End all the process.
        """
        self.end_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.elapsed_time = self.calculate_elapsed_time(self.start_at, self.end_at)
        self.save()

    def export_execution_history(self) -> ExecutionHistoryModel:
        """
        Export the execution history.
        """
        return ExecutionHistoryModel(
            execution_id=self.execution_id,
            chip_id=self.chip_id,
            start_at=datetime.strptime(self.start_at, "%Y-%m-%d %H:%M:%S"),
            end_at=datetime.strptime(self.end_at, "%Y-%m-%d %H:%M:%S"),
            elapsed_time=self.elapsed_time,
            tags=self.tags,
            tasks=list(self.tasks.keys()),
            status=self.status,
        )

    def save_execution_history(self):
        """
        Save the execution history.
        """
        save_path = f"{self.calib_data_path}/execution_history.json"
        with open(save_path, "w") as f:
            f.write(json.dumps(self.export_execution_history().model_dump(), indent=4))

    def export_task_histories(self) -> list[TaskHistoryModel]:
        """
        Export the task histories.
        """
        return [
            TaskHistoryModel(
                execution_id=self.execution_id,
                task_name=task_name,
                status=task.status,
                start_at=datetime.strptime(task.start_at, "%Y-%m-%d %H:%M:%S"),
                end_at=datetime.strptime(task.end_at, "%Y-%m-%d %H:%M:%S"),
                elapsed_time=task.elapsed_time,
                input_parameters=task.input_parameters,
                output_parameters=task.output_parameters,
            )
            for task_name, task in self.tasks.items()
        ]

    def save_task_histories(self):
        """
        Save the task histories.
        """
        save_path = f"{self.calib_data_path}/task_histories.json"
        with open(save_path, "w") as f:
            f.write(
                json.dumps(
                    [task.model_dump() for task in self.export_task_histories()],
                    indent=4,
                )
            )

    def export_task_history(self, task_name: str) -> TaskHistoryModel:
        """
        Export the task history.
        """
        return TaskHistoryModel(
            execution_id=self.execution_id,
            task_name=task_name,
            status=self.tasks[task_name].status,
            start_at=datetime.strptime(self.tasks[task_name].start_at, "%Y-%m-%d %H:%M:%S"),
            end_at=datetime.strptime(self.tasks[task_name].end_at, "%Y-%m-%d %H:%M:%S"),
            elapsed_time=self.tasks[task_name].elapsed_time,
            input_parameters=self.tasks[task_name].input_parameters,
            output_parameters=self.tasks[task_name].output_parameters,
        )

    def save_task_history(self, task_name: str):
        """
        Save the task history.
        """
        save_path = f"{self.calib_data_path}/{task_name}_history.json"
        with open(save_path, "w") as f:
            f.write(json.dumps(self.export_task_history(task_name).model_dump(), indent=4))
