"""Tests for CalibrationNoteRepository implementations.

This module tests both the in-memory implementation (for unit tests)
and verifies the protocol interface.
"""

import pytest
from qdash.datamodel.calibration_note import CalibrationNoteModel
from qdash.repository.inmemory import InMemoryCalibrationNoteRepository
from qdash.repository.protocols import CalibrationNoteRepository


class TestInMemoryCalibrationNoteRepository:
    """Test InMemoryCalibrationNoteRepository."""

    @pytest.fixture
    def repo(self) -> InMemoryCalibrationNoteRepository:
        """Create a fresh repository for each test."""
        return InMemoryCalibrationNoteRepository()

    @pytest.fixture
    def sample_note(self) -> CalibrationNoteModel:
        """Create a sample note for testing."""
        return CalibrationNoteModel(
            project_id="project-1",
            username="alice",
            chip_id="64Qv3",
            execution_id="20240101-001",
            task_id="master",
            note={"qubit_0": {"frequency": 5.0}},
        )

    def test_implements_protocol(self, repo: InMemoryCalibrationNoteRepository) -> None:
        """Test that InMemoryCalibrationNoteRepository implements the protocol."""
        assert isinstance(repo, CalibrationNoteRepository)

    def test_upsert_creates_new_note(
        self, repo: InMemoryCalibrationNoteRepository, sample_note: CalibrationNoteModel
    ) -> None:
        """Test upsert creates a new note when it doesn't exist."""
        result = repo.upsert(sample_note)

        assert result.project_id == sample_note.project_id
        assert result.username == sample_note.username
        assert result.chip_id == sample_note.chip_id
        assert result.note == sample_note.note
        assert result.timestamp is not None

    def test_upsert_updates_existing_note(
        self, repo: InMemoryCalibrationNoteRepository, sample_note: CalibrationNoteModel
    ) -> None:
        """Test upsert updates an existing note."""
        # First insert
        repo.upsert(sample_note)

        # Update with new note content
        updated_note = CalibrationNoteModel(
            project_id=sample_note.project_id,
            username=sample_note.username,
            chip_id=sample_note.chip_id,
            execution_id=sample_note.execution_id,
            task_id=sample_note.task_id,
            note={"qubit_0": {"frequency": 6.0}},
        )
        result = repo.upsert(updated_note)

        assert result.note == {"qubit_0": {"frequency": 6.0}}

    def test_find_one_returns_matching_note(
        self, repo: InMemoryCalibrationNoteRepository, sample_note: CalibrationNoteModel
    ) -> None:
        """Test find_one returns the matching note."""
        repo.upsert(sample_note)

        result = repo.find_one(
            project_id="project-1",
            username="alice",
            chip_id="64Qv3",
            task_id="master",
        )

        assert result is not None
        assert result.note == sample_note.note

    def test_find_one_returns_none_when_not_found(
        self, repo: InMemoryCalibrationNoteRepository
    ) -> None:
        """Test find_one returns None when note doesn't exist."""
        result = repo.find_one(
            project_id="nonexistent",
            chip_id="nonexistent",
        )

        assert result is None

    def test_find_one_with_partial_query(
        self, repo: InMemoryCalibrationNoteRepository, sample_note: CalibrationNoteModel
    ) -> None:
        """Test find_one works with partial query parameters."""
        repo.upsert(sample_note)

        result = repo.find_one(chip_id="64Qv3", task_id="master")

        assert result is not None
        assert result.username == "alice"

    def test_find_latest_master_returns_most_recent(
        self, repo: InMemoryCalibrationNoteRepository
    ) -> None:
        """Test find_latest_master returns the most recent master note."""
        # Create two master notes
        note1 = CalibrationNoteModel(
            project_id="project-1",
            username="alice",
            chip_id="64Qv3",
            execution_id="20240101-001",
            task_id="master",
            note={"version": 1},
        )
        note2 = CalibrationNoteModel(
            project_id="project-1",
            username="alice",
            chip_id="64Qv3",
            execution_id="20240101-002",
            task_id="master",
            note={"version": 2},
        )

        repo.upsert(note1)
        # Small delay to ensure different timestamps
        import time

        time.sleep(0.01)
        repo.upsert(note2)

        result = repo.find_latest_master(chip_id="64Qv3")

        assert result is not None
        assert result.note == {"version": 2}

    def test_find_latest_master_returns_none_when_no_master(
        self, repo: InMemoryCalibrationNoteRepository
    ) -> None:
        """Test find_latest_master returns None when no master note exists."""
        # Create a non-master note
        note = CalibrationNoteModel(
            project_id="project-1",
            username="alice",
            chip_id="64Qv3",
            execution_id="20240101-001",
            task_id="task-1",  # Not "master"
            note={"key": "value"},
        )
        repo.upsert(note)

        result = repo.find_latest_master(chip_id="64Qv3")

        assert result is None

    def test_find_latest_master_filters_by_project(
        self, repo: InMemoryCalibrationNoteRepository
    ) -> None:
        """Test find_latest_master filters by project_id when provided."""
        note1 = CalibrationNoteModel(
            project_id="project-1",
            username="alice",
            chip_id="64Qv3",
            execution_id="20240101-001",
            task_id="master",
            note={"project": 1},
        )
        note2 = CalibrationNoteModel(
            project_id="project-2",
            username="alice",
            chip_id="64Qv3",
            execution_id="20240101-001",
            task_id="master",
            note={"project": 2},
        )

        repo.upsert(note1)
        repo.upsert(note2)

        result = repo.find_latest_master(chip_id="64Qv3", project_id="project-1")

        assert result is not None
        assert result.note == {"project": 1}

    def test_find_latest_master_filters_by_username(
        self, repo: InMemoryCalibrationNoteRepository
    ) -> None:
        """Test find_latest_master filters by username when provided."""
        note1 = CalibrationNoteModel(
            project_id="project-1",
            username="alice",
            chip_id="64Qv3",
            execution_id="20240101-001",
            task_id="master",
            note={"user": "alice"},
        )
        note2 = CalibrationNoteModel(
            project_id="project-1",
            username="bob",
            chip_id="64Qv3",
            execution_id="20240101-001",
            task_id="master",
            note={"user": "bob"},
        )

        repo.upsert(note1)
        repo.upsert(note2)

        result = repo.find_latest_master(chip_id="64Qv3", username="bob")

        assert result is not None
        assert result.note == {"user": "bob"}

    def test_clear_removes_all_notes(
        self, repo: InMemoryCalibrationNoteRepository, sample_note: CalibrationNoteModel
    ) -> None:
        """Test clear removes all stored notes."""
        repo.upsert(sample_note)
        assert repo.find_one(chip_id="64Qv3") is not None

        repo.clear()

        assert repo.find_one(chip_id="64Qv3") is None
