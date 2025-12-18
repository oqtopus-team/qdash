"""Full calibration sequence: 1Q Check -> 1Q Full -> 2Q.

Executes complete calibration in 3 separate executions for better control.

Execution flow:
    1. 1Q Check (execution 1): Basic characterization
       - CheckRabi, CreateHPIPulse, CheckHPIPulse, CheckT1, CheckT2Echo, CheckRamsey
    2. 1Q Full (execution 2): Advanced calibration
       - DRAG pulses, ReadoutClassification, RB, X90 IRB
    3. 2Q (execution 3): Coupling calibration
       - CR, ZX90, BellState, BellStateTomography, ZX90 IRB

Each stage runs as a separate execution, allowing:
    - Independent monitoring and re-running
    - Clear separation of results
    - Easier debugging

Example:
    full_calibration(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1, 2, 3],
    )
"""

from typing import Any

from prefect import flow
from qdash.workflow.service import CalService


@flow
def full_calibration(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Full calibration: 1Q Check -> 1Q Full -> 2Q.

    Runs 3 separate executions for complete chip calibration.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to calibrate (default: all 16)
        exclude_qids: Qubit IDs to exclude
        qids: Not used (for UI compatibility)
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

    mode = "synchronized"  # or "scheduled"
    fidelity_threshold = 0.90
    max_parallel_ops = 10

    # =========================================================================
    # Execution (3 separate executions)
    # =========================================================================

    cal = CalService(username, chip_id, flow_name=flow_name, project_id=project_id)
    return cal.run_full_chip(
        mux_ids=mux_ids,
        exclude_qids=exclude_qids,
        mode=mode,
        fidelity_threshold=fidelity_threshold,
        max_parallel_ops=max_parallel_ops,
    )
