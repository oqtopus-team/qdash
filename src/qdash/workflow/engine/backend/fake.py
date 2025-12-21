from typing import Any

from qdash.workflow.engine.backend.base import BaseBackend


class FakeBackend(BaseBackend):
    """Backend management for Fake experiments."""

    name: str = "fake"

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the Fake backend with a configuration dictionary."""
        self._config = config
        self._instance: Any | None = None

    def version(self) -> str:
        """Return the version of the Fake backend."""
        return "0.1.0"

    def connect(self) -> None:
        if self._instance is None:
            self._instance = object()

    def get_instance(self) -> object | None:
        if self._instance is None:
            self.connect()
        if self._instance is None:
            msg = "Backend instance is not initialized. Please call connect() first."
            raise RuntimeError(msg)
        return self._instance or None
