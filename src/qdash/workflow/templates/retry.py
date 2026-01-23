"""Parallel calibration with retry template.

Demonstrates multiprocess parallel execution with retry logic.

Execution pattern:
    groups = [["0", "1"], ["2", "3"]]

    ┌─────────────────────────────────────────────────────────────┐
    │  PARALLEL PROCESSES: Groups run in separate processes       │
    ├─────────────────────────────────────────────────────────────┤
    │  Process0: Q0 → Q1 with retry (SEQUENTIAL)                 │
    │                    ↓                         PARALLEL       │
    │  Process1: Q2 → Q3 with retry (SEQUENTIAL)                 │
    └─────────────────────────────────────────────────────────────┘

    Groups run in PARALLEL using separate processes (DaskTaskRunner).
    Qubits within each group run SEQUENTIALLY with retry logic.
    Each process has isolated memory space, avoiding qubex state conflicts.

Example:
    parallel_retry_calibration(
        username="alice",
        chip_id="64Qv3",
    )
"""

from typing import Any

from prefect import flow, get_run_logger
from qdash.workflow.service import CalibService


@flow
def parallel_retry_calibration(
    username: str,
    chip_id: str,
    qids: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Parallel calibration with retry on failure.

    Uses multiprocess execution via DaskTaskRunner for true parallel
    execution with isolated memory space per group.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        qids: Not used (groups defined below)
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)
    """
    logger = get_run_logger()

    # =========================================================================
    # Configuration
    # =========================================================================

    # Qubit groups
    # - Groups run in PARALLEL PROCESSES (using DaskTaskRunner)
    # - Qubits within each group run SEQUENTIALLY
    groups = [
        ["0", "1"],  # Group 0: Q0 → Q1 sequential
        ["2", "3"],  # Group 1: Q2 → Q3 sequential
    ]
    all_qids = [qid for group in groups for qid in group]

    tasks = [
        "CheckRabi",
        "CreateHPIPulse",
        "CheckHPIPulse",
        "CreatePIPulse",
        "CheckPIPulse",
        "CheckT1",
        "CheckT2Echo",
    ]

    # Frequency offsets for retry: default, +1MHz, -1MHz
    frequency_offsets = [0, 0.001, -0.001]

    # =========================================================================
    # Execution
    # =========================================================================

    logger.info(f"Starting parallel calibration: {len(groups)} groups, {len(all_qids)} qubits")

    # Initialize parent session
    cal = CalibService(
        username,
        chip_id,
        qids=all_qids,
        flow_name=flow_name,
        project_id=project_id,
    )

    try:
        # Build session config for multiprocess execution
        session_config = {
            "username": cal.username,
            "chip_id": cal.chip_id,
            "backend_name": cal.backend_name,
            "execution_id": cal.execution_id,
            "project_id": cal.project_id,
        }

        # === PARALLEL PROCESSES: Run groups using DaskTaskRunner ===
        from qdash.workflow.service._internal.scheduling_tasks import (
            run_groups_with_retry_parallel,
        )

        results = run_groups_with_retry_parallel(
            groups=groups,
            tasks=tasks,
            offsets=frequency_offsets,
            session_config=session_config,
        )

        # Summary
        success = [q for q, r in results.items() if r["status"] == "success"]
        failed = [q for q, r in results.items() if r["status"] == "failed"]
        logger.info(f"Success: {len(success)}, Failed: {len(failed)}")

        cal.finish_calibration()
        return results

    except Exception as e:
        logger.error(f"Calibration failed: {e}")
        cal.fail_calibration(str(e))
        raise
