from abc import ABC, abstractmethod


class BaseBackend(ABC):
    """Abstract base class for backend management."""

    name: str = "base"

    @abstractmethod
    def connect(self) -> None: ...

    """Connect to the backend."""

    @abstractmethod
    def version(self) -> str:
        """Return the version of the backend."""
        msg = "This method should be implemented by subclasses."
        raise NotImplementedError(msg)

    @abstractmethod
    def get_instance(self) -> object:
        """Get the backend instance (e.g., Experiment object for qubex)."""
        msg = "This method should be implemented by subclasses."
        raise NotImplementedError(msg)

    def save_note(
        self,
        username: str,
        chip_id: str,
        calib_dir: str,
        execution_id: str,
        task_manager_id: str,
        project_id: str | None = None,
    ) -> None:
        """Save calibration note. Override in subclasses that support notes."""

    def update_note(
        self,
        username: str,
        chip_id: str,
        calib_dir: str,
        execution_id: str,
        task_manager_id: str,
        project_id: str | None = None,
        qid: str | None = None,
    ) -> None:
        """Update calibration note. Override in subclasses that support notes."""
