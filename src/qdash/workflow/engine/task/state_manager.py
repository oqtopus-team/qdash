"""TaskStateManager for managing task state and lifecycle.

This module provides the TaskStateManager class that handles task state
management, including task creation, status updates, and parameter handling.
"""

from collections.abc import Iterator
from typing import Any, cast

from pydantic import BaseModel
from qdash.common.datetime_utils import now
from qdash.datamodel.task import (
    BaseTaskResultModel,
    CalibDataModel,
    CouplingTaskModel,
    GlobalTaskModel,
    ParameterModel,
    QubitTaskModel,
    SystemTaskModel,
    TaskResultModel,
    TaskStatusModel,
    TaskTypes,
)


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

    def _find_task(self, task_name: str, task_type: str, qid: str) -> BaseTaskResultModel | None:
        """Find a task by name in the appropriate container.

        Parameters
        ----------
        task_name : str
            Name of the task to find
        task_type : TaskType
            Type of task (qubit, coupling, global, system)
        qid : str
            Qubit ID (empty for global/system tasks)

        Returns
        -------
        BaseTaskResultModel | None
            The found task, or None if not found

        """
        for task in self._iter_tasks(task_type, qid):
            if task.name == task_name:
                return task
        return None

    def _add_task(self, task: BaseTaskResultModel, task_type: str, qid: str) -> None:
        """Add a task to the appropriate container.

        Parameters
        ----------
        task : BaseTaskResultModel
            The task to add
        task_type : TaskType
            Type of task (qubit, coupling, global, system)
        qid : str
            Qubit ID (empty for global/system tasks)

        """
        if task_type == TaskTypes.QUBIT:
            # Initialize list if qid doesn't exist (for MUX distribution)
            if qid not in self.task_result.qubit_tasks:
                self.task_result.qubit_tasks[qid] = []
            self.task_result.qubit_tasks[qid].append(cast(QubitTaskModel, task))
        elif task_type == TaskTypes.COUPLING:
            # Initialize list if qid doesn't exist
            if qid not in self.task_result.coupling_tasks:
                self.task_result.coupling_tasks[qid] = []
            self.task_result.coupling_tasks[qid].append(cast(CouplingTaskModel, task))
        elif task_type == TaskTypes.GLOBAL:
            self.task_result.global_tasks.append(cast(GlobalTaskModel, task))
        elif task_type == TaskTypes.SYSTEM:
            self.task_result.system_tasks.append(cast(SystemTaskModel, task))

    def _iter_tasks(self, task_type: str, qid: str) -> Iterator[BaseTaskResultModel]:
        """Iterate over tasks in the appropriate container (read-only).

        Parameters
        ----------
        task_type : TaskType
            Type of task (qubit, coupling, global, system)
        qid : str
            Qubit ID (empty for global/system tasks)

        Yields
        ------
        BaseTaskResultModel
            Tasks in the container

        """
        if task_type == TaskTypes.QUBIT:
            # Return empty iterator if qid doesn't exist
            yield from self.task_result.qubit_tasks.get(qid, [])
        elif task_type == TaskTypes.COUPLING:
            # Return empty iterator if qid doesn't exist
            yield from self.task_result.coupling_tasks.get(qid, [])
        elif task_type == TaskTypes.GLOBAL:
            yield from self.task_result.global_tasks
        elif task_type == TaskTypes.SYSTEM:
            yield from self.task_result.system_tasks

    def _ensure_task_exists(self, task_name: str, task_type: str, qid: str) -> BaseTaskResultModel:
        """Ensure a task exists in the appropriate container.

        Parameters
        ----------
        task_name : str
            Name of the task
        task_type : TaskType
            Type of task (qubit, coupling, global, system)
        qid : str
            Qubit ID (empty for global/system tasks)

        Returns
        -------
        BaseTaskResultModel
            The existing or newly created task

        """
        existing = self._find_task(task_name, task_type, qid)
        if existing:
            return existing

        task = self._create_task(task_name, task_type, qid)
        self._add_task(task, task_type, qid)
        return task

    def _create_task(self, task_name: str, task_type: str, qid: str) -> BaseTaskResultModel:
        """Create a new task of the appropriate type.

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
            The new task instance

        """
        upstream_id = self._get_upstream_task_id()

        if task_type == TaskTypes.QUBIT:
            return QubitTaskModel(name=task_name, qid=qid, upstream_id=upstream_id)
        elif task_type == TaskTypes.COUPLING:
            return CouplingTaskModel(name=task_name, qid=qid, upstream_id=upstream_id)
        elif task_type == TaskTypes.GLOBAL:
            return GlobalTaskModel(name=task_name, upstream_id=upstream_id)
        elif task_type == TaskTypes.SYSTEM:
            return SystemTaskModel(name=task_name, upstream_id=upstream_id)
        else:
            raise ValueError(f"Unknown task type: {task_type}")

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
        task = self._find_task(task_name, task_type, qid)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found for {task_type}/{qid}")
        return task

    def start_task(self, task_name: str, task_type: str, qid: str) -> None:
        """Start a task (set status to RUNNING and record start time).

        Parameters
        ----------
        task_name : str
            Name of the task
        task_type : str
            Type of task
        qid : str
            Qubit ID

        """
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.status = TaskStatusModel.RUNNING
        task.start_at = now()

    def end_task(self, task_name: str, task_type: str, qid: str) -> None:
        """End a task (record end time and calculate elapsed time).

        Parameters
        ----------
        task_name : str
            Name of the task
        task_type : str
            Type of task
        qid : str
            Qubit ID

        """
        task = self.get_task(task_name, task_type, qid)
        end_time = now()
        task.end_at = end_time
        if task.start_at is not None:
            task.elapsed_time = task.calculate_elapsed_time(task.start_at, end_time)

    def update_task_status_to_completed(
        self, task_name: str, message: str, task_type: str, qid: str
    ) -> None:
        """Update task status to COMPLETED.

        Parameters
        ----------
        task_name : str
            Name of the task
        message : str
            Completion message
        task_type : str
            Type of task
        qid : str
            Qubit ID

        """
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.status = TaskStatusModel.COMPLETED
        task.message = message

    def update_task_status_to_failed(
        self, task_name: str, message: str, task_type: str, qid: str
    ) -> None:
        """Update task status to FAILED.

        Parameters
        ----------
        task_name : str
            Name of the task
        message : str
            Failure message
        task_type : str
            Type of task
        qid : str
            Qubit ID

        """
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.status = TaskStatusModel.FAILED
        task.message = message

    def update_task_status_to_skipped(
        self, task_name: str, message: str, task_type: str, qid: str
    ) -> None:
        """Update task status to SKIPPED.

        Parameters
        ----------
        task_name : str
            Name of the task
        message : str
            Skip message
        task_type : str
            Type of task
        qid : str
            Qubit ID

        """
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.status = TaskStatusModel.SKIPPED
        task.message = message

    def update_task_status(
        self,
        task_name: str,
        new_status: TaskStatusModel,
        message: str,
        task_type: str,
        qid: str,
    ) -> None:
        """Update task status.

        Parameters
        ----------
        task_name : str
            Name of the task
        new_status : TaskStatusModel
            The new status
        message : str
            Status message
        task_type : str
            Type of task
        qid : str
            Qubit ID

        """
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.status = new_status
        task.message = message

    def put_input_parameters(
        self, task_name: str, input_parameters: dict[str, Any], task_type: str, qid: str
    ) -> None:
        """Store input parameters for a task.

        Parameters
        ----------
        task_name : str
            Name of the task
        input_parameters : dict
            The input parameters
        task_type : str
            Type of task
        qid : str
            Qubit ID

        """
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.put_input_parameter(input_parameters)

    def put_output_parameters(
        self,
        task_name: str,
        output_parameters: dict[str, ParameterModel],
        task_type: str,
        qid: str,
    ) -> None:
        """Store output parameters for a task and update calibration data.

        Parameters
        ----------
        task_name : str
            Name of the task
        output_parameters : dict[str, ParameterModel]
            The output parameters
        task_type : str
            Type of task
        qid : str
            Qubit ID

        """
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
        """Clear output parameters for a task and rollback calib_data.

        This method clears both the task's output_parameters and removes
        the corresponding entries from calib_data to ensure data consistency
        when R² validation fails.

        Parameters
        ----------
        task_name : str
            Name of the task
        task_type : str
            Type of task
        qid : str
            Qubit ID

        """
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
        """Get output parameters for a specific task.

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
        dict
            The output parameters

        """
        task = self.get_task(task_name, task_type, qid)
        return dict(task.output_parameters)

    def start_all_qid_tasks(self, task_name: str, task_type: str, qids: list[str]) -> None:
        """Start a task for all given qubit IDs.

        Parameters
        ----------
        task_name : str
            Name of the task
        task_type : str
            Type of task
        qids : list[str]
            List of qubit IDs

        """
        for qid in qids:
            self.start_task(task_name, task_type, qid)

    def update_not_executed_tasks_to_skipped(
        self, task_type: str, qid: str, message: str = "Not executed"
    ) -> None:
        """Mark all scheduled tasks as skipped.

        Parameters
        ----------
        task_type : str
            Type of task
        qid : str
            Qubit ID
        message : str
            Skip message

        """
        for task in self._iter_tasks(task_type, qid):
            if task.status == TaskStatusModel.SCHEDULED:
                task.status = TaskStatusModel.SKIPPED
                task.message = message

    def this_task_is_completed(self, task_name: str, task_type: str, qid: str) -> bool:
        """Check if a task is completed.

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
        bool
            True if task is completed

        """
        try:
            task = self.get_task(task_name, task_type, qid)
            return bool(task.status == TaskStatusModel.COMPLETED)
        except ValueError:
            return False

    def _clear_qubit_calib_data(self, qid: str, parameter_names: list[str]) -> None:
        """Clear specific parameters from qubit calibration data.

        Parameters
        ----------
        qid : str
            Qubit ID
        parameter_names : list[str]
            Names of parameters to clear

        """
        if qid in self.calib_data.qubit:
            for name in parameter_names:
                self.calib_data.qubit[qid].pop(name, None)

    def _clear_coupling_calib_data(self, qid: str, parameter_names: list[str]) -> None:
        """Clear specific parameters from coupling calibration data.

        Parameters
        ----------
        qid : str
            Qubit ID (coupling ID like "0-1")
        parameter_names : list[str]
            Names of parameters to clear

        """
        if qid in self.calib_data.coupling:
            for name in parameter_names:
                self.calib_data.coupling[qid].pop(name, None)

    def get_qubit_calib_data(self, qid: str) -> dict[Any, Any]:
        """Get calibration data for a qubit.

        Parameters
        ----------
        qid : str
            Qubit ID

        Returns
        -------
        dict
            The qubit calibration data

        """
        return dict(self.calib_data.qubit.get(qid, {}))

    def get_coupling_calib_data(self, qid: str) -> dict[Any, Any]:
        """Get calibration data for a coupling.

        Parameters
        ----------
        qid : str
            Coupling ID

        Returns
        -------
        dict
            The coupling calibration data

        """
        return dict(self.calib_data.coupling.get(qid, {}))

    def set_figure_paths(
        self,
        task_name: str,
        task_type: str,
        qid: str,
        png_paths: list[str],
        json_paths: list[str],
    ) -> None:
        """Set figure paths for a task.

        Parameters
        ----------
        task_name : str
            Name of the task
        task_type : str
            Type of task
        qid : str
            Qubit ID
        png_paths : list[str]
            Paths to PNG files
        json_paths : list[str]
            Paths to JSON files

        """
        task = self.get_task(task_name, task_type, qid)
        task.figure_path = png_paths
        task.json_figure_path = json_paths

    def set_raw_data_paths(
        self, task_name: str, task_type: str, qid: str, paths: list[str]
    ) -> None:
        """Set raw data paths for a task.

        Parameters
        ----------
        task_name : str
            Name of the task
        task_type : str
            Type of task
        qid : str
            Qubit ID
        paths : list[str]
            Paths to raw data files

        """
        task = self.get_task(task_name, task_type, qid)
        task.raw_data_path = paths

    def has_only_qubit_or_global_tasks(self, task_names: list[str]) -> bool:
        """Check if all tasks are qubit or global types only.

        Parameters
        ----------
        task_names : list[str]
            Names of tasks to check

        Returns
        -------
        bool
            True if all tasks are qubit or global types

        """
        for name in task_names:
            # Check in global tasks
            if any(t.name == name for t in self.task_result.global_tasks):
                continue
            # Check in any qubit tasks
            found = False
            for qubit_tasks in self.task_result.qubit_tasks.values():
                if any(t.name == name for t in qubit_tasks):
                    found = True
                    break
            if not found:
                # Check if it's a coupling task
                for coupling_tasks in self.task_result.coupling_tasks.values():
                    if any(t.name == name for t in coupling_tasks):
                        return False
        return True

    def has_only_coupling_or_global_tasks(self, task_names: list[str]) -> bool:
        """Check if all tasks are coupling or global types only.

        Parameters
        ----------
        task_names : list[str]
            Names of tasks to check

        Returns
        -------
        bool
            True if all tasks are coupling or global types

        """
        for name in task_names:
            # Check in global tasks
            if any(t.name == name for t in self.task_result.global_tasks):
                continue
            # Check in any coupling tasks
            found = False
            for coupling_tasks in self.task_result.coupling_tasks.values():
                if any(t.name == name for t in coupling_tasks):
                    found = True
                    break
            if not found:
                # Check if it's a qubit task
                for qubit_tasks in self.task_result.qubit_tasks.values():
                    if any(t.name == name for t in qubit_tasks):
                        return False
        return True

    def has_only_system_tasks(self, task_names: list[str]) -> bool:
        """Check if all tasks are system types only.

        Parameters
        ----------
        task_names : list[str]
            Names of tasks to check

        Returns
        -------
        bool
            True if all tasks are system types

        """
        for name in task_names:
            if not any(t.name == name for t in self.task_result.system_tasks):
                return False
        return True

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

    def clear_qubit_calib_data(self, qid: str, parameter_names: list[str]) -> None:
        """Public method to clear qubit calibration data.

        Parameters
        ----------
        qid : str
            Qubit ID
        parameter_names : list[str]
            Names of parameters to clear

        """
        self._clear_qubit_calib_data(qid, parameter_names)

    def update_task_status_to_running(
        self, task_name: str, message: str, task_type: str, qid: str
    ) -> None:
        """Update task status to RUNNING.

        Parameters
        ----------
        task_name : str
            Name of the task
        message : str
            Running message
        task_type : str
            Type of task
        qid : str
            Qubit ID

        """
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.status = TaskStatusModel.RUNNING
        task.message = message
