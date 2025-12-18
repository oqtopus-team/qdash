"""One-qubit full calibration template.

Advanced 1-qubit calibration tasks. Run this after one_qubit_check.py.

Tasks:
    - CreatePIPulse: Create pi pulse
    - CheckPIPulse: Verify pi pulse
    - CreateDRAGHPIPulse: Create DRAG half-pi pulse
    - CheckDRAGHPIPulse: Verify DRAG half-pi pulse
    - CreateDRAGPIPulse: Create DRAG pi pulse
    - CheckDRAGPIPulse: Verify DRAG pi pulse
    - ReadoutClassification: Readout state classification
    - RandomizedBenchmarking: Single-qubit RB
    - X90InterleavedRandomizedBenchmarking: X90 gate fidelity measurement

Execution flow:
    1. Run one_qubit_check -> basic characterization
    2. Run one_qubit_full (this template) -> advanced calibration
    3. Run two_qubit -> 2Q calibration (use candidate_qubits from this execution)

Example:
    one_qubit_full(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1, 2, 3],
    )
"""

from typing import Any

from prefect import flow
from qdash.workflow.service import CalibService
from qdash.workflow.service.tasks import FULL_1Q_TASKS_AFTER_CHECK


@flow
def one_qubit_full(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    mode: str = "synchronized",
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """One-qubit full calibration (after check).

    Advanced calibration tasks including DRAG pulses and RB.

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

    # Use FULL_1Q_TASKS_AFTER_CHECK: advanced calibration
    tasks = FULL_1Q_TASKS_AFTER_CHECK

    # =========================================================================
    # Execution
    # =========================================================================

    cal = CalibService(username, chip_id, flow_name=flow_name, project_id=project_id)
    return cal.one_qubit(
        mux_ids=mux_ids,
        exclude_qids=exclude_qids,
        tasks=tasks,
        mode=mode,
    )
