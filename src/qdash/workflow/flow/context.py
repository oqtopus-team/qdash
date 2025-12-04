"""Session context management for Python Flow Editor.

This module provides thread-safe session context management for Prefect flows,
replacing direct global variable access with a more structured approach.
"""

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qdash.workflow.flow.session import FlowSession


class SessionContext:
    """Thread-safe session context manager.

    This class provides a structured way to manage FlowSession instances
    in a thread-safe manner.

    Attributes
    ----------
    _local : threading.local
        Thread-local storage for session instances
    _global_session : FlowSession | None
        Fallback global session (for backward compatibility)
    """

    _instance: "SessionContext | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "SessionContext":
        """Singleton pattern for global access."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._local = threading.local()
                    cls._instance._global_session = None
        return cls._instance

    def set_session(self, session: "FlowSession | None") -> None:
        """Set the current session.

        Parameters
        ----------
        session : FlowSession | None
            Session to set as current, or None to clear
        """
        self._local.session = session
        self._global_session = session

    def get_session(self) -> "FlowSession | None":
        """Get the current session.

        Returns
        -------
        FlowSession | None
            Current session or None if not set
        """
        # Try thread-local first, fallback to global
        return getattr(self._local, "session", None) or self._global_session

    def clear_session(self) -> None:
        """Clear the current session."""
        self._local.session = None
        self._global_session = None


# Global singleton instance
_session_context = SessionContext()


def set_current_session(session: "FlowSession | None") -> None:
    """Set the current session (convenience function).

    Parameters
    ----------
    session : FlowSession | None
        Session to set as current
    """
    _session_context.set_session(session)


def get_current_session() -> "FlowSession | None":
    """Get the current session (convenience function).

    Returns
    -------
    FlowSession | None
        Current session or None
    """
    return _session_context.get_session()


def clear_current_session() -> None:
    """Clear the current session (convenience function)."""
    _session_context.clear_session()
