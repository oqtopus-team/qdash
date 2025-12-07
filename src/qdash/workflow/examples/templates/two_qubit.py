"""Two-qubit coupling calibration template.

Calibrates 2-qubit coupling (Cross Resonance, ZX90, Bell state).

Execution pattern:
    pairs = [("0", "1"), ("2", "3"), ("4", "5")]

    ┌─────────────────────────────────────────────────────────────┐
    │  PARALLEL: All pairs submitted simultaneously               │
    ├─────────────────────────────────────────────────────────────┤
    │  0-1: CR → ZX90 → Bell (SEQUENTIAL)                        │
    │  2-3: CR → ZX90 → Bell (SEQUENTIAL)        PARALLEL        │
    │  4-5: CR → ZX90 → Bell (SEQUENTIAL)                        │
    └─────────────────────────────────────────────────────────────┘

    Pairs run in PARALLEL, tasks within pair run SEQUENTIALLY.

Example:
    two_qubit_calibration(
        username="alice",
        chip_id="64Qv3",
    )
"""

from prefect import flow
from qdash.workflow.flow import CalService


@flow
def two_qubit_calibration(
    username: str,
    chip_id: str,
    qids: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
):
    """Two-qubit coupling calibration.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        qids: Not used (pairs defined below)
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)
    """
    # =========================================================================
    # Configuration
    # =========================================================================

    # Coupling pairs (control, target) - all pairs run in PARALLEL
    pairs = [
        ("0", "1"),  # Q0-Q1 coupling
        ("2", "3"),  # Q2-Q3 coupling
        ("4", "5"),  # Q4-Q5 coupling
    ]

    # Tasks run SEQUENTIALLY for each pair
    tasks = [
        "CheckCrossResonance",
        "CreateZX90",
        "CheckZX90",
        "CheckBellState",
    ]

    # =========================================================================
    # Execution
    # =========================================================================

    cal = CalService(username, chip_id, flow_name=flow_name, project_id=project_id)
    return cal.two_qubit(pairs=pairs, tasks=tasks)
