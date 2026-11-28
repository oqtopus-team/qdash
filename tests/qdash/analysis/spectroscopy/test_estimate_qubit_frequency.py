import importlib
from collections.abc import Sequence
from types import SimpleNamespace

import pytest

from qdash.analysis.spectroscopy.estimate_qubit_frequency import (
    EstimateQubitFrequencyConfig,
    estimate_qubit_frequency,
)

qubit_frequency = importlib.import_module("qdash.analysis.spectroscopy.estimate_qubit_frequency")


def test_retry_with_trim_retries_one_additional_top_row(monkeypatch) -> None:
    calls: list[tuple[list[float], float]] = []

    class FakeQubitResponse:
        def __init__(
            self,
            _xs: Sequence[float],
            ys: Sequence[float],
            _zs: Sequence[Sequence[float]],
            config: EstimateQubitFrequencyConfig,
        ) -> None:
            calls.append((list(ys), config.top_power))
            self.f01 = SimpleNamespace(frequency=4.0) if len(ys) == 2 else None
            self.f12 = None

    monkeypatch.setattr(qubit_frequency, "QubitResponse", FakeQubitResponse)

    config = EstimateQubitFrequencyConfig(top_power=0.0)
    result = estimate_qubit_frequency(
        xs=[4.0, 4.1],
        ys=[-40.0, -30.0, -20.0, -10.0],
        zs=[
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
        ],
        config=config,
        retry_with_trim=True,
    )

    assert result.f01 is not None
    assert calls == [
        ([-40.0, -30.0, -20.0, -10.0], 0.0),
        ([-40.0, -30.0, -20.0], -10.0),
        ([-40.0, -30.0], -20.0),
    ]


def test_top_power_at_the_highest_row_is_rejected_before_any_retry_trim() -> None:
    # The reanalysis service drops rows at or above a top_power inside the sweep
    # before calling the estimator, because the estimator itself rejects it, even
    # with retry_with_trim, before the first retry can run.
    with pytest.raises(ValueError, match="top_power"):
        estimate_qubit_frequency(
            xs=[4.0, 4.1],
            ys=[-15.0, -10.0, -5.0],
            zs=[[0.0, 1.0], [0.0, 1.0], [0.0, 1.0]],
            config=EstimateQubitFrequencyConfig(top_power=-5.0, f01_height_min=8.0),
            retry_with_trim=True,
        )
