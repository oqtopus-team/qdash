"""Session context management for Python Flow Editor.

This module provides thread-safe session context management for Prefect flows,
replacing direct global variable access with a more structured approach.
"""

import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator

if TYPE_CHECKING:
    from qdash.workflow.flow.session import FlowSession


class SessionContext:
    """Thread-safe session context manager.

    This class provides a structured way to manage FlowSession instances
    in a thread-safe manner, supporting both global access and context
    manager patterns.

    Attributes
    ----------
    _local : threading.local
        Thread-local storage for session instances
    _global_session : FlowSession | None
        Fallback global session (for backward compatibility)

    Example
    -------
    ```python
    # Global access (backward compatible)
    context = SessionContext()
    context.set_session(session)
    current = context.get_session()

    # Context manager pattern
    with context.session_scope(session):
        # session is active in this scope
        current = context.get_session()
    # session is automatically cleared
    ```
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

    def has_session(self) -> bool:
        """Check if a session is currently active.

        Returns
        -------
        bool
            True if a session is active
        """
        return self.get_session() is not None

    @contextmanager
    def session_scope(self, session: "FlowSession") -> Generator["FlowSession", None, None]:
        """Context manager for session scope.

        Parameters
        ----------
        session : FlowSession
            Session to use in this scope

        Yields
        ------
        FlowSession
            The active session

        Example
        -------
        ```python
        context = SessionContext()
        session = FlowSession(...)

        with context.session_scope(session) as s:
            s.execute_task("CheckFreq", "0")
        # session is cleared after scope
        ```
        """
        previous_session = self.get_session()
        try:
            self.set_session(session)
            yield session
        finally:
            self.set_session(previous_session)


# Global singleton instance
_session_context = SessionContext()


def get_session_context() -> SessionContext:
    """Get the global session context.

    Returns
    -------
    SessionContext
        The global session context instance
    """
    return _session_context


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


def has_current_session() -> bool:
    """Check if a session is active (convenience function).

    Returns
    -------
    bool
        True if a session is active
    """
    return _session_context.has_session()
