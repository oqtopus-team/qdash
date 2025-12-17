"""ExecutionStateManager for pure state management without DB dependencies.

This module provides the ExecutionStateManager class that handles execution state
transitions without any database or I/O operations.
"""

from typing import Any

import pendulum
from pydantic import BaseModel
from qdash.datamodel.execution import (
    CalibDataModel,
    ExecutionModel,
    ExecutionStatusModel,
    TaskResultModel,
)
from qdash.datamodel.system_info import SystemInfoModel


class ExecutionStateManager(BaseModel):
    """Manager for execution state transitions (pure logic, no DB dependencies).

    This class handles:
    - Execution lifecycle (start, complete, fail)
    - Task result merging
    - Calibration data merging
    - Controller info updates

    Attributes
    ----------
    execution : ExecutionModel
        The execution model being managed

    """

    username: str = "admin"
    name: str = ""
    execution_id: str = ""
    calib_data_path: str = ""
    note: dict = {}
    status: ExecutionStatusModel = ExecutionStatusModel.SCHEDULED
    task_results: dict[str, TaskResultModel] = {}
    tags: list[str] = []
    controller_info: dict[str, dict] = {}
    fridge_info: dict = {}
    chip_id: str = ""
    project_id: str | None = None
    start_at: str = ""
    end_at: str = ""
    elapsed_time: str = ""
    calib_data: CalibDataModel = CalibDataModel(qubit={}, coupling={})
    message: str = ""
    system_info: SystemInfoModel = SystemInfoModel()

    def start(self) -> "ExecutionStateManager":
        """Set execution to started state.

        Returns
        -------
        ExecutionStateManager
            Self for method chaining

        """
        self.start_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
        self.status = ExecutionStatusModel.RUNNING
        self.system_info.update_time()
        return self

    def complete(self) -> "ExecutionStateManager":
        """Set execution to completed state.

        Returns
        -------
        ExecutionStateManager
            Self for method chaining

        """
        end_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
        self.end_at = end_at
        self.elapsed_time = self._calculate_elapsed_time(self.start_at, end_at)
        self.status = ExecutionStatusModel.COMPLETED
        self.system_info.update_time()
        return self

    def fail(self) -> "ExecutionStateManager":
        """Set execution to failed state.

        Returns
        -------
        ExecutionStateManager
            Self for method chaining

        """
        end_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
        self.end_at = end_at
        self.elapsed_time = self._calculate_elapsed_time(self.start_at, end_at)
        self.status = ExecutionStatusModel.FAILED
        self.system_info.update_time()
        return self

    def update_status(self, new_status: ExecutionStatusModel) -> "ExecutionStateManager":
        """Update execution status.

        Parameters
        ----------
        new_status : ExecutionStatusModel
            The new status to set

        Returns
        -------
        ExecutionStateManager
            Self for method chaining

        """
        self.status = new_status
        self.system_info.update_time()
        return self

    def merge_task_result(self, task_manager_id: str, task_result: TaskResultModel) -> None:
        """Merge task result into execution.

        Parameters
        ----------
        task_manager_id : str
            The task manager ID
        task_result : TaskResultModel
            The task result to merge

        """
        self.task_results[task_manager_id] = task_result
        self.system_info.update_time()

    def merge_calib_data(self, calib_data: CalibDataModel) -> None:
        """Merge calibration data into execution.

        Parameters
        ----------
        calib_data : CalibDataModel
            The calibration data to merge

        """
        # Merge qubit calibration data
        for qid, data in calib_data.qubit.items():
            if qid not in self.calib_data.qubit:
                self.calib_data.qubit[qid] = {}
            self.calib_data.qubit[qid].update(data)

        # Merge coupling calibration data
        for qid, data in calib_data.coupling.items():
            if qid not in self.calib_data.coupling:
                self.calib_data.coupling[qid] = {}
            self.calib_data.coupling[qid].update(data)

        self.system_info.update_time()

    def merge_controller_info(self, controller_info: dict[str, dict]) -> None:
        """Merge controller info into execution.

        Parameters
        ----------
        controller_info : dict[str, dict]
            The controller info to merge

        """
        for controller_id, info in controller_info.items():
            self.controller_info[controller_id] = info
        self.system_info.update_time()

    def get_qubit_parameter(self, qid: str, param_name: str) -> Any:
        """Get a qubit parameter from calibration data.

        Parameters
        ----------
        qid : str
            The qubit ID
        param_name : str
            The parameter name

        Returns
        -------
        any
            The parameter value, or None if not found

        """
        qubit_data = self.calib_data.qubit.get(qid, {})
        param = qubit_data.get(param_name)
        if param is None:
            return None
        # Handle OutputParameterModel
        return param.value if hasattr(param, "value") else param

    def get_coupling_parameter(self, qid_pair: str, param_name: str) -> Any:
        """Get a coupling parameter from calibration data.

        Parameters
        ----------
        qid_pair : str
            The coupling pair ID (e.g., "0-1")
        param_name : str
            The parameter name

        Returns
        -------
        any
            The parameter value, or None if not found

        """
        coupling_data = self.calib_data.coupling.get(qid_pair, {})
        param = coupling_data.get(param_name)
        if param is None:
            return None
        # Handle OutputParameterModel
        return param.value if hasattr(param, "value") else param

    def _calculate_elapsed_time(self, start_at: str, end_at: str) -> str:
        """Calculate elapsed time between two timestamps.

        Parameters
        ----------
        start_at : str
            Start timestamp in ISO8601 format
        end_at : str
            End timestamp in ISO8601 format

        Returns
        -------
        str
            Human-readable elapsed time

        Raises
        ------
        ValueError
            If timestamps cannot be parsed

        """
        try:
            start_time = pendulum.parse(start_at)
            end_time = pendulum.parse(end_at)
        except Exception as e:
            raise ValueError(f"Failed to parse the time. {e}")
        return end_time.diff_for_humans(start_time, absolute=True)  # type: ignore

    def to_datamodel(self) -> ExecutionModel:
        """Convert to ExecutionModel for persistence.

        Returns
        -------
        ExecutionModel
            The execution model representation

        """
        return ExecutionModel(
            username=self.username,
            name=self.name,
            execution_id=self.execution_id,
            calib_data_path=self.calib_data_path,
            note=self.note,
            status=self.status,
            task_results=self.task_results,
            tags=self.tags,
            controller_info=self.controller_info,
            fridge_info=self.fridge_info,
            chip_id=self.chip_id,
            project_id=self.project_id,
            start_at=self.start_at,
            end_at=self.end_at,
            elapsed_time=self.elapsed_time,
            calib_data=self.calib_data.model_dump(),
            message=self.message,
            system_info=self.system_info.model_dump(),
        )

    @classmethod
    def from_datamodel(cls, model: ExecutionModel) -> "ExecutionStateManager":
        """Create from ExecutionModel.

        Parameters
        ----------
        model : ExecutionModel
            The execution model to convert from

        Returns
        -------
        ExecutionStateManager
            New instance from the model

        """
        return cls(
            username=model.username,
            name=model.name,
            execution_id=model.execution_id,
            calib_data_path=model.calib_data_path,
            note=model.note,
            status=model.status,
            task_results=model.task_results,
            tags=model.tags,
            controller_info=model.controller_info,
            fridge_info=model.fridge_info,
            chip_id=model.chip_id,
            project_id=model.project_id,
            start_at=model.start_at,
            end_at=model.end_at,
            elapsed_time=model.elapsed_time,
            calib_data=CalibDataModel(**model.calib_data)
            if isinstance(model.calib_data, dict)
            else model.calib_data,
            message=model.message,
            system_info=SystemInfoModel(**model.system_info)
            if isinstance(model.system_info, dict)
            else model.system_info,
        )
