from __future__ import annotations

import numpy as np

from qdash.workflow.engine.backend.fake_qubex.simulation import FakeExperiment


def test_fake_ramsey_fit_exposes_qubex_compatible_fields() -> None:
    exp = FakeExperiment()

    result = exp.ramsey_experiment(
        targets=["Q00"],
        time_range=np.arange(0.0, 1000.0, 100.0),
        detuning=0.001,
        plot=False,
    )

    fit = result.data["Q00"].fit()

    assert fit["f"] == 0.001
    assert fit["f_err"] == 0.0
    assert fit["tau_err"] == 0.0


def test_fake_default_t1_and_t2_echo_lifetimes_have_small_variation() -> None:
    exp = FakeExperiment()

    t1_result = exp.t1_experiment(
        targets=["Q00", "Q01"],
        time_range=np.geomspace(100.0, 10_000.0, 5),
        plot=False,
    )
    t2_result = exp.t2_experiment(
        targets=["Q00", "Q01"],
        time_range=np.geomspace(300.0, 10_000.0, 5),
        plot=False,
    )

    assert t1_result.data["Q00"].t1 != t2_result.data["Q00"].t2
    assert t1_result.data["Q00"].t1 != t1_result.data["Q01"].t1
    assert t2_result.data["Q00"].t2 != t2_result.data["Q01"].t2


def test_fake_default_coherence_lifetimes_and_time_scale_vary_between_runs(
    monkeypatch,
) -> None:
    values = iter(
        [
            0.0,
            0.0,
            -0.020,
            0.030,
            0.0,
            0.020,
            0.0,
            0.0,
            -0.015,
            0.0,
            0.025,
            0.015,
        ]
    )
    monkeypatch.setattr(
        "qdash.workflow.engine.backend.fake_qubex.simulation.random.uniform",
        lambda *_: next(values),
    )
    exp = FakeExperiment()

    first_t1 = exp.t1_experiment(
        targets=["Q00"],
        time_range=np.geomspace(100.0, 10_000.0, 5),
        plot=False,
    )
    second_t1 = exp.t1_experiment(
        targets=["Q00"],
        time_range=np.geomspace(100.0, 10_000.0, 5),
        plot=False,
    )
    first_t2 = exp.t2_experiment(
        targets=["Q00"],
        time_range=np.geomspace(300.0, 10_000.0, 5),
        plot=False,
    )
    second_t2 = exp.t2_experiment(
        targets=["Q00"],
        time_range=np.geomspace(300.0, 10_000.0, 5),
        plot=False,
    )

    assert first_t1.data["Q00"].t1 != second_t1.data["Q00"].t1
    assert not np.array_equal(first_t1.data["Q00"].sweep_range, second_t1.data["Q00"].sweep_range)
    assert first_t2.data["Q00"].t2 != second_t2.data["Q00"].t2
    assert not np.array_equal(first_t2.data["Q00"].sweep_range, second_t2.data["Q00"].sweep_range)


def test_fake_explicit_lifetimes_are_preserved() -> None:
    exp = FakeExperiment(qubit_lifetimes=((11.0, 12.0), (21.0, 22.0)))

    assert exp._qubit_lifetime(0) == (11.0, 12.0)
    assert exp._qubit_lifetime(1) == (21.0, 22.0)
