"""FlowSession factory for dependency injection.

This module provides factory functions and classes for creating FlowSession
instances with proper dependency injection, enabling both production and
test configurations.
"""

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from qdash.workflow.engine.calibration.execution.manager import ExecutionManager
from qdash.workflow.engine.calibration.task.manager import TaskManager
from qdash.workflow.engine.session.factory import create_session
from qdash.workflow.flow.config import FlowSessionConfig

if TYPE_CHECKING:
    from qdash.workflow.flow.session import FlowSession


@runtime_checkable
class SessionFactory(Protocol):
    """Protocol for backend session factory."""

    def create(self, config: dict) -> Any:
        """Create a backend session.

        Args:
            config: Session configuration dictionary

        Returns:
            Backend session instance
        """
        ...


@runtime_checkable
class ExecutionManagerFactory(Protocol):
    """Protocol for ExecutionManager factory."""

    def create(
        self,
        username: str,
        execution_id: str,
        calib_data_path: str,
        chip_id: str,
        name: str,
        tags: list[str],
        note: dict,
    ) -> ExecutionManager:
        """Create an ExecutionManager instance.

        Args:
            username: Username for the session
            execution_id: Execution identifier
            calib_data_path: Path for calibration data
            chip_id: Target chip ID
            name: Human-readable execution name
            tags: Tags for categorization
            note: Additional notes

        Returns:
            ExecutionManager instance
        """
        ...


@runtime_checkable
class TaskManagerFactory(Protocol):
    """Protocol for TaskManager factory."""

    def create(
        self,
        username: str,
        execution_id: str,
        qids: list[str],
        calib_dir: str,
    ) -> TaskManager:
        """Create a TaskManager instance.

        Args:
            username: Username for the session
            execution_id: Execution identifier
            qids: List of qubit IDs
            calib_dir: Calibration directory path

        Returns:
            TaskManager instance
        """
        ...


class DefaultSessionFactory:
    """Default implementation of SessionFactory using create_session."""

    def __init__(self, backend: str = "qubex"):
        """Initialize factory with backend type.

        Args:
            backend: Backend type ('qubex' or 'fake')
        """
        self.backend = backend

    def create(self, config: dict) -> Any:
        """Create a backend session using the standard factory.

        Args:
            config: Session configuration dictionary

        Returns:
            Backend session instance
        """
        return create_session(backend=self.backend, config=config)


class DefaultExecutionManagerFactory:
    """Default implementation of ExecutionManagerFactory."""

    def create(
        self,
        username: str,
        execution_id: str,
        calib_data_path: str,
        chip_id: str,
        name: str,
        tags: list[str],
        note: dict,
    ) -> ExecutionManager:
        """Create an ExecutionManager with default repositories.

        Args:
            username: Username for the session
            execution_id: Execution identifier
            calib_data_path: Path for calibration data
            chip_id: Target chip ID
            name: Human-readable execution name
            tags: Tags for categorization
            note: Additional notes

        Returns:
            ExecutionManager instance with default MongoDB repositories
        """
        return ExecutionManager(
            username=username,
            execution_id=execution_id,
            calib_data_path=calib_data_path,
            chip_id=chip_id,
            name=name,
            tags=tags,
            note=note,
        )


class DefaultTaskManagerFactory:
    """Default implementation of TaskManagerFactory."""

    def create(
        self,
        username: str,
        execution_id: str,
        qids: list[str],
        calib_dir: str,
    ) -> TaskManager:
        """Create a TaskManager instance.

        Args:
            username: Username for the session
            execution_id: Execution identifier
            qids: List of qubit IDs
            calib_dir: Calibration directory path

        Returns:
            TaskManager instance
        """
        return TaskManager(
            username=username,
            execution_id=execution_id,
            qids=qids,
            calib_dir=calib_dir,
        )


class FlowSessionDependencies:
    """Container for FlowSession dependencies.

    This class holds all the factory instances needed to create a FlowSession,
    enabling easy swapping for testing.

    Attributes:
        session_factory: Factory for backend sessions
        execution_manager_factory: Factory for ExecutionManager
        task_manager_factory: Factory for TaskManager
    """

    def __init__(
        self,
        session_factory: SessionFactory | None = None,
        execution_manager_factory: ExecutionManagerFactory | None = None,
        task_manager_factory: TaskManagerFactory | None = None,
    ):
        """Initialize with optional custom factories.

        Args:
            session_factory: Custom session factory (defaults to DefaultSessionFactory)
            execution_manager_factory: Custom execution manager factory
            task_manager_factory: Custom task manager factory
        """
        self.session_factory = session_factory
        self.execution_manager_factory = execution_manager_factory or DefaultExecutionManagerFactory()
        self.task_manager_factory = task_manager_factory or DefaultTaskManagerFactory()

    @classmethod
    def production(cls, backend: str = "qubex") -> "FlowSessionDependencies":
        """Create production dependencies.

        Args:
            backend: Backend type ('qubex' or 'fake')

        Returns:
            FlowSessionDependencies configured for production
        """
        return cls(
            session_factory=DefaultSessionFactory(backend=backend),
            execution_manager_factory=DefaultExecutionManagerFactory(),
            task_manager_factory=DefaultTaskManagerFactory(),
        )

    @classmethod
    def fake(cls) -> "FlowSessionDependencies":
        """Create dependencies for fake/test backend.

        Returns:
            FlowSessionDependencies configured for fake backend
        """
        return cls(
            session_factory=DefaultSessionFactory(backend="fake"),
            execution_manager_factory=DefaultExecutionManagerFactory(),
            task_manager_factory=DefaultTaskManagerFactory(),
        )


def create_flow_session(
    config: FlowSessionConfig,
    dependencies: FlowSessionDependencies | None = None,
) -> "FlowSession":
    """Create a FlowSession with the given configuration and dependencies.

    This is the primary factory function for creating FlowSession instances.
    It handles dependency injection and provides sensible defaults for
    production use.

    Args:
        config: FlowSession configuration
        dependencies: Optional custom dependencies (defaults to production)

    Returns:
        Configured FlowSession instance

    Example:
        ```python
        config = FlowSessionConfig.create(
            username="alice",
            chip_id="chip_1",
            qids=["0", "1", "2"],
        )

        # Production use
        session = create_flow_session(config)

        # Test use with fake backend
        test_deps = FlowSessionDependencies.fake()
        test_session = create_flow_session(config, dependencies=test_deps)
        ```
    """
    from qdash.workflow.flow.session import FlowSession

    # Use production dependencies if not specified
    if dependencies is None:
        dependencies = FlowSessionDependencies.production(backend=config.backend)

    # Convert config to kwargs for FlowSession.__init__
    return FlowSession(
        username=config.username,
        chip_id=config.chip_id,
        qids=list(config.qids),
        execution_id=config.execution_id,
        backend=config.backend,
        name=config.name,
        tags=list(config.tags) if config.tags else None,
        use_lock=config.use_lock,
        note=dict(config.note) if config.note else None,
        enable_github_pull=config.enable_github_pull,
        github_push_config=config.github_push_config,
        muxes=list(config.muxes) if config.muxes else None,
    )
