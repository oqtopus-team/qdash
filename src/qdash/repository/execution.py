"""MongoDB implementation of ExecutionRepository.

This module provides the MongoExecutionRepository class that handles execution
state persistence to MongoDB with optimistic locking support.

Used by workflow components for managing calibration execution state.
"""

import logging
import os
from collections.abc import Callable
from typing import Any

from pymongo import MongoClient, ReturnDocument
from pymongo.collection import Collection
from qdash.datamodel.execution import (
    ExecutionModel,
    ExecutionStatusModel,
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
        database: str | None = None,
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
        database : str | None
            Database name (defaults to MONGO_DB_NAME env var or 'qdash')

        """
        self._host = host or "mongo"
        self._port = port or 27017
        self._username = username or os.getenv("MONGO_INITDB_ROOT_USERNAME")
        self._password = password or os.getenv("MONGO_INITDB_ROOT_PASSWORD")
        self._database: str = database if database else os.getenv("MONGO_DB_NAME") or "qdash"

    def _get_client(self) -> MongoClient[Any]:
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

    def _get_collection(self, client: MongoClient[Any]) -> Collection[Any]:
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
        if execution.tags and execution.project_id:
            TagDocument.insert_tags(execution.tags, execution.username, execution.project_id)

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
                        if isinstance(model.system_info, SystemInfoModel):
                            model.system_info = model.system_info.model_copy()
                            model.system_info.updated_at = SystemInfoModel().updated_at
                        elif isinstance(model.system_info, dict):
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
        self, collection: Collection[Any], execution_id: str, initial_model: ExecutionModel
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
                    "project_id": initial_model.project_id,
                    "username": initial_model.username,
                    "name": initial_model.name,
                    "execution_id": execution_id,
                    "calib_data_path": initial_model.calib_data_path,
                    "note": {},
                    "status": ExecutionStatusModel.SCHEDULED,
                    "tags": [],
                    "chip_id": "",
                    "start_at": None,
                    "end_at": None,
                    "elapsed_time": None,
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
        update_data: dict[str, Any] = model.model_dump(mode="json")

        # Convert elapsed_time to seconds for MongoDB storage
        elapsed_time = model.elapsed_time
        elapsed_seconds = elapsed_time.total_seconds() if elapsed_time else None

        return {
            "$set": {
                "project_id": update_data["project_id"],
                "username": update_data["username"],
                "name": update_data["name"],
                "calib_data_path": update_data["calib_data_path"],
                "note": update_data["note"],
                "status": update_data["status"],
                "tags": update_data["tags"],
                "chip_id": update_data["chip_id"],
                "start_at": model.start_at,
                "end_at": model.end_at,
                "elapsed_time": elapsed_seconds,
                "message": update_data["message"],
                "system_info": update_data["system_info"],
            }
        }

    def _doc_to_model(self, doc: dict[str, Any]) -> ExecutionModel:
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
        return ExecutionModel(
            project_id=doc.get("project_id"),
            username=doc.get("username", "admin"),
            name=doc.get("name", ""),
            execution_id=doc.get("execution_id", ""),
            calib_data_path=doc.get("calib_data_path", ""),
            note=doc.get("note", {}),
            status=doc.get("status", ExecutionStatusModel.SCHEDULED),
            tags=doc.get("tags", []),
            chip_id=doc.get("chip_id", ""),
            start_at=doc.get("start_at") or None,
            end_at=doc.get("end_at") or None,
            elapsed_time=doc.get("elapsed_time") or None,
            message=doc.get("message", ""),
            system_info=doc.get("system_info", {}),
        )
