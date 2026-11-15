"""Execution modes of one-qubit calibration steps.

An execution mode decides where and when the targets of a one-qubit step run.
Every target still runs the step's full task list in order; the mode never
splits that list into per-task barriers.

``sequential``
    One MUX at a time, and one qubit at a time within a MUX.

``parallel_by_mux``
    MUX groups that the scheduler allows to share a stage run in parallel; the
    qubits of one MUX run one after another. Each MUX advances independently:
    as soon as one of its qubits finishes, its next qubit may start.

``parallel_by_round``
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
another); ``simultaneous_spectroscopy`` keeps its own batch schedule.

``manual``
    The step's ``rounds`` list the rounds explicitly, e.g.
    ``rounds=[["0", "8"], ["1", "9"]]``. Rounds run in the written order, the
    qubits of a round run in parallel, and the next round starts after every
    qubit of the round has finished, as in ``parallel_by_round``. The rounds are
    never regrouped, reordered or split; :mod:`qdash.common.manual_rounds` checks
    them before any qubit runs. Only calibration steps accept ``manual``
    (:data:`OneQubitStepExecutionMode`); flow templates and ``BringUp`` take the
    scheduled modes of :data:`OneQubitExecutionMode`.
"""

from __future__ import annotations

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


OneQubitStepExecutionMode = Literal[
    "parallel_by_round",
    "parallel_by_mux",
    "simultaneous_spectroscopy",
    "sequential",
    "manual",
]
"""Modes of ``OneQubitCheck``, ``OneQubitFineTune`` and ``CustomOneQubit``."""

ONE_QUBIT_STEP_EXECUTION_MODES: tuple[OneQubitStepExecutionMode, ...] = (
    *ONE_QUBIT_EXECUTION_MODES,
    "manual",
)


def validate_one_qubit_execution_mode(value: object) -> OneQubitExecutionMode:
    """Return ``value`` as an execution mode, or raise ``ValueError`` for any other value.

    Python entry points (step classes, strategy lookup) call this because a
    ``Literal`` annotation is not checked at run time. Pipeline specs and flow
    parameters are validated by Pydantic against :data:`OneQubitExecutionMode`.
    """
    if isinstance(value, str) and value in ONE_QUBIT_EXECUTION_MODES:
        return cast("OneQubitExecutionMode", value)
    valid = ", ".join(ONE_QUBIT_EXECUTION_MODES)
    raise ValueError(f"Unknown execution_mode {value!r}. Valid execution modes: {valid}")


def validate_one_qubit_step_execution_mode(value: object) -> OneQubitStepExecutionMode:
    """Like :func:`validate_one_qubit_execution_mode`, also accepting ``manual``."""
    if isinstance(value, str) and value in ONE_QUBIT_STEP_EXECUTION_MODES:
        return cast("OneQubitStepExecutionMode", value)
    valid = ", ".join(ONE_QUBIT_STEP_EXECUTION_MODES)
    raise ValueError(f"Unknown execution_mode {value!r}. Valid execution modes: {valid}")
