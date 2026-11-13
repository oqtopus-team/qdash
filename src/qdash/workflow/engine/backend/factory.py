from typing import TYPE_CHECKING, Any

from qdash.workflow.engine.backend.base import BaseBackend

if TYPE_CHECKING:
    from qdash.common.mux_mapping import MuxMapping


def create_backend(
    backend: str, config: dict[str, Any], *, mux_mapping: "MuxMapping | None" = None
) -> BaseBackend:
    """Return the appropriate backend based on the backend configuration.

    ``mux_mapping`` is the chip's MUX membership. The Qubex backend rejects a
    mapping it cannot drive (see ``QubexBackend.ensure_mux_mapping_compatible``);
    other backends accept any mapping and ignore it.
    """
    if backend == "qubex":
        return _load_qubex_backend(config, mux_mapping)
    if backend == "fake":
        return _load_fake_backend(config)
    raise ValueError(f"Unsupported BACKEND: {backend}. Supported backends are 'qubex' and 'fake'.")


def _load_qubex_backend(config: dict[str, Any], mux_mapping: "MuxMapping | None") -> BaseBackend:
    try:
        from qdash.workflow.engine.backend.qubex import QubexBackend

        return QubexBackend(config, mux_mapping=mux_mapping)
    except ImportError as e:
        msg = "QubexBackend is not available. Did you install qubex?"
        raise ImportError(msg) from e


def _load_fake_backend(config: dict[str, Any]) -> BaseBackend:
    from qdash.workflow.engine.backend.fake import FakeBackend

    return FakeBackend(config)
