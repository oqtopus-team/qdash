"""Bring-up calibration for MUX-level characterization.

This template runs MUX-level bring-up tasks like resonator spectroscopy.
These tasks are executed once per MUX, not per qubit.

Example:
    bringup(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1, 2, 3],
    )
"""

from typing import Any

from prefect import flow
from qdash.workflow.service import CalibService
from qdash.workflow.service.steps import BringUp
from qdash.workflow.service.targets import MuxTargets


@flow
def bringup(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    mode: str = "scheduled",
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Bring-up calibration for MUX-level characterization.

    This flow runs MUX-level tasks (e.g., CheckResonatorSpectroscopy) that
    characterize the entire MUX unit. Tasks are executed only for the
    representative qubit (qid % 4 == 0) of each MUX.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to calibrate (default: all 16)
        exclude_qids: Qubit IDs to exclude
        qids: Not used (for UI compatibility)
        mode: Execution mode:
            - "scheduled": Box-based parallelism with hardware constraints (default)
            - "serial": Fully sequential execution (one MUX at a time)
            - "synchronized": Step-based synchronized execution
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results with bring-up step outputs
    """
    if mux_ids is None:
        mux_ids = list(range(16))
    if exclude_qids is None:
        exclude_qids = []

    targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids)

    steps = [
        BringUp(mode=mode),
    ]

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        skip_execution=True,
    )
    return cal.run(targets, steps=steps)
