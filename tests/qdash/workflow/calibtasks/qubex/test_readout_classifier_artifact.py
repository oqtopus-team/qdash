"""Tests for per-task readout classifier snapshots saved as NetCDF artifacts."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest
from qubex.experiment.models.result import Result
from qubex.measurement.classifiers import (
    StateClassifier,
    StateClassifierGMM,
    StateClassifierKMeans,
)

from qdash.common.raw_data import StateClassifierRawData
from qdash.datamodel.task import QubitTaskModel, TaskStatusModel
from qdash.repository import FilesystemCalibDataSaver
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.measurement.ef_readout_classification import (
    EFReadoutClassification,
)
from qdash.workflow.calibtasks.qubex.measurement.readout_classification import (
    ReadoutClassification,
)
from qdash.workflow.calibtasks.qubex.raw_data import (
    extract_state_classifier_raw_data,
    state_classifier_raw_data,
)
from qdash.workflow.engine.task.executor import TaskExecutor


def _shots(n_states: int, *, offset: complex = 0, seed: int = 0) -> dict[int, np.ndarray]:
    rng = np.random.default_rng(seed)
    centers = [0.0 + 0.0j, 1.0 + 0.5j, 0.2 + 1.2j]
    return {
        state: offset + centers[state] + 0.08 * (rng.normal(size=300) + 1j * rng.normal(size=300))
        for state in range(n_states)
    }


def _build_classifier_result(target: str, classifier: StateClassifier) -> Result:
    """Mirror the result shape returned by Qubex ``Experiment.build_classifier``."""
    return Result(
        data={
            "readout_fidelities": {target: [0.99] * classifier.n_states},
            "average_readout_fidelity": {target: 0.99},
            "data": {target: {}},
            "classifiers": {target: classifier},
        }
    )


def _assert_same_classifier(restored: Any, original: StateClassifier, shots: np.ndarray) -> None:
    assert type(restored) is type(original)
    assert restored.label_map == original.label_map
    assert restored.phase == pytest.approx(original.phase)
    assert restored.created_at == original.created_at
    np.testing.assert_array_equal(restored.confusion_matrix, original.confusion_matrix)
    for state in original.dataset:
        np.testing.assert_array_equal(restored.dataset[state], original.dataset[state])
    np.testing.assert_array_equal(restored.predict(shots), original.predict(shots))


@pytest.mark.parametrize("classifier_type", [StateClassifierGMM, StateClassifierKMeans])
@pytest.mark.parametrize("n_states", [2, 3])
def test_snapshot_round_trips_qubex_classifier_through_netcdf(
    tmp_path: Path, classifier_type: type[StateClassifier], n_states: int
) -> None:
    shots = _shots(n_states)
    classifier = classifier_type.fit(shots, phase=0.3)
    reference_path = tmp_path / "reference.pkl"
    classifier.save(reference_path)

    artifact = state_classifier_raw_data("Q00", classifier)
    path = tmp_path / "classifier.nc"
    artifact.save_netcdf(path)
    loaded = StateClassifierRawData.load_netcdf(path)

    # The stored bytes are exactly what Qubex StateClassifier.save writes.
    assert loaded.classifier_bytes() == reference_path.read_bytes()
    restored = loaded.load_classifier()
    _assert_same_classifier(restored, classifier, shots[n_states - 1])
    _assert_same_classifier(StateClassifier.load(reference_path), restored, shots[n_states - 1])

    # Inspectable fields do not require unpickling.
    assert loaded.target == "Q00"
    assert loaded.source_type.endswith(classifier_type.__name__)
    assert loaded.n_states == n_states
    assert loaded.data.shape == (n_states, 300)
    np.testing.assert_array_equal(loaded.axes["state"], np.arange(n_states))
    expected_training = np.exp(-1j * 0.3) * shots[0]
    np.testing.assert_allclose(loaded.data[0], expected_training)
    assert loaded.label_map == {str(k): v for k, v in classifier.label_map.items()}
    np.testing.assert_array_equal(loaded.confusion_matrix, classifier.confusion_matrix)
    np.testing.assert_allclose(
        loaded.centers, [classifier.centers[state] for state in range(n_states)]
    )
    assert loaded.phase == pytest.approx(0.3)


def test_snapshot_is_isolated_from_later_shared_classifier_overwrites(tmp_path: Path) -> None:
    """Qubex overwrites ``<classifier_dir>/<chip>/<label>.pkl``; the task artifact must not."""
    shared_path = tmp_path / "classifier" / "chip" / "Q00.pkl"
    shared_path.parent.mkdir(parents=True)
    first = StateClassifierGMM.fit(_shots(2), phase=0.0)
    first.save(shared_path)
    saver = FilesystemCalibDataSaver(str(tmp_path / "exec-1"))
    [artifact_path] = saver.save_raw_data(
        [state_classifier_raw_data("Q00", first)], "ReadoutClassification", "qubit", "0"
    )

    second = StateClassifierGMM.fit(_shots(2, offset=3 + 3j, seed=1), phase=0.0)
    second.save(shared_path)

    restored = StateClassifierRawData.load_netcdf(artifact_path).load_classifier()
    _assert_same_classifier(restored, first, _shots(2)[1])
    shared = StateClassifier.load(shared_path)
    assert not np.array_equal(shared.dataset[0], restored.dataset[0])


def test_extract_ignores_results_without_qubex_classifiers() -> None:
    assert extract_state_classifier_raw_data({"classifiers": {"Q00": SimpleNamespace()}}) == []
    assert extract_state_classifier_raw_data(SimpleNamespace(data={"fidelity": 1.0})) == []
    assert extract_state_classifier_raw_data(None) == []


@pytest.mark.parametrize(
    ("task_type", "n_states"),
    [(ReadoutClassification, 2), (EFReadoutClassification, 3)],
)
def test_task_registers_classifier_snapshot_as_raw_data_artifact(
    tmp_path: Path, task_type: type[ReadoutClassification | EFReadoutClassification], n_states: int
) -> None:
    classifier = StateClassifierGMM.fit(_shots(n_states), phase=0.1)
    run_result = RunResult(raw_result=_build_classifier_result("Q00", classifier))
    task = task_type()
    state_manager = MagicMock()
    state_manager.get_task.return_value = QubitTaskModel(
        name=task.name, qid="0", task_id="task-1", status=TaskStatusModel.RUNNING
    )
    calib_dir = tmp_path / "exec-1"
    executor = TaskExecutor(
        state_manager=state_manager,
        calib_dir=str(calib_dir),
        execution_id="exec-1",
        task_manager_id="tm-1",
    )

    # Same calls TaskExecutor.execute makes between run and postprocess.
    raw_data = executor._extract_raw_data(task, run_result)
    executor._save_raw_data(raw_data, task.name, "qubit", "0")

    state_manager.set_raw_data_paths.assert_called_once()
    _, _, _, paths = state_manager.set_raw_data_paths.call_args.args
    assert len(paths) == 1
    path = Path(paths[0])
    assert path.parent == calib_dir / "raw_data"
    assert path.suffix == ".nc"
    loaded = StateClassifierRawData.load_netcdf(path)
    assert loaded.n_states == n_states
    _assert_same_classifier(loaded.load_classifier(), classifier, _shots(n_states)[0])
