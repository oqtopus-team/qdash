"""In-memory implementation of CalibrationNoteRepository for testing.

This module provides a mock implementation that stores data in memory,
useful for unit testing without requiring a MongoDB instance.
"""

import pendulum
from qdash.datamodel.calibration_note import CalibrationNoteModel


class InMemoryCalibrationNoteRepository:
    """In-memory implementation of CalibrationNoteRepository for testing.

    This implementation stores calibration notes in a dictionary, making it
    suitable for unit tests that don't require a real database.

    Example
    -------
        >>> repo = InMemoryCalibrationNoteRepository()
        >>> note = CalibrationNoteModel(
        ...     project_id="proj-1",
        ...     username="alice",
        ...     chip_id="64Qv3",
        ...     execution_id="20240101-001",
        ...     task_id="master",
        ...     note={"key": "value"},
        ... )
        >>> saved = repo.upsert(note)
        >>> found = repo.find_one(chip_id="64Qv3", task_id="master")
        >>> assert found.note == {"key": "value"}

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._notes: dict[str, CalibrationNoteModel] = {}

    def _make_key(
        self,
        project_id: str,
        username: str,
        chip_id: str,
        execution_id: str,
        task_id: str,
    ) -> str:
        """Create a unique key for storage."""
        return f"{project_id}:{username}:{chip_id}:{execution_id}:{task_id}"

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
        for note in self._notes.values():
            match = True
            if project_id is not None and note.project_id != project_id:
                match = False
            if username is not None and note.username != username:
                match = False
            if chip_id is not None and note.chip_id != chip_id:
                match = False
            if execution_id is not None and note.execution_id != execution_id:
                match = False
            if task_id is not None and note.task_id != task_id:
                match = False
            if match:
                return note
        return None

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
        candidates = []
        for note in self._notes.values():
            if chip_id is not None and note.chip_id != chip_id:
                continue
            if note.task_id != "master":
                continue
            if project_id is not None and note.project_id != project_id:
                continue
            if username is not None and note.username != username:
                continue
            candidates.append(note)

        if not candidates:
            return None

        # Sort by timestamp descending and return the first
        candidates.sort(key=lambda n: n.timestamp or "", reverse=True)
        return candidates[0]

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
        key = self._make_key(
            note.project_id,
            note.username,
            note.chip_id,
            note.execution_id,
            note.task_id,
        )

        timestamp = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
        updated_note = CalibrationNoteModel(
            project_id=note.project_id,
            username=note.username,
            chip_id=note.chip_id,
            execution_id=note.execution_id,
            task_id=note.task_id,
            note=note.note,
            timestamp=timestamp,
            system_info=note.system_info,
        )

        self._notes[key] = updated_note
        return updated_note

    def clear(self) -> None:
        """Clear all stored notes (useful for test setup/teardown)."""
        self._notes.clear()
