"""TaskManager Facade - maintains backward compatibility while delegating to extracted components.

This facade provides the same public interface as the original TaskManager,
keeping task_result, calib_data, and controller_info as regular Pydantic fields
that can be assigned directly, while delegating complex logic to TaskExecutor.

The TaskManager now acts as a thin wrapper that:
1. Maintains state via TaskStateManager
2. Delegates task execution to TaskExecutor
3. Records history via TaskHistoryRecorder
4. Saves data via FilesystemCalibDataSaver
"""

import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field
from qdash.datamodel.task import (
    CalibDataModel,
    TaskResultModel,
    TaskStatusModel,
)
from qdash.workflow.engine.calibration.repository import FilesystemCalibDataSaver
from qdash.workflow.engine.calibration.task.executor import TaskExecutor
from qdash.workflow.engine.calibration.task.history_recorder import TaskHistoryRecorder
from qdash.workflow.engine.calibration.task.result_processor import TaskResultProcessor
from qdash.workflow.engine.calibration.task.state_manager import TaskStateManager

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from qdash.workflow.caltasks.base import BaseTask
    from qdash.workflow.engine.backend.base import BaseBackend
    from qdash.workflow.engine.calibration.execution.manager import ExecutionManager


class TaskManager(BaseModel):
    """Task manager facade with backward-compatible interface.

    This class acts as a thin facade, delegating to internal components:
    - TaskStateManager: state management (task_result, calib_data, status)
    - TaskExecutor: task execution lifecycle
    - TaskResultProcessor: R² and fidelity validation
    - TaskHistoryRecorder: history recording to MongoDB
    - FilesystemCalibDataSaver: figure and raw data saving

    Attributes
    ----------
        username (str): The username.
        id (str): The unique identifier of the task manager.
        execution_id (str): The execution ID.
        task_result (TaskResultModel): The task result container.
        calib_data (CalibDataModel): The calibration data container.
        calib_dir (str): The calibration directory.
        controller_info (dict): Controller information.

    """

    username: str = "admin"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    execution_id: str
    task_result: TaskResultModel = Field(default_factory=TaskResultModel)
    calib_data: CalibDataModel = Field(
        default_factory=lambda: CalibDataModel(qubit={}, coupling={})
    )
    calib_dir: str = ""
    controller_info: dict[str, dict] = Field(default_factory=dict)

    # Upstream task ID for dependency tracking (set by session.py)
    _upstream_task_id: str = ""

    # Internal components
    _state_manager: TaskStateManager | None = None
    _executor: TaskExecutor | None = None
    _result_processor: TaskResultProcessor | None = None
    _history_recorder: TaskHistoryRecorder | None = None
    _data_saver: FilesystemCalibDataSaver | None = None

    model_config = {"arbitrary_types_allowed": True}

    def __init__(
        self, username: str, execution_id: str, qids: list[str] = [], calib_dir: str = "."
    ) -> None:
        """Initialize TaskManager.

        Parameters
        ----------
        username : str
            The username.
        execution_id : str
            The execution ID.
        qids : list[str]
            List of qubit IDs.
        calib_dir : str
            The calibration directory.

        """
        super().__init__(
            username=username,
            execution_id=execution_id,
            task_result=TaskResultModel(),
            calib_data=CalibDataModel(qubit={}, coupling={}),
            calib_dir=calib_dir,
            controller_info={},
        )

        # Initialize state manager
        self._state_manager = TaskStateManager(qids=qids)

        # Initialize other components
        self._result_processor = TaskResultProcessor()
        self._history_recorder = TaskHistoryRecorder()
        self._data_saver = FilesystemCalibDataSaver(calib_dir)

        # Initialize executor (needs state manager)
        self._executor = TaskExecutor(
            state_manager=self._state_manager,
            calib_dir=calib_dir,
            execution_id=execution_id,
            task_manager_id=self.id,
            username=username,
            result_processor=self._result_processor,
            history_recorder=self._history_recorder,
            data_saver=self._data_saver,
        )

        # Initialize containers for each qid
        for qid in qids:
            self.task_result.qubit_tasks[qid] = []
            self.task_result.coupling_tasks[qid] = []
            if self._is_qubit_format(qid):
                self.calib_data.qubit[qid] = {}
            elif self._is_coupling_format(qid):
                self.calib_data.coupling[qid] = {}
            else:
                raise ValueError(f"Unknown qubit format: {qid}")

        # Sync with state manager
        self._sync_to_state_manager()

    def __setattr__(self, name, value) -> None:  # type: ignore[override]
        """Intercept attribute assignments to keep internal components in sync."""
        super().__setattr__(name, value)

        if name == "id":
            executor = self.__dict__.get("_executor")
            if executor is not None:
                executor.task_manager_id = value
        elif name == "controller_info":
            executor = self.__dict__.get("_executor")
            if executor is not None:
                executor.set_controller_info(value)
        elif name == "_upstream_task_id":
            state_manager = self.__dict__.get("_state_manager")
            if state_manager is not None:
                state_manager.set_upstream_task_id(value)

    # ========== State Synchronization ==========

    def _sync_from_state_manager(self) -> None:
        """Sync public fields from internal state manager."""
        if self._state_manager:
            self.task_result = self._state_manager.task_result
            self.calib_data = self._state_manager.calib_data

    def _sync_to_state_manager(self) -> None:
        """Sync public fields to internal state manager."""
        if self._state_manager:
            self._state_manager.task_result = self.task_result
            self._state_manager.calib_data = self.calib_data
            # Sync upstream_task_id for dependency tracking
            self._state_manager.set_upstream_task_id(self._upstream_task_id)

    # ========== Format Checking ==========

    def _is_qubit_format(self, qid: str) -> bool:
        """Check if qid is in qubit format."""
        if "-" in qid:
            return False
        return qid in self.task_result.qubit_tasks

    def _is_coupling_format(self, qid: str) -> bool:
        """Check if qid is in coupling format."""
        return qid in self.task_result.coupling_tasks

    # ========== Internal Methods (delegated to state manager) ==========

    def _ensure_task_exists(self, task_name: str, task_type: str, qid: str) -> Any:
        """Ensure a task exists in the appropriate container.

        Parameters
        ----------
        task_name : str
            Name of the task
        task_type : str
            Type of task (qubit, coupling, global, system)
        qid : str
            Qubit ID (empty for global/system tasks)

        Returns
        -------
        BaseTaskResultModel
            The existing or newly created task

        """
        self._sync_to_state_manager()
        result = self._state_manager._ensure_task_exists(task_name, task_type, qid)
        self._sync_from_state_manager()
        return result

    def _resolve_conflict(self, filepath: Path) -> Path:
        """Resolve filename conflicts by incrementing suffix.

        Parameters
        ----------
        filepath : Path
            Original file path

        Returns
        -------
        Path
            Resolved path with incremented suffix if needed

        """
        if self._data_saver:
            return self._data_saver._resolve_conflict(filepath)
        # Fallback implementation if data saver not available
        if not filepath.exists():
            return filepath
        stem = filepath.stem
        suffix = filepath.suffix
        parent = filepath.parent
        counter = 1
        while True:
            new_path = parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return new_path
            counter += 1

    # ========== Task State Methods (delegated to state manager) ==========

    def get_task(self, task_name: str, task_type: str = "global", qid: str = "") -> Any:
        """Get a task by name and type."""
        self._sync_to_state_manager()
        return self._state_manager.get_task(task_name, task_type, qid)

    def start_task(self, task_name: str, task_type: str = "global", qid: str = "") -> None:
        """Start a task."""
        self._sync_to_state_manager()
        self._state_manager.start_task(task_name, task_type, qid)
        self._sync_from_state_manager()

    def start_all_qid_tasks(
        self, task_name: str, task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        """Start a task for all given qubit IDs."""
        for qid in qids:
            self.start_task(task_name, task_type, qid)

    def end_task(self, task_name: str, task_type: str = "global", qid: str = "") -> None:
        """End a task."""
        self._sync_to_state_manager()
        self._state_manager.end_task(task_name, task_type, qid)
        self._sync_from_state_manager()

    def end_all_qid_tasks(
        self, task_name: str, task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        """End a task for all given qubit IDs."""
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
        """Update task status."""
        self._sync_to_state_manager()
        self._state_manager.update_task_status(task_name, new_status, message, task_type, qid)
        self._sync_from_state_manager()

    def update_task_status_to_running(
        self, task_name: str, message: str = "", task_type: str = "global", qid: str = ""
    ) -> None:
        """Update task status to RUNNING."""
        self.update_task_status(task_name, TaskStatusModel.RUNNING, message, task_type, qid)

    def update_task_status_to_completed(
        self, task_name: str, message: str = "", task_type: str = "global", qid: str = ""
    ) -> None:
        """Update task status to COMPLETED."""
        self.update_task_status(task_name, TaskStatusModel.COMPLETED, message, task_type, qid)

    def update_task_status_to_failed(
        self, task_name: str, message: str = "", task_type: str = "global", qid: str = ""
    ) -> None:
        """Update task status to FAILED."""
        self.update_task_status(task_name, TaskStatusModel.FAILED, message, task_type, qid)

    def update_task_status_to_skipped(
        self, task_name: str, message: str = "", task_type: str = "global", qid: str = ""
    ) -> None:
        """Update task status to SKIPPED."""
        self.update_task_status(task_name, TaskStatusModel.SKIPPED, message, task_type, qid)

    def update_all_qid_task_status_to_running(
        self, task_name: str, message: str = "", task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        """Update task status to RUNNING for all qids."""
        for qid in qids:
            self.update_task_status_to_running(task_name, message, task_type, qid)

    def update_all_qid_task_status_to_completed(
        self, task_name: str, message: str = "", task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        """Update task status to COMPLETED for all qids."""
        for qid in qids:
            self.update_task_status_to_completed(task_name, message, task_type, qid)

    def update_all_qid_task_status_to_failed(
        self, task_name: str, message: str = "", task_type: str = "qubit", qids: list[str] = []
    ) -> None:
        """Update task status to FAILED for all qids."""
        for qid in qids:
            self.update_task_status_to_failed(task_name, message, task_type, qid)

    def update_not_executed_tasks_to_skipped(
        self, task_type: str = "global", qid: str = ""
    ) -> None:
        """Mark unexecuted tasks as skipped."""
        self._sync_to_state_manager()
        self._state_manager.update_not_executed_tasks_to_skipped(task_type, qid)
        self._sync_from_state_manager()

    # ========== Parameter Methods (delegated to state manager) ==========

    def put_input_parameters(
        self, task_name: str, input_parameters: dict, task_type: str = "global", qid: str = ""
    ) -> None:
        """Store input parameters."""
        self._sync_to_state_manager()
        self._state_manager.put_input_parameters(task_name, input_parameters, task_type, qid)
        self._sync_from_state_manager()

    def put_output_parameters(
        self, task_name: str, output_parameters: dict, task_type: str = "global", qid: str = ""
    ) -> None:
        """Store output parameters."""
        self._sync_to_state_manager()
        self._state_manager.put_output_parameters(task_name, output_parameters, task_type, qid)
        self._sync_from_state_manager()

    def put_note_to_task(
        self, task_name: str, note: dict, task_type: str = "global", qid: str = ""
    ) -> None:
        """Add a note to a task."""
        self._sync_to_state_manager()
        self._state_manager.put_note_to_task(task_name, note, task_type, qid)
        self._sync_from_state_manager()

    def get_qubit_calib_data(self, qid: str) -> dict:
        """Get calibration data for a qubit."""
        self._sync_to_state_manager()
        return self._state_manager.get_qubit_calib_data(qid)

    def get_coupling_calib_data(self, qid: str) -> dict:
        """Get calibration data for a coupling."""
        self._sync_to_state_manager()
        return self._state_manager.get_coupling_calib_data(qid)

    def _clear_qubit_calib_data(self, qid: str, keys: list[str]) -> None:
        """Clear specific keys from qubit calibration data.

        Parameters
        ----------
        qid : str
            Qubit ID
        keys : list[str]
            Keys to clear from calibration data

        """
        self._sync_to_state_manager()
        self._state_manager._clear_qubit_calib_data(qid, keys)
        self._sync_from_state_manager()

    def _clear_coupling_calib_data(self, qid: str, keys: list[str]) -> None:
        """Clear specific keys from coupling calibration data.

        Parameters
        ----------
        qid : str
            Qubit ID
        keys : list[str]
            Keys to clear from calibration data

        """
        self._sync_to_state_manager()
        self._state_manager._clear_coupling_calib_data(qid, keys)
        self._sync_from_state_manager()

    def get_output_parameter_by_task_name(
        self, task_name: str, task_type: str = "global", qid: str = ""
    ) -> dict[str, Any]:
        """Get output parameters for a task."""
        self._sync_to_state_manager()
        task = self._state_manager.get_task(task_name, task_type, qid)
        return dict(task.output_parameters)

    def this_task_is_completed(
        self, task_name: str, task_type: str = "global", qid: str = ""
    ) -> bool:
        """Check if a task is completed."""
        self._sync_to_state_manager()
        task = self._state_manager.get_task(task_name, task_type, qid)
        return task.status == TaskStatusModel.COMPLETED

    # ========== Figure/Data Saving (delegated to data saver) ==========

    def save_figures(
        self,
        figures: list,
        task_name: str,
        task_type: str = "global",
        savedir: str = "",
        qid: str = "",
    ) -> None:
        """Save figures."""
        if self._data_saver:
            override_dir = savedir or None
            png_paths, json_paths = self._data_saver.save_figures(
                figures,
                task_name,
                task_type,
                qid,
                output_dir=override_dir,
            )
            self._sync_to_state_manager()
            self._state_manager.set_figure_paths(task_name, task_type, qid, png_paths, json_paths)
            self._sync_from_state_manager()

    def save_figure(
        self,
        figure: Any,
        task_name: str,
        task_type: str = "global",
        savedir: str = "",
        qid: str = "",
    ) -> None:
        """Save a single figure."""
        self.save_figures([figure], task_name, task_type, savedir, qid)

    def save_raw_data(
        self, raw_data: list, task_name: str, task_type: str = "global", qid: str = ""
    ) -> None:
        """Save raw data."""
        if self._data_saver:
            paths = self._data_saver.save_raw_data(
                raw_data,
                task_name,
                task_type,
                qid,
                output_dir=None,
            )
            self._sync_to_state_manager()
            self._state_manager.set_raw_data_paths(task_name, task_type, qid, paths)
            self._sync_from_state_manager()

    # ========== Persistence ==========

    def save(self, calib_dir: str = "") -> None:
        """Save task manager state to JSON file."""
        if calib_dir == "":
            calib_dir = f"{self.calib_dir}/task"

        Path(calib_dir).mkdir(parents=True, exist_ok=True)
        with Path(f"{calib_dir}/{self.id}.json").open("w") as f:
            json.dump(self.model_dump(), f, indent=2)

    def diagnose(self) -> None:
        """Diagnose the task manager."""
        pass

    def put_controller_info(self, box_info: dict) -> None:
        """Store controller information."""
        self.controller_info = box_info
        # Also update executor's controller_info for ExecutionManager updates
        if self._executor:
            self._executor.set_controller_info(box_info)

    # ========== Task Type Checking ==========

    def _is_global_task(self, task_name: str) -> bool:
        """Check if task is a global task."""
        return any(task.name == task_name for task in self.task_result.global_tasks)

    def _is_qubit_task(self, task_name: str) -> bool:
        """Check if task is a qubit task."""
        return any(
            task_name in [task.name for task in tasks]
            for tasks in self.task_result.qubit_tasks.values()
        )

    def _is_coupling_task(self, task_name: str) -> bool:
        """Check if task is a coupling task."""
        return any(
            task_name in [task.name for task in tasks]
            for tasks in self.task_result.coupling_tasks.values()
        )

    def _is_system_task(self, task_name: str) -> bool:
        """Check if task is a system task."""
        return any(task.name == task_name for task in self.task_result.system_tasks)

    def has_only_qubit_or_global_tasks(self, task_names: list[str]) -> bool:
        """Check if all tasks are qubit or global types."""
        return all(self._is_qubit_task(n) or self._is_global_task(n) for n in task_names)

    def has_only_coupling_or_global_tasks(self, task_names: list[str]) -> bool:
        """Check if all tasks are coupling or global types."""
        return all(self._is_coupling_task(n) or self._is_global_task(n) for n in task_names)

    def has_only_system_tasks(self, task_names: list[str]) -> bool:
        """Check if all tasks are system types."""
        return all(self._is_system_task(n) for n in task_names)

    # ========== Task Execution (delegated to TaskExecutor) ==========

    def execute_task(
        self,
        task_instance: "BaseTask",
        backend: "BaseBackend",
        execution_manager: "ExecutionManager",
        qid: str,
    ) -> tuple["ExecutionManager", "TaskManager"]:
        """Execute task with integrated save processing.

        This method delegates to TaskExecutor for the actual execution
        while maintaining backward compatibility with the original interface.

        Parameters
        ----------
        task_instance : BaseTask
            Task instance to execute
        backend : BaseBackend
            Backend object for device communication
        execution_manager : ExecutionManager
            Execution manager
        qid : str
            Qubit ID

        Returns
        -------
        tuple[ExecutionManager, TaskManager]
            Updated execution manager and this task manager

        """
        # Sync state before execution
        self._sync_to_state_manager()

        # Delegate to TaskExecutor
        execution_manager, result = self._executor.execute(
            task=task_instance,
            backend=backend,
            execution_manager=execution_manager,
            qid=qid,
        )

        # Sync state after execution
        self._sync_from_state_manager()

        # Save task manager state
        self.save()

        return execution_manager, self
