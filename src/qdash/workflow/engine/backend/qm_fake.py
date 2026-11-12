"""QM fake backend (``qm-fake``): the QM tasks against a local fake QOP device.

``QMFakeBackend`` plays the role for the ``qm`` backend that the ``fake`` backend
plays for qubex: the tasks run the same experiment code as on hardware, and only the
device boundary is replaced. A QM task on ``qm-fake`` builds its program with the real
``qualang-tools`` ``QUA_calibrations`` class, runs it through ``run_calibrations``,
and fetches and converts the results with the real SDK and ``qualang-tools`` helpers.
``QMFakeQuantumMachinesManager`` (``qm_fake_qop.py``) takes the place of
``qm.QuantumMachinesManager``: it validates the QUA configuration with the installed
SDK, decodes the generated QUA program, interprets the supported 1D amplitude Rabi
subset and answers with demodulated values drawn from a small qubit model.

The backend therefore needs the workflow ``qm`` extra (``qm-qua`` and
``qualang-tools``) but no OPX, no QOP server and no network. Without the extra,
``connect`` raises ``QMDependencyError`` with the install command; it never falls
back to another response.

A ``qm-fake`` run checks that the task builds, executes, fetches and analyses a
program the way a hardware run does, against the same QUA configuration and qubit
bindings. It does not check QUA compilation, controller timing, waveform output,
firmware or wiring, and its response comes from the model described in
``qm_fake_qop``, not from a device.

The settings file defaults to ``<config dir>/qm-config/<chip_id>/qm-fake.yaml``. The
``qm_fake_config_path`` session option or the ``QDASH_QM_FAKE_CONFIG`` environment
variable overrides that path. It holds the QUA configuration and qubit bindings in
the same form as ``qm.yaml`` (``qua_config_file`` or ``qua_config`` and ``qubits``),
plus ``seed``, ``qop_version`` and the ``device`` response of each qubit. Settings
that reach a QOP server (``mode``, ``connection``, ``simulation``) are rejected.

The ``qm-fake`` backend is never a calibration source: ``is_hardware`` is ``False``,
so ``BackendSaver`` keeps its results in the run history only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from qdash.workflow.engine.backend.base import BaseBackend
from qdash.workflow.engine.backend.qm import (
    QM_INSTALL_HINT,
    QMConfigurationError,
    QMDependencyError,
    QMQuaSettings,
    import_qm_sdk,
    read_settings_mapping,
    resolve_qm_settings_path,
    string_qids,
)

if TYPE_CHECKING:
    from pathlib import Path

    from qdash.workflow.engine.backend.qm_fake_qop import QMFakeQuantumMachinesManager

logger = logging.getLogger(__name__)

QM_FAKE_BACKEND_NAME = "qm-fake"
QM_FAKE_SETTINGS_FILE_NAME = "qm-fake.yaml"
QM_FAKE_CONFIG_ENV = "QDASH_QM_FAKE_CONFIG"
QM_FAKE_CONFIG_OPTION = "qm_fake_config_path"
# Labels that mark every fake artifact, so a fake result can never pass as measured data.
QM_FAKE_SOURCE_TYPE = "qdash.qm_fake.qualang_tools.Rabi"
QM_FAKE_VERSION_LABEL = "qm-fake (QDash fake QOP device)"
# Settings of the qm backend that reach a QOP server; a qm-fake settings file must not set them.
QOP_ONLY_SETTINGS = ("mode", "connection", "simulation")
# Keys of the former response-only qm-fake qubit entries, rejected with a pointer to 'device'.
FORMER_RESPONSE_KEYS = ("pi_amplitude_scale", "iq_offset", "contrast", "phase_deg")


class QMFakeQubitDevice(BaseModel):
    """Response of one qubit on the fake device."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    pi_pulse_area: float = Field(
        default=4.8,
        gt=0,
        description=(
            "Area in V*ns of the drive pulse envelope that rotates the qubit by pi; "
            "a played pulse rotates it by pi * amp * |envelope area| / pi_pulse_area"
        ),
    )
    ground_iq: tuple[float, float] = Field(
        default=(0.010, 0.002), description="Readout amplitude (I, Q) of the ground state in V"
    )
    excited_iq: tuple[float, float] = Field(
        default=(0.0025, 0.015), description="Readout amplitude (I, Q) of the excited state in V"
    )
    noise_per_shot: float = Field(
        default=0.01, ge=0, description="Gaussian noise in V per quadrature on every measurement"
    )

    @model_validator(mode="after")
    def _distinct_states(self) -> QMFakeQubitDevice:
        if self.ground_iq == self.excited_iq:
            raise ValueError("ground_iq and excited_iq must differ")
        return self


