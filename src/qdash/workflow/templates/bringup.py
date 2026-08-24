"""Bring-up calibration for MUX-level characterization.

This template configures selected MUXes, then runs MUX-level bring-up tasks like
resonator spectroscopy. Bring-up tasks are executed once per MUX, not per qubit.

Example:
    bringup(
        username="alice",
        chip_id="16Q",
        mux_ids=[0, 1, 2, 3],
    )
"""

from typing import Any

from prefect import flow

from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import BringUp, ConfigureAll
from qdash.workflow.service.targets import MuxTargets

BRINGUP_TASKS: list[str] = [
    "CheckResonatorSpectroscopy",
    "CheckQubitSpectroscopy",
    "CheckControlAmplitude",
    "CheckChevron",
]


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
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

    This flow first pushes the current configuration to the selected MUXes, then
    runs MUX-level tasks (e.g., CheckResonatorSpectroscopy) that characterize the
    entire MUX unit. Tasks are executed only for the representative qubit
    (qid % 4 == 0) of each MUX.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to calibrate (required)
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
        raise ValueError("mux_ids is required; select MUX targets before running this flow")
    if exclude_qids is None:
        exclude_qids = []

    targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids)

    default_run_parameters: dict[str, Any] = {
        "interval": {"value": 150 * 1024, "value_type": "int"},
        # For a 16Q chip, use the following frequency-sorted resonator assignment:
        # "CheckResonatorSpectroscopy": {
        #     "resonator_assignment_order": {
        #         "value": [0, 3, 1, 2],
        #         "value_type": "list",
        #     },
        #     "frequency_range": {
        #         "value": [5.75, 6.75, 0.002],
        #         "value_type": "np.arange",
        #     },
        # },
        # "CheckQubitSpectroscopy": {
        #     "frequency_range": {
        #         "value": [3.0, 5.75, 0.005],
        #         "value_type": "np.arange",
        #     },
        # },
    }

    steps = [
        ConfigureAll(),
        BringUp(mode=mode, tasks=BRINGUP_TASKS),
    ]

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        skip_execution=True,
        default_run_parameters=default_run_parameters,
    )
    return cal.run(targets, steps=steps)
