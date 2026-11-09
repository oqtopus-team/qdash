"""Fine 1-qubit calibration based on the one_qubit fine-tuning stage.

Run this after coarse_one or an equivalent calibration has established the
qubit frequency, control amplitude, and readout settings. The flow applies
those settings and tunes readout amplitude -> frequency -> amplitude -> frequency.
Configure applies the updated frequency after each amplitude/frequency pair.
Each amplitude/frequency pair starts with fresh Rabi and full pulse calibration
in HPI -> PI -> DRAG HPI -> DRAG PI order, including a check of each pulse.
This refreshes the base pulses as well as the DRAG pulses used for state preparation.
After both rounds, all pulses are calibrated at the final readout settings
before readout classification and randomized benchmarking.

Example:
    fine_one(username="alice", chip_id="64Qv3", mux_ids=[0, 1])
"""

from typing import Any

from prefect import flow

from qdash.workflow import TaskCall
from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import OneQubitFineTune
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target

FINE_ONE_TASKS: list[TaskCall] = [
    TaskCall(name="Configure", call_id="configure_round1"),
    # Round 1: calibrate HPI -> PI -> DRAG HPI -> DRAG PI, then tune amplitude/frequency.
    TaskCall(name="CheckRabi", call_id="rabi_round1"),
    TaskCall(name="CreateHPIPulse", call_id="hpi_create_round1", run={"hpi_duration": 32}),
    TaskCall(name="CheckHPIPulse", call_id="hpi_check_round1"),
    TaskCall(name="CreatePIPulse", call_id="pi_create_round1", run={"pi_duration": 32}),
    TaskCall(name="CheckPIPulse", call_id="pi_check_round1"),
    TaskCall(
        name="CreateDRAGHPIPulse", call_id="drag_hpi_create_round1", run={"drag_hpi_duration": 16}
    ),
    TaskCall(name="CheckDRAGHPIPulse", call_id="drag_hpi_check_round1"),
    TaskCall(
        name="CreateDRAGPIPulse", call_id="drag_pi_create_round1", run={"drag_pi_duration": 24}
    ),
    TaskCall(name="CheckDRAGPIPulse", call_id="drag_pi_check_round1"),
    TaskCall(name="CheckOptimalReadoutAmplitude", call_id="readout_amplitude_round1"),
    TaskCall(name="CheckOptimalReadoutFrequency", call_id="readout_frequency_round1"),
    TaskCall(
        name="Configure", call_id="configure_round2"
    ),  # Apply round 1's readout frequency before recalibrating pulses.
    # Round 2: recalibrate all four pulse types at the updated settings, then repeat the pair.
    TaskCall(name="CheckRabi", call_id="rabi_round2"),
    TaskCall(name="CreateHPIPulse", call_id="hpi_create_round2", run={"hpi_duration": 32}),
    TaskCall(name="CheckHPIPulse", call_id="hpi_check_round2"),
    TaskCall(name="CreatePIPulse", call_id="pi_create_round2", run={"pi_duration": 32}),
    TaskCall(name="CheckPIPulse", call_id="pi_check_round2"),
    TaskCall(
        name="CreateDRAGHPIPulse", call_id="drag_hpi_create_round2", run={"drag_hpi_duration": 16}
    ),
    TaskCall(name="CheckDRAGHPIPulse", call_id="drag_hpi_check_round2"),
    TaskCall(
        name="CreateDRAGPIPulse", call_id="drag_pi_create_round2", run={"drag_pi_duration": 24}
    ),
    TaskCall(name="CheckDRAGPIPulse", call_id="drag_pi_check_round2"),
    TaskCall(name="CheckOptimalReadoutAmplitude", call_id="readout_amplitude_round2"),
    TaskCall(name="CheckOptimalReadoutFrequency", call_id="readout_frequency_round2"),
    TaskCall(
        name="Configure", call_id="configure_final"
    ),  # Apply the final readout frequency before final pulse calibration.
    # Calibrate all pulses at the final readout settings before classification and RB.
    TaskCall(name="CheckRabi", call_id="rabi_final"),
    TaskCall(name="CreateHPIPulse", call_id="hpi_create_final", run={"hpi_duration": 32}),
    TaskCall(name="CheckHPIPulse", call_id="hpi_check_final"),
    TaskCall(name="CreatePIPulse", call_id="pi_create_final", run={"pi_duration": 32}),
    TaskCall(name="CheckPIPulse", call_id="pi_check_final"),
    TaskCall(
        name="CreateDRAGHPIPulse", call_id="drag_hpi_create_final", run={"drag_hpi_duration": 16}
    ),
    TaskCall(name="CheckDRAGHPIPulse", call_id="drag_hpi_check_final"),
    TaskCall(
        name="CreateDRAGPIPulse", call_id="drag_pi_create_final", run={"drag_pi_duration": 24}
    ),
    TaskCall(name="CheckDRAGPIPulse", call_id="drag_pi_check_final"),
    TaskCall(name="ReadoutClassification"),
    TaskCall(name="RandomizedBenchmarking"),
    TaskCall(name="X90InterleavedRandomizedBenchmarking"),
]


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def fine_one(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Run the 1-qubit fine-tuning stage using existing coarse calibration.

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
        Pipeline results with one_qubit_fine_tune output
    """
    targets: Target
    if mux_ids is not None:
        targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids or [])
    elif qids is not None:
        targets = QubitTargets(qids=qids)
    else:
        raise ValueError("mux_ids or qids is required; select targets before running this flow")

    steps = [OneQubitFineTune(mode="synchronized", tasks=FINE_ONE_TASKS)]

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        default_run_parameters={
            "readout_duration": 1024,
            "interval": 150 * 1024,
        },
    )
    return cal.run(targets, steps=steps)
