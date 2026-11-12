"""Quantum Machines (OPX) backend.

The backend connects to a Quantum Orchestration Platform (QOP) server through the
``qm-qua`` SDK. The SDK and ``qualang-tools`` are optional dependencies (the workflow
project's ``qm`` extra) and are imported only when the backend connects, so the
qubex and fake backends keep working without them.

Each backend runs in one of three explicit modes, set in the QM settings file:

``hardware``
    Programs are executed on the OPX. Tasks may fit the measured response and
    publish calibration values.
``simulator``
    Programs are sent to the QOP simulator (``QuantumMachinesManager.simulate``).
    The simulator returns the controller output waveforms only: it verifies pulse
    timing and amplitudes, not the physical response of a qubit. Tasks never
    publish calibration values in this mode.
``mock``
    No QOP server and no QM package is involved. A local ``QMMockDevice``
    (``qm_mock.py``) answers with a synthetic averaged I/Q response, which tasks
    analyze exactly like a hardware measurement. Results stay in the run history,
    labelled as mock; they never replace calibration values. A mock settings file
    holds a ``mock`` section and must not hold ``connection``, ``cloud``,
    ``simulation``, ``qubits`` or a QUA configuration.

In hardware and simulator mode the backend reaches the QOP server in one of two ways:

``connection``
    A QOP server at a fixed host, as ``QuantumMachinesManager(host=...)`` takes it.
``cloud``
    A QM SaaS cloud simulator instance (``qm-saas``, the workflow ``qm-cloud`` extra),
    simulator mode only. The backend logs in with credentials read from named
    environment variables, spawns one instance of the configured QOP version, connects
    with ``QuantumMachinesManager(**instance.qmm_connection_params)`` and closes that
    instance again on disconnect or on a failed connect. It never closes instances it
    did not spawn.

The settings file defaults to ``<config dir>/qm-config/<chip_id>/qm.yaml``. The
``qm_config_path`` session option or the ``QDASH_QM_CONFIG`` environment variable
overrides that path.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from qdash.common.config.loader import ConfigLoader
from qdash.workflow.engine.backend.base import BaseBackend
from qdash.workflow.engine.backend.qm_mock import QM_MOCK_VERSION, QMMockDevice, QMMockSettings

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)

QM_CONFIG_DIR_NAME = "qm-config"
QM_SETTINGS_FILE_NAME = "qm.yaml"
QM_CONFIG_ENV = "QDASH_QM_CONFIG"
QM_INSTALL_HINT = (
    "The QM backend needs the optional Quantum Machines packages. "
    "Install them with: uv sync --package qdash-workflow --extra qm"
)
QM_CLOUD_INSTALL_HINT = (
    "The QM cloud simulator needs the optional qm-saas package. "
    "Install it with: uv sync --package qdash-workflow --extra qm-cloud"
)
QM_SAAS_DEFAULT_HOST = "qm-saas.quantum-machines.co"
QM_SAAS_DEFAULT_EMAIL_ENV = "QM_SAAS_EMAIL"
QM_SAAS_DEFAULT_PASSWORD_ENV = "QM_SAAS_PASSWORD"  # noqa: S105 - variable name, not a secret
# QOP release names as qm-saas spells them, for example v2_6_0.
QOP_VERSION_PATTERN = re.compile(r"^v(\d+)_(\d+)_(\d+)$")
# QOP 2.x simulates OPX+ controllers, QOP 3.x simulates OPX1000 controllers.
QOP_MAJOR_OPX_PLUS = 2
QOP_MAJOR_OPX1000 = 3
# Upper bound on the simulated program time, which bounds the samples the simulator returns.
MAX_SIMULATION_DURATION_NS = 1_000_000

QMMode = Literal["hardware", "simulator", "mock"]
# Settings that only make sense with a QOP server; a mock settings file must not set them.
QOP_ONLY_SETTINGS = ("connection", "cloud", "simulation", "qubits", "qua_config")


class QMDependencyError(ImportError):
    """Raised when the optional Quantum Machines packages are not installed."""


class QMConfigurationError(ValueError):
    """Raised when the QM settings file is missing or invalid."""


class QMCloudError(RuntimeError):
    """Raised when the QM SaaS cloud simulator cannot be reached or started."""


class QMConnectionSettings(BaseModel):
    """Address of the QOP server, passed to ``QuantumMachinesManager``."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1)
    port: int | None = Field(default=None, gt=0, lt=65536)
    cluster_name: str | None = None
    timeout: float | None = Field(default=None, gt=0)


