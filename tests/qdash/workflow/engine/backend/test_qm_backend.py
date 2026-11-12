"""QM backend settings, lifecycle and optional-dependency behavior."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from tests.qdash.workflow.qm_helpers import (
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
    QM_CONFIG_ENV,
    QMBackend,
    QMCloudError,
    QMCloudSettings,
    QMConfigurationError,
    QMDependencyError,
    load_qm_settings,
    resolve_qm_settings_path,
)


def _write_settings(tmp_path: Path, **changes: Any) -> Path:
    data = yaml.safe_load(EXAMPLE_SETTINGS_PATH.read_text(encoding="utf-8"))
    data["qua_config_file"] = str(EXAMPLE_SETTINGS_PATH.parent / data["qua_config_file"])
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

    def test_inline_and_file_qua_config_are_exclusive(self, tmp_path: Path) -> None:
        with pytest.raises(QMConfigurationError, match="either qua_config"):
            load_qm_settings(_write_settings(tmp_path, qua_config={"elements": {}}))

    def test_missing_files_are_reported(self, tmp_path: Path) -> None:
        with pytest.raises(QMConfigurationError, match="settings file not found"):
            load_qm_settings(tmp_path / "absent.yaml")
        with pytest.raises(QMConfigurationError, match="QUA configuration file not found"):
            load_qm_settings(_write_settings(tmp_path, qua_config_file="absent.json"))

    def test_unconfigured_qubit_is_reported(self) -> None:
        with pytest.raises(QMConfigurationError, match=r"Qubit 5 .*configured: 0"):
            example_settings().qubit("5")


CLOUD = {"qop_version": "v2_6_0"}


class TestCloudSettings:
    def test_cloud_replaces_connection(self, tmp_path: Path) -> None:
        settings = load_qm_settings(_write_settings(tmp_path, connection=None, cloud=CLOUD))

        assert settings.connection is None
        assert settings.cloud is not None
        assert settings.cloud.qop_major == 2
        assert settings.cloud.email_env == "QM_SAAS_EMAIL"
        assert settings.cloud.password_env == "QM_SAAS_PASSWORD"  # noqa: S105

    @pytest.mark.parametrize(
        ("changes", "message"),
        [
            ({"cloud": CLOUD}, "exactly one"),
            ({"connection": None}, "exactly one"),
            ({"connection": None, "cloud": CLOUD, "mode": "hardware"}, "mode: simulator"),
            ({"connection": None, "cloud": {}}, "qop_version"),
            ({"connection": None, "cloud": {"qop_version": "latest"}}, "v<major>"),
            ({"connection": None, "cloud": {"qop_version": "v1_0_0"}}, "2.x"),
            ({"connection": None, "cloud": {"qop_version": "v3_8_1"}}, r"OPX\+"),
            ({"connection": None, "cloud": {**CLOUD, "password": "x"}}, "password"),
            ({"connection": None, "cloud": {**CLOUD, "email_env": "a-b"}}, "email_env"),
        ],
    )
    def test_rejects_invalid_cloud_settings(
        self, tmp_path: Path, changes: dict[str, Any], message: str
    ) -> None:
        with pytest.raises(QMConfigurationError, match=message):
            load_qm_settings(_write_settings(tmp_path, **changes))

    def test_opx1000_config_needs_qop_3(self) -> None:
        settings = example_settings()
        qua_config = {
            **settings.qua_config,
            "controllers": {"con1": {"type": "opx1000", "fems": {}}},
        }
        data = settings.model_dump() | {"connection": None, "qua_config": qua_config}

        with pytest.raises(ValueError, match="OPX1000"):
            type(settings).model_validate(data | {"cloud": CLOUD})
        assert type(settings).model_validate(data | {"cloud": {"qop_version": "v3_8_1"}})

    def test_simulation_duration_is_bounded(self, tmp_path: Path) -> None:
        with pytest.raises(QMConfigurationError, match="duration_ns"):
            load_qm_settings(_write_settings(tmp_path, simulation={"duration_ns": 2_000_000}))

    def test_missing_credentials_name_variables_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QM_SAAS_EMAIL", "user@example.test")
        monkeypatch.delenv("QM_SAAS_PASSWORD", raising=False)

        with pytest.raises(QMConfigurationError) as excinfo:
            QMCloudSettings(qop_version="v2_6_0").read_credentials()

        assert "QM_SAAS_PASSWORD" in str(excinfo.value)
        assert "user@example.test" not in str(excinfo.value)


class TestSettingsPath:
    def test_defaults_to_chip_directory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(QM_CONFIG_ENV, raising=False)
        monkeypatch.setattr(ConfigLoader, "get_config_dir", classmethod(lambda cls: Path("/cfg")))

        path = resolve_qm_settings_path({"chip_id": "chip-1"})

        assert path == Path("/cfg/qm-config/chip-1/qm.yaml")

    def test_environment_variable_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(QM_CONFIG_ENV, "/elsewhere/qm.yaml")

        assert resolve_qm_settings_path({"chip_id": "chip-1"}) == Path("/elsewhere/qm.yaml")

    def test_session_option_overrides_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(QM_CONFIG_ENV, "/elsewhere/qm.yaml")
        config = {"chip_id": "chip-1", "qm_config_path": "/explicit/qm.yaml"}

        assert resolve_qm_settings_path(config) == Path("/explicit/qm.yaml")

    def test_needs_a_chip_or_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(QM_CONFIG_ENV, raising=False)

        with pytest.raises(QMConfigurationError, match="chip_id"):
            resolve_qm_settings_path({})


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
        backend = QMBackend({"qm_config_path": str(path)})

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
        backend = QMBackend({"qm_config_path": str(_write_settings(tmp_path, mode=None))})

        with pytest.raises(QMConfigurationError):
            backend.connect()
        assert not backend.is_connected


@dataclass
class FakeSaasInstance:
    """Mimics ``qm_saas.QmSaasInstance``: spawn/close and the connection parameters."""

    version: str
    fail_spawn: bool = False
    fail_close: bool = False
    alive: bool = True
    spawned: int = 0
    closed: int = 0
    id: str = "sim-1"
    expires_at: str = "2026-11-12T00:15:00"

    def spawn(self) -> None:
        if self.fail_spawn:
            raise RuntimeError("spawn failed")
        self.spawned += 1

    def close(self) -> None:
        self.closed += 1
        if self.fail_close:
            raise RuntimeError("close failed")

    @property
    def is_alive(self) -> bool:
        return self.alive

    @property
    def qmm_connection_params(self) -> dict[str, Any]:
        return {
            "host": "sim-1.example.test",
            "port": 443,
            "connection_headers": {"simulation-id": self.id, "simulation-auth": "token"},
            "credentials": "ssl-context",
            "follow_gateway_redirections": False,
        }


@dataclass
class FakeSaasSdk:
    """Fake ``qm_saas`` module recording logins and spawned instances."""

    versions: tuple[str, ...] = ("v2_6_0", "v3_8_1")
    fail_login: bool = False
    fail_spawn: bool = False
    logins: list[dict[str, Any]] = field(default_factory=list)
    instances: list[FakeSaasInstance] = field(default_factory=list)
    close_all_calls: int = 0

    def QOPVersion(self, name: str) -> str:
        return name

    def QmSaas(self, **kwargs: Any) -> SimpleNamespace:
        self.logins.append(kwargs)
        if self.fail_login:
            kwargs["log"].error("Authentication for %s failed: HTTP401", kwargs["email"])
            raise Exception("Authentication failed: invalid credentials")

        def simulator(version: str) -> FakeSaasInstance:
            instance = FakeSaasInstance(version=version, fail_spawn=self.fail_spawn)
            self.instances.append(instance)
            return instance

        def close_all() -> None:
            self.close_all_calls += 1

        return SimpleNamespace(
            versions=lambda: list(self.versions), simulator=simulator, close_all=close_all
        )


class TestCloudLifecycle:
    @pytest.fixture
    def sdks(self, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
        managers: list[dict[str, Any]] = []
        manager = StubQuantumMachinesManager()
        state = SimpleNamespace(managers=managers, manager=manager, fail_manager=False)

        def factory(**kwargs: Any) -> StubQuantumMachinesManager:
            managers.append(kwargs)
            if state.fail_manager:
                raise RuntimeError("gRPC connection failed")
            return manager

        saas = FakeSaasSdk()
        state.saas = saas
        monkeypatch.setattr(
            qm_backend, "import_qm_sdk", lambda: SimpleNamespace(QuantumMachinesManager=factory)
        )
        monkeypatch.setattr(qm_backend, "import_qm_saas", lambda: saas)
        monkeypatch.setenv("QM_SAAS_EMAIL", "user@example.test")
        monkeypatch.setenv("QM_SAAS_PASSWORD", "pw-value")
        return state

    @staticmethod
    def _backend() -> QMBackend:
        settings = example_settings().model_copy(
            update={"connection": None, "cloud": QMCloudSettings(qop_version="v2_6_0")}
        )
        return QMBackend({"qm_settings": settings})

    def test_connect_spawns_one_instance_and_uses_its_params(self, sdks: SimpleNamespace) -> None:
        backend = self._backend()

        backend.connect()
        backend.connect()
        session = backend.get_instance()

        (login,) = sdks.saas.logins
        assert login["email"] == "user@example.test"
        assert login["password"] == "pw-value"  # noqa: S105
        assert login["host"] == "qm-saas.quantum-machines.co"
        assert login["port"] == 443
        (instance,) = sdks.saas.instances
        assert instance.version == "v2_6_0"
        assert instance.spawned == 1
        assert sdks.managers == [instance.qmm_connection_params]
        assert session.manager is sdks.manager
        assert session.is_simulator

    def test_disconnect_closes_manager_and_instance_once(self, sdks: SimpleNamespace) -> None:
        backend = self._backend()
        backend.connect()

        backend.disconnect()
        backend.disconnect()

        assert sdks.manager.closed == 1
        assert sdks.saas.instances[0].closed == 1
        assert sdks.saas.close_all_calls == 0
        assert not backend.is_connected

    def test_failed_manager_connection_closes_the_spawned_instance(
        self, sdks: SimpleNamespace
    ) -> None:
        sdks.fail_manager = True
        backend = self._backend()

        with pytest.raises(RuntimeError, match="gRPC"):
            backend.connect()

        assert sdks.saas.instances[0].closed == 1
        assert not backend.is_connected
        backend.disconnect()
        assert sdks.saas.instances[0].closed == 1

    def test_failed_spawn_is_cleaned_up(self, sdks: SimpleNamespace) -> None:
        sdks.saas.fail_spawn = True
        backend = self._backend()

        with pytest.raises(RuntimeError, match="spawn failed"):
            backend.connect()

        # Closing an unspawned qm-saas instance is a no-op in the SDK.
        assert sdks.saas.instances[0].closed == 1
        assert sdks.managers == []

    def test_close_failure_is_logged_not_raised(
        self, sdks: SimpleNamespace, caplog: pytest.LogCaptureFixture
    ) -> None:
        backend = self._backend()
        backend.connect()
        sdks.saas.instances[0].fail_close = True

        with caplog.at_level(logging.WARNING):
            backend.disconnect()

        assert sdks.manager.closed == 1
        assert "stays allocated until it expires" in caplog.text
        assert not backend.is_connected

    def test_manager_close_failure_still_closes_instance(self, sdks: SimpleNamespace) -> None:
        backend = self._backend()
        backend.connect()

        def fail() -> None:
            raise RuntimeError("manager close failed")

        sdks.manager.close = fail

        with pytest.raises(RuntimeError, match="manager close failed"):
            backend.disconnect()
        assert sdks.saas.instances[0].closed == 1
        assert not backend.is_connected

    def test_expired_instance_is_replaced(self, sdks: SimpleNamespace) -> None:
        backend = self._backend()
        backend.connect()
        sdks.saas.instances[0].alive = False

        backend.get_instance()

        first, second = sdks.saas.instances
        assert first.closed == 1
        assert second.spawned == 1

    def test_unknown_version_fails_before_spawning(self, sdks: SimpleNamespace) -> None:
        sdks.saas.versions = ("v2_4_4",)
        backend = self._backend()

        with pytest.raises(QMConfigurationError, match=r"v2_6_0; available: v2_4_4"):
            backend.connect()
        assert sdks.saas.instances == []

    def test_login_failure_redacts_credentials(
        self, sdks: SimpleNamespace, caplog: pytest.LogCaptureFixture
    ) -> None:
        sdks.saas.fail_login = True
        backend = self._backend()

        with caplog.at_level(logging.DEBUG), pytest.raises(QMCloudError) as excinfo:
            backend.connect()

        for text in (str(excinfo.value), caplog.text):
            assert "user@example.test" not in text
            assert "pw-value" not in text
        assert "Authentication for *** failed" in caplog.text
        assert excinfo.value.__cause__ is None
        assert not backend.is_connected

    def test_missing_credentials_fail_before_login(
        self, sdks: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("QM_SAAS_PASSWORD")

        with pytest.raises(QMConfigurationError, match="QM_SAAS_PASSWORD"):
            self._backend().connect()
        assert sdks.saas.logins == []

    def test_missing_qm_saas_reports_install_hint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "qm_saas", None)
        monkeypatch.setattr(qm_backend, "import_qm_sdk", SimpleNamespace)

        with pytest.raises(QMDependencyError, match="--extra qm-cloud"):
            self._backend().connect()


class TestMissingDependency:
    def test_connect_reports_install_hint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "qm", None)
        backend = QMBackend({"qm_settings": example_settings()})

        with pytest.raises(QMDependencyError, match="--extra qm"):
            backend.connect()
        assert not backend.is_connected
        assert backend.version() == "qm-qua (not installed)"

    def test_default_backends_import_without_qm_packages(self) -> None:
        """The task registry, the qubex/fake/qm backends and a qm-fake run need no QM SDK."""
        script = textwrap.dedent(
            """
            import sys

            class Block:
                def find_spec(self, name, path=None, target=None):
                    if name.split(".")[0] in {"qm", "qualang_tools", "qm_saas"}:
                        raise ImportError(f"blocked {name}")
                    return None

            sys.meta_path.insert(0, Block())
            import qdash.workflow.calibtasks as calibtasks
            from qdash.workflow.engine.backend.factory import create_backend

            assert "QMAmplitudeRabi" in calibtasks.BaseTask.registry["qm"]
            assert "CheckRabi" in calibtasks.BaseTask.registry["fake"]
            assert create_backend("fake", {}).name == "fake"
            assert create_backend("qm", {}).name == "qm"
            assert calibtasks.BaseTask.registry["qm-fake"]["QMAmplitudeRabi"] is (
                calibtasks.BaseTask.registry["qm"]["QMAmplitudeRabi"]
            )
            fake = create_backend("qm-fake", {"qm_fake_config_path": sys.argv[1]})
            task = calibtasks.BaseTask.registry["qm-fake"]["QMAmplitudeRabi"]()
            assert task.run(fake, "0").r2["0"] > 0.98
            fake.disconnect()
            assert not any(
                m.split(".")[0] in {"qm", "qualang_tools", "qm_saas"} for m in sys.modules
            )
            """
        )
        completed = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-c",
                script,
                str(REPO_ROOT / "config/qm-config/example-fake/qm-fake.yaml"),
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
