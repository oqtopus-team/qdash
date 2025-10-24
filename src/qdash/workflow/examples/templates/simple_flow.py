"""Simple calibration flow template."""

from prefect import flow, get_run_logger
from qdash.workflow.helpers import calibrate_qubits_parallel, finish_calibration, init_calibration


@flow
def my_custom_flow(
    username: str,  # Automatically provided from UI properties
    chip_id: str,  # Automatically provided from UI properties
    qids: list[str] | None = None,
    flow_name: str | None = None,  # Automatically injected by API
):
    """Simple calibration flow for demonstration.

    Note: username and chip_id are automatically provided from UI properties.
    You only need to specify qids (qubit IDs) if you want to override the default.

    Args:
    ----
        username: User name for calibration (from UI)
        chip_id: Target chip ID (from UI)
        qids: List of qubit IDs to calibrate (e.g., ["32", "38"])

    """
    logger = get_run_logger()

    if qids is None:
        qids = ["32"]  # TODO: Change to your qubit IDs

    logger.info(f"Starting calibration for user={username}, chip_id={chip_id}, qids={qids}")

    # Initialize calibration session
    init_calibration(username, chip_id, qids, flow_name=flow_name)

    # TODO: Edit the tasks you want to run
    # Available tasks: CheckRabi, CreateHPIPulse, CheckHPIPulse, etc.
    logger.info("Executing tasks in parallel...")
    results = calibrate_qubits_parallel(qids=qids, tasks=["CheckRabi", "CreateHPIPulse", "CheckHPIPulse"])

    # Finish calibration
    finish_calibration()

    logger.info("Calibration completed successfully")
    return results
