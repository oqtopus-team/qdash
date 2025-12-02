"""MongoDB implementation of ExecutionRepository.

This module provides the MongoExecutionRepository class that handles execution
state persistence to MongoDB with optimistic locking support.
"""

import logging
import os
from collections.abc import Callable
from typing import Any

from pymongo import MongoClient, ReturnDocument

from qdash.datamodel.execution import (
    CalibDataModel,
    ExecutionModel,
    ExecutionStatusModel,
    TaskResultModel,
)
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.tag import TagDocument

logger = logging.getLogger(__name__)


class MongoExecutionRepository:
    """MongoDB implementation of ExecutionRepository.

    This class handles:
    - Execution state persistence to MongoDB
    - Optimistic locking for concurrent updates
    - Merge operations for task results and calibration data

    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        database: str = "qubex",
    ):
        """Initialize MongoExecutionRepository.

        Parameters
        ----------
        host : str | None
            MongoDB host (defaults to 'mongo' for Docker)
        port : int | None
            MongoDB port (defaults to 27017)
        username : str | None
            MongoDB username (defaults to env var)
        password : str | None
            MongoDB password (defaults to env var)
        database : str
            Database name (defaults to 'qubex')

        """
        self._host = host or "mongo"
        self._port = port or 27017
        self._username = username or os.getenv("MONGO_INITDB_ROOT_USERNAME")
        self._password = password or os.getenv("MONGO_INITDB_ROOT_PASSWORD")
        self._database = database

    def _get_client(self) -> MongoClient:
        """Get MongoDB client.

        Returns
        -------
        MongoClient
            Connected MongoDB client

        """
        return MongoClient(
            self._host,
            port=self._port,
            username=self._username,
            password=self._password,
        )

    def _get_collection(self, client: MongoClient):
        """Get the execution history collection.

        Parameters
        ----------
        client : MongoClient
            MongoDB client

        Returns
        -------
        Collection
            The execution history collection

        """
        return client[self._database][ExecutionHistoryDocument.Settings.name]

    def save(self, execution: ExecutionModel) -> None:
        """Save execution state to the database.

        Parameters
        ----------
        execution : ExecutionModel
            The execution model to save

        """
        ExecutionHistoryDocument.upsert_document(execution)
        # Auto-register tags
        if execution.tags:
            TagDocument.insert_tags(execution.tags, execution.username)

    def find_by_id(self, execution_id: str) -> ExecutionModel | None:
        """Find execution by ID.

        Parameters
        ----------
        execution_id : str
            The execution identifier

        Returns
        -------
        ExecutionModel | None
            The execution model if found, None otherwise

        """
        doc = ExecutionHistoryDocument.find_one({"execution_id": execution_id}).run()
        if doc is None:
            return None
        return self._doc_to_model(doc.model_dump())

    def update_with_optimistic_lock(
        self,
        execution_id: str,
        update_func: Callable[[ExecutionModel], None],
        initial_model: ExecutionModel | None = None,
    ) -> ExecutionModel:
        """Update execution with optimistic locking.

        This method reads the current state, applies the update function,
        and saves with version checking to handle concurrent modifications.

        Parameters
        ----------
        execution_id : str
            The execution identifier
        update_func : callable
            Function that takes ExecutionModel and modifies it in place
        initial_model : ExecutionModel | None
            Initial model to use if document doesn't exist

        Returns
        -------
        ExecutionModel
            The updated execution model

        """
        try:
            client = self._get_client()
            collection = self._get_collection(client)

            # Ensure document exists with initial structure
            if initial_model:
                self._ensure_document_exists(collection, execution_id, initial_model)

            # Get latest document and apply updates with retry
            while True:
                try:
                    # Get current state
                    doc = collection.find_one({"execution_id": execution_id})
                    if doc is None:
                        if initial_model:
                            model = initial_model
                        else:
                            raise ValueError(f"Execution {execution_id} not found")
                    else:
                        model = self._doc_to_model(doc)

                    # Execute update function
                    update_func(model)

                    # Update system_info timestamp
                    if hasattr(model, "system_info"):
                        model.system_info["updated_at"] = SystemInfoModel().updated_at

                    # Prepare update operations
                    update_ops = self._build_update_ops(model)

                    # Try to update with optimistic locking
                    result = collection.find_one_and_update(
                        {
                            "execution_id": execution_id,
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
                        return self._doc_to_model(result)

                    # If update failed, retry with latest document
                    logger.info("Retrying update due to concurrent modification")
                    continue

                except Exception as e:
                    logger.error(f"Error during update retry: {e}")
                    raise

        except Exception as e:
            logger.error(f"DB transaction failed: {e}")
            raise

    def _ensure_document_exists(
        self, collection, execution_id: str, initial_model: ExecutionModel
    ) -> None:
        """Ensure document exists in collection.

        Parameters
        ----------
        collection
            MongoDB collection
        execution_id : str
            Execution ID
        initial_model : ExecutionModel
            Initial model for setOnInsert

        """
        collection.update_one(
            {"execution_id": execution_id},
            {
                "$setOnInsert": {
                    "username": initial_model.username,
                    "name": initial_model.name,
                    "execution_id": execution_id,
                    "calib_data_path": initial_model.calib_data_path,
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

    def _build_update_ops(self, model: ExecutionModel) -> dict[str, Any]:
        """Build MongoDB update operations from model.

        Parameters
        ----------
        model : ExecutionModel
            The execution model

        Returns
        -------
        dict[str, Any]
            MongoDB update operations

        """
        update_data = model.model_dump() if hasattr(model, "model_dump") else model

        update_ops: dict[str, Any] = {
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
        if update_data.get("task_results"):
            for k, v in update_data["task_results"].items():
                if hasattr(v, "model_dump"):
                    update_ops["$set"][f"task_results.{k}"] = v.model_dump()
                else:
                    update_ops["$set"][f"task_results.{k}"] = v

        # Merge controller_info
        if update_data.get("controller_info"):
            for k, v in update_data["controller_info"].items():
                update_ops["$set"][f"controller_info.{k}"] = v

        # Merge fridge_info
        if update_data.get("fridge_info"):
            for k, v in update_data["fridge_info"].items():
                update_ops["$set"][f"fridge_info.{k}"] = v

        # Merge calibration data
        calib_data = update_data.get("calib_data", {})
        if calib_data.get("qubit"):
            for qid, data in calib_data["qubit"].items():
                update_ops["$set"][f"calib_data.qubit.{qid}"] = data

        if calib_data.get("coupling"):
            for qid, data in calib_data["coupling"].items():
                update_ops["$set"][f"calib_data.coupling.{qid}"] = data

        return update_ops

    def _doc_to_model(self, doc: dict) -> ExecutionModel:
        """Convert MongoDB document to ExecutionModel.

        Parameters
        ----------
        doc : dict
            MongoDB document

        Returns
        -------
        ExecutionModel
            Converted model

        """
        # Handle TaskResultModel conversion
        task_results = {}
        for k, v in doc.get("task_results", {}).items():
            if isinstance(v, dict):
                task_results[k] = TaskResultModel(**v)
            else:
                task_results[k] = v

        # Handle CalibDataModel conversion
        calib_data = doc.get("calib_data", {"qubit": {}, "coupling": {}})
        if isinstance(calib_data, dict):
            calib_data_model = CalibDataModel(**calib_data)
        else:
            calib_data_model = calib_data

        return ExecutionModel(
            username=doc.get("username", "admin"),
            name=doc.get("name", ""),
            execution_id=doc.get("execution_id", ""),
            calib_data_path=doc.get("calib_data_path", ""),
            note=doc.get("note", {}),
            status=doc.get("status", ExecutionStatusModel.SCHEDULED),
            task_results=task_results,
            tags=doc.get("tags", []),
            controller_info=doc.get("controller_info", {}),
            fridge_info=doc.get("fridge_info", {}),
            chip_id=doc.get("chip_id", ""),
            start_at=doc.get("start_at", ""),
            end_at=doc.get("end_at", ""),
            elapsed_time=doc.get("elapsed_time", ""),
            calib_data=calib_data_model.model_dump(),
            message=doc.get("message", ""),
            system_info=doc.get("system_info", {}),
        )
