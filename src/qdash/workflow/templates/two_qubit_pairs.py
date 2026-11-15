"""Two-qubit calibration on selected directed pairs, grouped automatically.

This template calibrates exactly the directed (control, target) pairs given in
``coupling_pairs``. At run time the CR scheduler groups them into parallel
groups that share no qubit, no MUX and no module the chip wiring shares between
MUXes; it never adds, drops or reverses a pair. Pairs that are not couplings of
the chip in the written direction stop the run before any pair is calibrated.

The execution dialog offers a coupling pair selection for this template. The
selected pairs replace ``coupling_pairs`` for that run and are grouped the same
way.

To run your own groups in a fixed order instead, use the 2Q Manual Rounds
template.

Example:
    two_qubit_pairs(
        username="alice",
        chip_id="64Qv3",
        coupling_pairs=[("0", "1"), ("1", "0"), ("4", "5")],
    )
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

TWO_QUBIT_PAIRS_TASKS: list[TaskCall] = [
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
def two_qubit_pairs(
    username: str,
    chip_id: str,
    coupling_pairs: list[tuple[str, str]] | None = None,
    tasks: list[TaskCall] | None = None,
    max_parallel_ops: int = 10,
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Two-qubit calibration on selected directed pairs, grouped automatically.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        coupling_pairs: Directed (control, target) pairs to calibrate, e.g.
            [("0", "1"), ("1", "0")]. Each pair runs in the written direction.
            The execution dialog fills this from its coupling pair selection.
        tasks: 2Q tasks to run. If None, runs full 2Q calibration tasks:
            - CheckCrossResonance
            - CreateZX90
            - CheckZX90
            - CheckBellState
            - CheckBellStateTomography
            - Check2QGateCoherenceLimit
            - ZX90InterleavedRandomizedBenchmarking
        max_parallel_ops: Maximum number of pairs in one parallel group.
            Default: 10.
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results with typed step outputs
    """
    # =========================================================================
    # Validation
    # =========================================================================

    if not coupling_pairs:
        raise ValueError("Specify coupling_pairs: the directed (control, target) pairs to run")
    for pair in coupling_pairs:
        if len(pair) != 2 or pair[0] == pair[1]:
            raise ValueError(f"Invalid pair {pair}: must be a (control, target) tuple")
    if len({tuple(pair) for pair in coupling_pairs}) != len(coupling_pairs):
        raise ValueError("coupling_pairs must not contain duplicates")

    # =========================================================================
    # Define Targets
    # =========================================================================

    targets = CouplingTargets(pairs=coupling_pairs)

    # =========================================================================
    # Define Pipeline Steps
    # =========================================================================

    # The step groups exactly the target pairs at run time.
    if tasks is None:
        # Full 2Q calibration
        step: TwoQubitCalibration | CustomTwoQubit = TwoQubitCalibration(
            tasks=TWO_QUBIT_PAIRS_TASKS,
            max_parallel_ops=max_parallel_ops,
        )
    else:
        # Custom task list - use CustomTwoQubit
        step = CustomTwoQubit(
            step_name="two_qubit_pairs",
            tasks=tasks,
            max_parallel_ops=max_parallel_ops,
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
