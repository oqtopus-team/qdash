"""System-level skew measurement and calibration.

Measures and calibrates timing skew across MUX channels.

Example:
    check_skew(
        username="alice",
        chip_id="64Qv3",
        muxes=[0, 1, 2, 4, 5, 6],
    )
"""

from typing import Any

from prefect import flow, get_run_logger

from qdash.workflow.service import CalibService


@flow
def check_skew(
    username: str,
    chip_id: str,
    muxes: list[int] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """System-level CheckSkew calibration.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        muxes: MUX IDs to check skew (default: all except 3)
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        CheckSkew task result
    """
    logger = get_run_logger()

    # =========================================================================
    # Configuration
    # =========================================================================

    if muxes is None:
        muxes = [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]

    logger.info(f"Running CheckSkew: {len(muxes)} MUX channels")

    # =========================================================================
    # Execution
    # =========================================================================

    cal = CalibService(
        username,
        chip_id,
        muxes=muxes,
        flow_name=flow_name,
        project_id=project_id,
    )

    try:
        cal._initialize([])

        result = cal.execute_task(
            "CheckSkew",
            qid="",
            task_details={"CheckSkew": {"muxes": muxes}},
        )

        cal.finish_calibration()
        return result

    except Exception as e:
        logger.error(f"CheckSkew failed: {e}")
        cal.fail_calibration(str(e))
        raise
