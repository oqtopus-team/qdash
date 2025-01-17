import json
from copy import deepcopy
from datetime import datetime
from enum import Enum

import numpy as np
from pydantic import BaseModel


class TaskStatus(str, Enum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class TaskResult(BaseModel):
    name: str
    upstream_task: str
    status: TaskStatus = TaskStatus.SCHEDULED
    message: str
    input_parameters: dict = {}
    output_parameters: dict = {}
    calibrated_at: str = ""
    figure_path: str = ""

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


class TaskManager(BaseModel):
    calib_data_path: str = ""
    qubex_version: str = ""
    execution_id: str = ""
    tasks: dict[str, TaskResult] = {}
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = []
    box_infos: list[dict] = []

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
                calibrated_at="",
            )
            for i, name in enumerate(task_names)
        }
        self.tags = tags
        self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
            self.tasks[task_name].calibrated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
