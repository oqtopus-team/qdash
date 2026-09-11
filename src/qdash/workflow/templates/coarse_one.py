"""Coarse 1-qubit calibration through Ramsey, based on the one_qubit check stage.

Run this after bring-up has established the qubit frequency, control amplitude,
and readout settings. The flow applies the current hardware configuration,
refines readout settings, runs Rabi and calibrates/checks HPI, PI, DRAG HPI, and
DRAG PI, then measures T1/T2Echo and Ramsey
for explicitly selected MUXes or qubits.

Example:
    coarse_one(username="alice", chip_id="64Qv3", mux_ids=[0, 1])
"""

from typing import Any

from prefect import flow

from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import OneQubitCheck
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target

COARSE_ONE_TASKS: list[str] = [
    "Configure",  # Apply the starting configuration before the readout search.
    "CheckCoarseReadoutParams",
    "Configure",  # Apply the updated readout settings before pulse calibration.
    "CheckRabi",  # Update control amplitude from the measured Rabi frequency.
    "CheckRabi",  # Measure again at the updated amplitude for HPI creation.
    "CreateHPIPulse",
    "CheckHPIPulse",
    "CreatePIPulse",
    "CheckPIPulse",
    "CreateDRAGHPIPulse",
    "CheckDRAGHPIPulse",
    "CreateDRAGPIPulse",
    "CheckDRAGPIPulse",
    "CheckT1",
    "CheckT2Echo",
    "CheckRamsey",
]


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def coarse_one(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Run the coarse 1-qubit check stage through Ramsey.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to calibrate when using MUX-based scheduling
        exclude_qids: Qubit IDs to exclude when using mux_ids
        qids: Qubit IDs to calibrate when mux_ids is not set
        tags: Flow tags
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results with one_qubit_check output
    """
    targets: Target
    if mux_ids is not None:
        targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids or [])
    elif qids is not None:
        targets = QubitTargets(qids=qids)
    else:
        raise ValueError("mux_ids or qids is required; select targets before running this flow")

    steps = [OneQubitCheck(mode="synchronized", tasks=COARSE_ONE_TASKS)]

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        default_run_parameters={
            "CreateHPIPulse": {
                "hpi_duration": {"value": 32, "value_type": "int"},
            },
            "CreatePIPulse": {
                "pi_duration": {"value": 32, "value_type": "int"},
            },
            "CreateDRAGHPIPulse": {
                "drag_hpi_duration": {"value": 16, "value_type": "int"},
            },
            "CreateDRAGPIPulse": {
                "drag_pi_duration": {"value": 24, "value_type": "int"},
            },
            "interval": {"value": 150 * 1024, "value_type": "int"},
        },
    )
    return cal.run(targets, steps=steps)
