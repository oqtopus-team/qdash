"""Parallel calibration flow template."""

from prefect import flow, get_run_logger
from qdash.workflow.helpers import (
    calibrate_qubits_task_first,
    finish_calibration,
    init_calibration,
)


@flow
def parallel_calibration_flow(
    username: str,  # Automatically provided from UI properties
    chip_id: str,  # Automatically provided from UI properties
    qids: list[str] | None = None,
    flow_name: str | None = None,  # Automatically injected by API
):
    """Parallel calibration across multiple qubits.

    Execution order: Task1→[Q0,Q1,Q2], Task2→[Q0,Q1,Q2], Task3→[Q0,Q1,Q2]

    Note: username and chip_id are automatically provided from UI properties.

    Args:
    ----
        username: User name for calibration (from UI)
        chip_id: Target chip ID (from UI)
        qids: List of qubit IDs to calibrate (e.g., ["32", "38", "39"])

    """
    logger = get_run_logger()

    if qids is None:
        qids = ["32", "38"]  # TODO: Change to your qubit IDs

    logger.info(f"Starting parallel calibration for user={username}, chip_id={chip_id}, qids={qids}")

    init_calibration(username, chip_id, qids, flow_name=flow_name)

    # TODO: Edit the tasks you want to run in parallel
    # Execute tasks sequentially, but process all qubits in parallel for each task
    logger.info("Executing tasks in task-first order (parallel per task)...")
    results = calibrate_qubits_task_first(qids=qids, tasks=["CheckRabi", "CreateHPIPulse", "CheckHPIPulse"])

    finish_calibration()

    logger.info("Parallel calibration completed successfully")
    return results
