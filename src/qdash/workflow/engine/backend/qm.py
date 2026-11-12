"""Quantum Machines (OPX) backend.

The backend connects to a Quantum Orchestration Platform (QOP) server through the
``qm-qua`` SDK. The SDK and ``qualang-tools`` are optional dependencies (the workflow
project's ``qm`` extra) and are imported only when the backend connects, so the
qubex and fake backends keep working without them. The qm-fake backend imports them
too: it runs the same SDK program path against a local fake device.

Each backend runs in one of two explicit modes, set in the QM settings file:

``hardware``
    Programs are executed on the OPX. Tasks may fit the measured response and
    publish calibration values.
``simulator``
    Programs are sent to the QOP simulator (``QuantumMachinesManager.simulate``).
    The simulator returns the controller output waveforms only: it verifies pulse
    timing and amplitudes, not the physical response of a qubit. Tasks never
    publish calibration values in this mode.

Testing without QM hardware or a QOP server is the job of the separate ``qm-fake``
backend (``qm_fake.py``), which runs the same QM tasks and SDK program path against
a local fake device. This backend never falls back to it.

Both modes need a QOP server that the worker can reach, set in ``connection`` as
``QuantumMachinesManager(host=...)`` takes it. The QOP simulator runs on that server;
this package neither hosts a simulator nor provisions one.

The settings file defaults to ``<config dir>/qm-config/<chip_id>/qm.yaml``. The
``qm_config_path`` session option or the ``QDASH_QM_CONFIG`` environment variable
overrides that path.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from qdash.common.config.loader import ConfigLoader
from qdash.workflow.engine.backend.base import BaseBackend

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)

QM_CONFIG_DIR_NAME = "qm-config"
QM_SETTINGS_FILE_NAME = "qm.yaml"
QM_CONFIG_ENV = "QDASH_QM_CONFIG"
QM_CONFIG_OPTION = "qm_config_path"
QM_INSTALL_HINT = (
    "The qm and qm-fake backends need the optional Quantum Machines packages qm-qua and "
    "qualang-tools, which the standard QDash workflow image does not include. "
    "Install them with: uv sync --package qdash-workflow --extra qm"
)
# Upper bound on the simulated program time, which bounds the samples the simulator returns.
MAX_SIMULATION_DURATION_NS = 1_000_000

QMMode = Literal["hardware", "simulator"]
# Former in-backend mock mode, replaced by the qm-fake backend; rejected with a pointer to it.
REMOVED_MOCK_MODES = ("mock", "fake")


class QMDependencyError(ImportError):
    """Raised when the optional Quantum Machines packages are not installed."""


class QMConfigurationError(ValueError):
    """Raised when the QM settings file is missing or invalid."""


class QMConnectionSettings(BaseModel):
    """Address of the QOP server, passed to ``QuantumMachinesManager``."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1)
    port: int | None = Field(default=None, gt=0, lt=65536)
    cluster_name: str | None = None
    timeout: float | None = Field(default=None, gt=0)


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


def string_qids(value: Any) -> Any:
    """Key a per-qubit mapping by string QDash qubit IDs, as YAML may parse ``0`` as an int."""
    if isinstance(value, dict):
        return {str(qid): settings for qid, settings in value.items()}
    return value


