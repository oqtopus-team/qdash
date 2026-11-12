"""QM backend settings, lifecycle and optional-dependency behavior."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from tests.qdash.workflow.qm_helpers import (
    EXAMPLE_CONFIGURATION_PATH,
    EXAMPLE_FAKE_SETTINGS_PATH,
    EXAMPLE_SETTINGS_PATH,
    REPO_ROOT,
    StubQuantumMachinesManager,
    example_settings,
)

from qdash.common.config.loader import ConfigLoader
from qdash.workflow.engine.backend import qm as qm_backend
from qdash.workflow.engine.backend.factory import create_backend
from qdash.workflow.engine.backend.fake import FakeBackend
from qdash.workflow.engine.backend.qm import (
    QM_SETTINGS_ENV,
    QMBackend,
    QMConfigurationError,
    QMDependencyError,
    load_qm_settings,
    resolve_qm_settings_path,
)


def _write_settings(tmp_path: Path, **changes: Any) -> Path:
    data = yaml.safe_load(EXAMPLE_SETTINGS_PATH.read_text(encoding="utf-8"))
    data["qm_config_file"] = str(EXAMPLE_CONFIGURATION_PATH)
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    path = tmp_path / "qm.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


class TestSettings:
    def test_example_settings_are_valid(self) -> None:
        settings = load_qm_settings(EXAMPLE_SETTINGS_PATH)

        assert settings.mode == "simulator"
        assert settings.connection is not None
        assert settings.connection.host == "127.0.0.1"
        assert settings.simulation.duration_clock_cycles == 10_000
        assert settings.qubit("0").qubit_operation == "x180"
        assert settings.readout_pulse_length("0") == 200

    def test_mode_is_required(self, tmp_path: Path) -> None:
        with pytest.raises(QMConfigurationError, match="mode"):
            load_qm_settings(_write_settings(tmp_path, mode=None))

    def test_unknown_mode_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(QMConfigurationError, match="mode"):
            load_qm_settings(_write_settings(tmp_path, mode="cloud"))

    def test_unknown_operation_is_rejected(self, tmp_path: Path) -> None:
        qubits = {
            "0": {
                "qubit_element": "qubit",
                "qubit_operation": "missing_op",
                "readout_element": "resonator",
                "readout_operation": "readout",
            }
        }
        with pytest.raises(QMConfigurationError, match="missing_op"):
            load_qm_settings(_write_settings(tmp_path, qubits=qubits))

    def test_unknown_element_is_rejected(self, tmp_path: Path) -> None:
        qubits = {
            "0": {
                "qubit_element": "q9",
                "qubit_operation": "x180",
                "readout_element": "resonator",
                "readout_operation": "readout",
            }
        }
        with pytest.raises(QMConfigurationError, match="q9"):
            load_qm_settings(_write_settings(tmp_path, qubits=qubits))

    def test_integration_weight_count_must_match_outputs(self, tmp_path: Path) -> None:
        qubits = {
            "0": {
                "qubit_element": "qubit",
                "qubit_operation": "x180",
                "readout_element": "resonator",
                "readout_operation": "readout",
                "outputs": ["out1"],
            }
        }
        with pytest.raises(QMConfigurationError, match="integration weights"):
            load_qm_settings(_write_settings(tmp_path, qubits=qubits))

    def test_simulation_duration_must_be_whole_clock_cycles(self, tmp_path: Path) -> None:
        with pytest.raises(QMConfigurationError, match="multiple of the 4 ns"):
            load_qm_settings(_write_settings(tmp_path, simulation={"duration_ns": 1002}))

    def test_unknown_keys_are_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(QMConfigurationError, match="credentials"):
            load_qm_settings(_write_settings(tmp_path, credentials="secret"))

    @pytest.mark.parametrize("key", ["qua_config_file", "qua_config"])
    def test_former_qua_config_keys_point_to_the_native_configuration(
        self, tmp_path: Path, key: str
    ) -> None:
        with pytest.raises(QMConfigurationError, match=rf"{key} .*no longer supported.*config"):
            load_qm_settings(_write_settings(tmp_path, **{key: "qua_config.yaml"}))

    def test_native_configuration_is_required(self, tmp_path: Path) -> None:
        with pytest.raises(QMConfigurationError, match="set qm_config_file"):
            load_qm_settings(_write_settings(tmp_path, qm_config_file=None))

    def test_missing_files_are_reported(self, tmp_path: Path) -> None:
        with pytest.raises(QMConfigurationError, match="settings file not found"):
            load_qm_settings(tmp_path / "absent.yaml")
        with pytest.raises(QMConfigurationError, match="QM configuration file not found"):
            load_qm_settings(_write_settings(tmp_path, qm_config_file="absent.py"))

    @pytest.mark.parametrize("name", ["qua_config.yaml", "qua_config.json"])
    def test_configuration_must_be_python(self, tmp_path: Path, name: str) -> None:
        (tmp_path / name).write_text("{}", encoding="utf-8")

        with pytest.raises(QMConfigurationError, match="must be a Python file"):
            load_qm_settings(_write_settings(tmp_path, qm_config_file=name))

    def test_configuration_path_is_relative_to_the_settings_file(self, tmp_path: Path) -> None:
        native = tmp_path / "qm-config" / "chip-1"
        native.mkdir(parents=True)
        (native / "configuration.py").write_text(
            EXAMPLE_CONFIGURATION_PATH.read_text(encoding="utf-8"), encoding="utf-8"
        )
        settings_dir = tmp_path / "qm-backend" / "chip-1"
        settings_dir.mkdir(parents=True)

        path = _write_settings(
            settings_dir, qm_config_file="../../qm-config/chip-1/configuration.py"
        )

        assert load_qm_settings(path).qubit("0").qubit_element == "qubit"

    def test_unconfigured_qubit_is_reported(self) -> None:
        with pytest.raises(QMConfigurationError, match=r"Qubit 5 .*configured: 0"):
            example_settings().qubit("5")


class TestServerSettings:
    def test_connection_is_required(self, tmp_path: Path) -> None:
        with pytest.raises(QMConfigurationError, match="connection"):
            load_qm_settings(_write_settings(tmp_path, connection=None))

    def test_simulation_duration_is_bounded(self, tmp_path: Path) -> None:
        with pytest.raises(QMConfigurationError, match="duration_ns"):
            load_qm_settings(_write_settings(tmp_path, simulation={"duration_ns": 2_000_000}))

    def test_cloud_section_is_rejected(self, tmp_path: Path) -> None:
        # The backend has no hosted simulator support; such a section is an unknown key.
        with pytest.raises(QMConfigurationError, match="cloud"):
            load_qm_settings(_write_settings(tmp_path, cloud={"qop_version": "v2_6_0"}))


class TestSettingsPath:
    @pytest.fixture(autouse=True)
    def _clean_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in (QM_SETTINGS_ENV, "QDASH_QM_CONFIG", "QDASH_QM_FAKE_CONFIG"):
            monkeypatch.delenv(name, raising=False)

    def test_defaults_to_chip_directory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ConfigLoader, "get_config_dir", classmethod(lambda cls: Path("/cfg")))

        path = resolve_qm_settings_path({"chip_id": "chip-1"})

        assert path == Path("/cfg/qm-backend/chip-1/qm.yaml")

    def test_environment_variable_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(QM_SETTINGS_ENV, "/elsewhere/qm.yaml")

        assert resolve_qm_settings_path({"chip_id": "chip-1"}) == Path("/elsewhere/qm.yaml")

    def test_session_option_overrides_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(QM_SETTINGS_ENV, "/elsewhere/qm.yaml")
        config = {"chip_id": "chip-1", "qm_settings_path": "/explicit/qm.yaml"}

        assert resolve_qm_settings_path(config) == Path("/explicit/qm.yaml")

    def test_needs_a_chip_or_path(self) -> None:
        with pytest.raises(QMConfigurationError, match="chip_id"):
            resolve_qm_settings_path({})

    def test_renamed_session_option_is_rejected(self) -> None:
        with pytest.raises(
            QMConfigurationError, match="qm_config_path was renamed to qm_settings_path"
        ):
            resolve_qm_settings_path({"chip_id": "chip-1", "qm_config_path": "/x/qm.yaml"})

    def test_renamed_environment_variable_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("QDASH_QM_CONFIG", "/x/qm.yaml")

        with pytest.raises(QMConfigurationError, match="renamed to QDASH_QM_SETTINGS"):
            resolve_qm_settings_path({"chip_id": "chip-1"})

    def test_former_layout_is_reported_instead_of_read(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(ConfigLoader, "get_config_dir", classmethod(lambda cls: tmp_path))
        former = tmp_path / "qm-config" / "chip-1" / "qm.yaml"
        former.parent.mkdir(parents=True)
        former.write_text("mode: simulator\n", encoding="utf-8")

        with pytest.raises(
            QMConfigurationError, match=r"former layout.*qm-backend/chip-1/qm\.yaml"
        ):
            resolve_qm_settings_path({"chip_id": "chip-1"})

    def test_missing_default_file_is_not_replaced_by_another(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(ConfigLoader, "get_config_dir", classmethod(lambda cls: tmp_path))

        path = resolve_qm_settings_path({"chip_id": "chip-1"})

        with pytest.raises(QMConfigurationError, match="settings file not found"):
            load_qm_settings(path)


class TestLifecycle:
    @pytest.fixture
    def stub_sdk(self, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
        calls: list[dict[str, Any]] = []
        manager = StubQuantumMachinesManager()

        def factory(**kwargs: Any) -> StubQuantumMachinesManager:
            calls.append(kwargs)
            return manager

        sdk = SimpleNamespace(QuantumMachinesManager=factory, __version__="9.9.9")
        monkeypatch.setattr(qm_backend, "import_qm_sdk", lambda: sdk)
        return SimpleNamespace(calls=calls, manager=manager)

    def test_factory_creates_qm_backend_without_connecting(self) -> None:
        backend = create_backend("qm", {"chip_id": "chip-1"})

        assert isinstance(backend, QMBackend)
        assert backend.name == "qm"
        assert not backend.is_connected

    def test_connect_passes_connection_settings(
        self, tmp_path: Path, stub_sdk: SimpleNamespace
    ) -> None:
        path = _write_settings(
            tmp_path,
            connection={"host": "opx.local", "port": 9510, "cluster_name": "c1", "timeout": 30},
        )
        backend = QMBackend({"qm_settings_path": str(path)})

        backend.connect()
        backend.connect()

        assert stub_sdk.calls == [
            {"host": "opx.local", "port": 9510, "cluster_name": "c1", "timeout": 30.0}
        ]
        session = backend.get_instance()
        assert session.manager is stub_sdk.manager
        assert session.is_simulator
        assert backend.version() == "qm-qua 9.9.9"

    def test_get_instance_connects_on_demand(self, stub_sdk: SimpleNamespace) -> None:
        backend = QMBackend({"qm_settings": example_settings("hardware")})

        session = backend.get_instance()

        assert backend.is_connected
        assert session.mode == "hardware"
        assert not backend.is_simulator
        assert stub_sdk.calls == [{"host": "127.0.0.1", "port": 80}]

    def test_disconnect_closes_manager_once(self, stub_sdk: SimpleNamespace) -> None:
        backend = QMBackend({"qm_settings": example_settings()})
        backend.connect()

        backend.disconnect()
        backend.disconnect()

        assert stub_sdk.manager.closed == 1
        assert not backend.is_connected

    def test_disconnect_is_safe_without_connection(self) -> None:
        backend = QMBackend({})

        backend.disconnect()

        assert not backend.is_connected

    def test_invalid_settings_fail_before_importing_sdk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail() -> None:
            raise AssertionError("SDK must not be imported")

        monkeypatch.setattr(qm_backend, "import_qm_sdk", fail)
        backend = QMBackend({"qm_settings_path": str(_write_settings(tmp_path, mode=None))})

        with pytest.raises(QMConfigurationError):
            backend.connect()
        assert not backend.is_connected


class TestMissingDependency:
    def test_connect_reports_install_hint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "qm", None)
        backend = QMBackend({"qm_settings": example_settings()})

        with pytest.raises(QMDependencyError, match="--extra qm"):
            backend.connect()
        assert not backend.is_connected
        assert backend.version() == "qm-qua (not installed)"

    def test_default_backends_import_without_qm_packages(self) -> None:
        """The task registry and the qubex/fake/qm/qm-fake backends import without the QM SDK.

        A qm-fake run needs the SDK: connecting fails with the install hint instead of
        falling back to another response.
        """
        script = textwrap.dedent(
            """
            import sys

            class Block:
                def find_spec(self, name, path=None, target=None):
                    if name.split(".")[0] in {"qm", "qualang_tools"}:
                        raise ImportError(f"blocked {name}")
                    return None

            sys.meta_path.insert(0, Block())
            import qdash.workflow.calibtasks as calibtasks
            from qdash.workflow.engine.backend.factory import create_backend
            from qdash.workflow.engine.backend.qm import QMDependencyError

            assert "QMAmplitudeRabi" in calibtasks.BaseTask.registry["qm"]
            assert "CheckRabi" in calibtasks.BaseTask.registry["fake"]
            assert create_backend("fake", {}).name == "fake"
            assert create_backend("qm", {}).name == "qm"
            assert calibtasks.BaseTask.registry["qm-fake"]["QMAmplitudeRabi"] is (
                calibtasks.BaseTask.registry["qm"]["QMAmplitudeRabi"]
            )
            fake = create_backend("qm-fake", {"qm_fake_settings_path": sys.argv[1]})
            assert fake.settings.qubits["0"].qubit_element == "qubit"
            task = calibtasks.BaseTask.registry["qm-fake"]["QMAmplitudeRabi"]()
            try:
                task.run(fake, "0")
            except QMDependencyError as exc:
                assert "--extra qm" in str(exc), exc
                assert "standard QDash workflow image" in str(exc), exc
            else:
                raise AssertionError("qm-fake must not run without the QM packages")
            assert not fake.is_connected
            assert not any(
                m.split(".")[0] in {"qm", "qualang_tools"} for m in sys.modules
            )
            """
        )
        completed = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-c",
                script,
                str(EXAMPLE_FAKE_SETTINGS_PATH),
            ],
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
            capture_output=True,
            text=True,
            check=False,
        )

        assert completed.returncode == 0, completed.stderr


def test_existing_backends_are_unchanged() -> None:
    assert isinstance(create_backend("fake", {}), FakeBackend)
    with pytest.raises(ValueError, match="'qubex', 'fake', 'qm' and 'qm-fake'"):
        create_backend("unknown", {})
