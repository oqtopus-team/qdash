"""Calibration service for QDash API.

This module provides the business logic for calibration operations,
using repository abstractions for data access.
"""

from qdash.api.schemas.calibration import CalibrationNoteResponse
from qdash.repository.calibration_note import MongoCalibrationNoteRepository
from qdash.repository.protocols import CalibrationNoteRepository


class CalibrationService:
    """Service for calibration operations.

    This service encapsulates the business logic for calibration,
    delegating data access to repository implementations.

    Example
    -------
        >>> repo = MongoCalibrationNoteRepository()
        >>> service = CalibrationService(repo)
        >>> note = service.get_latest_note("project-1")

    """

    def __init__(
        self,
        calibration_note_repository: CalibrationNoteRepository,
    ) -> None:
        """Initialize the calibration service.

        Parameters
        ----------
        calibration_note_repository : CalibrationNoteRepository
            Repository for calibration note operations

        """
        self._calibration_note_repo = calibration_note_repository

    def get_latest_note(self, project_id: str) -> CalibrationNoteResponse | None:
        """Get the latest calibration note for a project.

        Parameters
        ----------
        project_id : str
            The project identifier

        Returns
        -------
        CalibrationNoteResponse | None
            The latest calibration note or None if not found

        """
        note = self._calibration_note_repo.find_latest_master_by_project(project_id)
        if note is None:
            return None

        return CalibrationNoteResponse(
            username=note.username,
            execution_id=note.execution_id,
            task_id=note.task_id,
            note=note.note,
            timestamp=note.timestamp or "",
        )