class QMCloudSettings(BaseModel):
    """QM SaaS cloud simulator, used instead of ``connection`` in simulator mode.

    The settings hold the names of the environment variables with the credentials,
    never the credentials themselves.
    """

    model_config = ConfigDict(extra="forbid")

    qop_version: str = Field(
        description="QOP version of the simulator instance, for example v2_6_0 (OPX+)"
    )
    email_env: str = Field(default=QM_SAAS_DEFAULT_EMAIL_ENV, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    password_env: str = Field(
        default=QM_SAAS_DEFAULT_PASSWORD_ENV, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"
    )
    host: str = Field(default=QM_SAAS_DEFAULT_HOST, min_length=1)
    port: int = Field(default=443, gt=0, lt=65536)

    @field_validator("qop_version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        match = QOP_VERSION_PATTERN.match(value)
        if match is None:
            raise ValueError("qop_version must look like v<major>_<minor>_<patch>, e.g. v2_6_0")
        if int(match.group(1)) not in (QOP_MAJOR_OPX_PLUS, QOP_MAJOR_OPX1000):
            raise ValueError("qop_version must be a QOP 2.x (OPX+) or 3.x (OPX1000) version")
        return value

    @property
    def qop_major(self) -> int:
        """Major QOP version, which selects the simulated controller family."""
        match = QOP_VERSION_PATTERN.match(self.qop_version)
        assert match is not None
        return int(match.group(1))

    def read_credentials(self) -> tuple[str, str]:
        """Return the email and password from the configured environment variables.

        Error messages name the variables only, never their values.
        """
        missing = [name for name in (self.email_env, self.password_env) if not os.environ.get(name)]
        if missing:
            raise QMConfigurationError(
                "QM cloud simulator credentials are missing; set the environment "
                f"variable(s) {', '.join(missing)}"
            )
        return os.environ[self.email_env], os.environ[self.password_env]


class QMQubitSettings(BaseModel):
    """QUA configuration names used to drive and read out one qubit.

    The names follow ``qualang_tools.addons.calibration.calibrations.QUA_calibrations``:
    ``qubit``/``readout`` are ``(element, operation)`` pairs, ``integration_weights``
    holds four names for dual demodulation (two names with a single output), and
    ``outputs`` names the readout element outputs.
    """

    model_config = ConfigDict(extra="forbid")

    qubit_element: str = Field(min_length=1)
    qubit_operation: str = Field(min_length=1)
    readout_element: str = Field(min_length=1)
    readout_operation: str = Field(min_length=1)
    integration_weights: tuple[str, ...] = ("cos", "sin", "minus_sin", "cos")
    outputs: tuple[str, ...] = ("out1", "out2")

    @model_validator(mode="after")
    def _check_demodulation(self) -> QMQubitSettings:
        expected = {1: 2, 2: 4}.get(len(self.outputs))
        if expected is None:
            raise ValueError("outputs must name one or two readout element outputs")
        if len(self.integration_weights) != expected:
            raise ValueError(
                f"{len(self.outputs)} output(s) need {expected} integration weights, "
                f"got {len(self.integration_weights)}"
            )
        return self


class QMSimulationSettings(BaseModel):
    """Simulator options used in ``simulator`` mode."""

    model_config = ConfigDict(extra="forbid")

    duration_ns: int = Field(default=40_000, gt=0, le=MAX_SIMULATION_DURATION_NS)

    @field_validator("duration_ns")
    @classmethod
    def _multiple_of_clock_cycle(cls, value: int) -> int:
        if value % 4:
            raise ValueError("duration_ns must be a multiple of the 4 ns clock cycle")
        return value

    @property
    def duration_clock_cycles(self) -> int:
        """Simulation duration in 4 ns clock cycles, the unit ``SimulationConfig`` takes."""
        return self.duration_ns // 4


class QMBackendSettings(BaseModel):
    """Validated contents of a QM settings file."""

    model_config = ConfigDict(extra="forbid")

    mode: QMMode
    connection: QMConnectionSettings | None = None
    cloud: QMCloudSettings | None = None
    simulation: QMSimulationSettings = Field(default_factory=QMSimulationSettings)
    qubits: dict[str, QMQubitSettings] = Field(default_factory=dict)
    qua_config: dict[str, Any] = Field(default_factory=dict)
    mock: QMMockSettings | None = None

    @field_validator("qubits", mode="before")
    @classmethod
    def _string_qids(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(qid): settings for qid, settings in value.items()}
        return value

    @model_validator(mode="before")
    @classmethod
    def _reject_server_settings_in_mock_mode(cls, data: Any) -> Any:
        # Checked before field validation, so a stray section gets this message instead
        # of errors about its own fields.
        if isinstance(data, dict) and data.get("mode") == "mock":
            present = [name for name in QOP_ONLY_SETTINGS if name in data]
            if present:
                raise ValueError(
                    "mode: mock runs locally without a QOP server or QUA configuration; "
                    f"remove {', '.join(present)} (qua_config also comes from qua_config_file)"
                )
        return data

    @model_validator(mode="after")
    def _check_mode_sections(self) -> QMBackendSettings:
        if self.mode == "mock":
            if self.mock is None:
                raise ValueError("mode: mock needs a 'mock' section with at least one qubit")
            return self
        if self.mock is not None:
            raise ValueError(f"'mock' is only valid with mode: mock, not mode: {self.mode}")
        if not self.qubits:
            raise ValueError("qubits must configure at least one qubit")
        if not self.qua_config:
            raise ValueError("set qua_config or qua_config_file")
        self._check_server()
        self._check_names_exist()
        return self

    def _check_server(self) -> None:
        if (self.connection is None) == (self.cloud is None):
            raise ValueError("set exactly one of 'connection' (QOP server) or 'cloud' (QM SaaS)")
        if self.cloud is None:
            return
        if self.mode != "simulator":
            raise ValueError("'cloud' runs the QM SaaS simulator and needs mode: simulator")
        controllers = self.qua_config.get("controllers") or {}
        uses_fems = any(
            isinstance(controller, dict) and "fems" in controller
            for controller in controllers.values()
        )
        expected = QOP_MAJOR_OPX1000 if uses_fems else QOP_MAJOR_OPX_PLUS
        if self.cloud.qop_major != expected:
            family = "OPX1000 (fems)" if uses_fems else "OPX+"
            raise ValueError(
                f"cloud.qop_version {self.cloud.qop_version} does not match the {family} "
                f"controllers of qua_config; use a QOP {expected}.x version"
            )

    def _check_names_exist(self) -> None:
        elements = self.qua_config.get("elements")
        if not isinstance(elements, dict):
            raise ValueError("qua_config must define 'elements'")
        for qid, qubit in self.qubits.items():
            for element, operation in (
                (qubit.qubit_element, qubit.qubit_operation),
                (qubit.readout_element, qubit.readout_operation),
            ):
                definition = elements.get(element)
                if not isinstance(definition, dict):
                    raise ValueError(f"qubit {qid}: element '{element}' is not in qua_config")
                if operation not in (definition.get("operations") or {}):
                    raise ValueError(
                        f"qubit {qid}: operation '{operation}' is not defined for '{element}'"
                    )

    def qubit(self, qid: str) -> QMQubitSettings:
        """Return the settings of ``qid`` or fail with the configured qubit IDs."""
        try:
            return self.qubits[qid]
        except KeyError:
            configured = ", ".join(sorted(self.qubits)) or "none"
            raise QMConfigurationError(
                f"Qubit {qid} is not configured for the QM backend (configured: {configured})"
            ) from None

    def readout_pulse_length(self, qid: str) -> int:
        """Return the readout pulse length in ns, used to convert demodulated data to volts."""
        qubit = self.qubit(qid)
        return self.pulse_length(qubit.readout_element, qubit.readout_operation)

    def drive_pulse_length(self, qid: str) -> int:
        """Return the length in ns of the qubit operation the Rabi sweep scales."""
        qubit = self.qubit(qid)
        return self.pulse_length(qubit.qubit_element, qubit.qubit_operation)

    def pulse_length(self, element: str, operation: str) -> int:
        """Return the length in ns of the pulse behind ``operation`` of ``element``."""
        pulse_name = self.qua_config["elements"][element]["operations"][operation]
        pulse = (self.qua_config.get("pulses") or {}).get(pulse_name)
        if not isinstance(pulse, dict) or "length" not in pulse:
            raise QMConfigurationError(f"qua_config has no length for pulse '{pulse_name}'")
        return int(pulse["length"])


def load_qm_settings(path: Path) -> QMBackendSettings:
    """Load and validate a QM settings file.

    ``qua_config_file``, when present, names a JSON or YAML QUA configuration
    relative to the settings file; otherwise ``qua_config`` holds it inline.
    """
    if not path.is_file():
        raise QMConfigurationError(f"QM settings file not found: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise QMConfigurationError(f"QM settings file must contain a mapping: {path}")

    qua_config_file = data.pop("qua_config_file", None)
    if qua_config_file is not None:
        if "qua_config" in data:
            raise QMConfigurationError("Set either qua_config or qua_config_file, not both")
        data["qua_config"] = _load_mapping_file(path.parent / str(qua_config_file))
    try:
        return QMBackendSettings.model_validate(data)
    except ValueError as exc:
        raise QMConfigurationError(f"Invalid QM settings in {path}: {exc}") from exc


def _load_mapping_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise QMConfigurationError(f"QUA configuration file not found: {path}")
    with path.open(encoding="utf-8") as f:
        loaded = json.load(f) if path.suffix == ".json" else yaml.safe_load(f)
    if not isinstance(loaded, dict):
        raise QMConfigurationError(f"QUA configuration must be a mapping: {path}")
    return loaded


def resolve_qm_settings_path(config: Mapping[str, Any]) -> Path:
    """Return the settings path for a session configuration."""
    explicit = config.get("qm_config_path") or os.environ.get(QM_CONFIG_ENV)
    if explicit:
        return Path(str(explicit))
    chip_id = config.get("chip_id")
    if not chip_id:
        raise QMConfigurationError(
            f"Cannot locate the QM settings: no chip_id, qm_config_path or {QM_CONFIG_ENV}"
        )
    return ConfigLoader.get_config_dir() / QM_CONFIG_DIR_NAME / str(chip_id) / QM_SETTINGS_FILE_NAME


def import_qm_sdk() -> Any:
    """Import the ``qm`` SDK module or raise ``QMDependencyError`` with an install hint."""
    try:
        import qm
    except ImportError as exc:
        raise QMDependencyError(QM_INSTALL_HINT) from exc
    return qm


def import_qm_saas() -> Any:
    """Import the ``qm_saas`` client or raise ``QMDependencyError`` with an install hint."""
    try:
        import qm_saas
    except ImportError as exc:
        raise QMDependencyError(QM_CLOUD_INSTALL_HINT) from exc
    return qm_saas


class _RedactingFilter(logging.Filter):
    """Replace credential values in records logged by the ``qm-saas`` client."""

    def __init__(self, secrets: tuple[str, ...]) -> None:
        super().__init__()
        self._secrets = tuple(secret for secret in secrets if secret)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = message
        for secret in self._secrets:
            redacted = redacted.replace(secret, "***")
        if redacted != message:
            record.msg, record.args = redacted, None
        return True


def _sdk_logger(secrets: tuple[str, ...]) -> logging.Logger:
    """Logger for the ``qm-saas`` client that redacts credentials before any handler.

    qm-saas logs the login email when authentication fails. The logger is private to
    one connection, so its filter does not leak to other backends, and it propagates
    to this module's logger.
    """
    sdk_logger = logging.Logger(f"{__name__}.saas")
    sdk_logger.parent = logger
    sdk_logger.addFilter(_RedactingFilter(secrets))
    return sdk_logger


@dataclass
class QMSession:
    """Live connection handed to QM tasks by ``QMBackend.get_instance``."""

    manager: Any
    settings: QMBackendSettings

    @property
    def mode(self) -> QMMode:
        """Execution mode of the session."""
        return self.settings.mode

    @property
    def is_simulator(self) -> bool:
        """Whether programs are simulated instead of executed on hardware."""
        return self.settings.mode == "simulator"

    @property
    def is_mock(self) -> bool:
        """Whether a local synthetic response replaces the QOP server."""
        return self.settings.mode == "mock"

    @property
    def is_hardware(self) -> bool:
        """Whether programs run on the OPX; only these results may become calibration values."""
        return self.settings.mode == "hardware"


class QMBackend(BaseBackend):
    """Backend for Quantum Machines OPX controllers: hardware, QOP simulator or local mock."""

    name: str = "qm"

    def __init__(self, config: dict[str, Any]) -> None:
        """Store the session configuration; settings are read on first use."""
        self._config = config
        self._settings: QMBackendSettings | None = config.get("qm_settings")
        self._manager: Any | None = None
        # QM SaaS instance spawned by this backend; only this instance is ever closed.
        self._cloud_instance: Any | None = None

    @property
    def config(self) -> dict[str, Any]:
        """Session configuration passed by the orchestrator."""
        return self._config

    @property
    def settings(self) -> QMBackendSettings:
        """Validated QM settings, loaded from the settings file on first access."""
        if self._settings is None:
            self._settings = load_qm_settings(resolve_qm_settings_path(self._config))
        return self._settings

    @property
    def mode(self) -> QMMode:
        """Execution mode from the settings file."""
        return self.settings.mode

    @property
    def is_simulator(self) -> bool:
        """Whether this backend simulates programs instead of running them on hardware."""
        return self.mode == "simulator"

    @property
    def is_mock(self) -> bool:
        """Whether this backend answers with a local synthetic response."""
        return self.mode == "mock"

    @property
    def is_hardware(self) -> bool:
        """Whether this backend runs programs on the OPX.

        Only hardware results may replace calibration values; ``BackendSaver`` checks
        this property.
        """
        return self.mode == "hardware"

    def version(self) -> str:
        """Return the installed ``qm-qua`` SDK version, or the mock label in mock mode."""
        try:
            if self.settings.mode == "mock":
                return QM_MOCK_VERSION
        except QMConfigurationError:
            pass
        try:
            qm = import_qm_sdk()
        except QMDependencyError:
            return "qm-qua (not installed)"
        return f"qm-qua {getattr(qm, '__version__', 'unknown')}"

    def connect(self) -> None:
        """Validate the settings and open a ``QuantumMachinesManager``.

        With ``cloud`` settings, spawn a QM SaaS simulator instance first. A failed
        connect closes the instance it spawned before the error propagates. In mock
        mode, start a local ``QMMockDevice`` instead; no QM package is imported.
        """
        if self._manager is not None:
            return
        settings = self.settings
        if settings.mock is not None:
            self._manager = QMMockDevice(settings.mock)
            logger.info(
                "Started the local QM mock (synthetic response, seed=%s); no QOP server is used",
                settings.mock.seed,
            )
            return
        qm = import_qm_sdk()
        if settings.cloud is not None:
            self._connect_cloud(qm, settings.cloud)
            return
        connection = settings.connection
        assert connection is not None
        kwargs: dict[str, Any] = {"host": connection.host}
        if connection.port is not None:
            kwargs["port"] = connection.port
        if connection.cluster_name is not None:
            kwargs["cluster_name"] = connection.cluster_name
        if connection.timeout is not None:
            kwargs["timeout"] = connection.timeout
        self._manager = qm.QuantumMachinesManager(**kwargs)
        logger.info("Connected to QOP at %s in %s mode", connection.host, settings.mode.upper())

    def _connect_cloud(self, qm: Any, cloud: QMCloudSettings) -> None:
        qm_saas = import_qm_saas()
        email, password = cloud.read_credentials()
        try:
            client = qm_saas.QmSaas(
                host=cloud.host,
                port=cloud.port,
                email=email,
                password=password,
                log=_sdk_logger((email, password)),
            )
        except Exception as exc:
            # The SDK raises a bare Exception; the message carries no credentials.
            raise QMCloudError(f"QM SaaS login at {cloud.host} failed: {exc}") from None

        version = qm_saas.QOPVersion(cloud.qop_version)
        try:
            available = sorted(str(v) for v in client.versions())
        except Exception as exc:
            raise QMCloudError(f"Could not list QM SaaS QOP versions: {exc}") from None
        if str(version) not in available:
            raise QMConfigurationError(
                f"QM SaaS does not offer QOP {version}; available: {', '.join(available) or 'none'}"
            )

        instance = client.simulator(version)
        self._cloud_instance = instance
        try:
            instance.spawn()
            self._manager = qm.QuantumMachinesManager(**instance.qmm_connection_params)
        except Exception:
            self._cloud_instance = None
            self._close_cloud_instance(instance)
            raise
        logger.info(
            "Connected to QM SaaS simulator instance %s (QOP %s), expires at %s",
            instance.id,
            version,
            instance.expires_at,
        )

    def disconnect(self) -> None:
        """Close the ``QuantumMachinesManager`` and the cloud instance this backend spawned.

        Safe to call repeatedly: both handles are cleared before they are closed.
        """
        manager, self._manager = self._manager, None
        instance, self._cloud_instance = self._cloud_instance, None
        try:
            close = getattr(manager, "close", None)
            if callable(close):
                close()
        finally:
            if instance is not None:
                self._close_cloud_instance(instance)

    @staticmethod
    def _close_cloud_instance(instance: Any) -> None:
        """Close a spawned instance; a failure is logged because the instance expires anyway."""
        instance_id = getattr(instance, "id", None)
        try:
            instance.close()
        except Exception:
            logger.warning(
                "Could not close QM SaaS simulator instance %s; it stays allocated until it "
                "expires",
                instance_id,
                exc_info=True,
            )
        else:
            if instance_id is not None:
                logger.info("Closed QM SaaS simulator instance %s", instance_id)

    @property
    def is_connected(self) -> bool:
        """Return whether a ``QuantumMachinesManager`` is open."""
        return self._manager is not None

    def get_instance(self) -> QMSession:
        """Return the live session, connecting first when needed.

        An expired cloud instance (QM SaaS closes instances after a fixed lifetime) is
        replaced by a new one before the session is returned.
        """
        instance = self._cloud_instance
        if instance is not None and not instance.is_alive:
            logger.warning("QM SaaS simulator instance %s expired; spawning a new one", instance.id)
            self.disconnect()
        if self._manager is None:
            self.connect()
        if self._manager is None:
            msg = "Backend instance is not initialized. Please call connect() first."
            raise RuntimeError(msg)
        return QMSession(manager=self._manager, settings=self.settings)
