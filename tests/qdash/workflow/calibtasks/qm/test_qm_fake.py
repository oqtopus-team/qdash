"""QM fake backend (qm-fake): settings, session lifecycle, synthetic response and pipeline.

Every test here blocks the Quantum Machines packages and outgoing sockets, so the
qm-fake backend is shown to run offline without the optional ``qm`` extras.
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np
import plotly.graph_objects as go
import pytest
import yaml

from qdash.common.config.backend import get_available_backends, get_tasks
from qdash.common.raw_data import PreFitRawData
from qdash.datamodel import sweep as sweep_values
from qdash.datamodel.qubit import QubitModel
from qdash.datamodel.task import TaskStatusModel
from qdash.datamodel.task_call import TaskCall
from qdash.repository import FilesystemCalibDataSaver
from qdash.repository.inmemory import (
    InMemoryChipHistoryRepository,
    InMemoryChipRepository,
    InMemoryCouplingCalibrationRepository,
    InMemoryQubitCalibrationRepository,
    InMemoryTaskResultHistoryRepository,
)
from qdash.workflow.calibtasks.active_protocols import generate_task_instances
from qdash.workflow.calibtasks.base import BaseTask
from qdash.workflow.calibtasks.qm import qm_amplitude_rabi
from qdash.workflow.calibtasks.qm.qm_amplitude_rabi import QMAmplitudeRabi
from qdash.workflow.calibtasks.qm.rabi_experiment import (
    RabiSweep,
    run_rabi_on_fake,
    run_rabi_on_hardware,
    simulate_rabi,
)
from qdash.workflow.engine.backend.factory import create_backend
from qdash.workflow.engine.backend.qm import QMConfigurationError, load_qm_settings
from qdash.workflow.engine.backend.qm_fake import (
    QM_FAKE_CONFIG_ENV,
    QM_FAKE_SOURCE_TYPE,
    QM_FAKE_VERSION,
    QMFakeBackend,
    QMFakeDevice,
    QMFakeQubitSettings,
    QMFakeSession,
    QMFakeSettings,
    load_qm_fake_settings,
    resolve_qm_fake_settings_path,
)
from qdash.workflow.engine.task.backend_saver import BackendSaver
from qdash.workflow.engine.task.executor import TaskExecutor
from qdash.workflow.engine.task.history_recorder import TaskHistoryRecorder
from qdash.workflow.engine.task.state_manager import TaskStateManager
from tests.qdash.workflow.qm_helpers import (
    EXAMPLE_SETTINGS_PATH,
    REPO_ROOT,
    StubQuantumMachinesManager,
    connected_backend,
)

FAKE_SETTINGS_PATH = REPO_ROOT / "config" / "qm-config" / "example-fake" / "qm-fake.yaml"
QM_PACKAGES = ("qm", "qualang_tools")
USERNAME = "alice"
CHIP_ID = "fake-chip"
PROJECT_ID = "project-1"
HARDWARE_PI_SCALE = 0.73


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the QM packages unimportable and every outgoing connection fail."""
    for name in list(sys.modules):
        if name.split(".")[0] in QM_PACKAGES:
            monkeypatch.delitem(sys.modules, name)
    for name in QM_PACKAGES:
        # A None entry makes ``import name`` raise ImportError.
        monkeypatch.setitem(sys.modules, name, None)

    def no_network(*_: Any, **__: Any) -> Any:
        raise AssertionError("the qm-fake backend must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.delenv(QM_FAKE_CONFIG_ENV, raising=False)


def _fake_backend(seed: int | None = 1234, **qubit: Any) -> QMFakeBackend:
    settings = load_qm_fake_settings(FAKE_SETTINGS_PATH)
    settings = settings.model_copy(
        update={"seed": seed, "qubits": {"0": settings.qubits["0"].model_copy(update=qubit)}}
    )
    return QMFakeBackend({"qm_fake_settings": settings})


def _write(tmp_path: Path, data: dict[str, Any], name: str = "qm-fake.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


MINIMAL_FAKE: dict[str, Any] = {"qubits": {"0": {}}}


class TestRegistration:
    def test_backend_yaml_lists_qm_and_qm_fake(self) -> None:
        assert {"qubex", "fake", "qm", "qm-fake"} <= set(get_available_backends())
        assert get_tasks("qm-fake") == ["QMAmplitudeRabi"]

    def test_every_qm_fake_task_is_the_qm_implementation(self) -> None:
        qm_registry = BaseTask.registry["qm"]
        fake_registry = BaseTask.registry["qm-fake"]

        assert set(fake_registry) == set(get_tasks("qm-fake"))
        for name, task_class in fake_registry.items():
            assert task_class is qm_registry[name]
            assert task_class.backend == "qm"

    def test_existing_fake_backend_is_untouched(self) -> None:
        assert "QMAmplitudeRabi" not in BaseTask.registry["fake"]
        assert "QMAmplitudeRabi" not in BaseTask.registry["qubex"]

    def test_catalog_lists_the_qm_declaration_under_qm_fake(self) -> None:
        catalog = json.loads(
            (REPO_ROOT / "src/qdash/workflow/calibtasks/task_catalog.json").read_text()
        )

        assert catalog["backends"]["qm-fake"] == catalog["backends"]["qm"]

    def test_factory_creates_qm_fake_backend(self) -> None:
        backend = create_backend("qm-fake", {"chip_id": CHIP_ID})

        assert isinstance(backend, QMFakeBackend)
        assert backend.name == "qm-fake"
        assert not backend.is_connected

    def test_factory_rejects_unknown_backend(self) -> None:
        with pytest.raises(ValueError, match="'qm' and 'qm-fake'"):
            create_backend("qm-mock", {})


class TestSettings:
    def test_example_fake_settings_are_valid(self) -> None:
        settings = load_qm_fake_settings(FAKE_SETTINGS_PATH)

        assert settings.seed == 1234
        assert settings.qubits["0"].pi_amplitude_scale == 0.6
        assert sorted(settings.qubits) == ["0", "1"]

    def test_example_fake_pi_scales_lie_inside_the_default_sweep(self) -> None:
        settings = load_qm_fake_settings(FAKE_SETTINGS_PATH)
        default_scales = QMAmplitudeRabi().sweep().amplitude_scales

        for params in settings.qubits.values():
            assert 0.2 < params.pi_amplitude_scale < 0.8 * float(default_scales.max())

    def test_minimal_fake_settings_use_defaults(self, tmp_path: Path) -> None:
        settings = load_qm_fake_settings(_write(tmp_path, MINIMAL_FAKE))

        assert settings.seed is None
        assert settings.qubits["0"] == QMFakeQubitSettings()

    def test_integer_qids_become_strings(self, tmp_path: Path) -> None:
        path = tmp_path / "qm-fake.yaml"
        path.write_text("qubits:\n  0:\n  1: {contrast: 0.02}\n")

        settings = load_qm_fake_settings(path)

        assert sorted(settings.qubits) == ["0", "1"]

    @pytest.mark.parametrize(
        ("extra", "named"),
        [
            ({"mode": "hardware"}, "mode"),
            ({"connection": {"host": "127.0.0.1"}}, "connection"),
            ({"simulation": {"duration_ns": 40_000}}, "simulation"),
            ({"qua_config": {"elements": {}}}, "qua_config"),
            ({"qua_config_file": "qua_config.yaml"}, "qua_config_file"),
        ],
    )
    def test_qop_server_settings_are_rejected(
        self, tmp_path: Path, extra: dict[str, Any], named: str
    ) -> None:
        with pytest.raises(QMConfigurationError, match=rf"without a QOP server.*remove {named}"):
            load_qm_fake_settings(_write(tmp_path, {**MINIMAL_FAKE, **extra}))

    def test_hardware_settings_file_is_rejected(self) -> None:
        with pytest.raises(QMConfigurationError, match="remove mode, connection, simulation"):
            load_qm_fake_settings(EXAMPLE_SETTINGS_PATH)

    def test_former_mock_section_points_to_the_new_layout(self, tmp_path: Path) -> None:
        with pytest.raises(QMConfigurationError, match="move the contents of 'mock' up"):
            load_qm_fake_settings(_write(tmp_path, {"mock": MINIMAL_FAKE}))

    @pytest.mark.parametrize(
        "qubit",
        [
            {"pi_amplitude": 0.6},  # typo of pi_amplitude_scale
            {"pi_amplitude_scale": 0.0},
            {"pi_amplitude_scale": 2.0},
            {"pi_amplitude_scale": float("nan")},
            {"contrast": 0.0},
            {"noise_per_shot": -0.1},
            {"iq_offset": [0.0]},
        ],
    )
    def test_invalid_fake_qubit_is_rejected(self, tmp_path: Path, qubit: dict[str, Any]) -> None:
        with pytest.raises(QMConfigurationError, match="Invalid qm-fake settings"):
            load_qm_fake_settings(_write(tmp_path, {"qubits": {"0": qubit}}))

    @pytest.mark.parametrize(
        "data", [{}, {"qubits": {}}, {"qubits": {"0": {}}, "seed": -1}, {"qubit": {"0": {}}}]
    )
    def test_invalid_fake_settings_are_rejected(self, tmp_path: Path, data: dict[str, Any]) -> None:
        with pytest.raises(QMConfigurationError, match="Invalid qm-fake settings"):
            load_qm_fake_settings(_write(tmp_path, data))

    def test_missing_file_is_reported(self, tmp_path: Path) -> None:
        with pytest.raises(QMConfigurationError, match="qm-fake settings file not found"):
            load_qm_fake_settings(tmp_path / "qm-fake.yaml")

    @pytest.mark.parametrize("mode", ["mock", "fake"])
    def test_qm_backend_refuses_local_fake_mode(self, tmp_path: Path, mode: str) -> None:
        with pytest.raises(QMConfigurationError, match="select backend 'qm-fake'"):
            load_qm_settings(_write(tmp_path, {"mode": mode, **MINIMAL_FAKE}, "qm.yaml"))

    def test_qm_backend_refuses_mock_section(self, tmp_path: Path) -> None:
        data = yaml.safe_load(EXAMPLE_SETTINGS_PATH.read_text())
        data["qua_config_file"] = str(EXAMPLE_SETTINGS_PATH.parent / "qua_config.yaml")
        data["mock"] = MINIMAL_FAKE

        with pytest.raises(QMConfigurationError, match="select backend 'qm-fake'"):
            load_qm_settings(_write(tmp_path, data, "qm.yaml"))


class TestSettingsPath:
    def test_defaults_to_qm_fake_yaml_in_chip_directory(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            "qdash.common.config.loader.ConfigLoader.get_config_dir", lambda: tmp_path
        )

        path = resolve_qm_fake_settings_path({"chip_id": CHIP_ID})

        assert path == tmp_path / "qm-config" / CHIP_ID / "qm-fake.yaml"

    def test_hardware_settings_variable_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            "qdash.common.config.loader.ConfigLoader.get_config_dir", lambda: tmp_path
        )
        monkeypatch.setenv("QDASH_QM_CONFIG", "/elsewhere/qm.yaml")

        path = resolve_qm_fake_settings_path({"chip_id": CHIP_ID, "qm_config_path": "x.yaml"})

        assert path == tmp_path / "qm-config" / CHIP_ID / "qm-fake.yaml"

    def test_environment_variable_and_session_option_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(QM_FAKE_CONFIG_ENV, "/env/qm-fake.yaml")

        assert resolve_qm_fake_settings_path({"chip_id": CHIP_ID}) == Path("/env/qm-fake.yaml")
        assert resolve_qm_fake_settings_path(
            {"chip_id": CHIP_ID, "qm_fake_config_path": "/opt/qm-fake.yaml"}
        ) == Path("/opt/qm-fake.yaml")

    def test_needs_a_chip_or_path(self) -> None:
        with pytest.raises(QMConfigurationError, match=r"Cannot locate qm-fake\.yaml"):
            resolve_qm_fake_settings_path({})


class TestLifecycle:
    def test_factory_creates_and_connects_without_qm_packages(self) -> None:
        backend = create_backend(
            "qm-fake", {"chip_id": CHIP_ID, "qm_fake_config_path": FAKE_SETTINGS_PATH}
        )
        assert isinstance(backend, QMFakeBackend)

        backend.connect()
        session = backend.get_instance()

        assert backend.is_connected
        assert isinstance(session, QMFakeSession)
        assert backend.is_fake and session.is_fake
        assert backend.mode == session.mode == "fake"
        assert not backend.is_hardware and not session.is_hardware
        assert not backend.is_simulator and not session.is_simulator
        assert backend.version() == QM_FAKE_VERSION
        assert not any(name in sys.modules and sys.modules[name] for name in QM_PACKAGES)

    def test_qm_backend_is_never_fake(self) -> None:
        backend = connected_backend(StubQuantumMachinesManager(), mode="hardware")

        assert not backend.is_fake
        assert not backend.get_instance().is_fake

    def test_disconnect_closes_the_device_and_is_idempotent(self) -> None:
        backend = _fake_backend()
        device = backend.get_instance().device

        backend.disconnect()
        backend.disconnect()

        assert device.closed
        assert not backend.is_connected
        with pytest.raises(RuntimeError, match="closed"):
            device.rabi_iq("0", np.linspace(0, 1, 5), 10)

    def test_reconnect_starts_a_fresh_seeded_device(self) -> None:
        backend = _fake_backend(seed=5)
        scales = np.linspace(0.0, 1.5, 21)
        first = backend.get_instance().device.rabi_iq("0", scales, 10)
        backend.disconnect()

        second_device = backend.get_instance().device

        np.testing.assert_array_equal(second_device.rabi_iq("0", scales, 10), first)

    def test_unknown_qubit_names_the_configured_ones(self) -> None:
        session = _fake_backend().get_instance()

        with pytest.raises(QMConfigurationError, match=r"Qubit 7 is not configured.*configured: 0"):
            run_rabi_on_fake(session, "7", RabiSweep.create(np.linspace(0, 1, 5), 10, 1000))

    def test_sessions_cannot_be_mixed(self) -> None:
        fake = _fake_backend().get_instance()
        hardware = connected_backend(StubQuantumMachinesManager(), mode="hardware").get_instance()
        sweep = RabiSweep.create(np.linspace(0, 1, 5), 10, 1000)

        with pytest.raises(RuntimeError, match="hardware mode"):
            run_rabi_on_hardware(cast("Any", fake), "0", sweep)
        with pytest.raises(RuntimeError, match="simulator mode"):
            simulate_rabi(cast("Any", fake), "0", sweep)
        with pytest.raises(RuntimeError, match="qm-fake backend"):
            run_rabi_on_fake(cast("Any", hardware), "0", sweep)


class TestResponse:
    def test_ideal_response_moves_from_ground_to_excited_point(self) -> None:
        params = QMFakeQubitSettings(
            pi_amplitude_scale=0.5, iq_offset=(0.01, -0.02), contrast=0.004, phase_deg=90.0
        )

        iq = params.ideal_iq(np.array([0.0, 0.25, 0.5, 1.0, -0.5]))

        np.testing.assert_allclose(
            iq,
            [0.01 - 0.02j, 0.01 - 0.018j, 0.01 - 0.016j, 0.01 - 0.02j, 0.01 - 0.016j],
            atol=1e-12,
        )

    def test_noise_shrinks_with_the_square_root_of_shots(self) -> None:
        params = QMFakeQubitSettings(noise_per_shot=0.02)
        device = QMFakeDevice(QMFakeSettings(seed=3, qubits={"0": params}))
        scales = np.linspace(0.0, 1.5, 20_000)
        ideal = params.ideal_iq(scales)

        for shots in (1, 100, 10_000):
            residual = device.rabi_iq("0", scales, shots) - ideal
            expected = 0.02 / np.sqrt(shots)
            assert np.std(residual.real) == pytest.approx(expected, rel=0.05)
            assert np.std(residual.imag) == pytest.approx(expected, rel=0.05)
            assert params.averaged_noise_std(shots) == pytest.approx(expected)

    def test_noise_free_qubit_returns_the_ideal_response(self) -> None:
        params = QMFakeQubitSettings(noise_per_shot=0.0)
        device = QMFakeDevice(QMFakeSettings(seed=None, qubits={"0": params}))
        scales = np.linspace(0.0, 1.5, 11)

        np.testing.assert_array_equal(device.rabi_iq("0", scales, 1), params.ideal_iq(scales))

    def test_seed_makes_results_reproducible(self) -> None:
        scales = np.linspace(0.0, 1.5, 51)

        def run(seed: int | None) -> np.ndarray:
            device = QMFakeDevice(QMFakeSettings(seed=seed, qubits={"0": QMFakeQubitSettings()}))
            return device.rabi_iq("0", scales, 100)

        np.testing.assert_array_equal(run(11), run(11))
        assert not np.array_equal(run(11), run(12))
        assert not np.array_equal(run(None), run(None))

    def test_rejects_non_positive_shots(self) -> None:
        with pytest.raises(ValueError, match="shots"):
            QMFakeQubitSettings().averaged_noise_std(0)


class TestTask:
    def test_run_uses_the_fake_device_and_the_shared_fit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for name in ("run_rabi_on_hardware", "simulate_rabi"):
            monkeypatch.setattr(
                qm_amplitude_rabi, name, MagicMock(side_effect=AssertionError(f"{name} ran"))
            )
        backend = _fake_backend()

        result = QMAmplitudeRabi().run(backend, "0")

        measurement = result.raw_result["measurement"]
        assert measurement.mode == "fake"
        assert measurement.source_type == QM_FAKE_SOURCE_TYPE
        assert measurement.shots == 1000
        assert measurement.metadata["seed"] == 1234
        assert measurement.metadata["backend"] == "qm-fake"
        assert result.r2 is not None
        assert (result.r2["0"] or 0.0) > 0.98
        assert result.raw_result["fit"].pi_amplitude_scale == pytest.approx(0.6, rel=0.01)

    def test_postprocess_labels_fake_output_figure_and_raw_data(self) -> None:
        backend = _fake_backend()
        task = QMAmplitudeRabi()
        run_result = task.run(backend, "0")

        post = task.postprocess(backend, "exec-1", run_result, "0")
        (raw,) = task.extract_raw_data(run_result)

        output = post.output_parameters["qm_pi_amplitude_scale"]
        assert post.validation_error is None
        assert output.value == pytest.approx(0.6, rel=0.01)
        assert output.description.startswith("QM-FAKE:")
        assert "hardware" not in post.figures[0].layout.title.text
        assert "QM-FAKE" in post.figures[0].layout.title.text
        assert "not measured" in post.figures[0].layout.annotations[0].text
        assert raw.source_type == QM_FAKE_SOURCE_TYPE
        assert raw.target == "qm-fake-q0"

    def test_fake_result_is_rejected_by_a_hardware_backend(self) -> None:
        run_result = QMAmplitudeRabi().run(_fake_backend(), "0")
        hardware = connected_backend(StubQuantumMachinesManager(), mode="hardware")

        with pytest.raises(RuntimeError, match="Fake Rabi result received from a backend in hard"):
            QMAmplitudeRabi().postprocess(hardware, "exec-1", run_result, "0")

    def test_pi_scale_outside_the_sweep_fails_validation(self) -> None:
        backend = _fake_backend(pi_amplitude_scale=1.9)
        task = QMAmplitudeRabi({"run": {"amplitude_scale_range": {"value": (0.0, 0.9, 31)}}})

        post = task.postprocess(backend, "exec-1", task.run(backend, "0"), "0")

        assert post.output_parameters == {}
        assert post.validation_error is not None
        assert "outside the swept range" in post.validation_error
        assert post.figures


def _executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, force_update_params: bool
) -> SimpleNamespace:
    """TaskExecutor with in-memory repositories and a hardware value already accepted."""
    qubit_repo = InMemoryQubitCalibrationRepository()
    qubit_repo.add_qubit(
        USERNAME,
        QubitModel(
            project_id=PROJECT_ID,
            username=USERNAME,
            qid="0",
            status="",
            chip_id=CHIP_ID,
            data={"qm_pi_amplitude_scale": {"value": HARDWARE_PI_SCALE, "unit": "a.u."}},
        ),
    )

    # The in-memory repository has no lookup of pre-update values; read its stored data.
    def previous_data(**kw: Any) -> dict[str, Any]:
        qubit = qubit_repo.find_one(username=kw["username"], qid=kw["qid"], chip_id=kw["chip_id"])
        return dict(qubit.data) if qubit is not None else {}

    monkeypatch.setattr(qubit_repo, "get_calibration_data_for_update", previous_data, raising=False)
    coupling_repo = InMemoryCouplingCalibrationRepository()
    monkeypatch.setattr("qdash.repository.MongoQubitCalibrationRepository", lambda: qubit_repo)
    monkeypatch.setattr(
        "qdash.repository.MongoCouplingCalibrationRepository", lambda: coupling_repo
    )
    update_params = MagicMock()
    monkeypatch.setattr(BackendSaver, "_update_backend_params", update_params)

    figures: list[go.Figure] = []

    def write_image(figure: go.Figure, path: str, *_: Any, **__: Any) -> None:
        # Keep the test free of the Kaleido renderer; the JSON figure is written for real.
        figures.append(figure)
        Path(path).write_bytes(b"png")

    monkeypatch.setattr(go.Figure, "write_image", write_image)

    history_repo = InMemoryTaskResultHistoryRepository()
    state = TaskStateManager(qids=["0"])
    executor = TaskExecutor(
        state_manager=state,
        calib_dir=str(tmp_path),
        execution_id="exec-1",
        task_manager_id="tm-1",
        username=USERNAME,
        history_recorder=TaskHistoryRecorder(
            task_result_history_repo=cast("Any", history_repo),
            chip_repo=InMemoryChipRepository(),
            chip_history_repo=InMemoryChipHistoryRepository(),
        ),
        data_saver=FilesystemCalibDataSaver(str(tmp_path)),
        force_update_params=force_update_params,
        update_calibration_parameters=True,
    )
    execution_service = MagicMock(project_id=PROJECT_ID, chip_id=CHIP_ID, execution_id="exec-1")
    execution_service.merge_calib_data.return_value = execution_service
    execution_service.to_datamodel.return_value = SimpleNamespace(
        project_id=PROJECT_ID, chip_id=CHIP_ID
    )
    return SimpleNamespace(
        executor=executor,
        state=state,
        execution_service=execution_service,
        qubit_repo=qubit_repo,
        coupling_repo=coupling_repo,
        history_repo=history_repo,
        update_params=update_params,
        figures=figures,
    )


