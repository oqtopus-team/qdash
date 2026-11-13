"""Two-qubit calibration with pre-defined schedule.

This template executes 2-qubit calibration using a user-provided schedule
instead of auto-generating one. Use this when you have specific qubit pairs
to calibrate or when you want to control the execution order.

The schedule is a list of parallel groups, where each group contains
(control, target) qubit ID tuples that can be executed simultaneously.

Instead of a schedule, ``coupling_pairs`` lists directed pairs without groups.
The execution dialog sends its coupling pair override through this parameter;
the run then groups the pairs by the chip's hardware constraints. A direct
Python call with ``coupling_pairs`` and no execution override runs one pair at
a time.

Example:
    two_qubit_scheduled(
        username="alice",
        chip_id="64Qv3",
        schedule=[
            [("0", "1"), ("4", "5")],   # Group 1: run in parallel
            [("2", "3"), ("8", "9")],   # Group 2: run after group 1
        ],
    )

Schedule versus manual rounds:
    ``schedule`` feeds a ``SetCRSchedule`` step, the legacy way to hand-write
    groups. The groups run as written but QDash does not check them against
    the chip. A two-qubit step with ``execution_mode="manual"`` and ``rounds``
    runs the same kind of groups and checks them before any pair runs: every
    pair is a coupling of the chip in the written direction, both of its
    qubits are among the step's current qubits, a pair appears in only one
    round, and the pairs of a round share no qubit, no MUX, and no readout or
    control module that the chip wiring shares between MUXes.

    This flow has no ``rounds`` parameter, so neither ``schedule`` nor any
    other argument turns on manual rounds. Edit a copy of the template:
    replace the entire Validation and Extract pairs for target definition
    sections with the targets below. This removes the requirement to supply
    ``schedule`` or ``coupling_pairs``. Replace both the ``SetCRSchedule`` step
    and the calibration step with one manual step::

        targets = CouplingTargets(pairs=[("0", "1"), ("4", "5"), ("8", "9")])
        steps = [
            CustomTwoQubit(
                step_name="two_qubit_scheduled",
                execution_mode="manual",
                rounds=[[("0", "1"), ("4", "5")], [("8", "9")]],
                tasks=[TaskCall(name="CheckCrossResonance")],
            ),
        ]

    Rounds run one after another, and the pairs of a round run in parallel.
    ``TwoQubitCalibration(tasks=..., execution_mode="manual", rounds=...)``
    works the same way. A manual step ignores an earlier ``SetCRSchedule``,
    rejects ``max_parallel_ops``, and Execute offers no coupling pair override
    for it. See docs/user-guide/manual-execution-rounds.md.
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
from qdash.workflow.service.steps import (
    CustomTwoQubit,
    SetCRSchedule,
    Step,
    TwoQubitCalibration,
)
from qdash.workflow.service.targets import CouplingTargets

TWO_QUBIT_SCHEDULED_TASKS: list[TaskCall] = [
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
def two_qubit_scheduled(
    username: str,
    chip_id: str,
    schedule: list[list[tuple[str, str]]] | None = None,
    tasks: list[TaskCall] | None = None,
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
    *,
    coupling_pairs: list[tuple[str, str]] | None = None,
) -> Any:
    """Two-qubit calibration with pre-defined schedule.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        schedule: Pre-defined schedule as list of parallel groups.
            Each group is a list of (control, target) qubit ID tuples.
            Groups are executed sequentially, pairs within a group run in parallel.
            The groups go to ``SetCRSchedule`` and are not checked against the
            chip; manual rounds are an edit to the steps, not this argument.
            Example: [[("0", "1"), ("4", "5")], [("2", "3")]]
        coupling_pairs: Directed (control, target) pairs to calibrate instead of
            ``schedule``. Takes precedence over ``schedule``. Without an execution
            override each pair runs in its own group.
            Example: [("0", "1"), ("1", "0")]
        tasks: 2Q tasks to run. If None, runs full 2Q calibration tasks:
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

    Example:
        # Run full 2Q calibration on specific pairs
        two_qubit_scheduled(
            username="alice",
            chip_id="64Qv3",
            schedule=[
                [("0", "1"), ("4", "5")],  # These pairs run in parallel
                [("2", "3")],              # This pair runs after the first group
            ],
        )

        # Run only CR check tasks
        two_qubit_scheduled(
            username="alice",
            chip_id="64Qv3",
            schedule=[[("0", "1")]],
            tasks=[TaskCall(name="CheckCrossResonance")],
        )
    """
    # =========================================================================
    # Validation
    # =========================================================================

    if coupling_pairs is not None:
        # One pair per group never runs conflicting pairs together. An execution
        # override replaces this schedule with hardware-aware parallel groups.
        schedule = [[(control, target)] for control, target in coupling_pairs]
    if not schedule:
        raise ValueError("Specify a non-empty schedule or coupling_pairs")

    for i, group in enumerate(schedule):
        if not group:
            raise ValueError(f"Group {i} in schedule is empty")
        for pair in group:
            if len(pair) != 2:
                raise ValueError(
                    f"Invalid pair {pair} in group {i}: must be (control, target) tuple"
                )

    # =========================================================================
    # Extract pairs for target definition
    # =========================================================================

    all_pairs = [pair for group in schedule for pair in group]
    targets = CouplingTargets(pairs=all_pairs)

    # =========================================================================
    # Define Pipeline Steps
    # =========================================================================

    steps: list[Step] = [
        # Set the pre-defined schedule. SetCRSchedule runs its groups without
        # chip checks; for checked groups, replace this step and the next one
        # with a manual step (see "Schedule versus manual rounds" above).
        SetCRSchedule(schedule=schedule),
        # Execute 2Q calibration using the schedule
    ]

    if tasks is not None:
        # Custom task list - use CustomTwoQubit
        steps.append(
            CustomTwoQubit(
                step_name="two_qubit_scheduled",
                tasks=tasks,
            )
        )
    else:
        # Full 2Q calibration
        steps.append(TwoQubitCalibration(tasks=TWO_QUBIT_SCHEDULED_TASKS))

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
    return cal.run(targets, steps=steps)
