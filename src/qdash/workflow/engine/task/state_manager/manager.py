"""TaskStateManager class for managing task state and lifecycle."""

from typing import Any

from pydantic import BaseModel
from qdash.common.datetime_utils import now
from qdash.datamodel.task import (
    BaseTaskResultModel,
    CalibDataModel,
    ParameterModel,
    TaskResultModel,
    TaskStatusModel,
    TaskTypes,
)
from qdash.workflow.engine.task.state_manager import data as data_ops
from qdash.workflow.engine.task.state_manager import lookup


class TaskStateManager(BaseModel):
    """Manager for task state and lifecycle.

    This class handles:
    - Task creation and lookup
    - Task status transitions (start, end, complete, fail, skip)
    - Input/output parameter management
    - Calibration data management

    Attributes
    ----------
    task_result : TaskResultModel
        Container for all task results
    calib_data : CalibDataModel
        Container for calibration data
    _upstream_task_id : str
        Upstream task ID for dependency tracking

    """

    task_result: TaskResultModel = TaskResultModel()
    calib_data: CalibDataModel = CalibDataModel(qubit={}, coupling={})
    _upstream_task_id: str = ""

    def __init__(self, qids: list[str] | None = None, **data: Any) -> None:
        """Initialize TaskStateManager.

        Parameters
        ----------
        qids : list[str] | None
            List of qubit IDs to initialize containers for

        """
        super().__init__(**data)
        if qids:
            for qid in qids:
                self.task_result.qubit_tasks[qid] = []
                self.task_result.coupling_tasks[qid] = []
                self.calib_data.qubit[qid] = {}

    # ------------------------------------------------------------------ #
    # Upstream task ID
    # ------------------------------------------------------------------ #

    def set_upstream_task_id(self, task_id: str) -> None:
        """Set upstream task ID for dependency tracking.

        Parameters
        ----------
        task_id : str
            The upstream task ID

        """
        self._upstream_task_id = task_id

    def _get_upstream_task_id(self) -> str:
        """Get upstream task ID (QDash task_id, not Prefect ID).

        Returns
        -------
        str
            The upstream task ID or empty string if not set

        """
        return self._upstream_task_id

    # ------------------------------------------------------------------ #
    # Lookup delegation
    # ------------------------------------------------------------------ #

    def _find_task(self, task_name: str, task_type: str, qid: str) -> BaseTaskResultModel | None:
        """Find a task by name in the appropriate container."""
        return lookup.find_task(self.task_result, task_name, task_type, qid)

    def _add_task(self, task: BaseTaskResultModel, task_type: str, qid: str) -> None:
        """Add a task to the appropriate container."""
        lookup.add_task(self.task_result, task, task_type, qid)

    def _iter_tasks(self, task_type: str, qid: str):
        """Iterate over tasks in the appropriate container (read-only)."""
        return lookup.iter_tasks(self.task_result, task_type, qid)

    def _create_task(self, task_name: str, task_type: str, qid: str) -> BaseTaskResultModel:
        """Create a new task of the appropriate type."""
        return lookup.create_task(task_name, task_type, qid, self._upstream_task_id)

    def _ensure_task_exists(self, task_name: str, task_type: str, qid: str) -> BaseTaskResultModel:
        """Ensure a task exists in the appropriate container."""
        return lookup.ensure_task_exists(
            self.task_result, task_name, task_type, qid, self._upstream_task_id
        )

    def get_task(self, task_name: str, task_type: str, qid: str) -> BaseTaskResultModel:
        """Get an existing task.

        Parameters
        ----------
        task_name : str
            Name of the task
        task_type : str
            Type of task
        qid : str
            Qubit ID

        Returns
        -------
        BaseTaskResultModel
            The task

        Raises
        ------
        ValueError
            If task not found

        """
        return lookup.get_task(self.task_result, task_name, task_type, qid)

    def ensure_task_exists(self, task_name: str, task_type: str, qid: str) -> BaseTaskResultModel:
        """Public method to ensure a task exists in the appropriate container.

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
        return self._ensure_task_exists(task_name, task_type, qid)

    # ------------------------------------------------------------------ #
    # Status transitions
    # ------------------------------------------------------------------ #

    def start_task(self, task_name: str, task_type: str, qid: str) -> None:
        """Start a task (set status to RUNNING and record start time)."""
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.status = TaskStatusModel.RUNNING
        task.start_at = now()

    def end_task(self, task_name: str, task_type: str, qid: str) -> None:
        """End a task (record end time and calculate elapsed time)."""
        task = self.get_task(task_name, task_type, qid)
        end_time = now()
        task.end_at = end_time
        if task.start_at is not None:
            task.elapsed_time = task.calculate_elapsed_time(task.start_at, end_time)

    def update_task_status_to_completed(
        self, task_name: str, message: str, task_type: str, qid: str
    ) -> None:
        """Update task status to COMPLETED."""
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.status = TaskStatusModel.COMPLETED
        task.message = message

    def update_task_status_to_failed(
        self, task_name: str, message: str, task_type: str, qid: str
    ) -> None:
        """Update task status to FAILED."""
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.status = TaskStatusModel.FAILED
        task.message = message

    def update_task_status_to_skipped(
        self, task_name: str, message: str, task_type: str, qid: str
    ) -> None:
        """Update task status to SKIPPED."""
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.status = TaskStatusModel.SKIPPED
        task.message = message

    def update_task_status_to_running(
        self, task_name: str, message: str, task_type: str, qid: str
    ) -> None:
        """Update task status to RUNNING."""
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.status = TaskStatusModel.RUNNING
        task.message = message

    def update_task_status(
        self,
        task_name: str,
        new_status: TaskStatusModel,
        message: str,
        task_type: str,
        qid: str,
    ) -> None:
        """Update task status."""
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.status = new_status
        task.message = message

    def start_all_qid_tasks(self, task_name: str, task_type: str, qids: list[str]) -> None:
        """Start a task for all given qubit IDs."""
        for qid in qids:
            self.start_task(task_name, task_type, qid)

    def update_not_executed_tasks_to_skipped(
        self, task_type: str, qid: str, message: str = "Not executed"
    ) -> None:
        """Mark all scheduled tasks as skipped."""
        for task in self._iter_tasks(task_type, qid):
            if task.status == TaskStatusModel.SCHEDULED:
                task.status = TaskStatusModel.SKIPPED
                task.message = message

    # ------------------------------------------------------------------ #
    # Parameter management
    # ------------------------------------------------------------------ #

    def put_input_parameters(
        self, task_name: str, input_parameters: dict[str, Any], task_type: str, qid: str
    ) -> None:
        """Store input parameters for a task."""
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.put_input_parameter(input_parameters)

    def put_run_parameters(
        self, task_name: str, run_parameters: dict[str, Any], task_type: str, qid: str
    ) -> None:
        """Store run parameters for a task."""
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.put_run_parameter(run_parameters)

    def put_output_parameters(
        self,
        task_name: str,
        output_parameters: dict[str, ParameterModel],
        task_type: str,
        qid: str,
    ) -> None:
        """Store output parameters for a task and update calibration data."""
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.put_output_parameter(output_parameters)

        # Update calibration data
        if task_type == TaskTypes.QUBIT:
            for key, value in output_parameters.items():
                self.calib_data.put_qubit_data(qid, key, value)
        elif task_type == TaskTypes.COUPLING:
            for key, value in output_parameters.items():
                self.calib_data.put_coupling_data(qid, key, value)

    def clear_output_parameters(self, task_name: str, task_type: str, qid: str) -> None:
        """Clear output parameters for a task and rollback calib_data."""
        task = self._ensure_task_exists(task_name, task_type, qid)

        # Get parameter names before clearing
        parameter_names = list(task.output_parameters.keys())

        # Clear task output parameters
        task.output_parameters = {}

        # Rollback calib_data by removing the parameters
        if parameter_names:
            if task_type == TaskTypes.QUBIT:
                self._clear_qubit_calib_data(qid, parameter_names)
            elif task_type == TaskTypes.COUPLING:
                self._clear_coupling_calib_data(qid, parameter_names)

    def get_output_parameter_by_task_name(
        self, task_name: str, task_type: str, qid: str
    ) -> dict[Any, Any]:
        """Get output parameters for a specific task."""
        task = self.get_task(task_name, task_type, qid)
        return dict(task.output_parameters)

    # ------------------------------------------------------------------ #
    # Calibration data delegation
    # ------------------------------------------------------------------ #

    def _clear_qubit_calib_data(self, qid: str, parameter_names: list[str]) -> None:
        """Clear specific parameters from qubit calibration data."""
        data_ops.clear_qubit_calib_data(self.calib_data, qid, parameter_names)

    def _clear_coupling_calib_data(self, qid: str, parameter_names: list[str]) -> None:
        """Clear specific parameters from coupling calibration data."""
        data_ops.clear_coupling_calib_data(self.calib_data, qid, parameter_names)

    def clear_qubit_calib_data(self, qid: str, parameter_names: list[str]) -> None:
        """Public method to clear qubit calibration data."""
        self._clear_qubit_calib_data(qid, parameter_names)

    def get_qubit_calib_data(self, qid: str) -> dict[Any, Any]:
        """Get calibration data for a qubit."""
        return data_ops.get_qubit_calib_data(self.calib_data, qid)

    def get_coupling_calib_data(self, qid: str) -> dict[Any, Any]:
        """Get calibration data for a coupling."""
        return data_ops.get_coupling_calib_data(self.calib_data, qid)

    def has_only_qubit_or_global_tasks(self, task_names: list[str]) -> bool:
        """Check if all tasks are qubit or global types only."""
        return data_ops.has_only_qubit_or_global_tasks(self.task_result, task_names)

    def has_only_coupling_or_global_tasks(self, task_names: list[str]) -> bool:
        """Check if all tasks are coupling or global types only."""
        return data_ops.has_only_coupling_or_global_tasks(self.task_result, task_names)

    def has_only_system_tasks(self, task_names: list[str]) -> bool:
        """Check if all tasks are system types only."""
        return data_ops.has_only_system_tasks(self.task_result, task_names)

    # ------------------------------------------------------------------ #
    # Artifacts
    # ------------------------------------------------------------------ #

    def set_figure_paths(
        self,
        task_name: str,
        task_type: str,
        qid: str,
        png_paths: list[str],
        json_paths: list[str],
    ) -> None:
        """Set figure paths for a task."""
        task = self.get_task(task_name, task_type, qid)
        task.figure_path = png_paths
        task.json_figure_path = json_paths

    def set_raw_data_paths(
        self, task_name: str, task_type: str, qid: str, paths: list[str]
    ) -> None:
        """Set raw data paths for a task."""
        task = self.get_task(task_name, task_type, qid)
        task.raw_data_path = paths

    def this_task_is_completed(self, task_name: str, task_type: str, qid: str) -> bool:
        """Check if a task is completed."""
        try:
            task = self.get_task(task_name, task_type, qid)
            return bool(task.status == TaskStatusModel.COMPLETED)
        except ValueError:
            return False
