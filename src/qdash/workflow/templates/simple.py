"""Simple calibration flow template.

The simplest template for learning and basic calibration tasks.
Uses the step-based API with CustomOneQubit.

Example:
    # MUX-based execution (recommended)
    simple_calibration(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1, 2, 3],
    )

    # Qubit-based execution
    simple_calibration(
        username="alice",
        chip_id="64Qv3",
        qids=["0", "1", "2", "3"],
    )

    # Custom tasks with MUX
    simple_calibration(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1],
        tasks=["CheckRamsey", "CheckT1"],
    )
"""

from typing import Any

from prefect import flow
from qdash.workflow.service import CalibService
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target


@flow
def simple_calibration(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    tasks: list[str] | None = None,
    mode: str = "scheduled",
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Simple calibration flow.

    Supports both MUX-based and qubit-based target specification.
    When mux_ids is provided, uses MUX-based parallel scheduling.
    When only qids is provided, uses direct qubit targeting.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to calibrate (uses MUX-based scheduling)
        exclude_qids: Qubit IDs to exclude (only with mux_ids)
        qids: Qubit IDs to calibrate (fallback if mux_ids not set)
        tasks: Task names to run (default: CheckRabi, CreateHPIPulse, CheckHPIPulse)
        mode: Execution mode:
            - "scheduled": Box-based parallelism with hardware constraints (default)
            - "serial": Fully sequential execution
            - "synchronized": Step-based synchronized execution
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results
    """
    # =========================================================================
    # Configuration
    # =========================================================================

    if exclude_qids is None:
        exclude_qids = []

    # Define targets: MUX-based takes priority over qubit-based
    targets: Target
    if mux_ids is not None:
        targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids)
    elif qids is not None:
        targets = QubitTargets(qids=qids)
    else:
        # Default: MUX 0-3 (16 qubits)
        targets = MuxTargets(mux_ids=list(range(4)), exclude_qids=exclude_qids)

    # Define tasks to run
    if tasks is None:
        tasks = [
            "CheckRabi",
            "CreateHPIPulse",
            "CheckHPIPulse",
        ]

    # Define steps
    steps = [
        CustomOneQubit(step_name="simple_tasks", tasks=tasks, mode=mode),
    ]

    # =========================================================================
    # Execution
    # =========================================================================

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        skip_execution=True,  # Child sessions create their own Executions
        default_run_parameters={
            "hpi_duration": {"value": 32, "value_type": "int"},
            "interval": {"value": 150 * 1024, "value_type": "int"},
        },
    )
    return cal.run(targets, steps=steps)
