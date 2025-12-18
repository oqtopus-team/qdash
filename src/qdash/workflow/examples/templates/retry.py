"""Parallel calibration with retry template.

Demonstrates @task + submit() pattern for custom parallel logic.

Execution pattern:
    groups = [["0", "1"], ["2", "3"]]

    ┌─────────────────────────────────────────────────────────────┐
    │  PARALLEL: Groups submitted simultaneously                  │
    ├─────────────────────────────────────────────────────────────┤
    │  Group0: Q0 → Q1 with retry (SEQUENTIAL)                   │
    │                    ↓                         PARALLEL       │
    │  Group1: Q2 → Q3 with retry (SEQUENTIAL)                   │
    └─────────────────────────────────────────────────────────────┘

    Groups run in PARALLEL, qubits within group run SEQUENTIALLY.
    Each qubit has retry logic with frequency offset on failure.

Example:
    parallel_retry_calibration(
        username="alice",
        chip_id="64Qv3",
    )
"""

from typing import Any

from prefect import flow, get_run_logger, task
from qdash.workflow.service import CalService


@task
def calibrate_group_with_retry(
    cal: CalService,
    qids: list[str],
    tasks: list[str],
    offsets: list[float],
) -> dict[str, Any]:
    """Calibrate a group of qubits sequentially with retry logic.

    Runs in PARALLEL with other groups via submit().
    Qubits within the group run SEQUENTIALLY.

    Args:
        cal: CalService instance (shared)
        qids: Qubit IDs in this group (run sequentially)
        tasks: Task names (run sequentially per qubit)
        offsets: Frequency offsets to try on failure

    Returns:
        Results dict keyed by qubit ID
    """
    logger = get_run_logger()
    results = {}

    for qid in qids:
        # Retry loop for each qubit
        for attempt, offset in enumerate(offsets):
            try:
                if offset != 0:
                    logger.info(
                        f"Q{qid}: Attempt {attempt + 1} with {offset * 1000:+.0f} MHz offset"
                    )

                # Tasks run SEQUENTIALLY within qubit
                result = {}
                for task_name in tasks:
                    task_details = None
                    if offset != 0:
                        task_details = {
                            task_name: {
                                "input_parameters": {"qubit_frequency_offset": {"value": offset}}
                            }
                        }
                    result[task_name] = cal.execute_task(task_name, qid, task_details=task_details)

                result["status"] = "success"
                result["attempt"] = attempt + 1
                results[qid] = result
                break  # Success, move to next qubit

            except Exception as e:
                logger.warning(f"Q{qid}: Attempt {attempt + 1} failed: {e}")
                if attempt == len(offsets) - 1:
                    results[qid] = {"status": "failed", "error": str(e), "attempt": attempt + 1}

    return results


@flow
def parallel_retry_calibration(
    username: str,
    chip_id: str,
    qids: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Parallel calibration with retry on failure.

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
    # - Groups run in PARALLEL (submitted simultaneously)
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

    # Initialize with all qids
    cal = CalService(
        username,
        chip_id,
        qids=all_qids,
        flow_name=flow_name,
        project_id=project_id,
    )

    try:
        # === PARALLEL: submit each group ===
        futures = [
            calibrate_group_with_retry.submit(cal, group, tasks, frequency_offsets)
            for group in groups
        ]

        # Wait for all groups to complete
        group_results = [f.result() for f in futures]

        # Merge results
        results = {}
        for group_result in group_results:
            results.update(group_result)

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
