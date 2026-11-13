"""Execution modes of two-qubit calibration steps.

``automatic`` (the default)
    The step runs the CR schedule of an earlier ``GenerateCRSchedule`` or
    ``SetCRSchedule`` step, or generates one from the candidate qubits. The
    scheduler colors the pairs into conflict-free groups and ``max_parallel_ops``
    caps the pairs of one group.

``manual``
    The step's ``rounds`` list the directed ``(control, target)`` pairs of each
    round, e.g. ``rounds=[[("0", "1"), ("4", "5")], [("8", "9")]]``. Rounds run
    in the written order, the pairs of a round run in parallel and the next round
    starts after every pair of the round has finished. The rounds are never
    regrouped, reordered, reversed or split, an earlier CR schedule is not used,
    and ``max_parallel_ops`` is rejected because it only caps automatic groups.
    :mod:`qdash.common.manual_rounds` checks the rounds before any pair runs.
"""

from __future__ import annotations

from typing import Literal, cast

TwoQubitExecutionMode = Literal["automatic", "manual"]

TWO_QUBIT_EXECUTION_MODES: tuple[TwoQubitExecutionMode, ...] = ("automatic", "manual")

DEFAULT_MAX_PARALLEL_OPS = 10
"""Pairs per group of an automatic CR schedule when ``max_parallel_ops`` is unset."""


def validate_two_qubit_execution_mode(value: object) -> TwoQubitExecutionMode:
    """Return ``value`` as a two-qubit execution mode, or raise ``ValueError``."""
    if isinstance(value, str) and value in TWO_QUBIT_EXECUTION_MODES:
        return cast("TwoQubitExecutionMode", value)
    valid = ", ".join(TWO_QUBIT_EXECUTION_MODES)
    raise ValueError(f"Unknown execution_mode {value!r}. Valid execution modes: {valid}")
