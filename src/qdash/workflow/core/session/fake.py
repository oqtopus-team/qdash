from typing import Any

from qdash.workflow.core.session.base import BaseSession


class FakeSession(BaseSession):
    """Session management for Qubex experiments."""

    def __init__(self, config: dict) -> None:
        """Initialize the Fake session with a configuration dictionary."""
        self._config = config
        self._session: Any | None = None

    def connect(self) -> None:
        if self._session is None:
            self._session = object()

    def get_session(self) -> object | None:
        if self._exp is None:
            self.connect()
        if self._exp is None:
            msg = "Experiment instance is not initialized. Please call connect() first."
            raise RuntimeError(msg)
        return self._exp or None

    def get_note(self) -> str:
        """Get the calibration note from the experiment."""
        exp = self.get_session()
        if exp is None:
            msg = "Experiment instance is not initialized. Please call connect() first."
            raise RuntimeError(msg)
        return "Fake calibration note for testing purposes."
