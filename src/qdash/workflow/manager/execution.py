# application code for the execution manager.
import json
import logging
from collections.abc import Callable
from pathlib import Path

import pendulum
from pydantic import BaseModel, Field
from qdash.datamodel.execution import (
    CalibDataModel,
    ExecutionModel,
    ExecutionStatusModel,
    TaskResultModel,
)
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.calibration_note import CalibrationNoteDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.initialize import initialize
from qdash.workflow.manager.task import TaskManager
from qdash.workflow.utils.merge_notes import merge_notes_by_timestamp

initialize()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
        username: str,
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
        self.username = username
        self.name = name
        self.execution_id = execution_id
        self.calib_data_path = calib_data_path
        self.tags = tags
        self.fridge_info = fridge_info
        self.chip_id = chip_id
        self.note = note

    def _with_db_transaction(self, func: Callable[["ExecutionManager"], None]) -> None:
        """Execute the function within a MongoDB transaction."""
        try:
            # 最新の状態を取得
            doc = ExecutionHistoryDocument.find_one({"execution_id": self.execution_id}).run()
            if doc is None:
                # 初回の場合は現在のインスタンスを使用
                instance = self
            else:
                instance = ExecutionManager.model_validate(doc.model_dump())

            # 関数を実行
            func(instance)
            instance.system_info.update_time()

            # DBに保存
            ExecutionHistoryDocument.upsert_document(instance.to_datamodel())
        except Exception as e:
            logger.error(f"DB transaction failed: {e}")
            raise

    def update_status(self, new_status: ExecutionStatusModel) -> None:
        """Update the status of the execution."""

        def updater(instance: ExecutionManager) -> None:
            instance.status = new_status

        self._with_db_transaction(updater)

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
        doc = ExecutionHistoryDocument.find_one({"execution_id": self.execution_id}).run()
        if doc is None:
            # 初回の場合は現在のインスタンスを保存
            ExecutionHistoryDocument.upsert_document(self.to_datamodel())
            return self
        return ExecutionManager.model_validate(doc.model_dump())

    def _merge_calib_notes(self, task_id: str) -> None:
        """Merge calibration notes from task with master note.

        Args:
        ----
            task_id: ID of the task whose note to merge

        Note:
        ----
            This function handles the loading, merging and saving of calibration notes.
            It uses timestamp-based merging to ensure the most recent data is kept.

        """
        try:
            # タスクのノートを読み込む
            task_note_path = Path(f"{self.calib_data_path}/calib_note/{task_id}.json")
            if not task_note_path.exists():
                return  # Skip if task note doesn't exist

            task_note = json.loads(task_note_path.read_text())

            # 最新のマスターノートを取得
            master_docs = (
                CalibrationNoteDocument.find({"task_id": "master"})
                .sort([("timestamp", -1)])  # timestampで降順ソート
                .limit(1)
                .run()
            )

            if not master_docs:
                # マスターノートが存在しない場合は新規作成
                CalibrationNoteDocument.upsert_note(
                    username=self.username,
                    execution_id=self.execution_id,
                    task_id="master",
                    note=task_note,
                )
            else:
                # マスターノートが存在する場合はマージして更新
                master_doc = master_docs[0]
                merged_note = merge_notes_by_timestamp(master_doc.note, task_note)
                CalibrationNoteDocument.upsert_note(
                    username=self.username,
                    execution_id=self.execution_id,  # 最新のexecution_idで更新
                    task_id="master",
                    note=merged_note,
                )

            # タスクのノートもDBに保存
            CalibrationNoteDocument.upsert_note(
                username=self.username,
                execution_id=self.execution_id,
                task_id=task_id,
                note=task_note,
            )

        except Exception as e:
            logger.info(f"Error merging notes: {e}")  # Log error but continue execution

    def update_with_task_manager(self, task_manager: TaskManager) -> "ExecutionManager":
        def updater(updated: ExecutionManager) -> None:
            # Update task results
            updated.task_results[task_manager.id] = task_manager.task_result

            # Merge calibration data instead of overwriting
            for qid in task_manager.calib_data.qubit:
                if qid not in updated.calib_data.qubit:
                    updated.calib_data.qubit[qid] = {}
                updated.calib_data.qubit[qid].update(task_manager.calib_data.qubit[qid])

            for qid in task_manager.calib_data.coupling:
                if qid not in updated.calib_data.coupling:
                    updated.calib_data.coupling[qid] = {}
                updated.calib_data.coupling[qid].update(task_manager.calib_data.coupling[qid])

            # Update controller info
            for _id in task_manager.controller_info:
                updated.controller_info[_id] = task_manager.controller_info[_id]

            # Merge calibration notes
            self._merge_calib_notes(task_manager.id)

        self._with_db_transaction(updater)
        return self.reload()

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

        self._with_db_transaction(updater)
        return self.reload()

    def complete_execution(self) -> "ExecutionManager":
        """Complete the execution with success status."""

        def updater(instance: ExecutionManager) -> None:
            # 終了時刻を設定
            end_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
            instance.end_at = end_at
            instance.elapsed_time = instance.calculate_elapsed_time(instance.start_at, end_at)
            # 完了状態を設定
            instance.status = ExecutionStatusModel.COMPLETED

        self._with_db_transaction(updater)
        return self.reload()

    def fail_execution(self) -> "ExecutionManager":
        """Complete the execution with failure status."""

        def updater(instance: ExecutionManager) -> None:
            # 終了時刻を設定
            end_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
            instance.end_at = end_at
            instance.elapsed_time = instance.calculate_elapsed_time(instance.start_at, end_at)
            # 失敗状態を設定
            instance.status = ExecutionStatusModel.FAILED

        self._with_db_transaction(updater)
        return self.reload()

    def save(self) -> "ExecutionManager":
        """Save the execution manager to the database."""
        ExecutionHistoryDocument.upsert_document(self.to_datamodel())
        return self

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