def _task_from_call(call: TaskCall, backend: str = "qm-fake") -> Any:
    """Instantiate the task the way the orchestrator does, from the backend's registry."""
    return generate_task_instances(
        task_names=[call.name], task_details={call.name: call.settings()}, backend=backend
    )[call.name]


def _accepted_pi_scale(env: SimpleNamespace) -> Any:
    qubit = env.qubit_repo.find_one(username=USERNAME, qid="0", chip_id=CHIP_ID)
    stored = qubit.data["qm_pi_amplitude_scale"]
    return stored["value"] if isinstance(stored, dict) else stored.value


class TestPipeline:
    @pytest.mark.parametrize("force_update_params", [False, True])
    def test_fake_run_is_recorded_but_never_replaces_the_hardware_value(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, force_update_params: bool
    ) -> None:
        env = _executor(tmp_path, monkeypatch, force_update_params=force_update_params)
        monkeypatch.setenv(QM_FAKE_CONFIG_ENV, str(FAKE_SETTINGS_PATH))
        backend = create_backend("qm-fake", {"chip_id": CHIP_ID})
        assert backend.name == "qm-fake"
        received: list[tuple[str, np.ndarray, int]] = []
        rabi_iq = QMFakeDevice.rabi_iq

        def spy(self: QMFakeDevice, qid: str, scales: np.ndarray, shots: int) -> np.ndarray:
            received.append((qid, np.array(scales), shots))
            return rabi_iq(self, qid, scales, shots)

        monkeypatch.setattr(QMFakeDevice, "rabi_iq", spy)
        call = TaskCall(
            name="QMAmplitudeRabi",
            run={"amplitude_scale_range": sweep_values.linspace(0.0, 1.2, 41), "shots": 4000},
        )

        _, result = env.executor.execute(
            _task_from_call(call), backend, "0", cast("Any", env.execution_service)
        )

        # Edited run parameters reach the fake response.
        ((qid, scales, shots),) = received
        assert (qid, shots) == ("0", 4000)
        np.testing.assert_allclose(scales, np.linspace(0.0, 1.2, 41))

        # The shared fit and validation accept the response.
        assert result.success
        assert result.r2 is not None
        r2 = result.r2["0"]
        assert r2 is not None and r2 > 0.98
        model = env.state.get_task("QMAmplitudeRabi", "qubit", "0")
        assert model.status == TaskStatusModel.COMPLETED
        assert model.quality_metrics["r2"] == pytest.approx(r2)

        # The output stays visible in the task result, labelled fake and not written.
        output = model.output_parameters["qm_pi_amplitude_scale"]
        assert output["value"] == pytest.approx(0.6, rel=0.01)
        assert output["description"].startswith("QM-FAKE:")
        assert output["database_updated"] is False
        assert output["database_updates"] == [
            {
                "parameter_name": "qm_pi_amplitude_scale",
                "previous_value": None,
                "updated_value": output["value"],
                "updated": False,
            }
        ]

        # The accepted hardware value and the backend parameters are untouched.
        assert _accepted_pi_scale(env) == HARDWARE_PI_SCALE
        env.update_params.assert_not_called()

        # History keeps the same labelled result with its figure and raw data.
        entry = env.history_repo.get_all()[-1]
        assert entry.status == TaskStatusModel.COMPLETED
        assert entry.output_parameters["qm_pi_amplitude_scale"]["database_updated"] is False
        (json_path,) = entry.json_figure_path
        title = json.loads(Path(json_path).read_text())["layout"]["title"]["text"]
        assert "QM-FAKE synthetic response, not measured" in title
        assert len(env.figures) == 1
        (raw_path,) = entry.raw_data_path
        raw = PreFitRawData.load_netcdf(raw_path)
        assert raw.source_type == QM_FAKE_SOURCE_TYPE
        assert raw.target == "qm-fake-q0"
        np.testing.assert_allclose(raw.axes["amplitude_scale"], np.linspace(0.0, 1.2, 41))
        assert np.iscomplexobj(raw.data) and raw.data.shape == (41,)

    def test_failed_fit_keeps_figure_and_publishes_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = _executor(tmp_path, monkeypatch, force_update_params=True)
        backend = _fake_backend(noise_per_shot=0.5)
        call = TaskCall(name="QMAmplitudeRabi", run={"shots": 1})

        with pytest.raises(ValueError, match="R² value too low"):
            env.executor.execute(
                _task_from_call(call), backend, "0", cast("Any", env.execution_service)
            )

        model = env.state.get_task("QMAmplitudeRabi", "qubit", "0")
        assert model.status == TaskStatusModel.FAILED
        assert model.output_parameters == {}
        assert env.state.get_qubit_calib_data("0") == {}
        assert _accepted_pi_scale(env) == HARDWARE_PI_SCALE
        env.update_params.assert_not_called()
        entry = env.history_repo.get_all()[-1]
        assert entry.status == TaskStatusModel.FAILED
        assert entry.json_figure_path and entry.raw_data_path

    def test_hardware_run_still_replaces_the_accepted_value(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = _executor(tmp_path, monkeypatch, force_update_params=False)
        task = _task_from_call(TaskCall(name="QMAmplitudeRabi"), backend="qm")
        measurement = task.run(_fake_backend(), "0").raw_result["measurement"]
        measurement.mode = "hardware"
        monkeypatch.setattr(qm_amplitude_rabi, "run_rabi_on_hardware", lambda *_: measurement)
        hardware = connected_backend(StubQuantumMachinesManager(), mode="hardware")

        _, result = env.executor.execute(task, hardware, "0", cast("Any", env.execution_service))

        assert result.success
        assert _accepted_pi_scale(env) == pytest.approx(0.6, rel=0.01)
        output = env.state.get_task("QMAmplitudeRabi", "qubit", "0").output_parameters
        assert output["qm_pi_amplitude_scale"]["database_updated"] is True
        assert output["qm_pi_amplitude_scale"]["previous_database_value"] == HARDWARE_PI_SCALE
