"""Adaptive calibration flow template with convergence detection."""

from prefect import flow, get_run_logger
from qdash.workflow.helpers import adaptive_calibrate, finish_calibration, get_session, init_calibration


@flow
def adaptive_calibration_flow(
    username: str,  # Automatically provided from UI properties
    chip_id: str,  # Automatically provided from UI properties
    qids: list[str] | None = None,
    max_iterations: int = 5,  # TODO: Adjust maximum iterations
    convergence_threshold: float = 0.01,  # TODO: Adjust convergence threshold
    flow_name: str | None = None,  # Automatically injected by API
):
    """Adaptive calibration with convergence detection.

    Repeats calibration until convergence or max iterations reached.

    Note: username and chip_id are automatically provided from UI properties.

    Args:
    ----
        username: User name for calibration (from UI)
        chip_id: Target chip ID (from UI)
        qids: List of qubit IDs to calibrate (e.g., ["32", "38"])
        max_iterations: Maximum number of calibration iterations
        convergence_threshold: Threshold for convergence detection

    """
    logger = get_run_logger()

    if qids is None:
        qids = ["32"]  # TODO: Change to your qubit IDs

    logger.info(
        f"Starting adaptive calibration for user={username}, chip_id={chip_id}, qids={qids}, "
        f"max_iterations={max_iterations}, threshold={convergence_threshold}"
    )

    try:
        init_calibration(username, chip_id, qids, flow_name=flow_name)

        # TODO: Edit the tasks and convergence parameters
        # Execute adaptive calibration with convergence check
        logger.info("Executing adaptive calibration with convergence detection...")
        results = adaptive_calibrate(
            qids=qids,
            tasks=["CheckRabi", "CreateHPIPulse", "CheckHPIPulse"],
            max_iterations=max_iterations,
            convergence_threshold=convergence_threshold,
        )

        finish_calibration()

        logger.info("Adaptive calibration completed successfully")
        return results

    except Exception as e:
        logger.error(f"Adaptive calibration failed: {e}")
        session = get_session()
        session.fail_calibration(str(e))
        raise
