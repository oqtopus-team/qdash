"""1-Qubit calibration using step-based pipeline.

This template combines coarse_one and fine_one, advancing successful qubits
from the coarse stage to the fine stage. Each stage has its own Execution.

Example:
    one_qubit(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1, 2, 3],
    )
"""

import math  # noqa: F401  # used by commented range overrides below
from typing import Any

from prefect import flow

from qdash.workflow import TaskCall, sweep  # noqa: F401  # used by commented range overrides below
from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import (
    FilterByStatus,
    OneQubitCheck,
    OneQubitFineTune,
    Step,
)
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target

# Task lists are explicit so this template can be reviewed and edited on its own.
# Tests keep these stages aligned with coarse_one and fine_one.
# Step 1: coarse calibration through Ramsey, calibrating and checking all four pulse types.
ONE_QUBIT_CHECK_TASKS: list[TaskCall] = [
    # Apply the starting configuration before the readout search.
    TaskCall(name="Configure", call_id="configure_initial"),
    TaskCall(name="CheckCoarseReadoutParams"),
    # Apply the updated readout settings before pulse calibration.
    TaskCall(name="Configure", call_id="configure_readout"),
    # Update control amplitude from the measured Rabi frequency.
    TaskCall(name="CheckRabi", call_id="rabi_amplitude_update"),
    # Measure again at the updated amplitude for HPI creation.
    TaskCall(name="CheckRabi", call_id="rabi_at_updated_amplitude"),
    TaskCall(name="CreateHPIPulse"),
    TaskCall(name="CheckHPIPulse"),
    TaskCall(name="CreatePIPulse"),
    TaskCall(name="CheckPIPulse"),
    TaskCall(name="CreateDRAGHPIPulse"),
    TaskCall(name="CheckDRAGHPIPulse"),
    TaskCall(name="CreateDRAGPIPulse"),
    TaskCall(name="CheckDRAGPIPulse"),
    TaskCall(name="CheckT1"),
    TaskCall(name="CheckT2Echo"),
    TaskCall(name="CheckRamsey"),
]

