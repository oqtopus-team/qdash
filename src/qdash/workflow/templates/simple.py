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
"""

from collections.abc import Mapping
from typing import Any

from prefect import flow

from qdash.workflow import TaskCall
from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target

# Custom task lists inherit this call's run settings for every CreateHPIPulse call
# that does not set them itself.
CREATE_HPI_PULSE = TaskCall(name="CreateHPIPulse", run={"hpi_duration": 32})

SIMPLE_TASKS: list[TaskCall] = [
    TaskCall(name="CheckRabi"),
    CREATE_HPI_PULSE,
    TaskCall(name="CheckHPIPulse"),
]


def _with_hpi_defaults(entry: Any) -> Any:
    """Return a CreateHPIPulse call with the template run settings under its own.

    Other entries are returned unchanged, so the step still validates them and
    reports plain task names or repeated tasks without call ids.
    """
    if isinstance(entry, Mapping) and entry.get("name") == CREATE_HPI_PULSE.name:
        entry = TaskCall.model_validate(entry)
    if not isinstance(entry, TaskCall) or entry.name != CREATE_HPI_PULSE.name:
        return entry
    return entry.model_copy(update={"run": {**(CREATE_HPI_PULSE.run or {}), **(entry.run or {})}})


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
        tasks: Task calls to run; flow runs pass [{"name": "CheckRabi"}, ...]
            (default: CheckRabi, CreateHPIPulse, CheckHPIPulse). A CreateHPIPulse
            call uses hpi_duration=32 unless it sets its own value.
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
        raise ValueError("mux_ids or qids is required; select targets before running this flow")

    # Define tasks to run; build a new list so the caller's list is never modified.
    calls = [_with_hpi_defaults(entry) for entry in (SIMPLE_TASKS if tasks is None else tasks)]

    # Define steps
    steps = [
        CustomOneQubit(step_name="simple_tasks", tasks=calls, mode=mode),
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
