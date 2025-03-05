import json
import uuid
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pendulum
import plotly.graph_objs as go
from numpy import ndarray
from pydantic import BaseModel, Field
from qdash.datamodel.task import (
    BaseTaskResultModel,
    CalibDataModel,
    CouplingTaskModel,
    GlobalTaskModel,
    QubitTaskModel,
    TaskResultModel,
    TaskStatusModel,
)


class TaskManager(BaseModel):
    """Task manager class.

    Attributes
    ----------
        id (str): The unique identifier of the task manager.
        task_result (TaskResult): The task result.
        calib_data (CalibData): The calibration data.
        calib_dir (str): The calibration directory.

    """

    username: str = "admin"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    execution_id: str
    task_result: TaskResultModel = TaskResultModel()  # デフォルト値を指定
    calib_data: CalibDataModel = CalibDataModel(qubit={}, coupling={})
    calib_dir: str = ""
    controller_info: dict[str, dict] = {}

    def __init__(
        self, username: str, execution_id: str, qids: list[str] = [], calib_dir: str = "."
    ) -> None:
        super().__init__(
            username=username,
            execution_id=execution_id,
            task_result=TaskResultModel(),
            calib_data=CalibDataModel(qubit={}, coupling={}),
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
    ) -> list[GlobalTaskModel] | list[QubitTaskModel] | list[CouplingTaskModel]:
        container: list[GlobalTaskModel] | list[QubitTaskModel] | list[CouplingTaskModel]
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

    def get_task(
        self, task_name: str, task_type: str = "global", qid: str = ""
    ) -> BaseTaskResultModel:
        container = self._get_task_container(task_type, qid)
        return self._find_task_in_container(container, task_name)

    def _update_task_status_in_container(
        self, container: list, task_name: str, new_status: TaskStatusModel, message: str
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
                t.status = TaskStatusModel.RUNNING
                t.message = f"{task_name} is running."
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
                t.status = TaskStatusModel.COMPLETED
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
        new_status: TaskStatusModel,
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
            new_status=TaskStatusModel.RUNNING,
            message=message,
            task_type=task_type,
            qid=qid,
        )

    def update_task_status_to_completed(
        self, task_name: str, message: str = "", task_type: str = "global", qid: str = ""
    ) -> None:
        self.update_task_status(
            task_name=task_name,
            new_status=TaskStatusModel.COMPLETED,
            message=message,
            task_type=task_type,
            qid=qid,
        )

    def update_task_status_to_failed(
        self, task_name: str, message: str = "", task_type: str = "global", qid: str = ""
    ) -> None:
        self.update_task_status(
            task_name=task_name,
            new_status=TaskStatusModel.FAILED,
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
        self,
        container: list[GlobalTaskModel] | list[QubitTaskModel] | list[CouplingTaskModel],
        task_name: str,
    ) -> BaseTaskResultModel:
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

    def save_raw_data(
        self, raw_data: list[ndarray], task_name: str, task_type: str = "global", qid: str = ""
    ) -> None:
        container = self._get_task_container(task_type, qid)

        task = self._find_task_in_container(container, task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found.")
        savedir_path = Path(self.calib_dir) / "raw_data"
        savedir_path.mkdir(parents=True, exist_ok=True)

        for i, raw in enumerate(raw_data):
            base_savepath = savedir_path / f"{qid}_{task_name}_{i}"
            savepath = base_savepath.with_suffix(".csv")
            counter = 1
            while savepath.exists():
                savepath = base_savepath.with_name(f"{base_savepath.stem}_{counter}.csv")
                counter += 1
            task.raw_data_path.append(str(savepath))
            data = np.column_stack((raw.real, raw.imag))
            np.savetxt(savepath, data, delimiter=",", header="real,imag")

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
        return dict(self.calib_data.qubit[qid])

    def get_coupling_calib_data(self, qid: str) -> dict:
        return dict(self.calib_data.coupling[qid])

    def get_output_parameter_by_task_name(
        self, task_name: str, task_type: str = "global", qid: str = ""
    ) -> dict[str, Any]:
        container = self._get_task_container(task_type, qid)
        task = self._find_task_in_container(container, task_name)
        return dict(task.output_parameters)

    def this_task_is_completed(
        self, task_name: str, task_type: str = "global", qid: str = ""
    ) -> bool:
        """Check if the task is completed."""
        container = self._get_task_container(task_type, qid)
        task = self._find_task_in_container(container, task_name)
        return bool(task.status == TaskStatusModel.COMPLETED)
