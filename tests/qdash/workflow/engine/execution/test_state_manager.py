"""Tests for ExecutionStateManager."""

from qdash.datamodel.execution import ExecutionStatusModel
from qdash.datamodel.task import CalibDataModel, ParameterModel
from qdash.workflow.engine.execution.state_manager import (
    ExecutionStateManager,
)


class TestExecutionStateManagerInit:
    """Test ExecutionStateManager initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        manager = ExecutionStateManager(
            execution_id="exec-001",
        )

        assert manager.execution_id == "exec-001"
        assert manager.status == ExecutionStatusModel.SCHEDULED
        assert manager.calib_data.qubit == {}
        assert manager.calib_data.coupling == {}

    def test_init_with_all_fields(self):
        """Test initialization with all fields provided."""
        manager = ExecutionStateManager(
            username="test_user",
            name="Test Execution",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            note={"key": "value"},
            tags=["tag1", "tag2"],
            chip_id="chip-001",
        )

        assert manager.username == "test_user"
        assert manager.name == "Test Execution"
        assert manager.execution_id == "exec-001"
        assert manager.calib_data_path == "/tmp/calib"
        # note is converted to ExecutionNote, dict values go to .extra
        assert manager.note.extra == {"key": "value"}
        assert manager.tags == ["tag1", "tag2"]
        assert manager.chip_id == "chip-001"


class TestExecutionLifecycle:
    """Test execution lifecycle transitions."""

    def test_start_sets_running_status(self):
        """Test start() sets status to RUNNING."""
        manager = ExecutionStateManager(execution_id="exec-001")

        result = manager.start()

        assert result is manager  # Returns self for chaining
        assert manager.status == ExecutionStatusModel.RUNNING
        assert manager.start_at != ""

    def test_complete_sets_completed_status(self):
        """Test complete() sets status to COMPLETED."""
        manager = ExecutionStateManager(execution_id="exec-001")
        manager.start()

        result = manager.complete()

        assert result is manager
        assert manager.status == ExecutionStatusModel.COMPLETED
        assert manager.end_at != ""
        assert manager.elapsed_time != ""

    def test_fail_sets_failed_status(self):
        """Test fail() sets status to FAILED."""
        manager = ExecutionStateManager(execution_id="exec-001")
        manager.start()

        result = manager.fail()

        assert result is manager
        assert manager.status == ExecutionStatusModel.FAILED
        assert manager.end_at != ""
        assert manager.elapsed_time != ""

    def test_update_status_changes_status(self):
        """Test update_status() changes status to specified value."""
        manager = ExecutionStateManager(execution_id="exec-001")

        manager.update_status(ExecutionStatusModel.RUNNING)
        assert manager.status == ExecutionStatusModel.RUNNING

        manager.update_status(ExecutionStatusModel.COMPLETED)
        assert manager.status == ExecutionStatusModel.COMPLETED


class TestCalibDataMerging:
    """Test calibration data merging functionality."""

    def test_merge_calib_data_adds_qubit_data(self):
        """Test merging qubit calibration data."""
        manager = ExecutionStateManager(execution_id="exec-001")
        calib_data = CalibDataModel(
            qubit={"0": {"freq": ParameterModel(value=5.0)}},
            coupling={},
        )

        manager.merge_calib_data(calib_data)

        assert "0" in manager.calib_data.qubit
        assert "freq" in manager.calib_data.qubit["0"]

    def test_merge_calib_data_adds_coupling_data(self):
        """Test merging coupling calibration data."""
        manager = ExecutionStateManager(execution_id="exec-001")
        calib_data = CalibDataModel(
            qubit={},
            coupling={"0-1": {"cr_amp": ParameterModel(value=0.5)}},
        )

        manager.merge_calib_data(calib_data)

        assert "0-1" in manager.calib_data.coupling
        assert "cr_amp" in manager.calib_data.coupling["0-1"]

    def test_merge_calib_data_updates_existing(self):
        """Test merging updates existing calibration data."""
        manager = ExecutionStateManager(execution_id="exec-001")

        # First merge
        calib_data1 = CalibDataModel(
            qubit={"0": {"freq": ParameterModel(value=5.0)}},
            coupling={},
        )
        manager.merge_calib_data(calib_data1)

        # Second merge - same qid, different param
        calib_data2 = CalibDataModel(
            qubit={"0": {"t1": ParameterModel(value=100.0)}},
            coupling={},
        )
        manager.merge_calib_data(calib_data2)

        assert "freq" in manager.calib_data.qubit["0"]
        assert "t1" in manager.calib_data.qubit["0"]


class TestDatamodelConversion:
    """Test conversion to/from ExecutionModel."""

    def test_to_datamodel_returns_execution_model(self):
        """Test converting to ExecutionModel."""
        manager = ExecutionStateManager(
            username="test_user",
            name="Test Execution",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            chip_id="chip-001",
        )

        model = manager.to_datamodel()

        assert model.username == "test_user"
        assert model.name == "Test Execution"
        assert model.execution_id == "exec-001"
        assert model.calib_data_path == "/tmp/calib"
        assert model.chip_id == "chip-001"

    def test_from_datamodel_creates_manager(self):
        """Test creating manager from ExecutionModel."""
        from qdash.datamodel.execution import ExecutionModel

        model = ExecutionModel(
            username="test_user",
            name="Test Execution",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            chip_id="chip-001",
            note={},
            status=ExecutionStatusModel.RUNNING,
            tags=[],
            start_at=None,
            end_at=None,
            elapsed_time=None,
            message="",
            system_info={},
        )

        manager = ExecutionStateManager.from_datamodel(model)

        assert manager.username == "test_user"
        assert manager.name == "Test Execution"
        assert manager.execution_id == "exec-001"
        assert manager.status == ExecutionStatusModel.RUNNING


class TestParameterRetrieval:
    """Test parameter retrieval methods."""

    def test_get_qubit_parameter_found(self):
        """Test getting an existing qubit parameter."""
        manager = ExecutionStateManager(execution_id="exec-001")
        calib_data = CalibDataModel(
            qubit={"0": {"freq": ParameterModel(value=5.0)}},
            coupling={},
        )
        manager.merge_calib_data(calib_data)

        result = manager.get_qubit_parameter("0", "freq")
        assert result == 5.0

    def test_get_qubit_parameter_not_found(self):
        """Test getting a non-existent qubit parameter."""
        manager = ExecutionStateManager(execution_id="exec-001")

        result = manager.get_qubit_parameter("0", "freq")
        assert result is None

    def test_get_qubit_parameter_unknown_qid(self):
        """Test getting parameter for unknown qubit."""
        manager = ExecutionStateManager(execution_id="exec-001")
        calib_data = CalibDataModel(
            qubit={"0": {"freq": ParameterModel(value=5.0)}},
            coupling={},
        )
        manager.merge_calib_data(calib_data)

        result = manager.get_qubit_parameter("1", "freq")
        assert result is None

    def test_get_coupling_parameter_found(self):
        """Test getting an existing coupling parameter."""
        manager = ExecutionStateManager(execution_id="exec-001")
        calib_data = CalibDataModel(
            qubit={},
            coupling={"0-1": {"cr_amp": ParameterModel(value=0.5)}},
        )
        manager.merge_calib_data(calib_data)

        result = manager.get_coupling_parameter("0-1", "cr_amp")
        assert result == 0.5

    def test_get_coupling_parameter_not_found(self):
        """Test getting a non-existent coupling parameter."""
        manager = ExecutionStateManager(execution_id="exec-001")

        result = manager.get_coupling_parameter("0-1", "cr_amp")
        assert result is None


# Note: TestElapsedTimeCalculation tests were removed as elapsed time calculation
# was moved to datetime_utils.calculate_elapsed_time()
