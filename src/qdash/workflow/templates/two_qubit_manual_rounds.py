"""Two-qubit calibration in rounds of directed pairs that you write.

Edit ``ROUNDS`` and ``TARGET_PAIRS`` below, then save. Rounds run one after
another in the written order; the pairs of a round run in parallel and the
next round starts after every pair of the round has finished. QDash never
regroups, reorders, reverses or splits the rounds.

Before any pair runs, the execution preview and the run check that:

- every pair is a coupling of the chip in the written (control, target) direction;
- both qubits of every pair are among the targets;
- a pair appears in only one round;
- the pairs of a round share no qubit, no MUX, and no readout or control
  module that the chip wiring shares between MUXes.

The rounds name their own targets, so the execution dialog offers no target
override for this template. To let QDash group selected pairs instead, use the
2Q Automatic Pairs template.
"""

from typing import Any

from prefect import flow

from qdash.workflow import TaskCall
from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import CustomTwoQubit, TwoQubitCalibration
from qdash.workflow.service.targets import CouplingTargets

# Directed (control, target) pairs, one list per round, in run order.
ROUNDS: list[list[tuple[str, str]]] = [
    [("0", "1"), ("4", "5")],  # round 1: these pairs run in parallel
    [("8", "9")],  # round 2: starts after every pair of round 1 finished
]

# Every pair of ROUNDS, in round order. Keep both lists in sync when you edit them.
# The targets are the qubits of these pairs; the preview checks the rounds against them.
TARGET_PAIRS: list[tuple[str, str]] = [("0", "1"), ("4", "5"), ("8", "9")]

TWO_QUBIT_MANUAL_ROUNDS_TASKS: list[TaskCall] = [
    TaskCall(
        name="CheckCrossResonance",
        # Uncomment to tune the CR parameter search.
        # run={
        #     "adiabatic_safe_factor": 0.65,
        #     "max_amplitude": 0.85,
        #     "max_time_range": 8192,
        # },
    ),
    TaskCall(name="CreateZX90"),
    TaskCall(name="CheckZX90"),
    TaskCall(name="CheckBellState"),
    TaskCall(name="CheckBellStateTomography"),
    TaskCall(name="Check2QGateCoherenceLimit"),
    TaskCall(name="ZX90InterleavedRandomizedBenchmarking"),
]


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def two_qubit_manual_rounds(
    username: str,
    chip_id: str,
    tasks: list[TaskCall] | None = None,
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Two-qubit calibration in the rounds written in ``ROUNDS``.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        tasks: 2Q tasks every pair runs, in order. If None, runs full 2Q
            calibration tasks:
            - CheckCrossResonance
            - CreateZX90
            - CheckZX90
            - CheckBellState
            - CheckBellStateTomography
            - Check2QGateCoherenceLimit
            - ZX90InterleavedRandomizedBenchmarking
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results with typed step outputs
    """
    # =========================================================================
    # Validation
    # =========================================================================

    if [pair for round_ in ROUNDS for pair in round_] != TARGET_PAIRS:
        raise ValueError("TARGET_PAIRS must list every pair of ROUNDS, in round order")

    # =========================================================================
    # Define Targets and Pipeline Steps
    # =========================================================================

    targets = CouplingTargets(pairs=TARGET_PAIRS)

    if tasks is None:
        # Full 2Q calibration
        step: TwoQubitCalibration | CustomTwoQubit = TwoQubitCalibration(
            tasks=TWO_QUBIT_MANUAL_ROUNDS_TASKS,
            execution_mode="manual",
            rounds=ROUNDS,
        )
    else:
        # Custom task list - use CustomTwoQubit
        step = CustomTwoQubit(
            step_name="two_qubit_manual_rounds",
            tasks=tasks,
            execution_mode="manual",
            rounds=ROUNDS,
        )

    # =========================================================================
    # Execute Pipeline
    # =========================================================================

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        default_run_parameters={
            "readout_duration": 1024,
            "interval": 150 * 1024,
        },
    )
    return cal.run(targets, steps=[step])
