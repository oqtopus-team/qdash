# application code for the execution manager.
import json
from pathlib import Path
from typing import Callable

import pendulum
from datamodel.execution import (
    CalibDataModel,
    ExecutionModel,
    ExecutionStatusModel,
    TaskResultModel,
)
from datamodel.system_info import SystemInfoModel
from filelock import FileLock
from pydantic import BaseModel, Field
from qcflow.manager.task import TaskManager


class ExecutionManager(BaseModel):
    """ExecutionManager class to manage the execution of the calibration flow."""

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
    start_at: str = Field(
        default_factory=lambda: pendulum.now(tz="Asia/Tokyo").to_iso8601_string(),
        description="The time when the system information was created",
    )
    end_at: str = ""
    elapsed_time: str = ""
    calib_data: CalibDataModel = CalibDataModel(qubit={}, coupling={})
    message: str = ""
    system_info: SystemInfoModel = SystemInfoModel()

    def __init__(
        self,
        execution_id: str,
        calib_data_path: str,
        tags: list[str] = [],
        fridge_info: dict = {},
        chip_id: str = "",
        name: str = "default",
        note: dict = {},
        **kwargs,  # noqa: ANN003
    ) -> None:
        super().__init__(**kwargs)
        self.name = name
        self.execution_id = execution_id
        self.calib_data_path = calib_data_path
        self.tags = tags
        self.fridge_info = fridge_info
        self.chip_id = chip_id
        self.note = note
        self._lock_file = Path(f"{self.calib_data_path}/execution_note.lock")

    def _with_file_lock(self, func: Callable[["ExecutionManager"], None]) -> None:
        """Filelock in the update method."""
        lock = FileLock(str(self._lock_file))
        with lock:
            instance = ExecutionManager.load_from_file(self.calib_data_path)
            func(instance)
            instance.system_info.update_time()
            instance._atomic_save()  # noqa: SLF001

    def update_status(self, new_status: ExecutionStatusModel) -> None:
        """Update the status of the execution."""

        def updater(instance: ExecutionManager) -> None:
            instance.status = new_status

        self._with_file_lock(updater)

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
        """Reload the execution manager from the file and return self for chaining."""
        return ExecutionManager.load_from_file(self.calib_data_path)

    def update_with_task_manager(self, task_manager: TaskManager) -> "ExecutionManager":
        def updater(updated: ExecutionManager) -> None:
            updated.task_results[task_manager.id] = task_manager.task_result
            for qid in task_manager.calib_data.qubit:
                updated.calib_data.qubit[qid] = task_manager.calib_data.qubit[qid]
            for qid in task_manager.calib_data.coupling:
                updated.calib_data.coupling[qid] = task_manager.calib_data.coupling[qid]
            for _id in task_manager.controller_info:
                updated.controller_info[_id] = task_manager.controller_info[_id]

        self._with_file_lock(updater)
        return ExecutionManager.load_from_file(self.calib_data_path)

    def calculate_elapsed_time(self, start_at: str, end_at: str) -> str:
        try:
            start_time = pendulum.parse(start_at)
            end_time = pendulum.parse(end_at)
        except Exception as e:
            raise ValueError(f"Failed to parse the time. {e}")
        return end_time.diff_for_humans(start_time, absolute=True)  # type: ignore #noqa: PGH003

    def start_execution(self) -> "ExecutionManager":
        """Start the execution and set the start time."""

        def updater(instance: ExecutionManager) -> None:
            instance.start_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()

        self._with_file_lock(updater)
        return ExecutionManager.load_from_file(self.calib_data_path)

    def complete_execution(self) -> "ExecutionManager":
        """Complete the execution with success status."""
        # 最新の状態を読み込む
        instance = ExecutionManager.load_from_file(self.calib_data_path)
        # 終了時刻を設定
        end_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
        instance.end_at = end_at
        instance.elapsed_time = instance.calculate_elapsed_time(instance.start_at, end_at)
        # 完了状態を設定
        instance.status = ExecutionStatusModel.COMPLETED
        instance.save()
        return instance

    def fail_execution(self) -> "ExecutionManager":
        """Complete the execution with failure status."""
        # 最新の状態を読み込む
        instance = ExecutionManager.load_from_file(self.calib_data_path)
        # 終了時刻を設定
        end_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
        instance.end_at = end_at
        instance.elapsed_time = instance.calculate_elapsed_time(instance.start_at, end_at)
        # 失敗状態を設定
        instance.status = ExecutionStatusModel.FAILED
        instance.save()
        return instance

    def save(self) -> "ExecutionManager":
        self._atomic_save()
        return self

    def _atomic_save(self) -> None:
        """Filelock in the save method."""
        save_path = Path(f"{self.calib_data_path}/execution_note.json")
        temp_path = save_path.with_suffix(".tmp")
        with temp_path.open("w") as f:
            f.write(json.dumps(self.model_dump(), indent=2))
        temp_path.replace(save_path)

    @classmethod
    def load_from_file(cls, calib_data_path: str) -> "ExecutionManager":
        save_path = Path(f"{calib_data_path}/execution_note.json")
        if not save_path.exists():
            raise FileNotFoundError(f"{save_path} does not exist.")
        return cls.model_validate_json(save_path.read_text())

    def to_datamodel(self) -> ExecutionModel:
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
            start_at=self.start_at,
            end_at=self.end_at,
            elapsed_time=self.elapsed_time,
            calib_data=self.calib_data.model_dump(),
            message=self.message,
            system_info=self.system_info.model_dump(),
        )
