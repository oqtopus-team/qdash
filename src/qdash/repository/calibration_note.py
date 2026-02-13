"""MongoDB implementation of CalibrationNoteRepository.

This module provides the concrete MongoDB implementation for calibration note
persistence operations. Used by both API and workflow components.
"""

import logging
import time

from bunnet import SortDirection
from pymongo.errors import DuplicateKeyError
from qdash.common.datetime_utils import now
from qdash.datamodel.calibration_note import CalibrationNoteModel
from qdash.dbmodel.calibration_note import CalibrationNoteDocument

logger = logging.getLogger(__name__)


class MongoCalibrationNoteRepository:
    """MongoDB implementation of CalibrationNoteRepository.

    This class encapsulates all MongoDB-specific logic for calibration notes,
    providing a clean interface that returns domain models.

    Example
    -------
        >>> repo = MongoCalibrationNoteRepository()
        >>> note = repo.find_latest_master(chip_id="64Qv3", project_id="proj-1")
        >>> if note:
        ...     updated = CalibrationNoteModel(**note.model_dump(), note={"key": "value"})
        ...     repo.upsert(updated)

    """

    def find_one(
        self,
        *,
        project_id: str | None = None,
        username: str | None = None,
        chip_id: str | None = None,
        execution_id: str | None = None,
        task_id: str | None = None,
    ) -> CalibrationNoteModel | None:
        """Find a single calibration note by query parameters.

        Parameters
        ----------
        project_id : str, optional
            The project identifier
        username : str, optional
            The username who created the note
        chip_id : str, optional
            The chip identifier
        execution_id : str, optional
            The execution identifier
        task_id : str, optional
            The task identifier

        Returns
        -------
        CalibrationNoteModel | None
            The found note or None if not found

        """
        query: dict[str, str] = {}
        if project_id is not None:
            query["project_id"] = project_id
        if username is not None:
            query["username"] = username
        if chip_id is not None:
            query["chip_id"] = chip_id
        if execution_id is not None:
            query["execution_id"] = execution_id
        if task_id is not None:
            query["task_id"] = task_id

        if not query:
            logger.warning("find_one called with no query parameters")
            return None

        doc = CalibrationNoteDocument.find_one(query).run()
        if doc is None:
            return None

        return self._to_model(doc)

    def find_latest_master(
        self,
        *,
        chip_id: str | None = None,
        project_id: str | None = None,
        username: str | None = None,
    ) -> CalibrationNoteModel | None:
        """Find the latest master calibration note for a chip.

        Parameters
        ----------
        chip_id : str, optional
            The chip identifier
        project_id : str, optional
            The project identifier
        username : str, optional
            The username who created the note

        Returns
        -------
        CalibrationNoteModel | None
            The latest master note or None if not found

        """
        query: dict[str, str] = {"task_id": "master"}
        if chip_id is not None:
            query["chip_id"] = chip_id
        if project_id is not None:
            query["project_id"] = project_id
        if username is not None:
            query["username"] = username

        docs = (
            CalibrationNoteDocument.find(query)
            .sort([("timestamp", SortDirection.DESCENDING)])
            .limit(1)
            .run()
        )

        if not docs:
            return None

        return self._to_model(docs[0])

    def find_latest_master_by_project(
        self,
        project_id: str,
    ) -> CalibrationNoteModel | None:
        """Find the latest master calibration note for a project.

        Parameters
        ----------
        project_id : str
            The project identifier

        Returns
        -------
        CalibrationNoteModel | None
            The latest master note or None if not found

        """
        return self.find_latest_master(project_id=project_id)

    def upsert(self, note: CalibrationNoteModel, max_retries: int = 3) -> CalibrationNoteModel:
        """Create or update a calibration note atomically with retry logic.

        Uses MongoDB's find_one_and_update with upsert=True to ensure
        thread-safe operations during parallel calibration task execution.
        Implements retry logic to handle race conditions when multiple
        processes attempt to insert the same document simultaneously.

        Parameters
        ----------
        note : CalibrationNoteModel
            The note to create or update
        max_retries : int
            Maximum number of retry attempts for DuplicateKeyError (default: 3)

        Returns
        -------
        CalibrationNoteModel
            The saved note with updated timestamp

        """
        from pymongo import ReturnDocument

        query = {
            "project_id": note.project_id,
            "execution_id": note.execution_id,
            "task_id": note.task_id,
            "username": note.username,
            "chip_id": note.chip_id,
        }

        timestamp = now()

        # Atomic upsert using find_one_and_update
        # $set: always update these fields
        # $setOnInsert: only set these fields on insert (not on update)
        update = {
            "$set": {
                "note": note.note,
                "timestamp": timestamp,
            },
            "$setOnInsert": {
                "project_id": note.project_id,
                "execution_id": note.execution_id,
                "task_id": note.task_id,
                "username": note.username,
                "chip_id": note.chip_id,
            },
        }

        collection = CalibrationNoteDocument.get_motor_collection()

        last_error: DuplicateKeyError | None = None
        for attempt in range(max_retries):
            try:
                result = collection.find_one_and_update(
                    query,
                    update,
                    upsert=True,
                    return_document=ReturnDocument.AFTER,
                )
                # Convert raw document to CalibrationNoteDocument then to model
                doc = CalibrationNoteDocument.model_validate(result)
                return self._to_model(doc)
            except DuplicateKeyError as e:  # noqa: PERF203
                last_error = e
                logger.warning(
                    "DuplicateKeyError on upsert attempt %d/%d for %s, retrying...",
                    attempt + 1,
                    max_retries,
                    query,
                )
                # Brief sleep with exponential backoff before retry
                time.sleep(0.1 * (2**attempt))

        # All retries exhausted, raise the last error
        logger.error(
            "Failed to upsert calibration note after %d attempts: %s",
            max_retries,
            query,
        )
        raise last_error  # type: ignore[misc]

    def _to_model(self, doc: CalibrationNoteDocument) -> CalibrationNoteModel:
        """Convert a document to a domain model.

        Parameters
        ----------
        doc : CalibrationNoteDocument
            The MongoDB document

        Returns
        -------
        CalibrationNoteModel
            The domain model

        """
        return CalibrationNoteModel(
            project_id=doc.project_id,
            username=doc.username,
            chip_id=doc.chip_id,
            execution_id=doc.execution_id,
            task_id=doc.task_id,
            note=doc.note,
            timestamp=doc.timestamp,
            system_info=doc.system_info,
        )
