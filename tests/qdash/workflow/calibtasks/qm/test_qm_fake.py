"""QM fake backend (qm-fake) without the QM packages: settings, routing and the install hint.

Every test here makes the Quantum Machines packages unimportable and blocks outgoing
sockets. The settings, the registry and the factory work without the ``qm`` extra; a
qm-fake run does not, and must fail with the install command instead of producing any
response. Runs with the real SDK are in ``test_qm_fake_device.py``.
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from qdash.common.config.backend import get_available_backends, get_tasks
from qdash.workflow.calibtasks.base import BaseTask
from qdash.workflow.calibtasks.qm.qm_amplitude_rabi import QMAmplitudeRabi
from qdash.workflow.engine.backend.factory import create_backend
from qdash.workflow.engine.backend.qm import (
    QMConfigurationError,
    QMDependencyError,
    load_qm_settings,
)
from qdash.workflow.engine.backend.qm_fake import (
    QM_FAKE_CONFIG_ENV,
    QMFakeBackend,
    QMFakeQubitDevice,
    load_qm_fake_settings,
    resolve_qm_fake_settings_path,
)
from tests.qdash.workflow.qm_helpers import (
    EXAMPLE_FAKE_SETTINGS_PATH,
    EXAMPLE_SETTINGS_PATH,
    REPO_ROOT,
)

QM_PACKAGES = ("qm", "qualang_tools")
CHIP_ID = "fake-chip"
QUA_CONFIG_FILE = str(EXAMPLE_SETTINGS_PATH.parent / "qua_config.yaml")


@pytest.fixture(autouse=True)
def without_qm_packages(monkeypatch: pytest.MonkeyPatch) -> None:
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


def _fake_data(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(EXAMPLE_FAKE_SETTINGS_PATH.read_text(encoding="utf-8"))
    data["qua_config_file"] = QUA_CONFIG_FILE
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return data


def _write(tmp_path: Path, data: dict[str, Any], name: str = "qm-fake.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


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

    def test_factory_creates_qm_fake_backend_without_connecting(self) -> None:
        backend = create_backend("qm-fake", {"chip_id": CHIP_ID})

        assert isinstance(backend, QMFakeBackend)
        assert backend.name == "qm-fake"
        assert not backend.is_connected
        assert backend.is_fake and not backend.is_hardware and not backend.is_simulator
        assert backend.mode == "fake"

    def test_factory_rejects_unknown_backend(self) -> None:
        with pytest.raises(ValueError, match="'qm' and 'qm-fake'"):
            create_backend("qm-mock", {})


class TestWithoutQMPackages:
    def test_connect_fails_with_the_install_hint(self) -> None:
        backend = create_backend("qm-fake", {"qm_fake_config_path": EXAMPLE_FAKE_SETTINGS_PATH})

        with pytest.raises(QMDependencyError, match=r"uv sync --package qdash-workflow --extra qm"):
            backend.connect()
        assert not backend.is_connected

    def test_task_run_fails_instead_of_producing_a_response(self) -> None:
        backend = create_backend("qm-fake", {"qm_fake_config_path": EXAMPLE_FAKE_SETTINGS_PATH})

        assert isinstance(backend, QMFakeBackend)

        with pytest.raises(QMDependencyError, match="standard QDash workflow image"):
            QMAmplitudeRabi().run(backend, "0")
        assert not backend.is_connected

    def test_invalid_settings_fail_before_the_package_check(self, tmp_path: Path) -> None:
        backend = QMFakeBackend({"qm_fake_config_path": tmp_path / "absent.yaml"})

        with pytest.raises(QMConfigurationError, match="settings file not found"):
            backend.connect()

    def test_version_names_the_sdk_packages(self) -> None:
        version = QMFakeBackend({}).version()

        assert version.startswith("qm-fake (QDash fake QOP device)")
        assert "qm-qua" in version and "qualang-tools" in version


class TestSettings:
    def test_example_fake_settings_are_valid(self) -> None:
        settings = load_qm_fake_settings(EXAMPLE_FAKE_SETTINGS_PATH)
        hardware = load_qm_settings(EXAMPLE_SETTINGS_PATH)

        assert settings.seed == 1234
        assert settings.qop_version == 2
        # The fake device reads the same QUA configuration and bindings as qm.yaml.
        assert settings.qua_config == hardware.qua_config
        assert settings.qubits == hardware.qubits
        assert settings.device["0"] == QMFakeQubitDevice()

    def test_example_pi_rotation_lies_inside_the_default_sweep(self) -> None:
        settings = load_qm_fake_settings(EXAMPLE_FAKE_SETTINGS_PATH)
        drive = settings.qua_config["waveforms"]["x180_wf"]["sample"]
        area = drive * settings.drive_pulse_length("0")
        pi_scale = settings.device["0"].pi_pulse_area / area
        default_scales = QMAmplitudeRabi().sweep().amplitude_scales

        assert pi_scale == pytest.approx(0.6)
        assert 0.2 < pi_scale < 0.8 * float(default_scales.max())

    def test_empty_device_entry_uses_defaults(self, tmp_path: Path) -> None:
        path = _write(tmp_path, _fake_data(device={0: None}, seed=None))

        settings = load_qm_fake_settings(path)

        assert settings.seed is None
        assert settings.device == {"0": QMFakeQubitDevice()}

    @pytest.mark.parametrize(
        ("extra", "named"),
        [
            ({"mode": "hardware"}, "mode"),
            ({"connection": {"host": "127.0.0.1"}}, "connection"),
            ({"simulation": {"duration_ns": 40_000}}, "simulation"),
        ],
    )
    def test_qop_server_settings_are_rejected(
        self, tmp_path: Path, extra: dict[str, Any], named: str
    ) -> None:
        with pytest.raises(QMConfigurationError, match=rf"without a QOP server; remove {named}"):
            load_qm_fake_settings(_write(tmp_path, _fake_data(**extra)))

    def test_hardware_settings_file_is_rejected(self) -> None:
        with pytest.raises(QMConfigurationError, match="remove mode, connection, simulation"):
            load_qm_fake_settings(EXAMPLE_SETTINGS_PATH)

    def test_former_response_only_layout_points_to_device(self, tmp_path: Path) -> None:
        data = {"seed": 1, "qubits": {"0": {"pi_amplitude_scale": 0.6, "contrast": 0.01}}}

        with pytest.raises(QMConfigurationError, match="under 'device'"):
            load_qm_fake_settings(_write(tmp_path, data))

    @pytest.mark.parametrize(
        ("changes", "message"),
        [
            ({"device": {}}, "device has no entry for qubit"),
            ({"device": {"0": {}, "1": {}}}, "without a binding"),
            ({"qua_config_file": None}, "set qua_config or qua_config_file"),
            ({"qubits": {}}, "at least one qubit"),
            ({"qop_version": 4}, "qop_version"),
            ({"seed": -1}, "seed"),
        ],
    )
    def test_inconsistent_settings_are_rejected(
        self, tmp_path: Path, changes: dict[str, Any], message: str
    ) -> None:
        with pytest.raises(QMConfigurationError, match=message):
            load_qm_fake_settings(_write(tmp_path, _fake_data(**changes)))

    @pytest.mark.parametrize(
        "device",
        [
            {"pi_amplitude_area": 4.8},  # typo of pi_pulse_area
            {"pi_pulse_area": 0.0},
            {"pi_pulse_area": float("nan")},
            {"noise_per_shot": -0.1},
            {"ground_iq": [0.0]},
            {"ground_iq": [0.01, 0.0], "excited_iq": [0.01, 0.0]},
        ],
    )
    def test_invalid_device_is_rejected(self, tmp_path: Path, device: dict[str, Any]) -> None:
        with pytest.raises(QMConfigurationError, match="Invalid qm-fake settings"):
            load_qm_fake_settings(_write(tmp_path, _fake_data(device={"0": device})))

    def test_two_qubits_cannot_share_a_drive_element(self, tmp_path: Path) -> None:
        data = _fake_data()
        data["qubits"]["1"] = dict(data["qubits"]["0"])
        data["device"]["1"] = {}

        with pytest.raises(QMConfigurationError, match="share qubit_element 'qubit'"):
            load_qm_fake_settings(_write(tmp_path, data))

    def test_missing_file_is_reported(self, tmp_path: Path) -> None:
        with pytest.raises(QMConfigurationError, match="qm-fake settings file not found"):
            load_qm_fake_settings(tmp_path / "qm-fake.yaml")

    @pytest.mark.parametrize("mode", ["mock", "fake"])
    def test_qm_backend_refuses_local_fake_mode(self, tmp_path: Path, mode: str) -> None:
        data = yaml.safe_load(EXAMPLE_SETTINGS_PATH.read_text())
        data["qua_config_file"] = QUA_CONFIG_FILE
        data["mode"] = mode

        with pytest.raises(QMConfigurationError, match="select backend 'qm-fake'"):
            load_qm_settings(_write(tmp_path, data, "qm.yaml"))


class TestSharedQuaValidation:
    """qm.yaml and qm-fake.yaml check the QUA bindings with the same rules."""

    @pytest.mark.parametrize(
        ("binding", "message"),
        [
            ({"qubit_element": "absent"}, "element 'absent' is not in qua_config"),
            ({"qubit_operation": "x90"}, "operation 'x90' is not defined for 'qubit'"),
            ({"outputs": ["out1", "out3"]}, r"output\(s\) out3 are not defined for 'resonator'"),
            (
                {"integration_weights": ["cos", "sin", "minus_cos", "cos"]},
                r"integration weight\(s\) minus_cos are not defined for pulse 'readout_pulse'",
            ),
            ({"integration_weights": ["cos", "sin"]}, "need 4 integration weights"),
        ],
    )
    def test_invalid_binding_is_rejected_by_both_backends(
        self, tmp_path: Path, binding: dict[str, Any], message: str
    ) -> None:
        fake = _fake_data()
        fake["qubits"]["0"].update(binding)
        hardware = yaml.safe_load(EXAMPLE_SETTINGS_PATH.read_text())
        hardware["qua_config_file"] = QUA_CONFIG_FILE
        hardware["qubits"]["0"].update(binding)

        with pytest.raises(QMConfigurationError, match=message):
            load_qm_fake_settings(_write(tmp_path, fake))
        with pytest.raises(QMConfigurationError, match=message):
            load_qm_settings(_write(tmp_path, hardware, "qm.yaml"))


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
