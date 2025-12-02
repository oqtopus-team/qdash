"""TaskStateManager for managing task state and lifecycle.

This module provides the TaskStateManager class that handles task state
management, including task creation, status updates, and parameter handling.
"""

import pendulum
from pydantic import BaseModel

from qdash.datamodel.task import (
    BaseTaskResultModel,
    CalibDataModel,
    CouplingTaskModel,
    GlobalTaskModel,
    OutputParameterModel,
    QubitTaskModel,
    SystemTaskModel,
    TaskResultModel,
    TaskStatusModel,
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

    """

    task_result: TaskResultModel = TaskResultModel()
    calib_data: CalibDataModel = CalibDataModel(qubit={}, coupling={})

    def __init__(self, qids: list[str] | None = None, **data) -> None:
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

    def _ensure_task_exists(
        self, task_name: str, task_type: str, qid: str
    ) -> BaseTaskResultModel:
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
        tasks = self._get_task_container(task_type, qid)
        existing = [t for t in tasks if t.name == task_name]
        if existing:
            return existing[0]

        task = self._create_task(task_name, task_type, qid)
        tasks.append(task)
        return task

    def _get_task_container(self, task_type: str, qid: str) -> list:
        """Get the appropriate task container.

        Parameters
        ----------
        task_type : str
            Type of task
        qid : str
            Qubit ID

        Returns
        -------
        list
            The task container list

        """
        if task_type == "qubit":
            return self.task_result.qubit_tasks[qid]
        elif task_type == "coupling":
            return self.task_result.coupling_tasks[qid]
        elif task_type == "global":
            return self.task_result.global_tasks
        elif task_type == "system":
            return self.task_result.system_tasks
        else:
            raise ValueError(f"Unknown task type: {task_type}")

    def _create_task(
        self, task_name: str, task_type: str, qid: str
    ) -> BaseTaskResultModel:
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
        if task_type == "qubit":
            return QubitTaskModel(name=task_name, qid=qid)
        elif task_type == "coupling":
            return CouplingTaskModel(name=task_name, qid=qid)
        elif task_type == "global":
            return GlobalTaskModel(name=task_name)
        elif task_type == "system":
            return SystemTaskModel(name=task_name)
        else:
            raise ValueError(f"Unknown task type: {task_type}")

    def get_task(
        self, task_name: str, task_type: str, qid: str
    ) -> BaseTaskResultModel:
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
        tasks = self._get_task_container(task_type, qid)
        for task in tasks:
            if task.name == task_name:
                return task
        raise ValueError(f"Task '{task_name}' not found for {task_type}/{qid}")

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
        task.start_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()

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
        task.end_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
        task.elapsed_time = task.calculate_elapsed_time(task.start_at, task.end_at)

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

    def put_input_parameters(
        self, task_name: str, input_parameters: dict, task_type: str, qid: str
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
        output_parameters: dict[str, OutputParameterModel],
        task_type: str,
        qid: str,
    ) -> None:
        """Store output parameters for a task and update calibration data.

        Parameters
        ----------
        task_name : str
            Name of the task
        output_parameters : dict[str, OutputParameterModel]
            The output parameters
        task_type : str
            Type of task
        qid : str
            Qubit ID

        """
        task = self._ensure_task_exists(task_name, task_type, qid)
        task.put_output_parameter(output_parameters)

        # Update calibration data
        if task_type == "qubit":
            for key, value in output_parameters.items():
                self.calib_data.put_qubit_data(qid, key, value)
        elif task_type == "coupling":
            for key, value in output_parameters.items():
                self.calib_data.put_coupling_data(qid, key, value)

    def get_output_parameter_by_task_name(
        self, task_name: str, task_type: str, qid: str
    ) -> dict:
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
        return task.output_parameters

    def start_all_qid_tasks(
        self, task_name: str, task_type: str, qids: list[str]
    ) -> None:
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
        tasks = self._get_task_container(task_type, qid)
        for task in tasks:
            if task.status == TaskStatusModel.SCHEDULED:
                task.status = TaskStatusModel.SKIPPED
                task.message = message

    def this_task_is_completed(
        self, task_name: str, task_type: str, qid: str
    ) -> bool:
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
            return task.status == TaskStatusModel.COMPLETED
        except ValueError:
            return False

    def _clear_qubit_calib_data(
        self, qid: str, parameter_names: list[str]
    ) -> None:
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

    def _clear_coupling_calib_data(
        self, qid: str, parameter_names: list[str]
    ) -> None:
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

    def get_qubit_calib_data(self, qid: str) -> dict:
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
        return self.calib_data.qubit.get(qid, {})

    def get_coupling_calib_data(self, qid: str) -> dict:
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
        return self.calib_data.coupling.get(qid, {})

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
            for qid_tasks in self.task_result.qubit_tasks.values():
                if any(t.name == name for t in qid_tasks):
                    found = True
                    break
            if not found:
                # Check if it's a coupling task
                for qid_tasks in self.task_result.coupling_tasks.values():
                    if any(t.name == name for t in qid_tasks):
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
            for qid_tasks in self.task_result.coupling_tasks.values():
                if any(t.name == name for t in qid_tasks):
                    found = True
                    break
            if not found:
                # Check if it's a qubit task
                for qid_tasks in self.task_result.qubit_tasks.values():
                    if any(t.name == name for t in qid_tasks):
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

    def ensure_task_exists(
        self, task_name: str, task_type: str, qid: str
    ) -> BaseTaskResultModel:
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

    def clear_qubit_calib_data(self, qid: str, parameter_names) -> None:
        """Public method to clear qubit calibration data.

        Parameters
        ----------
        qid : str
            Qubit ID
        parameter_names : Iterable[str]
            Names of parameters to clear

        """
        self._clear_qubit_calib_data(qid, list(parameter_names))

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
