"""Two-qubit coupling calibration template.

Calibrates 2-qubit coupling (Cross Resonance, ZX90, Bell state) with automatic
CR scheduling that handles MUX conflicts and frequency directionality.

Execution pattern:
    CRScheduler generates parallel groups based on MUX conflicts:

    ┌─────────────────────────────────────────────────────────────┐
    │  Step 1: [0-1, 4-5, 8-9]  (no MUX conflicts)               │
    │  Step 2: [2-3, 6-7, 10-11] (no MUX conflicts)              │
    │  ...                                                        │
    └─────────────────────────────────────────────────────────────┘

    Groups run SEQUENTIALLY, pairs within group run in PARALLEL.

Example:
    # With explicit candidate qubits
    two_qubit_calibration(
        username="alice",
        chip_id="64Qv3",
        candidate_qubits=["0", "1", "2", "3", "4", "5"],
    )

    # With MUX-based selection (all qubits in specified MUXes)
    two_qubit_calibration(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1, 2, 3],
    )
"""

from prefect import flow
from qdash.workflow.flow import CalService


def _mux_ids_to_qids(mux_ids: list[int]) -> list[str]:
    """Convert MUX IDs to qubit IDs (4 qubits per MUX)."""
    qids = []
    for mux_id in mux_ids:
        for offset in range(4):
            qids.append(str(mux_id * 4 + offset))
    return qids


@flow
def two_qubit_calibration(
    username: str,
    chip_id: str,
    candidate_qubits: list[str] | None = None,
    mux_ids: list[int] | None = None,
    qids: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
    max_parallel_ops: int = 10,
):
    """Two-qubit coupling calibration with automatic CR scheduling.

    Uses CRScheduler to generate parallel execution groups based on
    MUX conflicts and frequency directionality.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        candidate_qubits: Explicit list of candidate qubits for 2Q calibration
        mux_ids: MUX IDs to include (alternative to candidate_qubits)
        qids: Alias for candidate_qubits (for UI compatibility)
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)
        max_parallel_ops: Maximum parallel operations per group (default: 10)
    """
    # =========================================================================
    # Configuration
    # =========================================================================

    # Resolve candidate qubits from various input options
    if candidate_qubits is None:
        if qids is not None:
            candidate_qubits = qids
        elif mux_ids is not None:
            candidate_qubits = _mux_ids_to_qids(mux_ids)
        else:
            # Default: all qubits from MUX 0-15
            candidate_qubits = _mux_ids_to_qids(list(range(16)))

    # =========================================================================
    # Execution
    # =========================================================================

    cal = CalService(username, chip_id, flow_name=flow_name, project_id=project_id)
    return cal.two_qubit(
        candidate_qubits=candidate_qubits,
        max_parallel_ops=max_parallel_ops,
    )
