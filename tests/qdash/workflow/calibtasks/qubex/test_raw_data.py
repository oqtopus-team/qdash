"""Tests for extracting pre-fit Qubex raw-data artifacts."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from qdash.common.raw_data import ArrayRawData, PreFitRawData
from qdash.workflow.calibtasks.qubex.raw_data import extract_qubex_raw_data


@dataclass
class _SweepData:
    target: str
    data: np.ndarray
    sweep_range: np.ndarray


@dataclass
class _ExperimentResult:
    data: dict[str, _SweepData]


def test_extract_qubex_raw_data_preserves_prefit_values_and_axis(tmp_path: Path) -> None:
    """Legacy experiment results expose the values passed to fitting."""
    expected_data = np.array([1 + 2j, 3 + 4j])
    expected_axis = np.array([100.0, 200.0])
    result = _ExperimentResult(
        data={
            "Q00": _SweepData(
                target="Q00",
                data=expected_data,
                sweep_range=expected_axis,
            )
        }
    )

    artifacts = extract_qubex_raw_data(result)

    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert isinstance(artifact, PreFitRawData)
    path = tmp_path / "t1.nc"
    artifact.save_netcdf(path)
    loaded = PreFitRawData.load_netcdf(path)
    assert loaded.target == "Q00"
    np.testing.assert_array_equal(loaded.data, expected_data)
    np.testing.assert_array_equal(loaded.axes["sweep_range"], expected_axis)


def test_extract_qubex_raw_data_handles_repeated_measurements() -> None:
    """Nested result lists, such as T1Average, produce one artifact per run."""
    result = {
        "results": [
            _ExperimentResult(
                data={
                    "Q00": _SweepData(
                        target="Q00",
                        data=np.array([index + 1j]),
                        sweep_range=np.array([100.0]),
                    )
                }
            )
            for index in range(3)
        ]
    }

    artifacts = extract_qubex_raw_data(result)

    assert len(artifacts) == 3


def test_extract_qubex_raw_data_keeps_canonical_data_model() -> None:
    """Canonical Qubex DataModel results are saved without conversion."""
    canonical = ArrayRawData(data=np.array([1.0]))

    artifacts = extract_qubex_raw_data(canonical)

    assert artifacts == [canonical]
