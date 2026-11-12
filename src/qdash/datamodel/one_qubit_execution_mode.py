"""Execution modes of one-qubit calibration steps and their deprecated aliases.

An execution mode decides where and when the targets of a one-qubit step run.
Every target still runs the step's full task list in order; the mode never
splits that list into per-task barriers.

``sequential`` (formerly ``serial``)
    One MUX at a time, and one qubit at a time within a MUX.

``parallel_by_mux`` (formerly ``scheduled``)
    MUX groups that the scheduler allows to share a stage run in parallel; the
    qubits of one MUX run one after another. Each MUX advances independently:
    as soon as one of its qubits finishes, its next qubit may start.

``parallel_by_round`` (formerly ``synchronized``)
    The scheduler selects rounds. A round is a set of qubits from different
    MUXes; each qubit of the round runs its full configured task list, and the
    next round starts only after every qubit of the current round has finished.
    A round is not a per-task barrier and does not synchronize pulse timing.

``simultaneous_spectroscopy``
    Experimental. Each supported spectroscopy call runs once over a batch of
    qubits, so every call is a barrier for its batch.

Example with MUX0 = {Q0, Q1} and MUX1 = {Q4, Q5} in the same stage. The order
below is illustrative; the actual grouping and order come from the scheduler::

    parallel_by_mux    MUX0: Q0 -> Q1        Q1 may start when Q0 finishes,
                       MUX1: Q4 -> Q5        while Q4 is still running.
    parallel_by_round  round 1: Q0, Q4       Q1 and Q5 start only after both
                       round 2: Q1, Q5       Q0 and Q4 have finished.

``sequential``, ``parallel_by_mux`` and ``parallel_by_round`` keep the hardware
stage constraints of the scheduler (for example, box stages still run one after
another); ``simultaneous_spectroscopy`` keeps its own batch schedule. Renaming
the modes did not change scheduling, stage classification, or concurrency.

The old value names (``serial``, ``scheduled``, ``synchronized``) and the old
``mode`` setting are deprecated but still accepted; use ``execution_mode`` with
the new names instead.
"""

from __future__ import annotations

import warnings
from typing import Literal, cast

OneQubitExecutionMode = Literal[
    "parallel_by_round",
    "parallel_by_mux",
    "simultaneous_spectroscopy",
    "sequential",
]

ONE_QUBIT_EXECUTION_MODES: tuple[OneQubitExecutionMode, ...] = (
    "parallel_by_round",
    "parallel_by_mux",
    "simultaneous_spectroscopy",
    "sequential",
)

LEGACY_ONE_QUBIT_EXECUTION_MODES: dict[str, OneQubitExecutionMode] = {
    "synchronized": "parallel_by_round",
    "scheduled": "parallel_by_mux",
    "serial": "sequential",
}


def _canonical(value: object, where: str) -> tuple[OneQubitExecutionMode, bool]:
    """The canonical mode for ``value`` and whether ``value`` is an old name."""
    if value in ONE_QUBIT_EXECUTION_MODES:
        return cast("OneQubitExecutionMode", value), False
    if isinstance(value, str) and value in LEGACY_ONE_QUBIT_EXECUTION_MODES:
        return LEGACY_ONE_QUBIT_EXECUTION_MODES[value], True
    valid = ", ".join(ONE_QUBIT_EXECUTION_MODES)
    raise ValueError(f"Unknown {where} {value!r}. Valid execution modes: {valid}")


def normalize_one_qubit_execution_mode(
    execution_mode: object | None,
    mode: object | None = None,
    *,
    default: OneQubitExecutionMode,
    where: str = "",
) -> tuple[OneQubitExecutionMode, list[str]]:
    """Resolve ``execution_mode`` and the deprecated ``mode`` to one canonical mode.

    ``None`` means "not given", so a caller's default is never mistaken for an
    explicit value. Old value names map to the new ones. When both settings are
    given, they must name the same mode (in either naming); otherwise this raises
    ``ValueError`` rather than letting one silently override the other.

    Args:
        execution_mode: The ``execution_mode`` value, or None when not given.
        mode: The deprecated ``mode`` value, or None when not given.
        default: Mode of this entry point when neither setting is given.
        where: Prefix for the setting names in messages, e.g. ``"steps[0]."``.

    Returns:
        The canonical mode and deprecation messages for every legacy form used.
        The messages are not emitted; callers report them through their own
        channel (``warnings``, run logs, or pipeline validation warnings).
    """
    notes: list[str] = []
    new_name, old_name = f"{where}execution_mode", f"{where}mode"
    resolved: OneQubitExecutionMode | None = None
    if execution_mode is not None:
        resolved, old_value = _canonical(execution_mode, new_name)
        if old_value:
            notes.append(
                f"{new_name}={execution_mode!r} uses a deprecated execution mode name, "
                f"which is still accepted; use {new_name}={resolved!r} instead"
            )
    if mode is not None:
        legacy, _ = _canonical(mode, old_name)
        if resolved is not None and legacy != resolved:
            raise ValueError(
                f"{new_name}={execution_mode!r} conflicts with the deprecated "
                f"{old_name}={mode!r}; set only {new_name}"
            )
        notes.append(
            f"{old_name}={mode!r} is deprecated and still accepted; "
            f"set {new_name}={legacy!r} instead"
        )
        resolved = legacy
    return (default if resolved is None else resolved), notes


def resolve_one_qubit_execution_mode(
    execution_mode: object | None,
    mode: object | None = None,
    *,
    default: OneQubitExecutionMode,
    where: str = "",
    stacklevel: int = 2,
) -> tuple[OneQubitExecutionMode, list[str]]:
    """Like :func:`normalize_one_qubit_execution_mode`, also emitting a ``DeprecationWarning``.

    Python entry points (step classes, flow templates) use this; each warning
    names the supported replacement. ``stacklevel`` counts from this function,
    so the default attributes the warning to its direct caller.
    """
    resolved, notes = normalize_one_qubit_execution_mode(
        execution_mode, mode, default=default, where=where
    )
    for note in notes:
        warnings.warn(note, DeprecationWarning, stacklevel=stacklevel + 1)
    return resolved, notes
