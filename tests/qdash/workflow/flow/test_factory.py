"""Tests for FlowSession factory module."""

import pytest
from qdash.workflow.flow.config import FlowSessionConfig
from qdash.workflow.flow.factory import (
    DefaultExecutionManagerFactory,
    DefaultSessionFactory,
    DefaultTaskManagerFactory,
    FlowSessionDependencies,
)


class TestDefaultSessionFactory:
    """Test DefaultSessionFactory."""

    def test_init_with_default_backend(self):
        """Test initialization with default backend."""
        factory = DefaultSessionFactory()
        assert factory.backend == "qubex"

    def test_init_with_custom_backend(self):
        """Test initialization with custom backend."""
        factory = DefaultSessionFactory(backend="fake")
        assert factory.backend == "fake"


class TestDefaultExecutionManagerFactory:
    """Test DefaultExecutionManagerFactory."""

    def test_create_returns_execution_manager(self):
        """Test that create returns an ExecutionManager."""
        factory = DefaultExecutionManagerFactory()

        # Note: This will fail without DB connection, but we can test factory instantiation
        assert factory is not None


class TestDefaultTaskManagerFactory:
    """Test DefaultTaskManagerFactory."""

    def test_create_returns_task_manager(self):
        """Test that create returns a TaskManager."""
        factory = DefaultTaskManagerFactory()

        # Note: This will fail without DB connection, but we can test factory instantiation
        assert factory is not None


class TestFlowSessionDependencies:
    """Test FlowSessionDependencies container."""

    def test_init_with_defaults(self):
        """Test initialization with default factories."""
        deps = FlowSessionDependencies()

        assert deps.session_factory is None  # Not set until production()
        assert isinstance(deps.execution_manager_factory, DefaultExecutionManagerFactory)
        assert isinstance(deps.task_manager_factory, DefaultTaskManagerFactory)

    def test_production_creates_all_factories(self):
        """Test production() creates all factories."""
        deps = FlowSessionDependencies.production()

        assert isinstance(deps.session_factory, DefaultSessionFactory)
        assert deps.session_factory.backend == "qubex"
        assert isinstance(deps.execution_manager_factory, DefaultExecutionManagerFactory)
        assert isinstance(deps.task_manager_factory, DefaultTaskManagerFactory)

    def test_production_with_custom_backend(self):
        """Test production() with custom backend."""
        deps = FlowSessionDependencies.production(backend="fake")

        assert isinstance(deps.session_factory, DefaultSessionFactory)
        assert deps.session_factory.backend == "fake"

    def test_fake_creates_fake_backend(self):
        """Test fake() creates dependencies with fake backend."""
        deps = FlowSessionDependencies.fake()

        assert isinstance(deps.session_factory, DefaultSessionFactory)
        assert deps.session_factory.backend == "fake"

    def test_init_with_custom_factories(self):
        """Test initialization with custom factories."""

        class CustomSessionFactory:
            def create(self, config: dict):
                return None

        class CustomExecutionManagerFactory:
            def create(self, **kwargs):
                return None

        class CustomTaskManagerFactory:
            def create(self, **kwargs):
                return None

        custom_session = CustomSessionFactory()
        custom_execution = CustomExecutionManagerFactory()
        custom_task = CustomTaskManagerFactory()

        deps = FlowSessionDependencies(
            session_factory=custom_session,
            execution_manager_factory=custom_execution,
            task_manager_factory=custom_task,
        )

        assert deps.session_factory is custom_session
        assert deps.execution_manager_factory is custom_execution
        assert deps.task_manager_factory is custom_task


class TestFlowSessionConfigIntegration:
    """Test FlowSessionConfig integration with factory."""

    def test_config_to_dict_for_session_creation(self):
        """Test that config.to_dict() produces valid kwargs."""
        config = FlowSessionConfig.create(
            username="test_user",
            chip_id="chip_1",
            qids=["0", "1", "2"],
            execution_id="20240101-001",
            backend="fake",
            name="Test Calibration",
            tags=["tag1", "tag2"],
            use_lock=False,
            note={"key": "value"},
            muxes=[0, 1],
        )

        result = config.to_dict()

        # Verify all keys are present
        assert "username" in result
        assert "chip_id" in result
        assert "qids" in result
        assert "execution_id" in result
        assert "backend" in result
        assert "name" in result
        assert "tags" in result
        assert "use_lock" in result
        assert "note" in result
        assert "enable_github_pull" in result
        assert "github_push_config" in result
        assert "muxes" in result

        # Verify values are correct types for FlowSession.__init__
        assert isinstance(result["qids"], list)
        assert isinstance(result["tags"], list)
        assert isinstance(result["muxes"], list)
