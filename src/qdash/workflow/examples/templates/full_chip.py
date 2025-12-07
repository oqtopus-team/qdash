"""Full chip calibration: 1-qubit + CR scheduling + 2-qubit.

Complete end-to-end calibration workflow with automatic quality filtering.

Example:
    full_chip_calibration(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1, 2, 3],
    )
"""

from prefect import flow
from qdash.workflow.flow import CalService


@flow
def full_chip_calibration(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
):
    """Full chip calibration: 1-qubit -> 2-qubit.

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
    # Execution
    # =========================================================================

    cal = CalService(username, chip_id, flow_name=flow_name, project_id=project_id)
    return cal.run_full_chip(
        mux_ids=mux_ids,
        exclude_qids=exclude_qids,
        mode=mode,
        fidelity_threshold=fidelity_threshold,
        max_parallel_ops=max_parallel_ops,
    )
