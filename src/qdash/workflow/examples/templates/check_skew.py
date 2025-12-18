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

from prefect import flow
from qdash.workflow.flow import CalService


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
        muxes: MUX IDs to check skew
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)
    """
    # =========================================================================
    # Configuration
    # =========================================================================

    if muxes is None:
        muxes = [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]

    # =========================================================================
    # Execution
    # =========================================================================

    cal = CalService(username, chip_id, flow_name=flow_name, project_id=project_id)
    return cal.check_skew(muxes=muxes)
