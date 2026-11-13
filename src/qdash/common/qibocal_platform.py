"""The one mapping between QDash's Qibocal calibration values and a native Qibolab platform.

The Qibolab platform template under ``config/domain/qibocal/platforms/<name>/`` keeps the
structure of the simulated device in Qibolab's own format: instruments, channels, the emulator
Hamiltonian, pulse envelopes, and readout. Its calibration values are only initial values.
QDash's calibration database is the single source of the values a run uses:

* ``QibocalBringUp`` copies the template's values into the database for parameters the chip does
  not have yet (:func:`template_values`).
* Every run writes the chip's database values into the run's own copy of ``parameters.json``
  (:func:`native_assignments`, :func:`overlay`); the template is never modified.
* The runner reads the same paths back from the loaded Qibolab platform before acquisition and
  QDash compares them (:func:`readback_mismatches`).

All three use :data:`CALIBRATION_FIELDS`. The paths are the ones ``qibocal.update`` writes
(``configs.<qubit>/drive.frequency`` and ``native_gates.single_qubit.<qubit>.RX.0.1.*``).

The parameter names start with ``qibocal_`` on purpose: they describe the emulated device's
Qibolab pulses (a Gaussian RX of the template's envelope), not the Qubex parameters with similar
names, and must never be read as those.

This module never imports Qibocal or Qibolab; it reads JSON and hashes files.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

QIBOCAL_BACKEND = "qibocal"
QIBOCAL_PRESET = "qibocal"
SETTINGS_FILE = "app/qibocal.yaml"
PARAMETERS_FILE = "parameters.json"
CALIBRATION_FILE = "calibration.json"
PLATFORM_FILE = "platform.py"
# Relative tolerance of the readback comparison: JSON round trips of float64 are exact, so any
# real difference is far larger.
READBACK_RTOL = 1e-12


@dataclass(frozen=True)
class NativeTarget:
    """A native platform value written from one QDash parameter.

    ``path`` is a dotted path into ``parameters.json`` with ``{qubit}`` as placeholder; numeric
    steps index lists. The native value is the QDash value times ``factor``.
    """

    path: str
    factor: float

    def resolve(self, qubit: int | str) -> str:
        return self.path.format(qubit=qubit)


@dataclass(frozen=True)
class CalibrationField:
    """A QDash calibration parameter and the native platform values it sets."""

    name: str
    unit: str
    native_unit: str
    description: str
    # The first target is the parameter's own native value; the others are derived from it.
    targets: tuple[NativeTarget, ...]
    maximum: float | None = None

    @property
    def primary(self) -> NativeTarget:
        return self.targets[0]

    def validate(self, value: Any) -> float:
        """Return ``value`` as a float, or raise when it cannot drive the emulator."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{self.name} must be a number, got {value!r}")
        numeric = float(value)
        if not math.isfinite(numeric) or numeric <= 0:
            raise ValueError(f"{self.name} must be finite and positive, got {value!r}")
        if self.maximum is not None and numeric > self.maximum:
            raise ValueError(f"{self.name} must not exceed {self.maximum:g}, got {value!r}")
        return numeric


_RX = "native_gates.single_qubit.{qubit}.RX.0.1"
_RX90 = "native_gates.single_qubit.{qubit}.RX90.0.1"

