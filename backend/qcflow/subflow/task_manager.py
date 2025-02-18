import json
import os
import uuid
from copy import deepcopy
from datetime import datetime
from enum import Enum
from typing import Literal

import numpy as np
import plotly.graph_objs as go
from pydantic import BaseModel, Field
from qcflow.subflow.constant import COMPLETED, FAILED, PENDING, RUNNING, SCHDULED
from qcflow.subflow.system_info import SystemInfo


class TaskStatus(str, Enum):
    """
    Task status enum.

    Attributes:
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


class CalibData(BaseModel):
    """
    Calibration data model.

    Attributes:
        qubit (dict[str, dict[str, float | int]]): The calibration data for qubits.
        coupling (dict[str, dict[str, float | int]]): The calibration data for couplings.
    """

    qubit: dict[str, dict[str, float | int]] = Field(default_factory=dict)
    coupling: dict[str, dict[str, float | int]] = Field(default_factory=dict)

    def put_qubit_data(self, qid: str, parameter_name: str, value: float | int):
        self.qubit[qid][parameter_name] = value

    def put_coupling_data(self, qid: str, parameter_name: str, value: float | int):
        self.coupling[qid][parameter_name] = value


class BaseTaskResult(BaseModel):
    """
    Base class for task results.

    Attributes:

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

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    upstream_id: str = ""
    status: TaskStatus = TaskStatus.SCHEDULED
    message: str = ""
    input_parameters: dict = {}
    output_parameters: dict = {}
    note: str = ""
    figure_path: list[str] = []
    start_at: str = ""
    end_at: str = ""
    elapsed_time: str = ""
    task_type: str = "global"
    system_info: SystemInfo = SystemInfo()

    def diagnose(self):
        """
        diagnose the task result and raise an error if the task failed.
        """
        if self.status == TaskStatus.FAILED:
            raise RuntimeError(f"Task {self.name} failed with message: {self.message}")

    def put_input_parameter(self, input_parameters: dict):
        """
        put a parameter to the task result.
        """
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

    def put_output_parameter(self, output_parameters: dict):
        from copy import deepcopy

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
        self.output_parameters = copied_parameters

    def put_note(self, note: str):
        """
        put a note to the task result.
        """
        self.note = note

    def calculate_elapsed_time(self, start_at: str, end_at: str):
        """
        Calculate the elapsed time.
        """
        start_time = datetime.strptime(start_at, "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(end_at, "%Y-%m-%d %H:%M:%S")
        elapsed_time = end_time - start_time
        return str(elapsed_time)


class GlobalTask(BaseTaskResult):
    """
    Global task result class.

    Attributes:
        task_type (str): The type of the task. e.g. "global".
    """

    task_type: Literal["global"] = "global"


class QubitTask(BaseTaskResult):
    """
    Qubit task result class.

    Attributes:
        task_type (str): The type of the task. e.g. "qubit".
        qid (str): The qubit id.
    """

    task_type: Literal["qubit"] = "qubit"
    qid: str


class CouplingTask(BaseTaskResult):
    """
    Coupling task result class.

    Attributes:
        task_type (str): The type of the task. e.g. "coupling".
        qid (str): The qubit id.
    """

    task_type: Literal["coupling"] = "coupling"
    qid: str


class TaskResult(BaseModel):
    """
    Task result class.

    Attributes:
        global_tasks (list[GlobalTask]): The global tasks.
        qubit_tasks (dict[str, list[QubitTask]]): The qubit tasks.
        coupling_tasks (dict[str, list[CouplingTask]]): The coupling tasks.
    """

    global_tasks: list[GlobalTask] = []
    qubit_tasks: dict[str, list[QubitTask]] = {}
    coupling_tasks: dict[str, list[CouplingTask]] = {}


class TaskManager(BaseModel):
    """
    Task manager class.

    Attributes:
        id (str): The unique identifier of the task manager.
        task_result (TaskResult): The task result.
        calib_data (CalibData): The calibration data.
        calib_dir (str): The calibration directory.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_result: TaskResult = TaskResult()  # デフォルト値を指定
    calib_data: CalibData = CalibData(qubit={}, coupling={})
    calib_dir: str = ""

    def __init__(self, qids: list[str] = [], calib_dir: str = ".", **data):
        super().__init__(**data)
        for qid in qids:
            self.task_result.qubit_tasks[qid] = []
            self.task_result.coupling_tasks[qid] = []
            self.calib_data.qubit[qid] = {}
            self.calib_dir = calib_dir

    def _get_task_container(
        self, task_name: str, task_type: str, qid: str = ""
    ) -> list[GlobalTask] | list[QubitTask] | list[CouplingTask]:
        container: list[GlobalTask] | list[QubitTask] | list[CouplingTask]
        if task_type == "global":
            return self.task_result.global_tasks
        elif task_type == "qubit":
            if qid is None:
                raise ValueError("For qubit tasks, a qid must be provided.")
            container = self.task_result.qubit_tasks[qid]
            if container is None:
                raise ValueError(f"No tasks found for qubit '{qid}'.")
            return container
        elif task_type == "coupling":
            if qid is None:
                raise ValueError("For coupling tasks, a qid must be provided.")
            container = self.task_result.coupling_tasks[qid]
            if container is None:
                raise ValueError(f"No tasks found for coupling with qid '{qid}'.")
            return container
        else:
            raise ValueError(f"Unknown task type: {task_type}")

    def _update_task_status_in_container(
        self, container: list, task_name: str, new_status: TaskStatus, message: str
    ) -> None:
        """
        Update the status of a task with the given name to the new status.
        """
        for t in container:
            if t.name == task_name:
                t.status = new_status
                t.message = message
                return
        raise ValueError(f"Task '{task_name}' not found in container.")

    def start_task(self, task_name: str, task_type: str = "global", qid: str = "") -> None:
        pass

    def start_all_qid_tasks(
        self, task_name: str, task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        for qid in qids:
            self.start_task(task_name, task_type, qid)

    def end_task(self, task_name: str, task_type: str = "global", qid: str = "") -> None:
        pass

    def end_all_qid_tasks(
        self, task_name: str, task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        for qid in qids:
            self.end_task(task_name, task_type, qid)

    def update_task_status(
        self,
        task_name: str,
        new_status: TaskStatus,
        message: str = "",
        task_type: str = "global",
        qid: str = "",
    ) -> None:
        """
        Update the status of a task with the given name to the new status.
        """
        container = self._get_task_container(task_name, task_type, qid)
        self._update_task_status_in_container(container, task_name, new_status, message)

    def update_task_status_to_running(
        self, task_name: str, task_type: str = "global", qid: str = ""
    ) -> None:
        self.update_task_status(task_name, TaskStatus.RUNNING, task_type=task_type, qid=qid)

    def update_all_qid_task_status_to_running(
        self, task_name: str, task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        for qid in qids:
            self.update_task_status_to_running(task_name, task_type, qid)

    def update_task_status_to_completed(
        self, task_name: str, message: str = "", task_type: str = "global", qid: str = ""
    ) -> None:
        self.update_task_status(task_name, TaskStatus.COMPLETED, message, task_type, qid)

    def update_all_qid_task_status_to_completed(
        self, task_name: str, message: str = "", task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        for qid in qids:
            self.update_task_status_to_completed(task_name, message, task_type, qid)

    def update_task_status_to_failed(
        self, task_name: str, message: str = "", task_type: str = "global", qid: str = ""
    ) -> None:
        self.update_task_status(task_name, TaskStatus.FAILED, message, task_type, qid)

    def update_all_qid_task_status_to_failed(
        self, task_name: str, message: str = "", task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        for qid in qids:
            self.update_task_status_to_failed(task_name, message, task_type, qid)

    def _find_task_in_container(
        self, container: list[GlobalTask] | list[QubitTask] | list[CouplingTask], task_name: str
    ) -> BaseTaskResult:
        for t in container:
            if t.name == task_name:
                return t
        raise ValueError(f"Task '{task_name}' not found in container.")

    def put_input_parameters(
        self, task_name: str, input_parameters: dict, task_type: str = "global", qid: str = ""
    ) -> None:
        container = self._get_task_container(task_name, task_type, qid)

        task = self._find_task_in_container(container, task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found.")
        task.put_input_parameter(input_parameters)
        task.system_info.update_time()

    def put_output_parameters(
        self, task_name: str, output_parameters: dict, task_type: str = "global", qid: str = ""
    ) -> None:
        container = self._get_task_container(task_name, task_type, qid)

        task = self._find_task_in_container(container, task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found.")
        task.put_output_parameter(output_parameters)
        task.system_info.update_time()

    def put_calib_data(
        self, qid: str, task_type: str, parameter_name: str, value: float | int
    ) -> None:
        if task_type == "qubit":
            self.calib_data.put_qubit_data(qid, parameter_name, value)
        elif task_type == "coupling":
            self.calib_data.put_coupling_data(qid, parameter_name, value)
        else:
            raise ValueError(f"Unknown task type: {task_type}")

    def put_note_to_task(
        self, task_name: str, note: str, task_type: str = "global", qid: str = ""
    ) -> None:
        container = self._get_task_container(task_name, task_type, qid)

        task = self._find_task_in_container(container, task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found.")
        task.note = note

    def save_figure(
        self,
        figure: go.Figure,
        task_name: str,
        task_type: str = "global",
        savedir: str = "",
        qid: str = "",
    ) -> None:
        container = self._get_task_container(task_name, task_type, qid)

        task = self._find_task_in_container(container, task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found.")
        if savedir == "":
            savedir = os.path.join(self.calib_dir, "fig")
        savepath = os.path.join(savedir, f"{qid}_{task_name}.png")
        task.figure_path.append(savepath)
        self._save_figure(savepath=savepath, fig=figure)

    def save(self, calib_dir: str = "") -> None:
        if calib_dir == "":
            calib_dir = f"{self.calib_dir}/task"
        with open(f"{calib_dir}/{self.id}.json", "w") as f:
            json.dump(self.model_dump(), f, indent=2)

    def diagnose(self):
        pass

    def _save_figure(
        self,
        fig: go.Figure,
        format: Literal["png", "svg", "jpeg", "webp"] = "png",
        width: int = 600,
        height: int = 300,
        scale: int = 3,
        name: str = "",
        savepath: str = "",
    ):
        """
        Save the figure.

        Args:
            savedir (str): The directory to save the figure.
            name (str): The name of the figure.
            fig (go.Figure): The figure to save.
            format (Literal["png", "svg", "jpeg", "webp"]): The format of the figure.
            width (int): The width of the figure.
            height (int): The height of the figure.
            scale (int): The scale of the figure.
        """
        if savepath == "":
            savepath = os.path.join(self.calib_dir, "fig", f"{name}.{format}")
        fig.write_image(
            savepath,
            format=format,
            width=width,
            height=height,
            scale=scale,
        )
