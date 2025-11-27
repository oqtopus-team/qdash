# application code for the execution manager.
import logging
from collections.abc import Callable

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
from qdash.workflow.engine.calibration.task_manager import TaskManager

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
        import os

        from pymongo import MongoClient, ReturnDocument

        try:
            client: MongoClient = MongoClient(
                "mongo",  # Docker service name
                port=27017,  # Docker internal port
                username=os.getenv("MONGO_INITDB_ROOT_USERNAME"),
                password=os.getenv("MONGO_INITDB_ROOT_PASSWORD"),
            )
            # Get collection
            collection = client.qubex[ExecutionHistoryDocument.Settings.name]

            # Define array_filters for nested updates (currently unused)
            # array_filters = []

            # First, ensure the document exists with initial structure
            collection.update_one(
                {"execution_id": self.execution_id},
                {
                    "$setOnInsert": {
                        "username": self.username,
                        "name": self.name,
                        "execution_id": self.execution_id,
                        "calib_data_path": self.calib_data_path,
                        "note": {},
                        "status": ExecutionStatusModel.SCHEDULED,
                        "task_results": {},
                        "tags": [],
                        "controller_info": {},
                        "fridge_info": {},
                        "chip_id": "",
                        "start_at": "",
                        "end_at": "",
                        "elapsed_time": "",
                        "calib_data": {"qubit": {}, "coupling": {}},
                        "message": "",
                        "system_info": {},
                    }
                },
                upsert=True,
            )

            # Get latest document and apply updates
            while True:
                try:
                    # Get current state
                    doc = collection.find_one({"execution_id": self.execution_id})
                    if doc is None:
                        instance = self
                    else:
                        instance = ExecutionManager.model_validate(doc)

                    # Execute update function
                    func(instance)
                    instance.system_info.update_time()

                    # Convert to dict
                    update_data = instance.to_datamodel().model_dump()

                    # Prepare update operations
                    update_ops = {
                        "$set": {
                            "username": update_data["username"],
                            "name": update_data["name"],
                            "calib_data_path": update_data["calib_data_path"],
                            "note": update_data["note"],
                            "status": update_data["status"],
                            "tags": update_data["tags"],
                            "chip_id": update_data["chip_id"],
                            "start_at": update_data["start_at"],
                            "end_at": update_data["end_at"],
                            "elapsed_time": update_data["elapsed_time"],
                            "message": update_data["message"],
                            "system_info": update_data["system_info"],
                        }
                    }

                    # Merge task_results
                    if update_data["task_results"]:
                        for k, v in update_data["task_results"].items():
                            update_ops["$set"][f"task_results.{k}"] = v

                    # Merge controller_info
                    if update_data["controller_info"]:
                        for k, v in update_data["controller_info"].items():
                            update_ops["$set"][f"controller_info.{k}"] = v

                    # Merge fridge_info
                    if update_data["fridge_info"]:
                        for k, v in update_data["fridge_info"].items():
                            update_ops["$set"][f"fridge_info.{k}"] = v

                    # Merge calibration data
                    if update_data["calib_data"].get("qubit"):
                        for qid, data in update_data["calib_data"]["qubit"].items():
                            update_ops["$set"][f"calib_data.qubit.{qid}"] = data

                    if update_data["calib_data"].get("coupling"):
                        for qid, data in update_data["calib_data"]["coupling"].items():
                            update_ops["$set"][f"calib_data.coupling.{qid}"] = data

                    # Try to update with optimistic locking
                    result = collection.find_one_and_update(
                        {
                            "execution_id": self.execution_id,
                            "$or": [
                                {"_version": {"$exists": False}},
                                {"_version": doc.get("_version", 0) if doc else 0},
                            ],
                        },
                        {
                            **update_ops,
                            "$inc": {"_version": 1},
                        },
                        return_document=ReturnDocument.AFTER,
                    )

                    if result is not None:
                        # Update successful
                        break

                    # If update failed, retry with latest document
                    logger.info("Retrying update due to concurrent modification")
                    continue

                except Exception as e:
                    logger.error(f"Error during update retry: {e}")
                    raise

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

            # Note: Calibration notes are now updated directly in session.update_note()
            # No need for additional merge processing here

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
        # Auto-register tags to TagDocument for UI tag selector
        if self.tags:
            TagDocument.insert_tags(self.tags, self.username)
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
