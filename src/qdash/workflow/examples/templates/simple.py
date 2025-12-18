"""Simple calibration flow template.

The simplest template for learning and basic calibration tasks.

Execution pattern:
    groups = [["0", "1"], ["2", "3"]]

    ┌─────────────────────────────────────────────────────────────┐
    │  PARALLEL: Groups submitted simultaneously                  │
    ├─────────────────────────────────────────────────────────────┤
    │  Group0 ["0", "1"]: Q0 → Q1 (SEQUENTIAL)                   │
    │                       ↓                      PARALLEL       │
    │  Group1 ["2", "3"]: Q2 → Q3 (SEQUENTIAL)                   │
    └─────────────────────────────────────────────────────────────┘

    Groups run in PARALLEL, qubits within group run SEQUENTIALLY.

Example:
    simple_calibration(
        username="alice",
        chip_id="64Qv3",
    )
"""

from typing import Any

from prefect import flow
from qdash.workflow.flow import CalService


@flow
def simple_calibration(
    username: str,
    chip_id: str,
    qids: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Simple calibration flow.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        qids: Not used (groups defined below)
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)
    """
    # =========================================================================
    # Configuration
    # =========================================================================

    # Qubit groups
    # - Groups run in PARALLEL (submitted simultaneously)
    # - Qubits within each group run SEQUENTIALLY (0→1, 2→3)
    groups = [
        ["0", "1"],  # Group 0: Q0 → Q1 sequential
        ["2", "3"],  # Group 1: Q2 → Q3 sequential
    ]

    tasks = [
        "CheckRabi",
        "CreateHPIPulse",
        "CheckHPIPulse",
    ]

    # =========================================================================
    # Execution
    # =========================================================================

    cal = CalService(username, chip_id, flow_name=flow_name, project_id=project_id)
    return cal.run(groups=groups, tasks=tasks)
