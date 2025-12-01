"""CheckSkew calibration flow template.

This template demonstrates how to execute system-level tasks like CheckSkew
that operate on MUX channels rather than individual qubits.

System tasks:
- Don't require qid specification (use empty string "")
- Use task_details to pass parameters like muxes
- Check and calibrate system-wide parameters like signal skew
"""

from prefect import flow, get_run_logger
from qdash.workflow.flow import finish_calibration, get_session, init_calibration


@flow
def check_skew_flow(
    username: str,  # Automatically provided from UI properties
    chip_id: str,  # Automatically provided from UI properties
    muxes: list[int] | None = None,
    flow_name: str | None = None,  # Automatically injected by API
):
    """CheckSkew calibration flow for system-level skew measurement.

    This flow executes the CheckSkew task which measures and calibrates
    timing skew across the specified MUX channels.

    Note: username and chip_id are automatically provided from UI properties.

    Args:
    ----
        username: User name for calibration (from UI)
        chip_id: Target chip ID (from UI)
        muxes: List of MUX IDs to check skew (e.g., [0, 1, 2, 4, 5, 6])
        flow_name: Flow name (automatically injected by API)

    """
    logger = get_run_logger()

    if muxes is None:
        # TODO: Change to your MUX IDs
        muxes = [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]

    logger.info(f"Starting CheckSkew calibration for user={username}, chip_id={chip_id}, muxes={muxes}")

    try:
        # Initialize calibration session
        # For system tasks, qids can be empty list
        init_calibration(
            username,
            chip_id,
            qids=[],  # System tasks don't require qids
            flow_name=flow_name,
        )

        session = get_session()

        # Execute CheckSkew task with muxes parameter
        # System tasks use empty string "" as qid
        # Pass muxes via task_details to override the default value
        logger.info("Executing CheckSkew task...")
        result = session.execute_task(
            "CheckSkew",
            qid="",
            task_details={
                "CheckSkew": {
                    "muxes": muxes,
                }
            },
        )

        logger.info(f"CheckSkew completed successfully: {result}")

        # Finish calibration
        finish_calibration()

        return result

    except Exception as e:
        logger.error(f"CheckSkew calibration failed: {e}")
        try:
            session = get_session()
            session.fail_calibration(str(e))
        except RuntimeError:
            # Session not initialized yet, skip fail_calibration
            pass
        raise
