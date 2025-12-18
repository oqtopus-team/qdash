from typing import Any

from qdash.workflow.engine.backend.base import BaseBackend


def create_backend(backend: str, config: dict[str, Any]) -> BaseBackend:
    """Return the appropriate backend based on the backend configuration."""
    if backend == "qubex":
        return _load_qubex_backend(config)
    if backend == "fake":
        return _load_fake_backend(config)
    raise ValueError(f"Unsupported BACKEND: {backend}. Supported backends are 'qubex' and 'fake'.")


def _load_qubex_backend(config: dict[str, Any]) -> BaseBackend:
    try:
        from qdash.workflow.engine.backend.qubex import QubexBackend

        return QubexBackend(config)
    except ImportError as e:
        msg = "QubexBackend is not available. Did you install qubex?"
        raise ImportError(msg) from e


def _load_fake_backend(config: dict[str, Any]) -> BaseBackend:
    from qdash.workflow.engine.backend.fake import FakeBackend

    return FakeBackend(config)
