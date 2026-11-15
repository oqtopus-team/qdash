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
        tasks=[TaskCall(name="CheckRamsey"), TaskCall(name="CheckT1")],
    )

Manual rounds:
    The ``execution_mode`` parameter of this flow is meant for the scheduled
    modes; passing ``"manual"`` to ``simple_calibration`` fails because the
    flow has no ``rounds`` parameter to give the step. To choose the rounds
    yourself, edit a copy of this template: replace the entire target-selection
    block (including its ``mux_ids or qids is required`` check) with the exact
    qubits of the rounds and set ``execution_mode="manual"`` and ``rounds`` on
    the step itself::

        targets = QubitTargets(qids=["0", "8", "1", "9"])
        steps = [
            CustomOneQubit(
                step_name="simple_tasks",
                execution_mode="manual",
                rounds=[["0", "8"], ["1", "9"]],
                tasks=[TaskCall(name="CheckRabi"), TaskCall(name="CheckT1")],
            ),
        ]

    Rounds run one after another in the written order, and the qubits of one
    round run in parallel; each qubit runs the whole task list. The rounds must
    name exactly the step's current qubits (the targets, without excluded
    qubits), and QDash checks them against the chip's topology and wiring (for
    example, the qubits of one round must use different MUXes) before any qubit
    runs. Execute offers no target override for a manual workflow, so keep the
    targets in the source. See docs/user-guide/manual-execution-rounds.md.
"""

from typing import Any

from prefect import flow

from qdash.datamodel.one_qubit_execution_mode import OneQubitExecutionMode
from qdash.workflow import TaskCall
from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def simple_calibration(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    tasks: list[TaskCall] | None = None,
    execution_mode: OneQubitExecutionMode = "parallel_by_mux",
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
        tasks: Task calls to run; flow runs pass [{"name": "CheckRabi"}, ...]
            (default: CheckRabi, CreateHPIPulse with hpi_duration=32, CheckHPIPulse).
            A custom list runs as given, with each call's own settings.
        execution_mode: How the one-qubit targets run (default: "parallel_by_mux"):
            - "parallel_by_mux": MUXes run in parallel within the scheduler's hardware
              stages; the qubits of one MUX run one after another
            - "parallel_by_round": the scheduler forms rounds of qubits from different
              MUXes; the next round starts after every qubit of the round has run
              all of its tasks
            - "sequential": one MUX and one qubit at a time
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
        raise ValueError("mux_ids or qids is required; select targets before running this flow")

    # Define steps; a custom task list runs as given.
    # For manual rounds, edit this step as shown in the module docstring
    # ("Manual rounds"); the execution_mode parameter cannot enable them.
    steps = [
        CustomOneQubit(
            step_name="simple_tasks",
            tasks=tasks
            if tasks is not None
            else [
                TaskCall(name="CheckRabi"),
                TaskCall(name="CreateHPIPulse", run={"hpi_duration": 32}),
                TaskCall(name="CheckHPIPulse"),
            ],
            execution_mode=execution_mode,
        ),
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
        default_run_parameters={
            "readout_duration": 1024,
            "interval": 150 * 1024,
        },
    )
    return cal.run(targets, steps=steps)