QUBIT_FREQUENCY = CalibrationField(
    name="qibocal_qubit_frequency",
    unit="GHz",
    native_unit="Hz",
    description="Drive frequency of the emulated qubit (Qibolab channel <qubit>/drive)",
    targets=(NativeTarget("configs.{qubit}/drive.frequency", 1e9),),
)
PI_AMPLITUDE = CalibrationField(
    name="qibocal_pi_amplitude",
    unit="a.u.",
    native_unit="a.u.",
    description=(
        "Amplitude of the emulated qubit's native RX pulse; RX90 uses half of it with the same "
        "duration and envelope"
    ),
    targets=(
        NativeTarget(f"{_RX}.amplitude", 1.0),
        NativeTarget(f"{_RX90}.amplitude", 0.5),
    ),
    # Qibolab normalises pulse amplitudes to [-1, 1].
    maximum=1.0,
)
PI_DURATION = CalibrationField(
    name="qibocal_pi_duration",
    unit="ns",
    native_unit="ns",
    description="Duration of the emulated qubit's native RX and RX90 pulses",
    targets=(
        NativeTarget(f"{_RX}.duration", 1.0),
        NativeTarget(f"{_RX90}.duration", 1.0),
    ),
)
CALIBRATION_FIELDS: tuple[CalibrationField, ...] = (QUBIT_FREQUENCY, PI_AMPLITUDE, PI_DURATION)
CALIBRATION_FIELDS_BY_NAME: dict[str, CalibrationField] = {f.name: f for f in CALIBRATION_FIELDS}
# Paths of the pulse whose shape the RX values assume; recorded with every run.
RX_PULSE_PATH = _RX


# --------------------------------------------------------------------------- dotted paths


def _step(container: Any, step: str) -> Any:
    if isinstance(container, list):
        return container[int(step)]
    return container[step]


def get_path(tree: Any, path: str) -> Any:
    """Return the value at dotted ``path``; raise ``KeyError`` when it does not exist."""
    current = tree
    try:
        for step in path.split("."):
            current = _step(current, step)
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise KeyError(f"Platform parameters have no '{path}'") from exc
    return current


def set_path(tree: Any, path: str, value: Any) -> None:
    """Replace the existing value at dotted ``path``; never create a new key."""
    steps = path.split(".")
    parent = get_path(tree, ".".join(steps[:-1])) if len(steps) > 1 else tree
    last = steps[-1]
    if isinstance(parent, list):
        index = int(last)
        if not 0 <= index < len(parent):
            raise KeyError(f"Platform parameters have no '{path}'")
        parent[index] = value
        return
    if not isinstance(parent, dict) or last not in parent:
        raise KeyError(f"Platform parameters have no '{path}'")
    parent[last] = value


# --------------------------------------------------------------------------- apply / readback


