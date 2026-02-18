"""Two-qubit calibration with pre-defined schedule.

This template executes 2-qubit calibration using a user-provided schedule
instead of auto-generating one. Use this when you have specific qubit pairs
to calibrate or when you want to control the execution order.

The schedule is a list of parallel groups, where each group contains
(control, target) qubit ID tuples that can be executed simultaneously.

Example:
    two_qubit_scheduled(
        username="alice",
        chip_id="64Qv3",
        schedule=[
            [("0", "1"), ("4", "5")],   # Group 1: run in parallel
            [("2", "3"), ("8", "9")],   # Group 2: run after group 1
        ],
    )
"""

from typing import Any

from prefect import flow
from qdash.workflow.service import CalibService
from qdash.workflow.service.steps import (
    CustomTwoQubit,
    SetCRSchedule,
    Step,
    TwoQubitCalibration,
)
from qdash.workflow.service.targets import CouplingTargets


@flow
def two_qubit_scheduled(
    username: str,
    chip_id: str,
    schedule: list[list[tuple[str, str]]],
    tasks: list[str] | None = None,
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Two-qubit calibration with pre-defined schedule.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        schedule: Pre-defined schedule as list of parallel groups.
            Each group is a list of (control, target) qubit ID tuples.
            Groups are executed sequentially, pairs within a group run in parallel.
            Example: [[("0", "1"), ("4", "5")], [("2", "3")]]
        tasks: 2Q tasks to run. If None, runs full 2Q calibration tasks:
            - CheckCrossResonance
            - CreateZX90
            - CheckZX90
            - CheckBellState
            - CheckBellStateTomography
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
            tasks=["CheckCrossResonance"],
        )
    """
    # =========================================================================
    # Validation
    # =========================================================================

    if not schedule:
        raise ValueError("schedule cannot be empty")

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
        # Set the pre-defined schedule
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
        steps.append(TwoQubitCalibration())

    # =========================================================================
    # Execute Pipeline
    # =========================================================================

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        skip_execution=True,  # Child sessions create their own Executions
        default_run_parameters={
            "interval": {"value": 150 * 1024, "value_type": "int"},
        },
    )
    return cal.run(targets, steps=steps)