class QMQuaSettings(BaseModel):
    """QUA configuration and qubit bindings shared by the ``qm`` and ``qm-fake`` backends.

    Both backends hand ``qua_config`` to ``QuantumMachinesManager.open_qm`` (the real
    one or the qm-fake stand-in) and build the Rabi program from the same ``qubits``
    bindings, so both validate them with the same rules.
    """

    model_config = ConfigDict(extra="forbid")

    qubits: dict[str, QMQubitSettings] = Field(default_factory=dict)
    qua_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("qubits", mode="before")
    @classmethod
    def _string_qids(cls, value: Any) -> Any:
        return string_qids(value)

    @model_validator(mode="after")
    def _check_qua_bindings(self) -> QMQuaSettings:
        if not self.qubits:
            raise ValueError("qubits must configure at least one qubit")
        if not self.qua_config:
            raise ValueError("set qua_config or qua_config_file")
        self._check_names_exist()
        return self

    def _check_names_exist(self) -> None:
        elements = self.qua_config.get("elements")
        if not isinstance(elements, dict):
            raise ValueError("qua_config must define 'elements'")
        pulses = self.qua_config.get("pulses") or {}
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
            readout = elements[qubit.readout_element]
            missing_outputs = [o for o in qubit.outputs if o not in (readout.get("outputs") or {})]
            if missing_outputs:
                raise ValueError(
                    f"qubit {qid}: output(s) {', '.join(missing_outputs)} are not defined for "
                    f"'{qubit.readout_element}'"
                )
            pulse_name = readout["operations"][qubit.readout_operation]
            pulse = pulses.get(pulse_name)
            weights = (pulse.get("integration_weights") or {}) if isinstance(pulse, dict) else {}
            missing_weights = sorted({w for w in qubit.integration_weights if w not in weights})
            if missing_weights:
                raise ValueError(
                    f"qubit {qid}: integration weight(s) {', '.join(missing_weights)} are not "
                    f"defined for pulse '{pulse_name}'"
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


class QMBackendSettings(QMQuaSettings):
    """Validated contents of a QM settings file."""

    mode: QMMode
    connection: QMConnectionSettings
    simulation: QMSimulationSettings = Field(default_factory=QMSimulationSettings)

    @model_validator(mode="before")
    @classmethod
    def _reject_local_fake(cls, data: Any) -> Any:
        # The qm backend always needs a QOP server; the local fake device is a
        # separate backend, so a settings file can never route a run to it silently.
        if isinstance(data, dict) and (data.get("mode") in REMOVED_MOCK_MODES or "mock" in data):
            raise ValueError(
                "the qm backend runs on the OPX or the QOP simulator only (mode: hardware or "
                "simulator); for a local fake device select backend 'qm-fake' and put "
                "its settings in qm-fake.yaml"
            )
        return data


def read_settings_mapping(path: Path, kind: str) -> dict[str, Any]:
    """Read a QM or qm-fake settings file and inline its ``qua_config_file``.

    ``qua_config_file``, when present, names a JSON or YAML QUA configuration
    relative to the settings file; otherwise ``qua_config`` holds it inline.
    """
    if not path.is_file():
        raise QMConfigurationError(f"{kind} settings file not found: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise QMConfigurationError(f"{kind} settings file must contain a mapping: {path}")

    qua_config_file = data.pop("qua_config_file", None)
    if qua_config_file is not None:
        if "qua_config" in data:
            raise QMConfigurationError("Set either qua_config or qua_config_file, not both")
        data["qua_config"] = _load_mapping_file(path.parent / str(qua_config_file))
    return data


def load_qm_settings(path: Path) -> QMBackendSettings:
    """Load and validate a QM settings file."""
    data = read_settings_mapping(path, "QM")
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


def resolve_qm_settings_path(
    config: Mapping[str, Any],
    *,
    option: str = QM_CONFIG_OPTION,
    env: str = QM_CONFIG_ENV,
    file_name: str = QM_SETTINGS_FILE_NAME,
) -> Path:
    """Return the settings path for a session configuration.

    The session option ``option`` wins over the environment variable ``env``; without
    either, the file ``file_name`` in ``<config dir>/qm-config/<chip_id>/`` is used.
    The qm-fake backend passes its own option, variable and file name.
    """
    explicit = config.get(option) or os.environ.get(env)
    if explicit:
        return Path(str(explicit))
    chip_id = config.get("chip_id")
    if not chip_id:
        raise QMConfigurationError(f"Cannot locate {file_name}: no chip_id, {option} or {env}")
    return ConfigLoader.get_config_dir() / QM_CONFIG_DIR_NAME / str(chip_id) / file_name


def import_qm_sdk() -> Any:
    """Import the ``qm`` SDK module or raise ``QMDependencyError`` with an install hint."""
    try:
        import qm
    except ImportError as exc:
        raise QMDependencyError(QM_INSTALL_HINT) from exc
    return qm


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
    def is_fake(self) -> bool:
        """Always ``False``; the local fake device is the qm-fake backend."""
        return False

    @property
    def is_hardware(self) -> bool:
        """Whether programs run on the OPX; only these results may become calibration values."""
        return self.settings.mode == "hardware"


class QMBackend(BaseBackend):
    """Backend for Quantum Machines OPX controllers: hardware or QOP simulator."""

    name: str = "qm"

    def __init__(self, config: dict[str, Any]) -> None:
        """Store the session configuration; settings are read on first use."""
        self._config = config
        self._settings: QMBackendSettings | None = config.get("qm_settings")
        self._manager: Any | None = None

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
    def is_fake(self) -> bool:
        """Always ``False``; the local fake device is the qm-fake backend."""
        return False

    @property
    def is_hardware(self) -> bool:
        """Whether this backend runs programs on the OPX.

        Only hardware results may replace calibration values; ``BackendSaver`` checks
        this property.
        """
        return self.mode == "hardware"

    def version(self) -> str:
        """Return the installed ``qm-qua`` SDK version."""
        try:
            qm = import_qm_sdk()
        except QMDependencyError:
            return "qm-qua (not installed)"
        return f"qm-qua {getattr(qm, '__version__', 'unknown')}"

    def connect(self) -> None:
        """Validate the settings and open a ``QuantumMachinesManager``."""
        if self._manager is not None:
            return
        settings = self.settings
        qm = import_qm_sdk()
        connection = settings.connection
        kwargs: dict[str, Any] = {"host": connection.host}
        if connection.port is not None:
            kwargs["port"] = connection.port
        if connection.cluster_name is not None:
            kwargs["cluster_name"] = connection.cluster_name
        if connection.timeout is not None:
            kwargs["timeout"] = connection.timeout
        self._manager = qm.QuantumMachinesManager(**kwargs)
        logger.info("Connected to QOP at %s in %s mode", connection.host, settings.mode.upper())

    def disconnect(self) -> None:
        """Close the ``QuantumMachinesManager``; safe to call repeatedly."""
        manager, self._manager = self._manager, None
        close = getattr(manager, "close", None)
        if callable(close):
            close()

    @property
    def is_connected(self) -> bool:
        """Return whether a ``QuantumMachinesManager`` is open."""
        return self._manager is not None

    def get_instance(self) -> QMSession:
        """Return the live session, connecting first when needed."""
        if self._manager is None:
            self.connect()
        if self._manager is None:
            msg = "Backend instance is not initialized. Please call connect() first."
            raise RuntimeError(msg)
        return QMSession(manager=self._manager, settings=self.settings)
