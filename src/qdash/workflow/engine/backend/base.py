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
    def get_session(self) -> object:
        """Get the backend session object."""
        msg = "This method should be implemented by subclasses."
        raise NotImplementedError(msg)
