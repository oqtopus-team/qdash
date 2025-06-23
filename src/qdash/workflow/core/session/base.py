from abc import ABC, abstractmethod
from typing import Any


class BaseSession(ABC):
    """Abstract base class for session management."""

    name: str = "base"

    @abstractmethod
    def connect(self) -> None: ...

    """Connect to the session."""

    def get_name(self) -> str:
        """Get the name of the session."""
        return self.name

    def get_session(self) -> Any:
        """Get the session object."""
        raise NotImplementedError("This method should be implemented by subclasses.")
