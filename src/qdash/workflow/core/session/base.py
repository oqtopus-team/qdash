from abc import ABC, abstractmethod
from typing import Any


class BaseSession(ABC):
    """Abstract base class for session management."""

    @abstractmethod
    def connect(self) -> None: ...

    """Connect to the session."""

    def get_session(self) -> Any:
        """Get the session object."""
        raise NotImplementedError("This method should be implemented by subclasses.")
