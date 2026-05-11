"""Tests for CalibrationNoteRepository implementations.

This module tests both the in-memory implementation (for unit tests)
and verifies the protocol interface.
"""

from typing import Any

import pytest
from qdash.datamodel.calibration_note import CalibrationNoteModel
from qdash.dbmodel.calibration_note import CalibrationNoteDocument
from qdash.repository.calibration_note import MongoCalibrationNoteRepository
from qdash.repository.inmemory import InMemoryCalibrationNoteRepository
from qdash.repository.protocols import CalibrationNoteRepository


class RecordingCollection:
    """Capture MongoDB updates and fail on conflicting update operators."""

    def __init__(self) -> None:
        self.update: dict[str, Any] | None = None

    def find_one_and_update(
        self, query: dict[str, Any], update: dict[str, Any], **kwargs: object
    ) -> dict[str, Any]:
        self.update = update
        set_fields = set(update.get("$set", {}))
        set_on_insert_fields = set(update.get("$setOnInsert", {}))
        assert set_fields.isdisjoint(set_on_insert_fields)

        return {
            **query,
            **update.get("$setOnInsert", {}),
            **update.get("$set", {}),
            "version": update.get("$inc", {}).get("version", 0),
        }


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

    def test_upsert_on_insert_preserves_existing_note(
        self, repo: InMemoryCalibrationNoteRepository, sample_note: CalibrationNoteModel
    ) -> None:
        """Test insert-only upsert does not replace existing note."""
        repo.upsert(sample_note)
        stale_note = CalibrationNoteModel(
            project_id=sample_note.project_id,
            username=sample_note.username,
            chip_id=sample_note.chip_id,
            execution_id=sample_note.execution_id,
            task_id=sample_note.task_id,
            note={},
        )

        result = repo.upsert_on_insert(stale_note)

        assert result.note == sample_note.note

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


class TestMongoCalibrationNoteRepository:
    """Test MongoDB-specific update document construction."""

    def test_upsert_does_not_set_user_id_in_conflicting_operators(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MongoDB rejects the same path in $set and $setOnInsert."""
        collection = RecordingCollection()
        monkeypatch.setattr(
            CalibrationNoteDocument,
            "get_motor_collection",
            classmethod(lambda cls: collection),
        )
        monkeypatch.setattr(
            MongoCalibrationNoteRepository,
            "_user_id_for_username",
            staticmethod(lambda username: "usr_alice"),
        )

        repo = MongoCalibrationNoteRepository()
        result = repo.upsert(
            CalibrationNoteModel(
                project_id="project-1",
                username="alice",
                chip_id="64Qv3",
                execution_id="20240101-001",
                task_id="master",
                note={"qubit_0": {"frequency": 5.0}},
            )
        )

        assert result.user_id == "usr_alice"
        assert collection.update is not None
        assert collection.update["$set"]["user_id"] == "usr_alice"
        assert "user_id" not in collection.update["$setOnInsert"]

    def test_upsert_on_insert_does_not_replace_existing_note(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Parallel worker initialization must not overwrite merged note fields."""
        collection = RecordingCollection()
        monkeypatch.setattr(
            CalibrationNoteDocument,
            "get_motor_collection",
            classmethod(lambda cls: collection),
        )
        monkeypatch.setattr(
            MongoCalibrationNoteRepository,
            "_user_id_for_username",
            staticmethod(lambda username: "usr_alice"),
        )

        repo = MongoCalibrationNoteRepository()
        repo.upsert_on_insert(
            CalibrationNoteModel(
                project_id="project-1",
                username="alice",
                chip_id="64Qv3",
                execution_id="20240101-001",
                task_id="master",
                note={"rabi_params": {"Q00": {"amplitude": 0.1}}},
            )
        )

        assert collection.update is not None
        assert "note" not in collection.update["$set"]
        assert collection.update["$setOnInsert"]["note"] == {
            "rabi_params": {"Q00": {"amplitude": 0.1}}
        }

    def test_document_upsert_note_does_not_set_user_id_in_conflicting_operators(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Keep legacy document helper compatible with MongoDB upsert rules."""
        collection = RecordingCollection()
        monkeypatch.setattr(
            CalibrationNoteDocument,
            "get_motor_collection",
            classmethod(lambda cls: collection),
        )
        monkeypatch.setattr(
            CalibrationNoteDocument,
            "_user_id_for_username",
            staticmethod(lambda username: "usr_alice"),
        )

        result = CalibrationNoteDocument.upsert_note(
            username="alice",
            chip_id="64Qv3",
            execution_id="20240101-001",
            task_id="master",
            note={"qubit_0": {"frequency": 5.0}},
            project_id="project-1",
        )

        assert result.user_id == "usr_alice"
        assert collection.update is not None
        assert collection.update["$set"]["user_id"] == "usr_alice"
        assert "user_id" not in collection.update["$setOnInsert"]
