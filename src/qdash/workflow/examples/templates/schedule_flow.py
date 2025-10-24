"""Custom schedule-based calibration flow template."""

from prefect import flow, get_run_logger
from qdash.datamodel.menu import BatchNode, ParallelNode, SerialNode
from qdash.workflow.helpers import execute_schedule, finish_calibration, init_calibration


@flow
def schedule_based_flow(
    username: str,  # Automatically provided from UI properties
    chip_id: str,  # Automatically provided from UI properties
    qids: list[str] | None = None,
    flow_name: str | None = None,  # Automatically injected by API
):
    """Custom schedule-based calibration flow.

    Demonstrates complex orchestration using schedule nodes.

    Note: username and chip_id are automatically provided from UI properties.

    Args:
    ----
        username: User name for calibration (from UI)
        chip_id: Target chip ID (from UI)
        qids: List of qubit IDs to calibrate (at least 3 recommended, e.g., ["32", "38", "39"])

    """
    logger = get_run_logger()

    if qids is None:
        qids = ["32", "38", "39"]  # TODO: Change to your qubit IDs

    logger.info(f"Starting schedule-based calibration for user={username}, chip_id={chip_id}, qids={qids}")

    init_calibration(username, chip_id, qids, flow_name=flow_name)

    # TODO: Define your custom schedule
    # Example: Execute first two qubits in parallel, then all qubits together
    # - SerialNode: Execute nodes one after another
    # - ParallelNode: Execute qubits in parallel
    # - BatchNode: Execute all qubits together
    schedule = SerialNode(
        serial=[ParallelNode(parallel=[qids[0], qids[1]] if len(qids) >= 2 else qids), BatchNode(batch=qids)]
    )
    logger.info(f"Executing custom schedule: {schedule}")

    # TODO: Edit the tasks you want to run
    logger.info("Executing tasks according to custom schedule...")
    results = execute_schedule(tasks=["CheckRabi", "CreateHPIPulse", "CheckHPIPulse"], schedule=schedule)

    finish_calibration()

    logger.info("Schedule-based calibration completed successfully")
    return results
