"""Extract Qubex-compatible NetCDF artifacts from task run results."""

from __future__ import annotations

import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any

import numpy as np
from qubex.core import DataModel
from qubex.measurement.classifiers import StateClassifier

from qdash.common.raw_data import PreFitRawData, StateClassifierRawData

_AXIS_NAMES = (
    "sweep_range",
    "time_range",
    "frequency_range",
    "amplitude_range",
    "detuning_range",
)


def extract_qubex_raw_data(value: Any) -> list[DataModel]:
    """Extract canonical Qubex models or legacy pre-fit target data recursively."""
    artifacts: list[DataModel] = []
    seen: set[int] = set()

    def visit(item: Any) -> None:
        if item is None or isinstance(item, (str, bytes, int, float, bool, np.generic)):
            return

        item_id = id(item)
        if item_id in seen:
            return
        seen.add(item_id)

        if isinstance(item, DataModel):
            artifacts.append(item)
            return

        if is_dataclass(item) and hasattr(item, "target"):
            data = getattr(item, "data", getattr(item, "raw", None))
            if isinstance(data, np.ndarray):
                axes = {
                    name: np.asarray(getattr(item, name))
                    for name in _AXIS_NAMES
                    if getattr(item, name, None) is not None
                }
                artifacts.append(
                    PreFitRawData(
                        target=str(getattr(item, "target", "")),
                        data=np.asarray(data),
                        axes=axes,
                        source_type=f"{type(item).__module__}.{type(item).__name__}",
                    )
                )
                return

        if isinstance(item, Mapping):
            for nested in item.values():
                visit(nested)
            return

        if isinstance(item, Sequence) and not isinstance(item, np.ndarray):
            for nested in item:
                visit(nested)
            return

        nested_data = getattr(item, "data", None)
        if isinstance(nested_data, Mapping):
            visit(nested_data)

    visit(value)
    return artifacts


def state_classifier_raw_data(target: str, classifier: StateClassifier) -> StateClassifierRawData:
    """Snapshot a trained Qubex classifier with the serializer Qubex itself uses."""
    # Serialize through StateClassifier.save so the stored bytes match the shared
    # classifier file Qubex writes and reads, independent of later overwrites.
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / f"{target}.pkl"
        classifier.save(path)
        payload = path.read_bytes()

    states = sorted(classifier.dataset)
    training_shots = np.stack(
        [
            np.asarray(classifier.dataset[state])[:, 0]
            + 1j * np.asarray(classifier.dataset[state])[:, 1]
            for state in states
        ]
    )
    centers = classifier.centers
    return StateClassifierRawData(
        target=target,
        source_type=f"{type(classifier).__module__}.{type(classifier).__name__}",
        n_states=len(states),
        data=training_shots,
        axes={"state": np.asarray(states, dtype=np.int64)},
        label_map={str(key): int(value) for key, value in classifier.label_map.items()},
        confusion_matrix=np.asarray(classifier.confusion_matrix),
        centers=np.asarray([complex(centers[state]) for state in states]),
        phase=float(classifier.phase),
        scale=float(getattr(classifier, "scale", 1.0)),
        created_at=str(classifier.created_at),
        classifier_pickle=StateClassifierRawData.pack_bytes(payload),
        classifier_pickle_size=len(payload),
    )


def extract_state_classifier_raw_data(value: Any) -> list[StateClassifierRawData]:
    """Return snapshots of the classifiers in a Qubex ``build_classifier`` result."""
    data = getattr(value, "data", value)
    classifiers = data.get("classifiers") if isinstance(data, Mapping) else None
    if not isinstance(classifiers, Mapping):
        return []
    return [
        state_classifier_raw_data(str(target), classifier)
        for target, classifier in classifiers.items()
        if isinstance(classifier, StateClassifier)
    ]
