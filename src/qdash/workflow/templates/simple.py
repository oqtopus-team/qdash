"""Simple calibration flow template.

The simplest template for learning and basic calibration tasks.
Uses the step-based API with CustomOneQubit.

Example:
    simple_calibration(
        username="alice",
        chip_id="64Qv3",
        qids=["0", "1", "2", "3"],
    )
"""

from typing import Any

from prefect import flow
from qdash.workflow.service import CalibService
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import QubitTargets


@flow
def simple_calibration(
    username: str,
    chip_id: str,
    qids: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Simple calibration flow.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        qids: Qubit IDs to calibrate (default: ["0", "1", "2", "3"])
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results
    """
    # =========================================================================
    # Configuration
    # =========================================================================

    if qids is None:
        qids = ["0", "1", "2", "3"]

    # Define target qubits
    targets = QubitTargets(qids=qids)

    # Define tasks to run
    tasks = [
        "CheckRabi",
        "CreateHPIPulse",
        "CheckHPIPulse",
    ]

    # Define steps
    steps = [
        CustomOneQubit(step_name="simple_tasks", tasks=tasks),
    ]

    # =========================================================================
    # Execution
    # =========================================================================

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        project_id=project_id,
        skip_execution=True,  # Child sessions create their own Executions
    )
    return cal.run(targets, steps=steps)
