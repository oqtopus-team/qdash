"""Sequential calibration flow template."""

from prefect import flow, get_run_logger
from qdash.workflow.helpers import (
    calibrate_qubits_qubit_first,
    finish_calibration,
    get_session,
    init_calibration,
)


@flow
def sequential_calibration_flow(
    username: str,  # Automatically provided from UI properties
    chip_id: str,  # Automatically provided from UI properties
    qids: list[str] | None = None,
    flow_name: str | None = None,  # Automatically injected by API
):
    """Sequential calibration - complete all tasks for each qubit before moving to next.

    Execution order: Q0:[Task1→Task2→Task3], Q1:[Task1→Task2→Task3], Q2:[Task1→Task2→Task3]

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

    logger.info(f"Starting sequential calibration for user={username}, chip_id={chip_id}, qids={qids}")

    try:
        init_calibration(username, chip_id, qids, flow_name=flow_name)

        # TODO: Edit the tasks you want to run sequentially
        # Complete all tasks for each qubit before moving to the next qubit
        logger.info("Executing tasks in qubit-first order (sequential per qubit)...")
        results = calibrate_qubits_qubit_first(qids=qids, tasks=["CheckRabi", "CreateHPIPulse", "CheckHPIPulse"])

        finish_calibration()

        logger.info("Sequential calibration completed successfully")
        return results

    except Exception as e:
        logger.error(f"Sequential calibration failed: {e}")
        session = get_session()
        session.fail_calibration(str(e))
        raise
