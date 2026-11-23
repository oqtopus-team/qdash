"""Helpers shared by the CheckCrossResonance and CreateZX90 tasks.

The functions validate CR run parameters before any acquisition and keep a task from
leaving its own rejected fit in the Qubex calibration note.

The Qubex calibration note merges an update into an existing entry only when the
update's timestamp is strictly newer, at one-second resolution, and otherwise drops it
without an error. The tasks therefore check that the entry Qubex stored is newer than
the entry the run started from, and put a previous entry back by removing the pair's
entry before writing it.
"""

from __future__ import annotations

import copy
import math
from datetime import datetime
from typing import Any

# Defaults shared with Qubex obtain_cr_params and calibrate_zx90.
DEFAULT_ADIABATIC_SAFE_FACTOR = 0.75
DEFAULT_MAX_AMPLITUDE = 1.0

# Timestamp format of Qubex calibration note entries.
NOTE_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

# Relative tolerance for comparing amplitudes against an approved cap.
_AMPLITUDE_TOLERANCE = 1e-9


def finite_number(value: Any, name: str) -> float:
    """Return ``value`` as a finite float or raise ``ValueError``."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, got {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric, got {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return number


def validate_ramptime(value: Any, name: str = "ramptime") -> float:
    """Validate a CR ramp time in ns: finite and strictly positive."""
    ramptime = finite_number(value, name)
    if ramptime <= 0:
        raise ValueError(f"{name} must be positive (ns), got {value!r}")
    return ramptime


def validate_fraction(value: Any, name: str) -> float:
    """Validate a value in (0, 1], such as an adiabatic safety factor or amplitude cap."""
    number = finite_number(value, name)
    if not 0 < number <= 1:
        raise ValueError(f"{name} must be in (0, 1], got {value!r}")
    return number


def exceeds(value: float, limit: float) -> bool:
    """Return whether ``value`` is above ``limit`` beyond floating-point noise."""
    return value > limit + _AMPLITUDE_TOLERANCE * max(1.0, abs(limit))


def resolve_bound(run_value: Any, inherited_value: Any, name: str, default: float) -> float:
    """Resolve a bound that a run may tighten but not loosen.

    ``inherited_value`` is the bound CheckCrossResonance approved for the pair, read from
    the input ``cr_<name>``. A run value above it is rejected.
    """
    inherited_name = f"cr_{name}"
    inherited = None
    if inherited_value is not None:
        inherited = validate_fraction(inherited_value, f"input {inherited_name}")
    if run_value is None:
        return default if inherited is None else inherited
    value = validate_fraction(run_value, name)
    if inherited is not None and exceeds(value, inherited):
        raise ValueError(
            f"{name}={value} is looser than the approved {inherited_name}={inherited}; "
            f"rerun CheckCrossResonance with the larger bound, or override the input "
            f"{inherited_name}"
        )
    return value


def cr_pair_label(exp: Any, qid: str) -> str:
    """Return the Qubex CR label for a coupling qid, for example ``"0-1"`` -> ``"Q00-Q01"``."""
    return "-".join(str(exp.get_qubit_label(int(q))) for q in qid.split("-"))


def copy_cr_entry(calib_note: Any, label: str) -> dict[str, Any] | None:
    """Return a deep copy of one pair's CR note entry, or ``None`` when absent."""
    entry = calib_note.get_cr_param(label)
    return copy.deepcopy(dict(entry)) if entry is not None else None


def put_back_cr_entry(calib_note: Any, label: str, entry: dict[str, Any] | None) -> None:
    """Put a copied CR entry back exactly, timestamp included.

    The pair's current entry is removed first, because the Qubex merge would drop an
    entry that is not newer than the current one. ``entry=None`` leaves the pair without
    an entry. Other pairs are not touched.
    """
    remove = getattr(calib_note, "remove_cr_param", None)
    if callable(remove) and calib_note.get_cr_param(label) is not None:
        remove(label)
    if entry is not None:
        calib_note.update_cr_param(label, copy.deepcopy(entry))


def _note_timestamp(entry: dict[str, Any] | None) -> datetime | None:
    value = entry.get("timestamp") if entry else None
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, NOTE_TIMESTAMP_FORMAT)
    except ValueError:
        return None


def require_fresh_cr_entry(
    previous: dict[str, Any] | None, stored: dict[str, Any] | None, label: str
) -> dict[str, Any]:
    """Return the stored entry when Qubex wrote it after ``previous``, else raise.

    Qubex drops an update that is not strictly newer than the stored entry, at
    one-second resolution, for example when the stored entry is future-dated. Reading
    the note back would then return the old entry as if it were this run's result.
    """
    if stored is None:
        raise ValueError(f"Qubex stored no CR parameters for {label}.")
    started_at = _note_timestamp(previous)
    if started_at is not None:
        stored_at = _note_timestamp(stored)
        if stored_at is None or stored_at <= started_at:
            raise RuntimeError(
                f"Qubex did not store fresh CR parameters for {label}: the note entry is "
                f"dated {stored.get('timestamp')}, not after {started_at}; check for a "
                "future-dated note entry or host clock skew"
            )
    return dict(stored)