class QMFakeSettings(QMQuaSettings):
    """Validated contents of a ``qm-fake.yaml`` settings file.

    ``qubits`` and ``qua_config`` follow ``qm.yaml`` and are validated by the same
    rules; ``device`` adds the response of each bound qubit.
    """

    seed: int | None = Field(
        default=None,
        ge=0,
        description="Seed of the noise generator; omit it for different noise on every session",
    )
    qop_version: Literal[2, 3] = Field(
        default=2,
        description="QOP major version whose capabilities the SDK validates the configuration for",
    )
    device: dict[str, QMFakeQubitDevice] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _reject_qop_settings(cls, data: Any) -> Any:
        # Checked before field validation, so a QOP server section copied from
        # qm.yaml gets this message instead of an "extra field" error.
        if not isinstance(data, dict):
            return data
        present = [name for name in QOP_ONLY_SETTINGS if name in data]
        if present:
            raise ValueError(
                "the qm-fake backend runs on a local fake device without a QOP server; "
                f"remove {', '.join(present)}. Use backend 'qm' with qm.yaml for the OPX or "
                "the QOP simulator"
            )
        if "mock" in data:
            raise ValueError("'mock' is not a qm-fake setting; describe the response in 'device'")
        qubits = data.get("qubits")
        if isinstance(qubits, dict) and any(
            isinstance(entry, dict) and any(key in entry for key in FORMER_RESPONSE_KEYS)
            for entry in qubits.values()
        ):
            raise ValueError(
                "qubits holds the QUA bindings as in qm.yaml; describe the response of each "
                "qubit under 'device' (pi_pulse_area, ground_iq, excited_iq, noise_per_shot)"
            )
        return data

    @field_validator("device", mode="before")
    @classmethod
    def _string_device_qids(cls, value: Any) -> Any:
        if isinstance(value, dict):
            value = {qid: entry or {} for qid, entry in value.items()}
        return string_qids(value)

    @model_validator(mode="after")
    def _check_device(self) -> QMFakeSettings:
        missing = sorted(set(self.qubits) - set(self.device))
        unbound = sorted(set(self.device) - set(self.qubits))
        if missing:
            raise ValueError(f"device has no entry for qubit(s) {', '.join(missing)}")
        if unbound:
            raise ValueError(f"device describes qubit(s) {', '.join(unbound)} without a binding")
        for role in ("qubit_element", "readout_element"):
            seen: dict[str, str] = {}
            for qid, binding in self.qubits.items():
                element = getattr(binding, role)
                if element in seen:
                    raise ValueError(
                        f"qubits {seen[element]} and {qid} share {role} '{element}'; the fake "
                        "device models one qubit per drive and readout element"
                    )
                seen[element] = qid
        return self

    def qubit_device(self, qid: str) -> QMFakeQubitDevice:
        """Return the fake response parameters of ``qid``."""
        self.qubit(qid)
        return self.device[qid]


def load_qm_fake_settings(path: Path) -> QMFakeSettings:
    """Load and validate a ``qm-fake.yaml`` settings file."""
    data = read_settings_mapping(path, "qm-fake")
    try:
        return QMFakeSettings.model_validate(data)
    except ValueError as exc:
        raise QMConfigurationError(f"Invalid qm-fake settings in {path}: {exc}") from exc


def resolve_qm_fake_settings_path(config: dict[str, Any]) -> Path:
    """Return the ``qm-fake.yaml`` path for a session configuration."""
    return resolve_qm_settings_path(
        config,
        option=QM_FAKE_CONFIG_OPTION,
        env=QM_FAKE_CONFIG_ENV,
        file_name=QM_FAKE_SETTINGS_FILE_NAME,
    )


def import_qm_fake_packages() -> None:
    """Import the SDK and ``qualang-tools`` that a qm-fake run executes, or explain how."""
    import_qm_sdk()
    try:
        import qualang_tools.addons.calibration.calibrations  # noqa: F401
    except ImportError as exc:
        raise QMDependencyError(QM_INSTALL_HINT) from exc


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not installed"


