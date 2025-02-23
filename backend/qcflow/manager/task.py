import json
import uuid
from copy import deepcopy
from enum import Enum
from pathlib import Path
from typing import Literal

import numpy as np
import pendulum
import plotly.graph_objs as go
from pydantic import BaseModel, Field
from qcflow.manager.constant import COMPLETED, FAILED, PENDING, RUNNING, SCHDULED
from qcflow.manager.system_info import SystemInfo


class TaskStatus(str, Enum):
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


class Data(BaseModel):
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


class CalibData(BaseModel):
    """Calibration data model.

    Attributes
    ----------
        qubit (dict[str, dict[str, Data]]): The calibration data for qubits.
        coupling (dict[str, dict[str, Data]]): The calibration data for couplings.

    """

    qubit: dict[str, dict[str, Data]] = Field(default_factory=dict)
    coupling: dict[str, dict[str, Data]] = Field(default_factory=dict)

    def put_qubit_data(self, qid: str, parameter_name: str, data: Data) -> None:
        self.qubit[qid][parameter_name] = data

    def put_coupling_data(self, qid: str, parameter_name: str, data: Data) -> None:
        self.coupling[qid][parameter_name] = data

    def __getitem__(self, key: str) -> dict:
        """Get the item by key."""
        if key in ("qubit", "coupling"):
            return getattr(self, key)  # type: ignore #noqa: PGH003
        raise KeyError(f"Invalid key: {key}")


class BaseTaskResult(BaseModel):
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
    status: TaskStatus = TaskStatus.SCHEDULED
    message: str = ""
    input_parameters: dict = {}
    output_parameters: dict = {}
    output_parameter_names: list[str] = []
    note: dict = {}
    figure_path: list[str] = []
    start_at: str = ""
    end_at: str = ""
    elapsed_time: str = ""
    task_type: str = "global"
    system_info: SystemInfo = SystemInfo()

    def diagnose(self) -> None:
        """Diagnose the task result and raise an error if the task failed."""
        if self.status == TaskStatus.FAILED:
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


class GlobalTask(BaseTaskResult):
    """Global task result class.

    Attributes
    ----------
        task_type (str): The type of the task. e.g. "global".

    """

    task_type: Literal["global"] = "global"


class QubitTask(BaseTaskResult):
    """Qubit task result class.

    Attributes
    ----------
        task_type (str): The type of the task. e.g. "qubit".
        qid (str): The qubit id.

    """

    task_type: Literal["qubit"] = "qubit"
    qid: str


class CouplingTask(BaseTaskResult):
    """Coupling task result class.

    Attributes
    ----------
        task_type (str): The type of the task. e.g. "coupling".
        qid (str): The qubit id.

    """

    task_type: Literal["coupling"] = "coupling"
    qid: str


class TaskResult(BaseModel):
    """Task result class.

    Attributes
    ----------
        global_tasks (list[GlobalTask]): The global tasks.
        qubit_tasks (dict[str, list[QubitTask]]): The qubit tasks.
        coupling_tasks (dict[str, list[CouplingTask]]): The coupling tasks.

    """

    global_tasks: list[GlobalTask] = []
    qubit_tasks: dict[str, list[QubitTask]] = {}
    coupling_tasks: dict[str, list[CouplingTask]] = {}


