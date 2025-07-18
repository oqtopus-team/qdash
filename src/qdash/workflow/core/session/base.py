from abc import ABC, abstractmethod


class BaseSession(ABC):
    """Abstract base class for session management."""

    name: str = "base"

    @abstractmethod
    def connect(self) -> None: ...

    """Connect to the session."""

    @abstractmethod
    def version(self) -> str:
        """Return the version of the session."""
        msg = "This method should be implemented by subclasses."
        raise NotImplementedError(msg)

    @abstractmethod
    def get_session(self) -> object:
        """Get the session object."""
        msg = "This method should be implemented by subclasses."
        raise NotImplementedError(msg)