@dataclass
class QMFakeSession:
    """Session handed to QM tasks by ``QMFakeBackend.get_instance``.

    ``manager`` has the ``open_qm`` API of ``QuantumMachinesManager``, so the task's
    shared hardware code path runs against it unchanged. The session answers the same
    questions as ``QMSession`` (``mode``, ``is_hardware``, ``is_simulator``,
    ``is_fake``).
    """

    manager: QMFakeQuantumMachinesManager
    settings: QMFakeSettings

    @property
    def mode(self) -> Literal["fake"]:
        """Execution mode of the session."""
        return "fake"

    @property
    def is_simulator(self) -> bool:
        """A fake session never runs the QOP simulator."""
        return False

    @property
    def is_fake(self) -> bool:
        """A fake session executes programs on the local fake device."""
        return True

    @property
    def is_hardware(self) -> bool:
        """A fake session never measures a device."""
        return False

    def result_metadata(self, qid: str, job: Any) -> dict[str, Any]:
        """Describe the fake device and what it executed, for labelling a result."""
        return {
            "backend": QM_FAKE_BACKEND_NAME,
            "seed": self.settings.seed,
            "qop_version": self.settings.qop_version,
            "device": self.settings.qubit_device(qid).model_dump(mode="json"),
            "execution": dict(getattr(job, "fake_report", {})),
            "qm_qua": _package_version("qm-qua"),
            "qualang_tools": _package_version("qualang-tools"),
        }


class QMFakeBackend(BaseBackend):
    """Backend that runs QM tasks against ``QMFakeQuantumMachinesManager`` instead of a QOP."""

    name: str = QM_FAKE_BACKEND_NAME

    def __init__(self, config: dict[str, Any]) -> None:
        """Store the session configuration; settings are read on first use."""
        self._config = config
        self._settings: QMFakeSettings | None = config.get("qm_fake_settings")
        self._manager: QMFakeQuantumMachinesManager | None = None

    @property
    def config(self) -> dict[str, Any]:
        """Session configuration passed by the orchestrator."""
        return self._config

    @property
    def settings(self) -> QMFakeSettings:
        """Validated qm-fake settings, loaded from the settings file on first access."""
        if self._settings is None:
            self._settings = load_qm_fake_settings(resolve_qm_fake_settings_path(self._config))
        return self._settings

    @property
    def mode(self) -> Literal["fake"]:
        """Execution mode, compared with the mode recorded in each result."""
        return "fake"

    @property
    def is_simulator(self) -> bool:
        """The fake backend never runs the QOP simulator."""
        return False

    @property
    def is_fake(self) -> bool:
        """The fake backend executes programs on the local fake device."""
        return True

    @property
    def is_hardware(self) -> bool:
        """Always ``False``: ``BackendSaver`` never writes fake results as calibration values."""
        return False

    def version(self) -> str:
        """Return the fake device label with the SDK versions it runs."""
        return (
            f"{QM_FAKE_VERSION_LABEL}; qm-qua {_package_version('qm-qua')}, "
            f"qualang-tools {_package_version('qualang-tools')}"
        )

    def connect(self) -> None:
        """Validate the settings, import the QM packages and start the fake device."""
        if self._manager is not None:
            return
        settings = self.settings
        import_qm_fake_packages()
        from qdash.workflow.engine.backend.qm_fake_qop import QMFakeQuantumMachinesManager

        self._manager = QMFakeQuantumMachinesManager(settings)
        logger.info(
            "Started the qm-fake device (seed=%s, QOP %s capabilities); no QOP server is used",
            settings.seed,
            settings.qop_version,
        )

    def disconnect(self) -> None:
        """Close the fake manager and its machines; safe to call repeatedly."""
        manager, self._manager = self._manager, None
        if manager is not None:
            manager.close()

    @property
    def is_connected(self) -> bool:
        """Return whether the fake manager is open."""
        return self._manager is not None

    def get_instance(self) -> QMFakeSession:
        """Return the live session, starting the fake device first when needed."""
        if self._manager is None:
            self.connect()
        if self._manager is None:
            msg = "Backend instance is not initialized. Please call connect() first."
            raise RuntimeError(msg)
        return QMFakeSession(manager=self._manager, settings=self.settings)
