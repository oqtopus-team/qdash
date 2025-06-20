# core/session/factory.py

from qdash.config import get_settings
from qdash.workflow.core.session.base import BaseSession


def get_session(config: dict) -> BaseSession:
    """Return the appropriate session based on the backend configuration."""
    settings = get_settings()
    backend = settings.backend
    if backend == "qubex":
        return _load_qubex_session(config)
    if backend == "fake":
        return _load_fake_session(config)
    raise ValueError(f"Unsupported BACKEND: {backend}. Supported backends are 'qubex' and 'fake'.")


def _load_qubex_session(config: dict) -> BaseSession:
    try:
        from qdash.workflow.core.session.qubex import QubexSession

        return QubexSession(config)
    except ImportError as e:
        msg = "QubexSession is not available. Did you install qubex?"
        raise ImportError(msg) from e


def _load_fake_session(config: dict) -> BaseSession:
    from qdash.workflow.core.session.fake import FakeSession

    return FakeSession(config)
