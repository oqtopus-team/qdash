from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from qdash.workflow.engine.backend.fake import FakeBackend
from qdash.workflow.engine.backend.fake_qubex.simulation import FakeExperiment


def test_fake_explicit_lifetimes_are_preserved() -> None:
    exp = FakeExperiment(qubit_lifetimes=((11.0, 12.0), (21.0, 22.0)))

    assert exp._qubit_lifetime(0) == (11.0, 12.0)
    assert exp._qubit_lifetime(1) == (21.0, 22.0)


def test_fake_zx90_accepts_explicit_cr_parameters_and_x180(monkeypatch) -> None:
    exp = FakeExperiment()
    x180 = object()
    monkeypatch.setattr(
        "qdash.workflow.engine.backend.fake_qubex.simulation._simulation_dependencies",
        lambda: (_ for _ in ()).throw(ImportError),
    )

    schedule = exp.zx90(
        "Q00",
        "Q01",
        cr_duration=100.0,
        cr_ramptime=16.0,
        cr_amplitude=0.2,
        cr_phase=0.1,
        cr_beta=0.01,
        cancel_amplitude=0.02,
        cancel_phase=0.3,
        cancel_beta=0.04,
        rotary_amplitude=0.05,
        x180={"Q00": x180},
    )

    assert schedule.duration == 100.0
    assert exp._resolve_zx90_x180("Q00", {"Q00": x180}) is x180


def test_fake_backend_passes_session_configuration_to_experiment(monkeypatch) -> None:
    experiment = MagicMock()
    factory = MagicMock(return_value=experiment)
    monkeypatch.setattr(
        "qdash.workflow.engine.backend.fake_qubex.FakeExperiment",
        factory,
    )
    backend = FakeBackend(
        {
            "task_type": "qubit",
            "qids": ["0"],
            "chip_id": "chip-1",
            "readout_duration": 2048.0,
            "configuration_mode": "ge-ef-fh",
        }
    )

    backend.connect()

    assert factory.call_args.kwargs["readout_duration"] == 2048.0
    assert factory.call_args.kwargs["configuration_mode"] == "ge-ef-fh"
    experiment.connect.assert_called_once_with()


def test_fake_default_control_amplitude_drives_a_pi_rotation_in_pi_duration() -> None:
    exp = FakeExperiment()

    rate = exp.calc_rabi_rate("Q00")

    assert rate == pytest.approx(1.0 / (2.0 * exp.pi_duration))
    assert exp.control_params.get_control_amplitude("Q00") == exp.CONTROL_AMPLITUDE_SCALE


def test_default_device_parameters_follow_the_physical_qubit() -> None:
    """A session on a subset of qubits simulates each qubit as the full device does."""
    full = FakeExperiment()
    subset = FakeExperiment(qubits=[2, 3])

    for label in ("Q02", "Q03"):
        assert subset.get_target(label).frequency == full.get_target(label).frequency
        assert subset.get_target(f"R{label}").frequency == full.get_target(f"R{label}").frequency
        assert subset.get_qubit(label).anharmonicity == full.get_qubit(label).anharmonicity
