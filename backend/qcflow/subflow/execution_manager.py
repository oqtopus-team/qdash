import json
from enum import Enum
from pathlib import Path
from typing import Callable

import pendulum
from filelock import FileLock
from pydantic import BaseModel
from qcflow.subflow.constant import COMPLETED, FAILED, RUNNING, SCHDULED
from qcflow.subflow.system_info import SystemInfo
from qcflow.subflow.task_manager import CalibData, TaskManager, TaskResult


class ExecutionStatus(str, Enum):
    """enum class for the status of the execution."""

    SCHEDULED = SCHDULED
    RUNNING = RUNNING
    COMPLETED = COMPLETED
    FAILED = FAILED


class ExecutionManager(BaseModel):
    """ExecutionManager class to manage the execution of the calibration flow."""

    name: str = ""
    execution_id: str = ""
    calib_data_path: str = ""
    qubex_version: str = ""
    status: ExecutionStatus = ExecutionStatus.SCHEDULED
    task_results: dict[str, TaskResult] = {}
    tags: list[str] = []
    controller_info: dict[str, dict] = {}
    fridge_info: dict = {}
    chip_id: str = ""
    start_at: str = ""
    end_at: str = ""
    elapsed_time: str = ""
    calib_data: CalibData = CalibData(qubit={}, coupling={})
    system_info: SystemInfo = SystemInfo()

    def __init__(
        self,
        execution_id: str,
        calib_data_path: str,
        tags: list[str] = [],
        fridge_info: dict = {},
        chip_id: str = "",
        name: str = "default",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.name = name
        self.execution_id = execution_id
        self.calib_data_path = calib_data_path
        self.tags = tags
        self.fridge_info = fridge_info
        self.chip_id = chip_id
        self._lock_file = Path(f"{self.calib_data_path}/execution_note.lock")

    def _with_file_lock(self, func: Callable[["ExecutionManager"], None]) -> None:
        """Filelock in the update method."""
        lock = FileLock(str(self._lock_file))
        with lock:
            instance = ExecutionManager.load_from_file(self.calib_data_path)
            func(instance)
            instance.system_info.update_time()
            instance._atomic_save()

    def update_status(self, new_status: ExecutionStatus) -> None:
        """Update the status of the execution."""

        def updater(instance: ExecutionManager) -> None:
            instance.status = new_status

        self._with_file_lock(updater)

    def update_execution_status_to_running(self) -> None:
        self.update_status(ExecutionStatus.RUNNING)

    def update_execution_status_to_completed(self) -> None:
        self.update_status(ExecutionStatus.COMPLETED)

    def update_execution_status_to_failed(self) -> None:
        self.update_status(ExecutionStatus.FAILED)

    def update_with_task_manager(self, task_manager: TaskManager) -> None:
        def updater(instance: ExecutionManager) -> None:
            instance.task_results[task_manager.id] = task_manager.task_result
            for qid in task_manager.calib_data.qubit:
                instance.calib_data.qubit[qid] = task_manager.calib_data.qubit[qid]
            for qid in task_manager.calib_data.coupling:
                instance.calib_data.coupling[qid] = task_manager.calib_data.coupling[qid]
            for _id in task_manager.controller_info:
                instance.controller_info[_id] = task_manager.controller_info[_id]

        self._with_file_lock(updater)

    def calculate_elapsed_time(self, start_at: str, end_at: str) -> str:
        try:
            start_time = pendulum.parse(start_at)
            end_time = pendulum.parse(end_at)
        except Exception as e:
            raise ValueError(f"Failed to parse the time. {e}")
        return end_time.diff_for_humans(start_time, absolute=True)

    def start_execution(self) -> None:
        def updater(instance: ExecutionManager) -> None:
            instance.start_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()

        self._with_file_lock(updater)

    def end_execution(self) -> None:
        def updater(instance: ExecutionManager) -> None:
            instance.end_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
            instance.elapsed_time = instance.calculate_elapsed_time(
                instance.start_at, instance.end_at
            )

        self._with_file_lock(updater)

    def save(self) -> None:
        self._atomic_save()

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
