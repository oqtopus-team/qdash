"""Serializable raw-data artifacts produced by calibration tasks."""

from __future__ import annotations

import pickle
from typing import Any

import numpy as np
import numpy.typing as npt
from pydantic import Field
from qubex.core import DataModel


class ArrayRawData(DataModel):
    """Lossless NetCDF wrapper for an unlabelled raw NumPy array."""

    data: npt.NDArray[Any]


class PreFitRawData(DataModel):
    """Pre-fit values and coordinate axes exported from an experiment result."""

    target: str
    data: npt.NDArray[Any]
    axes: dict[str, npt.NDArray[Any]] = Field(default_factory=dict)
    source_type: str


class StateClassifierRawData(DataModel):
    """Snapshot of a trained Qubex state classifier stored as a NetCDF artifact.

    ``data`` holds the phase-aligned training shots per prepared state, shaped
    ``(n_states, n_shots)``. ``classifier_pickle`` is the exact byte stream written by
    Qubex ``StateClassifier.save`` (the format Qubex reads back from its classifier
    directory), packed into little-endian int64 words so NetCDF stores it compactly.
    Call :meth:`load_classifier` or write :meth:`classifier_bytes` to a ``.pkl`` file to
    reuse the classifier. The bytes are a pickle: only load artifacts from a trusted QDash
    deployment, with a scikit-learn version compatible with the one that trained them.
    """

    target: str
    source_type: str
    n_states: int
    data: npt.NDArray[Any]
    axes: dict[str, npt.NDArray[Any]] = Field(default_factory=dict)
    label_map: dict[str, int]
    confusion_matrix: npt.NDArray[Any]
    centers: npt.NDArray[Any]
    phase: float
    scale: float
    created_at: str
    classifier_pickle: npt.NDArray[Any]
    classifier_pickle_size: int

    @staticmethod
    def pack_bytes(payload: bytes) -> npt.NDArray[np.int64]:
        """Pack bytes into int64 words; the original length is stored separately."""
        padded = payload + b"\x00" * (-len(payload) % 8)
        return np.frombuffer(padded, dtype="<i8").astype(np.int64)

    def classifier_bytes(self) -> bytes:
        """Return the Qubex ``StateClassifier.save`` byte stream."""
        words = np.asarray(self.classifier_pickle, dtype="<i8")
        return words.tobytes()[: self.classifier_pickle_size]

    def load_classifier(self) -> Any:
        """Restore the Qubex ``StateClassifier`` exactly as ``StateClassifier.load`` does."""
        return pickle.loads(self.classifier_bytes())  # noqa: S301
