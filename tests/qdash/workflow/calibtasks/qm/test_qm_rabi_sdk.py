"""Rabi adapter checks against the installed ``qm-qua`` and ``qualang-tools`` packages.

The tests run offline. Programs are built by the real qualang-tools ``QUA_calibrations``
class and serialized by the real SDK; the QOP server is replaced by
``StubQuantumMachinesManager``. Measured I/Q values come from ``SyntheticRabiResponse``
and simulated samples are synthetic arrays wrapped in the SDK's ``SimulatorSamples``
type, so neither stands for OPX hardware data or output of the official simulator.

They are skipped when the workflow ``qm`` extra is not installed. The QM SaaS checks
also need ``qm-saas`` (the ``qm-cloud`` extra); they replace its HTTP client and the
``QuantumMachinesManager`` with recorders, so no request leaves the process.
"""

from __future__ import annotations

import datetime
import inspect
import ssl
from typing import Any

import numpy as np
import pytest

qm = pytest.importorskip("qm")
pytest.importorskip("qualang_tools.addons.calibration.calibrations")

from qdash.datamodel.task_call import TaskCall  # noqa: E402
from qdash.workflow.calibtasks.qm.qm_amplitude_rabi import (  # noqa: E402
    QMAmplitudeRabi,
    simulator_run_parameters,
)
from qdash.workflow.calibtasks.qm.rabi_experiment import (  # noqa: E402
    RabiSweep,
    build_rabi_calibration,
    build_rabi_program,
    fit_amplitude_rabi,
    project_iq,
    run_rabi_on_hardware,
    simulate_rabi,
)
from qdash.workflow.engine.backend import qm as qm_backend  # noqa: E402
from qdash.workflow.engine.backend.qm import QMBackend  # noqa: E402
from tests.qdash.workflow.qm_helpers import (  # noqa: E402
    StubQuantumMachine,
    StubQuantumMachinesManager,
    SyntheticRabiResponse,
    connected_backend,
    example_settings,
)

SWEEP = RabiSweep.create(np.linspace(0.0, 1.5, 51), shots=8, cooldown_ns=1000)


def test_pinned_sdk_versions() -> None:
    from importlib.metadata import version

    assert version("qm-qua") == "1.5.0"
    assert version("qualang-tools") == "0.23.0"


def test_example_config_builds_the_qualang_tools_rabi_program() -> None:
    settings = example_settings()
    calibration = build_rabi_calibration(settings.qua_config, settings.qubit("0"), SWEEP)

    program = build_rabi_program(calibration)
    script = qm.generate_qua_script(program, settings.qua_config)

    assert isinstance(program, qm.Program)
    assert calibration.simulation is False
    assert "play('x180', 'qubit', amplitude_scale=" in script
    assert "measure('readout', 'resonator'" in script
    assert "wait(250, 'resonator')" in script
    assert 'r1.buffer(51).average().save("I")' in script


def test_hardware_run_executes_library_program_and_closes_machine() -> None:
    response = SyntheticRabiResponse(pi_amplitude_scale=0.6)
    machine = StubQuantumMachine(response=response, scales=SWEEP.amplitude_scales)
    manager = StubQuantumMachinesManager(machine=machine)
    session = connected_backend(manager, mode="hardware").get_instance()

    result = run_rabi_on_hardware(session, "0", SWEEP)

    assert len(machine.executed) == 1
    assert isinstance(machine.executed[0], qm.Program)
    assert machine.closed == 1
    assert manager.opened_configs == [session.settings.qua_config]
    # qualang-tools computes magnitude from the same job; both use demod2volts.
    np.testing.assert_allclose(result.magnitude, np.abs(result.iq))
    fit = fit_amplitude_rabi(result.amplitude_scales, project_iq(result.iq))
    assert fit.pi_amplitude_scale == pytest.approx(0.6, rel=1e-4)


def test_hardware_failure_still_closes_machine() -> None:
    machine = StubQuantumMachine(
        response=SyntheticRabiResponse(), scales=SWEEP.amplitude_scales, fail_execute=True
    )
    session = connected_backend(
        StubQuantumMachinesManager(machine=machine), mode="hardware"
    ).get_instance()

    with pytest.raises(RuntimeError, match="execution failed"):
        run_rabi_on_hardware(session, "0", SWEEP)
    assert machine.closed == 1


def _preset_task() -> QMAmplitudeRabi:
    call = TaskCall(name="QMAmplitudeRabi", run=simulator_run_parameters())
    return QMAmplitudeRabi(call.settings())


def test_simulator_preset_fits_the_default_simulation() -> None:
    sweep = _preset_task().sweep()
    settings = example_settings()

    np.testing.assert_allclose(sweep.amplitude_scales, [0.0, 0.5, 1.0, 1.5])
    assert np.count_nonzero(sweep.amplitude_scales) == 3
    assert sweep.shots == 1
    iteration_ns = sweep.iteration_duration_ns(
        settings.drive_pulse_length("0"), settings.readout_pulse_length("0")
    )
    assert iteration_ns == 4 * (40 + 200 + 1000)
    assert iteration_ns <= settings.simulation.duration_ns


