"""Parameter sweep calibration template.

Execute a task repeatedly with different parameter values.

Execution pattern:
    qids = ["0", "1", "2", "3"]
    params = [0.05, 0.10, 0.15, 0.20, 0.25]

    ┌─────────────────────────────────────────────────────────────┐
    │  SEQUENTIAL: Each iteration runs one after another          │
    ├─────────────────────────────────────────────────────────────┤
    │  Iter0 (0.05): Q0→Q1→Q2→Q3  ──┐                            │
    │  Iter1 (0.10): Q0→Q1→Q2→Q3    │                            │
    │  Iter2 (0.15): Q0→Q1→Q2→Q3    ├─ SEQUENTIAL                │
    │  Iter3 (0.20): Q0→Q1→Q2→Q3    │                            │
    │  Iter4 (0.25): Q0→Q1→Q2→Q3  ──┘                            │
    └─────────────────────────────────────────────────────────────┘

    Iterations run SEQUENTIALLY, qubits within iteration SEQUENTIALLY.

Example:
    parameter_sweep(
        username="alice",
        chip_id="64Qv3",
    )
"""

from typing import Any

from prefect import flow
from qdash.workflow.service import CalService


@flow
def parameter_sweep(
    username: str,
    chip_id: str,
    qids: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Parameter sweep calibration flow.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        qids: Not used (defined below)
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)
    """
    # =========================================================================
    # Configuration
    # =========================================================================

    # Qubits to sweep - run SEQUENTIALLY within each iteration
    qids = ["0", "1", "2", "3"]

    task = "CheckQubitSpectroscopy"

    # Parameter values - each iteration runs SEQUENTIALLY
    params = [
        {"readout_amplitude": {"value": 0.05}},
        {"readout_amplitude": {"value": 0.10}},
        {"readout_amplitude": {"value": 0.15}},
        {"readout_amplitude": {"value": 0.20}},
        {"readout_amplitude": {"value": 0.25}},
    ]

    # =========================================================================
    # Execution
    # =========================================================================

    cal = CalService(username, chip_id, flow_name=flow_name, project_id=project_id)
    return cal.sweep(qids=qids, task=task, params=params)
