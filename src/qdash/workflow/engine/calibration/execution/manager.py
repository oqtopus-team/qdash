# application code for the execution manager.
"""ExecutionManager - Facade for execution lifecycle management.

This module provides backward-compatible ExecutionManager that delegates
to ExecutionService and ExecutionStateManager internally.
"""

import logging

import pendulum
from pydantic import BaseModel, Field
from qdash.datamodel.execution import (
    CalibDataModel,
    ExecutionModel,
    ExecutionStatusModel,
    TaskResultModel,
)
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.tag import TagDocument
from qdash.workflow.engine.calibration.execution.state_manager import (
    ExecutionStateManager,
)
from qdash.workflow.engine.calibration.repository.mongo_execution import (
    MongoExecutionRepository,
)
from qdash.workflow.engine.calibration.task.manager import TaskManager

initialize()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ExecutionManager(BaseModel):
    """ExecutionManager class to manage the execution of the calibration flow.

    This class now acts as a facade, delegating to ExecutionStateManager
    for state management and MongoExecutionRepository for persistence.
    The public API remains unchanged for backward compatibility.
    """

    # Internal state manager (handles pure state logic)
    _state_manager: ExecutionStateManager | None = None
    # Internal repository (handles persistence)
    _repository: MongoExecutionRepository | None = None

    # Public fields (for backward compatibility and Pydantic serialization)
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
    start_at: str = Field(
        default_factory=lambda: pendulum.now(tz="Asia/Tokyo").to_iso8601_string(),
        description="The time when the system information was created",
    )
    end_at: str = ""
    elapsed_time: str = ""
    calib_data: CalibDataModel = CalibDataModel(qubit={}, coupling={})
    message: str = ""
    system_info: SystemInfoModel = SystemInfoModel()

    model_config = {"arbitrary_types_allowed": True}

    def __init__(
        self,
        username: str,
        execution_id: str,
        calib_data_path: str,
        tags: list[str] = [],
        fridge_info: dict = {},
        chip_id: str = "",
        name: str = "default",
        note: dict = {},
        project_id: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.username = username
        self.name = name
        self.execution_id = execution_id
        self.calib_data_path = calib_data_path
        self.tags = tags
        self.fridge_info = fridge_info
        self.chip_id = chip_id
        self.note = note
        self.project_id = project_id

        # Initialize internal components
        self._state_manager = ExecutionStateManager(
            username=username,
            name=name,
            execution_id=execution_id,
            calib_data_path=calib_data_path,
            note=note,
            status=ExecutionStatusModel.SCHEDULED,
            tags=tags,
            fridge_info=fridge_info,
            chip_id=chip_id,
            project_id=project_id,
        )
        self._repository = MongoExecutionRepository()

    def _sync_from_state_manager(self) -> None:
        """Sync public fields from internal state manager."""
        if self._state_manager:
            self.username = self._state_manager.username
            self.name = self._state_manager.name
            self.execution_id = self._state_manager.execution_id
            self.calib_data_path = self._state_manager.calib_data_path
            self.note = self._state_manager.note
            self.status = self._state_manager.status
            self.task_results = self._state_manager.task_results
            self.tags = self._state_manager.tags
            self.controller_info = self._state_manager.controller_info
            self.fridge_info = self._state_manager.fridge_info
            self.chip_id = self._state_manager.chip_id
            self.project_id = self._state_manager.project_id
            self.start_at = self._state_manager.start_at
            self.end_at = self._state_manager.end_at
            self.elapsed_time = self._state_manager.elapsed_time
            self.calib_data = self._state_manager.calib_data
            self.message = self._state_manager.message
            self.system_info = self._state_manager.system_info

    def _sync_to_state_manager(self) -> None:
        """Sync public fields to internal state manager."""
        if self._state_manager:
            self._state_manager.username = self.username
            self._state_manager.name = self.name
            self._state_manager.execution_id = self.execution_id
            self._state_manager.calib_data_path = self.calib_data_path
            self._state_manager.note = self.note
            self._state_manager.status = self.status
            self._state_manager.task_results = self.task_results
            self._state_manager.tags = self.tags
            self._state_manager.controller_info = self.controller_info
            self._state_manager.fridge_info = self.fridge_info
            self._state_manager.chip_id = self.chip_id
            self._state_manager.project_id = self.project_id
            self._state_manager.start_at = self.start_at
            self._state_manager.end_at = self.end_at
            self._state_manager.elapsed_time = self.elapsed_time
            self._state_manager.calib_data = self.calib_data
            self._state_manager.message = self.message
            self._state_manager.system_info = self.system_info

    def update_status(self, new_status: ExecutionStatusModel) -> None:
        """Update the status of the execution."""
        if self._state_manager and self._repository:
            self._state_manager.update_status(new_status)
            self._repository.update_with_optimistic_lock(
                execution_id=self.execution_id,
                update_func=lambda m: setattr(m, "status", new_status),
                initial_model=self._state_manager.to_datamodel(),
            )
            self._sync_from_state_manager()

    def update_execution_status_to_running(self) -> "ExecutionManager":
        self.update_status(ExecutionStatusModel.RUNNING)
        return self

    def update_execution_status_to_completed(self) -> "ExecutionManager":
        self.update_status(ExecutionStatusModel.COMPLETED)
        return self

    def update_execution_status_to_failed(self) -> "ExecutionManager":
        self.update_status(ExecutionStatusModel.FAILED)
        return self

    def reload(self) -> "ExecutionManager":
        """Reload the execution manager from the database."""
        if self._repository:
            model = self._repository.find_by_id(self.execution_id)
            if model is None:
                # First time - save current instance
                ExecutionHistoryDocument.upsert_document(self.to_datamodel())
                return self

            # Update state manager from loaded model
            self._state_manager = ExecutionStateManager.from_datamodel(model)
            self._sync_from_state_manager()
        return self

    def update_with_task_manager(self, task_manager: TaskManager) -> "ExecutionManager":
        """Update execution with task manager results."""
        if self._state_manager and self._repository:
            # Merge task result
            self._state_manager.merge_task_result(task_manager.id, task_manager.task_result)

            # Merge calibration data
            self._state_manager.merge_calib_data(task_manager.calib_data)

            # Merge controller info
            self._state_manager.merge_controller_info(task_manager.controller_info)

            # Persist with optimistic locking
            def updater(model: ExecutionModel) -> None:
                # Update task results
                model.task_results[task_manager.id] = task_manager.task_result

                # Merge calibration data
                if isinstance(model.calib_data, dict):
                    for qid, data in task_manager.calib_data.qubit.items():
                        model.calib_data.setdefault("qubit", {}).setdefault(qid, {}).update(
                            data if isinstance(data, dict) else {}
                        )
                    for qid, data in task_manager.calib_data.coupling.items():
                        model.calib_data.setdefault("coupling", {}).setdefault(qid, {}).update(
                            data if isinstance(data, dict) else {}
                        )

                # Update controller info
                for _id, info in task_manager.controller_info.items():
                    model.controller_info[_id] = info

            self._repository.update_with_optimistic_lock(
                execution_id=self.execution_id,
                update_func=updater,
                initial_model=self._state_manager.to_datamodel(),
            )

            self._sync_from_state_manager()
        return self.reload()

    def calculate_elapsed_time(self, start_at: str, end_at: str) -> str:
        """Calculate elapsed time between two timestamps."""
        try:
            start_time = pendulum.parse(start_at)
            end_time = pendulum.parse(end_at)
        except Exception as e:
            raise ValueError(f"Failed to parse the time. {e}")
        return end_time.diff_for_humans(start_time, absolute=True)  # type: ignore

    def start_execution(self) -> "ExecutionManager":
        """Start the execution and set the start time."""
        if self._state_manager and self._repository:
            self._state_manager.start()

            def updater(model: ExecutionModel) -> None:
                model.start_at = self._state_manager.start_at
                model.status = ExecutionStatusModel.RUNNING

            self._repository.update_with_optimistic_lock(
                execution_id=self.execution_id,
                update_func=updater,
                initial_model=self._state_manager.to_datamodel(),
            )

            self._sync_from_state_manager()
        return self.reload()

    def complete_execution(self) -> "ExecutionManager":
        """Complete the execution with success status."""
        if self._state_manager and self._repository:
            self._state_manager.complete()

            def updater(model: ExecutionModel) -> None:
                model.end_at = self._state_manager.end_at
                model.elapsed_time = self._state_manager.elapsed_time
                model.status = ExecutionStatusModel.COMPLETED

            self._repository.update_with_optimistic_lock(
                execution_id=self.execution_id,
                update_func=updater,
                initial_model=self._state_manager.to_datamodel(),
            )

            self._sync_from_state_manager()
        return self.reload()

    def fail_execution(self) -> "ExecutionManager":
        """Complete the execution with failure status."""
        if self._state_manager and self._repository:
            self._state_manager.fail()

            def updater(model: ExecutionModel) -> None:
                model.end_at = self._state_manager.end_at
                model.elapsed_time = self._state_manager.elapsed_time
                model.status = ExecutionStatusModel.FAILED

            self._repository.update_with_optimistic_lock(
                execution_id=self.execution_id,
                update_func=updater,
                initial_model=self._state_manager.to_datamodel(),
            )

            self._sync_from_state_manager()
        return self.reload()

    def save(self) -> "ExecutionManager":
        """Save the execution manager to the database."""
        if self._repository:
            self._sync_to_state_manager()
            self._repository.save(self.to_datamodel())

        # Auto-register tags to TagDocument for UI tag selector
        if self.tags:
            TagDocument.insert_tags(self.tags, self.username)
        return self

    def to_datamodel(self) -> ExecutionModel:
        """Convert to ExecutionModel for persistence."""
        if self._state_manager:
            return self._state_manager.to_datamodel()

        # Fallback for cases where state manager is not initialized
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
