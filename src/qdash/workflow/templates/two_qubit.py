"""Two-qubit calibration with auto-generated schedule from candidate qubits.

This template takes a list of candidate qubit IDs and automatically generates
an optimal CR schedule using CRScheduler, then executes 2-qubit calibration.

Use this when you have already completed 1Q calibration and want to run 2Q
calibration on specific qubits without going through the full pipeline.

Example:
    two_qubit(
        username="alice",
        chip_id="64Qv3",
        qids=["0", "1", "4", "5", "8", "9"],
    )
"""

from typing import Any

from prefect import flow
from qdash.workflow.service import CalibService
from qdash.workflow.service.steps import (
    CustomTwoQubit,
    GenerateCRSchedule,
    Step,
    TwoQubitCalibration,
)
from qdash.workflow.service.targets import QubitTargets


@flow
def two_qubit(
    username: str,
    chip_id: str,
    qids: list[str] | None = None,
    tasks: list[str] | None = None,
    max_parallel_ops: int = 10,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Two-qubit calibration with auto-generated schedule.

    Takes candidate qubit IDs and generates an optimal CR schedule based on:
    - MUX conflicts (pairs sharing MUX cannot run in parallel)
    - Frequency constraints (CR direction based on qubit frequencies)
    - Hardware topology (valid coupling pairs from chip design)

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        qids: List of candidate qubit IDs (e.g., ["0", "1", "4", "5"]).
            These should be qubits that have passed 1Q calibration.
        tasks: 2Q tasks to run. If None, runs full 2Q calibration tasks:
            - CheckCrossResonance
            - CreateZX90
            - CheckZX90
            - CheckBellState
            - CheckBellStateTomography
            - ZX90InterleavedRandomizedBenchmarking
        max_parallel_ops: Maximum number of CR operations to run in parallel.
            Limited by hardware constraints. Default: 10.
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results with typed step outputs

    Example:
        # Run full 2Q calibration on candidate qubits
        two_qubit(
            username="alice",
            chip_id="64Qv3",
            qids=["0", "1", "4", "5", "8", "9"],
        )

        # Run only specific 2Q tasks
        two_qubit(
            username="alice",
            chip_id="64Qv3",
            qids=["0", "1", "4", "5"],
            tasks=["CheckCrossResonance", "CreateZX90", "CheckZX90"],
        )

        # Limit parallel operations
        two_qubit(
            username="alice",
            chip_id="64Qv3",
            qids=["0", "1", "4", "5", "8", "9", "12", "13"],
            max_parallel_ops=5,
        )
    """
    # =========================================================================
    # Validation
    # =========================================================================

    if not qids:
        raise ValueError("qids cannot be empty")

    if len(qids) < 2:
        raise ValueError("Need at least 2 candidate qubits for 2Q calibration")

    # =========================================================================
    # Define Targets
    # =========================================================================

    targets = QubitTargets(qids=qids)

    # =========================================================================
    # Define Pipeline Steps
    # =========================================================================

    steps: list[Step] = [
        # Generate CR schedule from candidate qubits
        GenerateCRSchedule(max_parallel_ops=max_parallel_ops),
    ]

    if tasks is not None:
        # Custom task list - use CustomTwoQubit
        steps.append(
            CustomTwoQubit(
                step_name="two_qubit",
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
        project_id=project_id,
        skip_execution=True,  # Child sessions create their own Executions
    )
    return cal.run(targets, steps=steps)