def native_assignments(qubit: int, values: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return every native value a run sets for ``qubit``, from QDash ``values``.

    Every field of :data:`CALIBRATION_FIELDS` must be present and valid; a missing or invalid
    value raises ``ValueError`` so that a run never falls back to a template value.
    """
    missing = [f.name for f in CALIBRATION_FIELDS if values.get(f.name) is None]
    if missing:
        raise ValueError("Missing Qibocal calibration values: " + ", ".join(missing))
    assignments: list[dict[str, Any]] = []
    for field in CALIBRATION_FIELDS:
        value = field.validate(values[field.name])
        for target in field.targets:
            assignments.append(
                {
                    "parameter": field.name,
                    "path": target.resolve(qubit),
                    "value": value * target.factor,
                }
            )
    return assignments


def overlay(
    parameters: Mapping[str, Any], assignments: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    """Return a copy of native ``parameters`` with every assignment written."""
    result: dict[str, Any] = copy.deepcopy(dict(parameters))
    for assignment in assignments:
        set_path(result, str(assignment["path"]), assignment["value"])
    return result


def readback_mismatches(
    parameters: Mapping[str, Any], assignments: Iterable[Mapping[str, Any]]
) -> list[str]:
    """Describe every assignment whose value ``parameters`` does not hold."""
    problems: list[str] = []
    for assignment in assignments:
        path = str(assignment["path"])
        expected = float(assignment["value"])
        try:
            actual = get_path(parameters, path)
        except KeyError:
            problems.append(f"{path}: missing")
            continue
        if (
            isinstance(actual, bool)
            or not isinstance(actual, (int, float))
            or not math.isclose(float(actual), expected, rel_tol=READBACK_RTOL, abs_tol=0.0)
        ):
            problems.append(f"{path}: expected {expected!r}, platform has {actual!r}")
    return problems


def template_values(parameters: Mapping[str, Any], qubit: int) -> dict[str, float]:
    """Return the QDash values of the template's own calibration for ``qubit``."""
    values: dict[str, float] = {}
    for field in CALIBRATION_FIELDS:
        native = get_path(parameters, field.primary.resolve(qubit))
        values[field.name] = field.validate(float(native) / field.primary.factor)
    return values


def rx_pulse(parameters: Mapping[str, Any], qubit: int) -> dict[str, Any]:
    """Return the native RX pulse of ``qubit``, envelope included, for provenance."""
    pulse = get_path(parameters, RX_PULSE_PATH.format(qubit=qubit))
    return copy.deepcopy(dict(pulse)) if isinstance(pulse, Mapping) else {}


# --------------------------------------------------------------------------- template identity


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _platform_qubits(parameters: Mapping[str, Any]) -> list[str]:
    natives = parameters.get("native_gates", {})
    single = natives.get("single_qubit", {}) if isinstance(natives, Mapping) else {}
    return sorted(single) if isinstance(single, Mapping) else []


def structural_fingerprint(platform_dir: Path) -> str:
    """Hash the platform's structure, leaving out the calibration values QDash owns.

    The hash covers ``platform.py``, ``calibration.json``, and ``parameters.json`` with every
    path of :data:`CALIBRATION_FIELDS` blanked for every qubit. Changing the template's initial
    calibration values keeps the fingerprint; changing the Hamiltonian, channels, envelopes,
    readout, or instruments changes it.
    """
    parameters = json.loads((platform_dir / PARAMETERS_FILE).read_text(encoding="utf-8"))
    for qubit in _platform_qubits(parameters):
        for field in CALIBRATION_FIELDS:
            for target in field.targets:
                with contextlib.suppress(KeyError):
                    set_path(parameters, target.resolve(qubit), None)
    parts: dict[str, Any] = {
        PARAMETERS_FILE: hashlib.sha256(_canonical(parameters)).hexdigest(),
        PLATFORM_FILE: hashlib.sha256((platform_dir / PLATFORM_FILE).read_bytes()).hexdigest(),
    }
    calibration = platform_dir / CALIBRATION_FILE
    if calibration.is_file():
        parts[CALIBRATION_FILE] = hashlib.sha256(
            _canonical(json.loads(calibration.read_text(encoding="utf-8")))
        ).hexdigest()
    return "sha256:" + hashlib.sha256(_canonical(parts)).hexdigest()


@dataclass(frozen=True)
class PlatformTemplate:
    """Where the configured Qibolab platform template is."""

    platforms_dir: Path
    name: str

    @property
    def directory(self) -> Path:
        return self.platforms_dir / self.name

    def parameters(self) -> dict[str, Any]:
        data = json.loads((self.directory / PARAMETERS_FILE).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{self.directory / PARAMETERS_FILE} is not a JSON object")
        return data

    def fingerprint(self) -> str:
        return structural_fingerprint(self.directory)


def load_platform_template(overrides: Mapping[str, Any] | None = None) -> PlatformTemplate:
    """Read ``platform.directory`` and ``platform.name`` from ``config/app/qibocal.yaml``.

    ``overrides`` may set ``platforms_dir`` and ``platform``. Relative directories resolve
    against the config directory.
    """
    from qdash.common.config.loader import ConfigLoader

    overrides = overrides or {}
    data = ConfigLoader._load_config(SETTINGS_FILE)
    platform = data.get("platform") or {}
    if not isinstance(platform, dict):
        raise ValueError(f"{SETTINGS_FILE}: 'platform' must be a mapping")
    directory = overrides.get("platforms_dir", platform.get("directory"))
    name = overrides.get("platform", platform.get("name"))
    if not directory or not name:
        raise ValueError(f"{SETTINGS_FILE} must set platform.directory and platform.name")
    name = str(name)
    if Path(name).name != name or name in {".", ".."}:
        raise ValueError(f"{SETTINGS_FILE}: platform.name must be a folder name")
    path = Path(str(directory)).expanduser()
    if not path.is_absolute():
        path = ConfigLoader.get_config_dir() / path
    return PlatformTemplate(platforms_dir=path, name=name)
