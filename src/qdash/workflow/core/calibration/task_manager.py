import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

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
    SystemTaskModel,
    TaskResultModel,
    TaskStatusModel,
)
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from qdash.workflow.core.calibration.execution_manager import ExecutionManager
    from qdash.workflow.core.session.base import BaseSession
    from qdash.workflow.tasks.base import BaseTask


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

    def __init__(self, username: str, execution_id: str, qids: list[str] = [], calib_dir: str = ".") -> None:
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
            if self._is_qubit_format(qid):
                self.calib_data.qubit[qid] = {}
            elif self._is_coupling_format(qid):
                self.calib_data.coupling[qid] = {}
            else:
                raise ValueError(f"Unknown qubit format: {qid}")
            self.calib_dir = calib_dir

    def _is_qubit_format(self, qid: str) -> bool:
        if "-" in qid:
            return False
        return qid in self.task_result.qubit_tasks

    def _is_coupling_format(self, qid: str) -> bool:
        return qid in self.task_result.coupling_tasks

    def _get_task_container(
        self, task_type: str, qid: str = ""
    ) -> list[GlobalTaskModel] | list[QubitTaskModel] | list[CouplingTaskModel] | list[SystemTaskModel]:
        container: list[GlobalTaskModel] | list[QubitTaskModel] | list[CouplingTaskModel] | list[SystemTaskModel]
        if task_type == "system":
            return self.task_result.system_tasks
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

    def get_task(self, task_name: str, task_type: str = "global", qid: str = "") -> BaseTaskResultModel:
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

    def _ensure_task_exists(self, task_name: str, task_type: str = "global", qid: str = "") -> None:
        """Ensure task exists in task_result, add if not present."""
        from qdash.datamodel.task import (
            CouplingTaskModel,
            GlobalTaskModel,
            QubitTaskModel,
            SystemTaskModel,
        )

        container = self._get_task_container(task_type, qid)
        # Check if task already exists
        for t in container:
            if t.name == task_name:
                return  # Task already exists

        # Get upstream task ID from Prefect context
        upstream_id = self._get_upstream_task_id()

        # Task doesn't exist, add it
        if task_type == "qubit":
            task = QubitTaskModel(name=task_name, upstream_id=upstream_id, qid=qid)
            self.task_result.qubit_tasks.setdefault(qid, []).append(task)
        elif task_type == "coupling":
            task = CouplingTaskModel(name=task_name, upstream_id=upstream_id, qid=qid)
            self.task_result.coupling_tasks.setdefault(qid, []).append(task)
        elif task_type == "global":
            task = GlobalTaskModel(name=task_name, upstream_id=upstream_id)
            self.task_result.global_tasks.append(task)
        elif task_type == "system":
            task = SystemTaskModel(name=task_name, upstream_id=upstream_id)
            self.task_result.system_tasks.append(task)

    def _get_upstream_task_id(self) -> str:
        """Get upstream task ID (QDash task_id, not Prefect ID)."""
        # Check if upstream_task_id was explicitly set
        if hasattr(self, "_upstream_task_id"):
            return self._upstream_task_id
        return ""

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

    def start_all_qid_tasks(self, task_name: str, task_type: str = "qubit", qids: list[str] = []) -> None:
        for qid in qids:
            self.start_task(task_name, task_type, qid)

    def end_task(self, task_name: str, task_type: str = "global", qid: str = "") -> None:
        container = self._get_task_container(task_type, qid)
        for t in container:
            if t.name == task_name:
                # t.status = TaskStatusModel.COMPLETED
                t.end_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
                t.elapsed_time = t.calculate_elapsed_time(t.start_at, t.end_at)
                t.system_info.update_time()
                return
        raise ValueError(f"Task '{task_name}' not found in container.")

    def end_all_qid_tasks(self, task_name: str, task_type: str = "qubit", qids: list[str] = []) -> None:
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

    def update_task_status_to_skipped(
        self, task_name: str, message: str = "", task_type: str = "global", qid: str = ""
    ) -> None:
        self.update_task_status(
            task_name=task_name,
            new_status=TaskStatusModel.SKIPPED,
            message=message,
            task_type=task_type,
            qid=qid,
        )

    def update_all_qid_task_status_to_running(
        self, task_name: str, message: str = "", task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        for qid in qids:
            self.update_task_status_to_running(task_name=task_name, message=message, task_type=task_type, qid=qid)

    def update_all_qid_task_status_to_completed(
        self, task_name: str, message: str = "", task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        for qid in qids:
            self.update_task_status_to_completed(task_name=task_name, message=message, task_type=task_type, qid=qid)

    def update_all_qid_task_status_to_failed(
        self, task_name: str, message: str = "", task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        for qid in qids:
            self.update_task_status_to_failed(task_name=task_name, message=message, task_type=task_type, qid=qid)

    def update_not_executed_tasks_to_skipped(self, task_type: str = "global", qid: str = "") -> None:
        container = self._get_task_container(task_type, qid)
        for t in container:
            if t.status not in {TaskStatusModel.COMPLETED, TaskStatusModel.FAILED}:
                t.status = TaskStatusModel.SKIPPED
                t.message = f"{t.name} is skipped."
                t.system_info.update_time()

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

    def put_note_to_task(self, task_name: str, note: dict, task_type: str = "global", qid: str = "") -> None:
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

        # Ensure both fields exist
        if not hasattr(task, "figure_path"):
            task.figure_path = []
        if not hasattr(task, "figure_json_path"):
            task.json_figure_path = []

        for i, fig in enumerate(figures):
            base_name = f"{qid}_{task_name}_{i}"
            base_path = savedir_path / base_name

            # Determine dimensions
            width, height = (1200, 1500) if task_name == "CheckSkew" else (600, 300)

            # JSON path
            json_path = base_path.with_suffix(".json")
            json_path = self._resolve_conflict(json_path)
            task.json_figure_path.append(str(json_path))
            self._write_figure_json(fig, savepath=json_path, width=1000, height=500)

            # PNG path
            png_path = base_path.with_suffix(".png")
            png_path = self._resolve_conflict(png_path)
            task.figure_path.append(str(png_path))
            self._write_figure_image(fig, savepath=png_path, width=width, height=height)

    def _write_figure_json(
        self,
        fig: go.Figure,
        savepath: Path,
        width: int = 1000,
        height: int = 500,
    ) -> None:
        fig.update_layout(width=width, height=height)
        fig.write_json(str(savepath), pretty=True)

    def _write_figure_image(
        self,
        fig: go.Figure,
        savepath: Path,
        width: int = 600,
        height: int = 300,
        scale: int = 3,
        file_format: Literal["png", "svg", "jpeg", "webp"] = "png",
    ) -> None:
        fig.write_image(
            str(savepath),
            format=file_format,
            width=width,
            height=height,
            scale=scale,
        )

    def _resolve_conflict(self, path: Path) -> Path:
        """Ensure unique path by appending index if needed."""
        counter = 1
        new_path = path
        while new_path.exists():
            new_path = path.with_name(f"{path.stem}_{counter}{path.suffix}")
            counter += 1
        return new_path

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

    def save_raw_data(self, raw_data: list[ndarray], task_name: str, task_type: str = "global", qid: str = "") -> None:
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
        fig.update_layout(width=width, height=height)
        fig.write_json(
            savepath,
            pretty=True,
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

    def this_task_is_completed(self, task_name: str, task_type: str = "global", qid: str = "") -> bool:
        """Check if the task is completed."""
        container = self._get_task_container(task_type, qid)
        task = self._find_task_in_container(container, task_name)
        return bool(task.status == TaskStatusModel.COMPLETED)

    def _is_global_task(self, task_name: str) -> bool:
        return any(task.name == task_name for task in self.task_result.global_tasks)

    def _is_qubit_task(self, task_name: str) -> bool:
        return any(task_name in [task.name for task in tasks] for tasks in self.task_result.qubit_tasks.values())

    def _is_coupling_task(self, task_name: str) -> bool:
        return any(task_name in [task.name for task in tasks] for tasks in self.task_result.coupling_tasks.values())

    def _is_system_task(self, task_name: str) -> bool:
        return any(task.name == task_name for task in self.task_result.system_tasks)

    def has_only_qubit_or_global_tasks(self, task_names: list[str]) -> bool:
        return all(self._is_qubit_task(task_name) or self._is_global_task(task_name) for task_name in task_names)

    def has_only_coupling_or_global_tasks(self, task_names: list[str]) -> bool:
        return all(self._is_coupling_task(task_name) or self._is_global_task(task_name) for task_name in task_names)

    def has_only_system_tasks(self, task_names: list[str]) -> bool:
        return all(self._is_system_task(task_name) for task_name in task_names)

    def execute_task(
        self,
        task_instance: "BaseTask",
        session: "BaseSession",
        execution_manager: "ExecutionManager",
        qid: str,
    ) -> tuple["ExecutionManager", "TaskManager"]:
        """Execute task with integrated save processing.

        Args:
        ----
            task_instance: Task instance
            session: Session object
            execution_manager: Execution manager
            qid: Qubit ID

        Returns:
        -------
            tuple[ExecutionManager, TaskManager]: Updated execution manager and task manager

        """
        task_name = task_instance.get_name()
        task_type = task_instance.get_task_type()

        try:
            # 0. Ensure task exists in task_result before execution
            self._ensure_task_exists(task_name, task_type, qid)

            # 1. Start task
            self.start_task(task_name, task_type, qid)

            # Save task execution state
            executed_task = self.get_task(task_name=task_name, task_type=task_type, qid=qid)
            TaskResultHistoryDocument.upsert_document(
                task=executed_task, execution_model=execution_manager.to_datamodel()
            )

            # Update execution manager
            execution_manager = execution_manager.update_with_task_manager(self)

            # 2. Preprocess (using existing BaseTask.preprocess)
            preprocess_result = task_instance.preprocess(session, qid)
            if preprocess_result is not None:
                self.put_input_parameters(task_name, preprocess_result.input_parameters, task_type=task_type, qid=qid)
                self.save()
                execution_manager = execution_manager.update_with_task_manager(self)

            # 3. Run (using existing BaseTask.run)
            run_result = task_instance.run(session, qid)

            if run_result is not None:
                # 4. Postprocess (using existing BaseTask.postprocess)
                postprocess_result = task_instance.postprocess(session, execution_manager.execution_id, run_result, qid)

                if postprocess_result is not None:
                    # 5. Integrated save processing (TaskManager is responsible)
                    self._save_all_results(
                        task_instance, execution_manager, postprocess_result, qid, run_result, session
                    )

            # 6. Complete task
            self.update_task_status_to_completed(
                task_name, message=f"{task_name} is completed", task_type=task_type, qid=qid
            )
            self.save()

            # Save completed state to database
            executed_task = self.get_task(task_name=task_name, task_type=task_type, qid=qid)
            TaskResultHistoryDocument.upsert_document(
                task=executed_task, execution_model=execution_manager.to_datamodel()
            )
            execution_manager = execution_manager.update_with_task_manager(self)

        except Exception as e:
            # Error handling
            self._handle_task_error(task_instance, execution_manager, qid, str(e))
            raise

        finally:
            # Finalization
            self.end_task(task_name, task_type, qid)
            self.save()
            execution_manager = execution_manager.update_with_task_manager(self)

            # Save final state
            executed_task = self.get_task(task_name=task_name, task_type=task_type, qid=qid)
            TaskResultHistoryDocument.upsert_document(
                task=executed_task, execution_model=execution_manager.to_datamodel()
            )

            # Create chip history
            from qdash.dbmodel.chip import ChipDocument
            from qdash.dbmodel.chip_history import ChipHistoryDocument

            chip_doc = ChipDocument.get_current_chip(username=self.username)
            ChipHistoryDocument.create_history(chip_doc)

        return execution_manager, self

    def _save_all_results(
        self,
        task_instance: "BaseTask",
        execution_manager: "ExecutionManager",
        postprocess_result: Any,
        qid: str,
        run_result: Any,
        session: "BaseSession",
    ) -> None:
        """Integrated save processing (TaskManager is responsible).

        Args:
        ----
            task_instance: Task instance
            execution_manager: Execution manager
            postprocess_result: Postprocess result
            qid: Qubit ID
            run_result: Run result
            session: Session object

        """
        task_name = task_instance.get_name()
        task_type = task_instance.get_task_type()

        # 1. Save output parameters
        if postprocess_result.output_parameters:
            self.put_output_parameters(task_name, postprocess_result.output_parameters, task_type=task_type, qid=qid)

        # 2. Save figures (using existing method)
        if postprocess_result.figures:
            self.save_figures(postprocess_result.figures, task_name, task_type=task_type, qid=qid)

        # 3. Save raw data (using existing method)
        if postprocess_result.raw_data:
            self.save_raw_data(postprocess_result.raw_data, task_name, task_type=task_type, qid=qid)

        # 4. Save task manager state
        self.save()

        # 5. R2 check
        if run_result.has_r2() and run_result.r2[qid] < task_instance.r2_threshold:
            raise ValueError(f"{task_instance.name} R² value too low: {run_result.r2[qid]:.4f}")

        # 6. Backend-specific save processing
        self._save_backend_specific(task_instance, execution_manager, qid, session)

    def _save_backend_specific(
        self, task_instance: "BaseTask", execution_manager: "ExecutionManager", qid: str, session: "BaseSession"
    ) -> None:
        """Backend-specific save processing.

        Args:
        ----
            task_instance: Task instance
            execution_manager: Execution manager
            qid: Qubit ID
            session: Session object

        """
        if task_instance.backend == "qubex":
            self._save_qubex_specific(task_instance, execution_manager, qid, session)
        elif task_instance.backend == "fake":
            self._save_fake_specific(task_instance, execution_manager, qid, session)

    def _save_qubex_specific(
        self,
        task_instance: "BaseTask",
        execution_manager: "ExecutionManager",
        qid: str,
        session: "BaseSession",
    ) -> None:
        """Qubex-specific save processing.

        Args:
        ----
            task_instance: Task instance
            execution_manager: Execution manager
            qid: Qubit ID
            session: Session object

        """
        from qdash.dbmodel.coupling import CouplingDocument
        from qdash.dbmodel.qubit import QubitDocument

        task_name = task_instance.get_name()
        task_type = task_instance.get_task_type()

        # 1. Save calibration note
        if session.name == "qubex":
            session.update_note(
                username=self.username,
                chip_id=execution_manager.chip_id,
                calib_dir=self.calib_dir,
                execution_id=execution_manager.execution_id,
                task_manager_id=self.id,
            )

        # 2. Update parameters
        output_parameters = self.get_output_parameter_by_task_name(task_name, task_type=task_type, qid=qid)

        if output_parameters:
            if task_instance.is_qubit_task():
                QubitDocument.update_calib_data(
                    username=self.username,
                    qid=qid,
                    chip_id=execution_manager.chip_id,
                    output_parameters=output_parameters,
                )
            elif task_instance.is_coupling_task():
                CouplingDocument.update_calib_data(
                    username=self.username,
                    qid=qid,
                    chip_id=execution_manager.chip_id,
                    output_parameters=output_parameters,
                )

    def _save_fake_specific(
        self,
        task_instance: "BaseTask",
        execution_manager: "ExecutionManager",
        qid: str,
        session: "BaseSession",
    ) -> None:
        """Fake-specific save processing.

        Args:
        ----
            task_instance: Task instance
            execution_manager: Execution manager
            qid: Qubit ID
            session: Session object

        """
        # Simulation metadata save, etc. (implement as needed)
        pass

    def _handle_task_error(
        self, task_instance: "BaseTask", execution_manager: "ExecutionManager", qid: str, error_msg: str
    ) -> None:
        """Error handling.

        Args:
        ----
            task_instance: Task instance
            execution_manager: Execution manager
            qid: Qubit ID
            error_msg: Error message

        """
        task_name = task_instance.get_name()
        task_type = task_instance.get_task_type()

        self.update_task_status_to_failed(task_name, message=error_msg, task_type=task_type, qid=qid)

        # Save error state to database
        task_result = self.get_task(task_name, task_type=task_type, qid=qid)
        TaskResultHistoryDocument.upsert_document(task_result, execution_manager.to_datamodel())