class TaskManager(BaseModel):
    """Task manager class.

    Attributes
    ----------
        id (str): The unique identifier of the task manager.
        task_result (TaskResult): The task result.
        calib_data (CalibData): The calibration data.
        calib_dir (str): The calibration directory.

    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    execution_id: str
    task_result: TaskResult = TaskResult()  # デフォルト値を指定
    calib_data: CalibData = CalibData(qubit={}, coupling={})
    calib_dir: str = ""
    controller_info: dict[str, dict] = {}

    def __init__(self, execution_id: str, qids: list[str] = [], calib_dir: str = ".") -> None:
        super().__init__(
            execution_id=execution_id,
            task_result=TaskResult(),
            calib_data=CalibData(qubit={}, coupling={}),
            calib_dir=calib_dir,
            controller_info={},
        )
        for qid in qids:
            self.task_result.qubit_tasks[qid] = []
            self.task_result.coupling_tasks[qid] = []
            self.calib_data.qubit[qid] = {}
            self.calib_dir = calib_dir

    def _get_task_container(
        self, task_type: str, qid: str = ""
    ) -> list[GlobalTask] | list[QubitTask] | list[CouplingTask]:
        container: list[GlobalTask] | list[QubitTask] | list[CouplingTask]
        if task_type == "global":
            return self.task_result.global_tasks
        if task_type == "qubit":
            if qid is None:
                error_message = "For qubit tasks, a qid must be provided."
                raise ValueError(error_message)
            container = self.task_result.qubit_tasks[qid]
            if container is None:
                error_message = f"No tasks found for qubit '{qid}'."
                raise ValueError(error_message)
            return container
        if task_type == "coupling":
            if qid is None:
                error_message = "For coupling tasks, a qid must be provided."
                raise ValueError(error_message)
            container = self.task_result.coupling_tasks[qid]
            if container is None:
                error_message = f"No tasks found for coupling with qid '{qid}'."
                raise ValueError(error_message)
            return container
        error_message = f"Unknown task type: {task_type}"
        raise ValueError(error_message)

    def get_task(self, task_name: str, task_type: str = "global", qid: str = "") -> BaseTaskResult:
        container = self._get_task_container(task_type, qid)
        return self._find_task_in_container(container, task_name)

    def _update_task_status_in_container(
        self, container: list, task_name: str, new_status: TaskStatus, message: str
    ) -> None:
        """Update the status of a task with the given name to the new status."""
        for t in container:
            if t.name == task_name:
                t.status = new_status
                t.message = message
                t.system_info.update_time()
                return
        raise ValueError(f"Task '{task_name}' not found in container.")

    def start_task(self, task_name: str, task_type: str = "global", qid: str = "") -> None:
        container = self._get_task_container(task_type, qid)
        for t in container:
            if t.name == task_name:
                t.status = TaskStatus.RUNNING
                t.start_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
                t.system_info.update_time()
                return
        raise ValueError(f"Task '{task_name}' not found in container.")

    def start_all_qid_tasks(
        self, task_name: str, task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        for qid in qids:
            self.start_task(task_name, task_type, qid)

    def end_task(self, task_name: str, task_type: str = "global", qid: str = "") -> None:
        container = self._get_task_container(task_type, qid)
        for t in container:
            if t.name == task_name:
                t.status = TaskStatus.COMPLETED
                t.end_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
                t.elapsed_time = t.calculate_elapsed_time(t.start_at, t.end_at)
                t.system_info.update_time()
                return
        raise ValueError(f"Task '{task_name}' not found in container.")

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
        """Update the status of a task with the given name to the new status."""
        container = self._get_task_container(task_type, qid)
        self._update_task_status_in_container(container, task_name, new_status, message)

    def update_task_status_to_running(
        self, task_name: str, message: str = "", task_type: str = "global", qid: str = ""
    ) -> None:
        self.update_task_status(
            task_name=task_name,
            new_status=TaskStatus.RUNNING,
            message=message,
            task_type=task_type,
            qid=qid,
        )

    def update_task_status_to_completed(
        self, task_name: str, message: str = "", task_type: str = "global", qid: str = ""
    ) -> None:
        self.update_task_status(
            task_name=task_name,
            new_status=TaskStatus.COMPLETED,
            message=message,
            task_type=task_type,
            qid=qid,
        )

    def update_task_status_to_failed(
        self, task_name: str, message: str = "", task_type: str = "global", qid: str = ""
    ) -> None:
        self.update_task_status(
            task_name=task_name,
            new_status=TaskStatus.FAILED,
            message=message,
            task_type=task_type,
            qid=qid,
        )

    def update_all_qid_task_status_to_running(
        self, task_name: str, message: str = "", task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        for qid in qids:
            self.update_task_status_to_running(
                task_name=task_name, message=message, task_type=task_type, qid=qid
            )

    def update_all_qid_task_status_to_completed(
        self, task_name: str, message: str = "", task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        for qid in qids:
            self.update_task_status_to_completed(
                task_name=task_name, message=message, task_type=task_type, qid=qid
            )

    def update_all_qid_task_status_to_failed(
        self, task_name: str, message: str = "", task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        for qid in qids:
            self.update_task_status_to_failed(
                task_name=task_name, message=message, task_type=task_type, qid=qid
            )

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
        container = self._get_task_container(task_type, qid)

        task = self._find_task_in_container(container, task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found.")
        task.put_input_parameter(input_parameters)
        task.system_info.update_time()

    def put_output_parameters(
        self, task_name: str, output_parameters: dict, task_type: str = "global", qid: str = ""
    ) -> None:
        container = self._get_task_container(task_type, qid)
        task = self._find_task_in_container(container, task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found.")
        task.put_output_parameter(output_parameters)
        task.system_info.update_time()
        self._put_calib_data(qid, task_type, output_parameters)

    def _put_calib_data(self, qid: str, task_type: str, output_parameters: dict) -> None:
        for key, value in output_parameters.items():
            if task_type == "qubit":
                self.calib_data.put_qubit_data(qid, key, value)
            elif task_type == "coupling":
                self.calib_data.put_coupling_data(qid, key, value)
            else:
                raise ValueError(f"Unknown task type: {task_type}")

    def put_note_to_task(
        self, task_name: str, note: dict, task_type: str = "global", qid: str = ""
    ) -> None:
        container = self._get_task_container(task_type, qid)

        task = self._find_task_in_container(container, task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found.")
        task.note = note

    def save_figures(
        self,
        figures: list[go.Figure],
        task_name: str,
        task_type: str = "global",
        savedir: str = "",
        qid: str = "",
    ) -> None:
        container = self._get_task_container(task_type, qid)

        task = self._find_task_in_container(container, task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found.")
        savedir_path = Path(self.calib_dir) / "fig" if savedir == "" else Path(savedir)
        savedir_path.mkdir(parents=True, exist_ok=True)

        for i, fig in enumerate(figures):
            base_savepath = savedir_path / f"{qid}_{task_name}_{i}"
            savepath = base_savepath.with_suffix(".png")
            counter = 1
            while savepath.exists():
                savepath = base_savepath.with_name(f"{base_savepath.stem}_{counter}.png")
                counter += 1
            task.figure_path.append(str(savepath))
            self._write_figure(savepath=str(savepath), fig=fig)

    def save_figure(
        self,
        figure: go.Figure,
        task_name: str,
        task_type: str = "global",
        savedir: str = "",
        qid: str = "",
    ) -> None:
        container = self._get_task_container(task_type, qid)

        task = self._find_task_in_container(container, task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found.")
        savedir_path = Path(self.calib_dir) / "fig" if savedir == "" else Path(savedir)
        savedir_path.mkdir(parents=True, exist_ok=True)

        base_savepath = savedir_path / f"{qid}_{task_name}"
        savepath = base_savepath.with_suffix(".png")
        counter = 1
        while savepath.exists():
            savepath = base_savepath.with_name(f"{base_savepath.stem}_{counter}.png")
            counter += 1

        task.figure_path.append(str(savepath))
        self._write_figure(savepath=str(savepath), fig=figure)

    def save(self, calib_dir: str = "") -> None:
        if calib_dir == "":
            calib_dir = f"{self.calib_dir}/task"

        with Path(f"{calib_dir}/{self.id}.json").open("w") as f:
            json.dump(self.model_dump(), f, indent=2)

    def diagnose(self) -> None:
        """Diagnose the task manager and raise an error if the task failed."""

    def _write_figure(
        self,
        fig: go.Figure,
        file_format: Literal["png", "svg", "jpeg", "webp"] = "png",
        width: int = 600,
        height: int = 300,
        scale: int = 3,
        name: str = "",
        savepath: str = "",
    ) -> None:
        """Save the figure.

        Args:
        ----
            savepath (str): The path to save the figure.
            fig (go.Figure): The figure to save.
            file_format (str, optional): The format of the file. Defaults to "png".
            width (int, optional): The width of the figure. Defaults to 600.
            height (int, optional): The height of the figure. Defaults to 300.
            scale (int, optional): The scale of the figure. Defaults to 3.
            name (str, optional): The name of the figure. Defaults to "".

        """
        if savepath == "":
            savepath = str(Path(self.calib_dir) / "fig" / f"{name}.{file_format}")
        fig.write_image(
            savepath,
            format=file_format,
            width=width,
            height=height,
            scale=scale,
        )

    def put_controller_info(self, box_info: dict) -> None:
        self.controller_info = box_info

    def get_qubit_calib_data(self, qid: str) -> dict:
        return self.calib_data.qubit[qid]

    def get_coupling_calib_data(self, qid: str) -> dict:
        return self.calib_data.coupling[qid]

    def get_output_parameter_by_task_name(
        self, task_name: str, task_type: str = "global", qid: str = ""
    ) -> dict:
        container = self._get_task_container(task_type, qid)
        task = self._find_task_in_container(container, task_name)
        return task.output_parameters

    def this_task_is_completed(
        self, task_name: str, task_type: str = "global", qid: str = ""
    ) -> bool:
        """Check if the task is completed."""
        container = self._get_task_container(task_type, qid)
        task = self._find_task_in_container(container, task_name)
        return task.status == TaskStatus.COMPLETED
