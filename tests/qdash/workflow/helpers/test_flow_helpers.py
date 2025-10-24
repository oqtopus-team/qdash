"""Tests for Python Flow helpers.

These tests verify the FlowSession API and helper functions for custom calibration flows.
"""

import pytest

from qdash.workflow.helpers.flow_helpers import (
    FlowSession,
    finish_calibration,
    get_session,
    init_calibration,
)


class TestFlowSessionInitialization:
    """Test FlowSession initialization and basic setup."""

    def test_flow_session_attributes(self, monkeypatch):
        """Test that FlowSession initializes with correct attributes."""

        # Mock ExecutionManager and session to avoid DB dependencies
        class MockExecutionManager:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)
                self.calib_data_path = kwargs.get("calib_data_path", "")
                self.calib_data = type("obj", (object,), {"qubit": {}, "coupling": {}})()

            def save(self):
                return self

            def start_execution(self):
                return self

            def complete_execution(self):
                return self

        class MockSession:
            def __init__(self, *args, **kwargs):
                pass

            def connect(self):
                pass

        # Patch the imports
        monkeypatch.setattr(
            "qdash.workflow.helpers.flow_helpers.ExecutionManager",
            MockExecutionManager,
        )
        monkeypatch.setattr(
            "qdash.workflow.helpers.flow_helpers.create_session",
            lambda **kwargs: MockSession(),
        )

        # Create session
        session = FlowSession(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
            backend="fake",
        )

        # Verify attributes
        assert session.username == "test_user"
        assert session.execution_id == "20240101-001"
        assert session.chip_id == "chip_1"
        assert session.backend == "fake"
        assert session.execution_manager is not None
        assert session.session is not None

    def test_flow_session_default_tags(self, monkeypatch):
        """Test that default tags are set correctly."""

        class MockExecutionManager:
            def __init__(self, **kwargs):
                self.tags = kwargs.get("tags", [])
                self.calib_data_path = kwargs.get("calib_data_path", "")
                self.calib_data = type("obj", (object,), {"qubit": {}, "coupling": {}})()

            def save(self):
                return self

            def start_execution(self):
                return self

        class MockSession:
            def __init__(self, *args, **kwargs):
                pass

            def connect(self):
                pass

        monkeypatch.setattr(
            "qdash.workflow.helpers.flow_helpers.ExecutionManager",
            MockExecutionManager,
        )
        monkeypatch.setattr(
            "qdash.workflow.helpers.flow_helpers.create_session",
            lambda **kwargs: MockSession(),
        )

        session = FlowSession(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
        )

        assert "python_flow" in session.execution_manager.tags


class TestFlowSessionParameterManagement:
    """Test parameter get/set operations."""

    def test_set_and_get_parameter(self, monkeypatch):
        """Test setting and getting parameters."""

        class MockExecutionManager:
            def __init__(self, **kwargs):
                self.calib_data_path = kwargs.get("calib_data_path", "")
                self.calib_data = type("obj", (object,), {"qubit": {}, "coupling": {}})()

            def save(self):
                return self

            def start_execution(self):
                return self

        class MockSession:
            def __init__(self, *args, **kwargs):
                pass

            def connect(self):
                pass

        monkeypatch.setattr(
            "qdash.workflow.helpers.flow_helpers.ExecutionManager",
            MockExecutionManager,
        )
        monkeypatch.setattr(
            "qdash.workflow.helpers.flow_helpers.create_session",
            lambda **kwargs: MockSession(),
        )

        session = FlowSession(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
        )

        # Set parameter
        session.set_parameter("0", "qubit_frequency", 5.0)

        # Get parameter
        freq = session.get_parameter("0", "qubit_frequency")
        assert freq == 5.0

    def test_get_nonexistent_parameter(self, monkeypatch):
        """Test getting a parameter that doesn't exist."""

        class MockExecutionManager:
            def __init__(self, **kwargs):
                self.calib_data_path = kwargs.get("calib_data_path", "")
                self.calib_data = type("obj", (object,), {"qubit": {}, "coupling": {}})()

            def save(self):
                return self

            def start_execution(self):
                return self

        class MockSession:
            def __init__(self, *args, **kwargs):
                pass

            def connect(self):
                pass

        monkeypatch.setattr(
            "qdash.workflow.helpers.flow_helpers.ExecutionManager",
            MockExecutionManager,
        )
        monkeypatch.setattr(
            "qdash.workflow.helpers.flow_helpers.create_session",
            lambda **kwargs: MockSession(),
        )

        session = FlowSession(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
        )

        # Get nonexistent parameter
        result = session.get_parameter("0", "nonexistent")
        assert result is None


