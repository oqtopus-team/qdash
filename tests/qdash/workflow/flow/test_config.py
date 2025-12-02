"""Tests for FlowSessionConfig value objects."""

import pytest
from qdash.workflow.flow.config import CalibrationPaths, FlowSessionConfig
from qdash.workflow.flow.github import GitHubPushConfig


class TestFlowSessionConfigCreation:
    """Test FlowSessionConfig creation."""

    def test_create_with_required_fields(self):
        """Test creating config with required fields only."""
        config = FlowSessionConfig(
            username="test_user",
            chip_id="chip_1",
            qids=("0", "1", "2"),
        )

        assert config.username == "test_user"
        assert config.chip_id == "chip_1"
        assert config.qids == ("0", "1", "2")
        assert config.execution_id is None
        assert config.backend == "qubex"
        assert config.name == "Python Flow Execution"
        assert config.tags is None
        assert config.use_lock is True
        assert config.note is None
        assert config.enable_github_pull is False
        assert config.github_push_config is None
        assert config.muxes is None

    def test_create_with_all_fields(self):
        """Test creating config with all fields."""
        github_config = GitHubPushConfig()
        config = FlowSessionConfig(
            username="test_user",
            chip_id="chip_1",
            qids=("0", "1"),
            execution_id="20240101-001",
            backend="fake",
            name="Test Calibration",
            tags=("tag1", "tag2"),
            use_lock=False,
            note={"key": "value"},
            enable_github_pull=True,
            github_push_config=github_config,
            muxes=(0, 1),
        )

        assert config.username == "test_user"
        assert config.chip_id == "chip_1"
        assert config.qids == ("0", "1")
        assert config.execution_id == "20240101-001"
        assert config.backend == "fake"
        assert config.name == "Test Calibration"
        assert config.tags == ("tag1", "tag2")
        assert config.use_lock is False
        assert config.note == {"key": "value"}
        assert config.enable_github_pull is True
        assert config.github_push_config is github_config
        assert config.muxes == (0, 1)

    def test_create_from_lists(self):
        """Test create() factory method converts lists to tuples."""
        config = FlowSessionConfig.create(
            username="test_user",
            chip_id="chip_1",
            qids=["0", "1", "2"],
            tags=["tag1", "tag2"],
            muxes=[0, 1],
        )

        assert config.qids == ("0", "1", "2")
        assert config.tags == ("tag1", "tag2")
        assert config.muxes == (0, 1)


class TestFlowSessionConfigValidation:
    """Test FlowSessionConfig validation."""

    def test_empty_username_raises(self):
        """Test that empty username raises ValueError."""
        with pytest.raises(ValueError, match="username cannot be empty"):
            FlowSessionConfig(
                username="",
                chip_id="chip_1",
                qids=("0",),
            )

    def test_empty_chip_id_raises(self):
        """Test that empty chip_id raises ValueError."""
        with pytest.raises(ValueError, match="chip_id cannot be empty"):
            FlowSessionConfig(
                username="test_user",
                chip_id="",
                qids=("0",),
            )

    def test_empty_qids_raises(self):
        """Test that empty qids raises ValueError."""
        with pytest.raises(ValueError, match="qids cannot be empty"):
            FlowSessionConfig(
                username="test_user",
                chip_id="chip_1",
                qids=(),
            )


class TestFlowSessionConfigImmutability:
    """Test FlowSessionConfig immutability."""

    def test_cannot_modify_fields(self):
        """Test that fields cannot be modified after creation."""
        config = FlowSessionConfig(
            username="test_user",
            chip_id="chip_1",
            qids=("0", "1"),
        )

        with pytest.raises(AttributeError):
            config.username = "new_user"

        with pytest.raises(AttributeError):
            config.qids = ("3", "4")


class TestFlowSessionConfigTransformation:
    """Test FlowSessionConfig transformation methods."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = FlowSessionConfig(
            username="test_user",
            chip_id="chip_1",
            qids=("0", "1"),
            tags=("tag1", "tag2"),
            note={"key": "value"},
            muxes=(0, 1),
        )

        result = config.to_dict()

        assert result["username"] == "test_user"
        assert result["chip_id"] == "chip_1"
        assert result["qids"] == ["0", "1"]  # Converted to list
        assert result["tags"] == ["tag1", "tag2"]  # Converted to list
        assert result["note"] == {"key": "value"}
        assert result["muxes"] == [0, 1]  # Converted to list

    def test_with_execution_id(self):
        """Test creating new config with execution_id."""
        original = FlowSessionConfig(
            username="test_user",
            chip_id="chip_1",
            qids=("0", "1"),
        )

        updated = original.with_execution_id("20240101-001")

        assert updated.execution_id == "20240101-001"
        assert original.execution_id is None  # Original unchanged
        assert updated.username == original.username
        assert updated.chip_id == original.chip_id
        assert updated.qids == original.qids

    def test_with_note_update_new_note(self):
        """Test updating note when note is None."""
        original = FlowSessionConfig(
            username="test_user",
            chip_id="chip_1",
            qids=("0",),
            note=None,
        )

        updated = original.with_note_update("key1", "value1")

        assert updated.note == {"key1": "value1"}
        assert original.note is None  # Original unchanged

    def test_with_note_update_existing_note(self):
        """Test updating existing note."""
        original = FlowSessionConfig(
            username="test_user",
            chip_id="chip_1",
            qids=("0",),
            note={"existing": "value"},
        )

        updated = original.with_note_update("new_key", "new_value")

        assert updated.note == {"existing": "value", "new_key": "new_value"}
        assert original.note == {"existing": "value"}  # Original unchanged


class TestCalibrationPaths:
    """Test CalibrationPaths value object."""

    def test_from_config(self):
        """Test creating paths from config."""
        paths = CalibrationPaths.from_config(
            username="test_user",
            execution_id="20240101-001",
        )

        assert paths.user_path == "/app/calib_data/test_user"
        assert paths.classifier_dir == "/app/calib_data/test_user/.classifier"
        assert paths.calib_data_path == "/app/calib_data/test_user/20240101/001"
        assert paths.task_path == "/app/calib_data/test_user/20240101/001/task"
        assert paths.fig_path == "/app/calib_data/test_user/20240101/001/fig"
        assert paths.calib_path == "/app/calib_data/test_user/20240101/001/calib"
        assert paths.calib_note_path == "/app/calib_data/test_user/20240101/001/calib_note"

    def test_immutability(self):
        """Test CalibrationPaths is immutable."""
        paths = CalibrationPaths.from_config(
            username="test_user",
            execution_id="20240101-001",
        )

        with pytest.raises(AttributeError):
            paths.user_path = "/new/path"
