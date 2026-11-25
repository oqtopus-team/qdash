"""The session that owns the current pipeline step, for in-process Prefect tasks.

A pipeline registers its owner session here while it runs, so in-process
Prefect tasks (serial strategies, batch calls) can reach it without receiving
it as a task parameter. Isolated worker processes never read it; they receive a
``WorkerSpec`` instead.
"""

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qdash.workflow.service._internal.session import ExecutionRuntime


class SessionContext:
    """Thread-safe session context manager.

    This class provides a structured way to manage the current ExecutionRuntime
    in a thread-safe manner.

    Attributes
    ----------
    _local : threading.local
        Thread-local storage for session instances
    _global_session : ExecutionRuntime | None
        Fallback global session
    """

    _instance: "SessionContext | None" = None
    _lock = threading.Lock()
    _local: threading.local
    _global_session: "ExecutionRuntime | None"

    def __new__(cls) -> "SessionContext":
        """Singleton pattern for global access."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._local = threading.local()
                    cls._instance._global_session = None
        return cls._instance

    def set_session(self, session: "ExecutionRuntime | None") -> None:
        """Set the current session.

        Parameters
        ----------
        session : ExecutionRuntime | None
            Session to set as current, or None to clear
        """
        self._local.session = session
        self._global_session = session

    def get_session(self) -> "ExecutionRuntime | None":
        """Get the current session.

        Returns
        -------
        ExecutionRuntime | None
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


def set_current_session(session: "ExecutionRuntime | None") -> None:
    """Set the current session (convenience function).

    Parameters
    ----------
    session : ExecutionRuntime | None
        Session to set as current
    """
    _session_context.set_session(session)


def get_current_session() -> "ExecutionRuntime | None":
    """Get the current session (convenience function).

    Returns
    -------
    ExecutionRuntime | None
        Current session or None
    """
    return _session_context.get_session()


def clear_current_session() -> None:
    """Clear the current session (convenience function)."""
    _session_context.clear_session()


def get_session() -> "ExecutionRuntime":
    """Return the current owner session or raise when no pipeline is running."""
    session = get_current_session()
    if session is None:
        msg = "No active calibration session."
        raise RuntimeError(msg)
    return session
