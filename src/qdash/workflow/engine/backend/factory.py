from typing import Any

from qdash.workflow.engine.backend.base import BaseBackend


def create_backend(backend: str, config: dict[str, Any]) -> BaseBackend:
    """Return the appropriate backend based on the backend configuration."""
    if backend == "qubex":
        return _load_qubex_backend(config)
    if backend == "fake":
        return _load_fake_backend(config)
    if backend == "qm":
        return _load_qm_backend(config)
    if backend == "qm-fake":
        return _load_qm_fake_backend(config)
    raise ValueError(
        f"Unsupported BACKEND: {backend}. "
        "Supported backends are 'qubex', 'fake', 'qm' and 'qm-fake'."
    )


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


def _load_qm_backend(config: dict[str, Any]) -> BaseBackend:
    # The Quantum Machines SDK is imported lazily when the backend connects, so
    # creating the backend does not require the optional ``qm`` extra.
    from qdash.workflow.engine.backend.qm import QMBackend

    return QMBackend(config)


def _load_qm_fake_backend(config: dict[str, Any]) -> BaseBackend:
    # Creating the backend imports no Quantum Machines package; connecting it does, because
    # the qm-fake device runs the real qm-qua and qualang-tools program path.
    from qdash.workflow.engine.backend.qm_fake import QMFakeBackend

    return QMFakeBackend(config)
