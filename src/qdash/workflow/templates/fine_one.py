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

    # Pulse durations (ns) shared by every round of pulse calibration.
    hpi_duration = 32
    pi_duration = 32
    drag_hpi_duration = 16
    drag_pi_duration = 24

    # Configure applies the latest readout settings before each pulse calibration round.
    fine_tasks: list[TaskCall] = [TaskCall(name="Configure", call_id="configure_round1")]
    for round_name, next_round in (("round1", "round2"), ("round2", "final"), ("final", None)):
        # Calibrate and check HPI -> PI -> DRAG HPI -> DRAG PI at the current settings.
        fine_tasks += [
            TaskCall(name="CheckRabi", call_id=f"rabi_{round_name}"),
            TaskCall(
                name="CreateHPIPulse",
                call_id=f"hpi_create_{round_name}",
                run={"hpi_duration": hpi_duration},
            ),
            TaskCall(name="CheckHPIPulse", call_id=f"hpi_check_{round_name}"),
            TaskCall(
                name="CreatePIPulse",
                call_id=f"pi_create_{round_name}",
                run={"pi_duration": pi_duration},
            ),
            TaskCall(name="CheckPIPulse", call_id=f"pi_check_{round_name}"),
            TaskCall(
                name="CreateDRAGHPIPulse",
                call_id=f"drag_hpi_create_{round_name}",
                run={"drag_hpi_duration": drag_hpi_duration},
            ),
            TaskCall(name="CheckDRAGHPIPulse", call_id=f"drag_hpi_check_{round_name}"),
            TaskCall(
                name="CreateDRAGPIPulse",
                call_id=f"drag_pi_create_{round_name}",
                run={"drag_pi_duration": drag_pi_duration},
            ),
            TaskCall(name="CheckDRAGPIPulse", call_id=f"drag_pi_check_{round_name}"),
        ]
        if next_round is not None:
            # Tune readout amplitude, then frequency, and apply them before the next round.
            fine_tasks += [
                TaskCall(
                    name="CheckOptimalReadoutAmplitude", call_id=f"readout_amplitude_{round_name}"
                ),
                TaskCall(
                    name="CheckOptimalReadoutFrequency", call_id=f"readout_frequency_{round_name}"
                ),
                TaskCall(name="Configure", call_id=f"configure_{next_round}"),
            ]
    # Classify readout and benchmark only after the final pulse calibration.
    fine_tasks += [
        TaskCall(name="ReadoutClassification"),
        TaskCall(name="RandomizedBenchmarking"),
        TaskCall(name="X90InterleavedRandomizedBenchmarking"),
    ]

    steps = [OneQubitFineTune(mode="synchronized", tasks=fine_tasks)]

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