# Step 3: fine calibration after the successful-qubit filter.
ONE_QUBIT_FINE_TUNE_TASKS: list[TaskCall] = [
    TaskCall(name="Configure", call_id="configure_round1"),
    # Round 1: calibrate HPI -> PI -> DRAG HPI -> DRAG PI, then tune amplitude/frequency.
    TaskCall(name="CheckRabi", call_id="rabi_round1"),
    TaskCall(name="CreateHPIPulse", call_id="hpi_create_round1"),
    TaskCall(name="CheckHPIPulse", call_id="hpi_check_round1"),
    TaskCall(name="CreatePIPulse", call_id="pi_create_round1"),
    TaskCall(name="CheckPIPulse", call_id="pi_check_round1"),
    TaskCall(name="CreateDRAGHPIPulse", call_id="drag_hpi_create_round1"),
    TaskCall(name="CheckDRAGHPIPulse", call_id="drag_hpi_check_round1"),
    TaskCall(name="CreateDRAGPIPulse", call_id="drag_pi_create_round1"),
    TaskCall(name="CheckDRAGPIPulse", call_id="drag_pi_check_round1"),
    TaskCall(name="CheckOptimalReadoutAmplitude", call_id="readout_amplitude_round1"),
    TaskCall(name="CheckOptimalReadoutFrequency", call_id="readout_frequency_round1"),
    TaskCall(
        name="Configure", call_id="configure_round2"
    ),  # Apply round 1's readout frequency before recalibrating pulses.
    # Round 2: recalibrate all four pulse types at the updated settings, then repeat the pair.
    TaskCall(name="CheckRabi", call_id="rabi_round2"),
    TaskCall(name="CreateHPIPulse", call_id="hpi_create_round2"),
    TaskCall(name="CheckHPIPulse", call_id="hpi_check_round2"),
    TaskCall(name="CreatePIPulse", call_id="pi_create_round2"),
    TaskCall(name="CheckPIPulse", call_id="pi_check_round2"),
    TaskCall(name="CreateDRAGHPIPulse", call_id="drag_hpi_create_round2"),
    TaskCall(name="CheckDRAGHPIPulse", call_id="drag_hpi_check_round2"),
    TaskCall(name="CreateDRAGPIPulse", call_id="drag_pi_create_round2"),
    TaskCall(name="CheckDRAGPIPulse", call_id="drag_pi_check_round2"),
    TaskCall(name="CheckOptimalReadoutAmplitude", call_id="readout_amplitude_round2"),
    TaskCall(name="CheckOptimalReadoutFrequency", call_id="readout_frequency_round2"),
    TaskCall(
        name="Configure", call_id="configure_final"
    ),  # Apply the final readout frequency before final pulse calibration.
    # Calibrate all pulses at the final readout settings before classification and RB.
    TaskCall(name="CheckRabi", call_id="rabi_final"),
    TaskCall(name="CreateHPIPulse", call_id="hpi_create_final"),
    TaskCall(name="CheckHPIPulse", call_id="hpi_check_final"),
    TaskCall(name="CreatePIPulse", call_id="pi_create_final"),
    TaskCall(name="CheckPIPulse", call_id="pi_check_final"),
    TaskCall(name="CreateDRAGHPIPulse", call_id="drag_hpi_create_final"),
    TaskCall(name="CheckDRAGHPIPulse", call_id="drag_hpi_check_final"),
    TaskCall(name="CreateDRAGPIPulse", call_id="drag_pi_create_final"),
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
def one_qubit(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
    check_only: bool = False,
) -> Any:
    """1-Qubit calibration using step-based pipeline.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to calibrate when using MUX-based scheduling
        exclude_qids: Qubit IDs to exclude
        qids: Qubit IDs to calibrate when mux_ids is not set
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)
        check_only: If True, run only the coarse stage with all four pulse types

    Returns:
        Pipeline results with typed step outputs
    """
    if exclude_qids is None:
        exclude_qids = []

    targets: Target
    if mux_ids is not None:
        targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids)
    elif qids is not None:
        targets = QubitTargets(qids=qids)
    else:
        raise ValueError("mux_ids or qids is required; select targets before running this flow")

    steps: list[Step]
    if check_only:
        # Run only the coarse stage shown above.
        steps = [
            OneQubitCheck(mode="synchronized", tasks=ONE_QUBIT_CHECK_TASKS),
        ]
    else:
        # Run coarse -> filter successful qubits -> fine, with one Execution per calibration stage.
        steps = [
            OneQubitCheck(mode="synchronized", tasks=ONE_QUBIT_CHECK_TASKS),
            FilterByStatus(),  # Only proceed with successful qubits
            OneQubitFineTune(mode="synchronized", tasks=ONE_QUBIT_FINE_TUNE_TASKS),
        ]

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        task_parameters={
            "CreateHPIPulse": {
                "run": {
                    "hpi_duration": 32,
                },
            },
            "CreatePIPulse": {
                "run": {
                    "pi_duration": 32,
                },
            },
            "CreateDRAGHPIPulse": {
                "run": {
                    "drag_hpi_duration": 16,
                },
            },
            "CreateDRAGPIPulse": {
                "run": {
                    "drag_pi_duration": 24,
                },
            },
            # Per-task overrides — uncomment to make coherence sweep ranges explicit.
            # "CheckT1": {
            #     "run": {
            #         "time_range": sweep.logspace(
            #             math.log10(100), math.log10(500_000), 51
            #         ),  # 100 ns 〜 500 μs
            #     },
            # },
            # "CheckT2Echo": {
            #     "run": {
            #         "time_range": sweep.logspace(
            #             math.log10(300), math.log10(100_000), 51
            #         ),  # 300 ns 〜 100 μs
            #     },
            # },
        },
        default_run_parameters={
            "readout_duration": 1024,
            "interval": 150 * 1024,
        },
    )
    return cal.run(targets, steps=steps)