class TestGlobalSessionHelpers:
    """Test global session helper functions."""

    def test_init_and_get_session(self, monkeypatch):
        """Test init_calibration and get_session."""

        class MockExecutionManager:
            def __init__(self, **kwargs):
                self.calib_data_path = kwargs.get("calib_data_path", "")
                self.calib_data = type("obj", (object,), {"qubit": {}, "coupling": {}})()

            def save(self):
                return self

            def start_execution(self):
                return self

        class MockSession:
            def __init__(self, *args, **kwargs):
                pass

            def connect(self):
                pass

        monkeypatch.setattr(
            "qdash.workflow.helpers.flow_helpers.ExecutionManager",
            MockExecutionManager,
        )
        monkeypatch.setattr(
            "qdash.workflow.helpers.flow_helpers.create_session",
            lambda **kwargs: MockSession(),
        )

        # Initialize session
        session1 = init_calibration(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
        )

        # Get session
        session2 = get_session()

        assert session1 is session2

    def test_get_session_without_init(self):
        """Test that get_session raises error when no session exists."""
        # Reset global session
        import qdash.workflow.helpers.flow_helpers as flow_helpers

        flow_helpers._current_session = None

        with pytest.raises(RuntimeError, match="No active calibration session"):
            get_session()

    def test_finish_calibration(self, monkeypatch):
        """Test finish_calibration helper."""

        class MockExecutionManager:
            def __init__(self, **kwargs):
                self.calib_data_path = kwargs.get("calib_data_path", "")
                self.calib_data = type("obj", (object,), {"qubit": {}, "coupling": {}})()
                self.completed = False

            def save(self):
                return self

            def start_execution(self):
                return self

            def complete_execution(self):
                self.completed = True
                return self

        class MockSession:
            def __init__(self, *args, **kwargs):
                pass

            def connect(self):
                pass

        monkeypatch.setattr(
            "qdash.workflow.helpers.flow_helpers.ExecutionManager",
            MockExecutionManager,
        )
        monkeypatch.setattr(
            "qdash.workflow.helpers.flow_helpers.create_session",
            lambda **kwargs: MockSession(),
        )

        # Initialize and finish
        session = init_calibration(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
        )

        finish_calibration()

        assert session.execution_manager.completed is True


class TestHelperFunctionSignatures:
    """Test that helper functions have correct signatures."""

    def test_calibrate_qubits_parallel_signature(self):
        """Test calibrate_qubits_parallel has correct signature."""
        from inspect import signature

        from qdash.workflow.helpers.flow_helpers import calibrate_qubits_parallel

        sig = signature(calibrate_qubits_parallel)
        params = list(sig.parameters.keys())

        assert "qids" in params
        assert "tasks" in params
        assert "task_details" in params

    def test_calibrate_qubits_serial_signature(self):
        """Test calibrate_qubits_serial has correct signature."""
        from inspect import signature

        from qdash.workflow.helpers.flow_helpers import calibrate_qubits_serial

        sig = signature(calibrate_qubits_serial)
        params = list(sig.parameters.keys())

        assert "qids" in params
        assert "tasks" in params
        assert "task_details" in params

    def test_adaptive_calibrate_signature(self):
        """Test adaptive_calibrate has correct signature."""
        from inspect import signature

        from qdash.workflow.helpers.flow_helpers import adaptive_calibrate

        sig = signature(adaptive_calibrate)
        params = list(sig.parameters.keys())

        assert "qid" in params
        assert "measure_func" in params
        assert "update_func" in params
        assert "converge_func" in params
        assert "max_iterations" in params