def test_simulation_sends_library_program_to_simulator() -> None:
    drive = np.concatenate([np.zeros(10), 0.2 * np.ones(40), np.zeros(10)])
    samples = qm.SimulatorSamples(
        {
            "con1": qm.SimulatorControllerSamples(
                analog={"1": drive, "2": np.zeros_like(drive)},
                digital={"1": np.zeros(drive.size, dtype=bool)},
            )
        }
    )
    manager = StubQuantumMachinesManager(samples=samples)
    backend = connected_backend(manager, mode="simulator")

    sweep = _preset_task().sweep()
    result = simulate_rabi(backend.get_instance(), "0", sweep)

    ((config, program, simulation),) = manager.simulated
    assert config is backend.settings.qua_config
    assert isinstance(program, qm.Program)
    assert isinstance(simulation, qm.SimulationConfig)
    assert simulation.duration == 10_000
    # The SDK labels ports as "<FEM>-<port>"; OPX+ ports belong to FEM 1.
    assert sorted(result.analog) == ["con1:1-1", "con1:1-2"]
    assert result.analog_sampling_rate["con1:1-1"] == 1e9
    assert result.has_output()
    assert "con1:1-1" in result.digital
    assert result.simulated_iterations == 1


def test_simulation_refuses_a_sweep_longer_than_the_duration() -> None:
    manager = StubQuantumMachinesManager()
    backend = connected_backend(manager, mode="simulator")

    # The task defaults: 51 points with a 100 us cooldown last more than 5 ms per sweep.
    with pytest.raises(ValueError, match=r"at least 5112240 ns \(6391300 ns.*duration_ns is 40000"):
        simulate_rabi(backend.get_instance(), "0", QMAmplitudeRabi().sweep())
    assert manager.simulated == []


class _RecordingSaasApi:
    """Replaces ``qm_saas.api.Client``; records calls instead of sending HTTP requests."""

    instances: list[_RecordingSaasApi] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.launched: list[tuple[str, dict[str, Any]]] = []
        self.closed: list[str] = []
        self.close_all_called = False
        _RecordingSaasApi.instances.append(self)

    def versions(self) -> list[str]:
        return ["v2_4_4", "v2_6_0", "v3_8_1"]

    def launch_simulator(self, version: str, cluster_config: dict[str, Any]) -> dict[str, Any]:
        self.launched.append((version, cluster_config))
        expires = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=15)
        return {
            "id": "sim-1",
            "token": "instance-token",
            "host": "sim-1.qm-saas.test",
            "port": 443,
            "expires_at": expires.replace(tzinfo=None).isoformat(),
        }

    def close_simulator(self, instance_id: str) -> None:
        self.closed.append(instance_id)

    def close_all_simulators(self) -> None:
        self.close_all_called = True


def test_cloud_simulator_uses_qm_saas_connection_params(monkeypatch: pytest.MonkeyPatch) -> None:
    qm_saas_client = pytest.importorskip("qm_saas.client")
    from importlib.metadata import version

    assert version("qm-saas") == "1.2.0"
    _RecordingSaasApi.instances.clear()
    monkeypatch.setattr(qm_saas_client, "Client", _RecordingSaasApi)
    managers: list[dict[str, Any]] = []

    def manager_factory(**kwargs: Any) -> StubQuantumMachinesManager:
        # The real constructor must accept what qm-saas hands over.
        inspect.signature(qm.QuantumMachinesManager).bind(**kwargs)
        managers.append(kwargs)
        return StubQuantumMachinesManager()

    monkeypatch.setattr(qm, "QuantumMachinesManager", manager_factory)
    monkeypatch.setenv("TEST_QM_EMAIL", "user@example.test")
    monkeypatch.setenv("TEST_QM_PASSWORD", "pw-value")
    settings = example_settings().model_copy(
        update={
            "connection": None,
            "cloud": qm_backend.QMCloudSettings(
                qop_version="v2_6_0", email_env="TEST_QM_EMAIL", password_env="TEST_QM_PASSWORD"
            ),
        }
    )
    backend = QMBackend({"qm_settings": settings})

    session = backend.get_instance()
    backend.disconnect()
    backend.disconnect()

    (api,) = _RecordingSaasApi.instances
    assert api.kwargs["email"] == "user@example.test"
    assert api.kwargs["host"] == "qm-saas.quantum-machines.co"
    assert api.launched == [("v2_6_0", {})]
    (params,) = managers
    assert params["host"] == "sim-1.qm-saas.test"
    assert params["connection_headers"] == {
        "simulation-id": "sim-1",
        "simulation-auth": "instance-token",
    }
    assert isinstance(params["credentials"], ssl.SSLContext)
    assert params["follow_gateway_redirections"] is False
    assert session.is_simulator
    assert api.closed == ["sim-1"]
    assert not api.close_all_called


def test_modes_cannot_be_mixed() -> None:
    simulator = connected_backend(StubQuantumMachinesManager(), mode="simulator").get_instance()
    hardware = connected_backend(StubQuantumMachinesManager(), mode="hardware").get_instance()

    with pytest.raises(RuntimeError, match="hardware mode"):
        run_rabi_on_hardware(simulator, "0", SWEEP)
    with pytest.raises(RuntimeError, match="simulator mode"):
        simulate_rabi(hardware, "0", SWEEP)


def test_task_run_end_to_end_on_stub_hardware() -> None:
    task = QMAmplitudeRabi({"run": {"shots": 8, "cooldown_time": 1000}})
    sweep = task.sweep()
    machine = StubQuantumMachine(
        response=SyntheticRabiResponse(pi_amplitude_scale=0.8), scales=sweep.amplitude_scales
    )
    backend = connected_backend(StubQuantumMachinesManager(machine=machine), mode="hardware")

    run_result = task.run(backend, "0")
    post = task.postprocess(backend, "exec-1", run_result, "0")

    assert post.output_parameters["qm_pi_amplitude_scale"].value == pytest.approx(0.8, rel=1e-4)
    assert run_result.r2 is not None
    assert (run_result.r2["0"] or 0.0) > 0.999
