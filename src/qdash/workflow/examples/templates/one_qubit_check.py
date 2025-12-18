"""One-qubit check calibration template.

Basic 1-qubit characterization tasks to verify qubit quality before full calibration.
Run this before one_qubit_full.py.

Tasks:
    - CheckRabi: Rabi oscillation measurement
    - CreateHPIPulse: Create half-pi pulse
    - CheckHPIPulse: Verify half-pi pulse
    - CheckT1: T1 relaxation time measurement
    - CheckT2Echo: T2 echo measurement
    - CheckRamsey: Ramsey fringe measurement

Execution flow:
    1. Run one_qubit_check (this template) -> check results
    2. Run one_qubit_full -> advanced calibration
    3. Run two_qubit -> 2Q calibration

Example:
    one_qubit_check(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1, 2, 3],
    )
"""

from typing import Any

from prefect import flow
from qdash.workflow.service import CalService
from qdash.workflow.service.tasks import CHECK_1Q_TASKS


@flow
def one_qubit_check(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    mode: str = "synchronized",
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """One-qubit check calibration.

    Basic characterization tasks to verify qubit quality.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to calibrate (default: all 16)
        exclude_qids: Qubit IDs to exclude
        qids: Not used (for UI compatibility)
        mode: Execution mode - "synchronized" or "scheduled"
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)
    """
    # =========================================================================
    # Configuration
    # =========================================================================

    if mux_ids is None:
        mux_ids = list(range(16))
    if exclude_qids is None:
        exclude_qids = []

    # Use CHECK_1Q_TASKS: basic characterization
    tasks = CHECK_1Q_TASKS

    # =========================================================================
    # Execution
    # =========================================================================

    cal = CalService(username, chip_id, flow_name=flow_name, project_id=project_id)
    return cal.one_qubit(
        mux_ids=mux_ids,
        exclude_qids=exclude_qids,
        tasks=tasks,
        mode=mode,
    )
