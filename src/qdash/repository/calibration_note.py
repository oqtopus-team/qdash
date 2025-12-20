"""MongoDB implementation of CalibrationNoteRepository.

This module provides the concrete MongoDB implementation for calibration note
persistence operations. Used by both API and workflow components.
"""

import logging
from typing import Any

import pendulum
from bunnet import SortDirection

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

    def upsert(self, note: CalibrationNoteModel) -> CalibrationNoteModel:
        """Create or update a calibration note.

        Parameters
        ----------
        note : CalibrationNoteModel
            The note to create or update

        Returns
        -------
        CalibrationNoteModel
            The saved note with updated timestamp

        """
        query = {
            "project_id": note.project_id,
            "execution_id": note.execution_id,
            "task_id": note.task_id,
            "username": note.username,
            "chip_id": note.chip_id,
        }

        doc = CalibrationNoteDocument.find_one(query).run()
        timestamp = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()

        if doc is None:
            # Create new document
            doc = CalibrationNoteDocument(
                project_id=note.project_id,
                username=note.username,
                chip_id=note.chip_id,
                execution_id=note.execution_id,
                task_id=note.task_id,
                note=note.note,
                timestamp=timestamp,
            )
            doc.save()
        else:
            # Update existing document
            doc.note = note.note
            doc.timestamp = timestamp
            doc.save()

        return self._to_model(doc)

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
