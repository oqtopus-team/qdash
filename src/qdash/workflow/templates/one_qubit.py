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

from typing import Any

import numpy as np  # noqa: F401  # used by commented per-task overrides below
from prefect import flow

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
ONE_QUBIT_CHECK_TASKS: list[str] = [
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

# Step 3: fine calibration after the successful-qubit filter.
ONE_QUBIT_FINE_TUNE_TASKS: list[str] = [
    "Configure",
    # Round 1: calibrate HPI -> PI -> DRAG HPI -> DRAG PI, then tune amplitude/frequency.
    "CheckRabi",
    "CreateHPIPulse",
    "CheckHPIPulse",
    "CreatePIPulse",
    "CheckPIPulse",
    "CreateDRAGHPIPulse",
    "CheckDRAGHPIPulse",
    "CreateDRAGPIPulse",
    "CheckDRAGPIPulse",
    "CheckOptimalReadoutAmplitude",
    "CheckOptimalReadoutFrequency",
    "Configure",  # Apply round 1's readout frequency before recalibrating pulses.
    # Round 2: recalibrate all four pulse types at the updated settings, then repeat the pair.
    "CheckRabi",
    "CreateHPIPulse",
    "CheckHPIPulse",
    "CreatePIPulse",
    "CheckPIPulse",
    "CreateDRAGHPIPulse",
    "CheckDRAGHPIPulse",
    "CreateDRAGPIPulse",
    "CheckDRAGPIPulse",
    "CheckOptimalReadoutAmplitude",
    "CheckOptimalReadoutFrequency",
    "Configure",  # Apply the final readout frequency before final pulse calibration.
    # Calibrate all pulses at the final readout settings before classification and RB.
    "CheckRabi",
    "CreateHPIPulse",
    "CheckHPIPulse",
    "CreatePIPulse",
    "CheckPIPulse",
    "CreateDRAGHPIPulse",
    "CheckDRAGHPIPulse",
    "CreateDRAGPIPulse",
    "CheckDRAGPIPulse",
    "ReadoutClassification",
    "RandomizedBenchmarking",
    "X90InterleavedRandomizedBenchmarking",
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
        task_run_parameters={
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
            # Per-task overrides — uncomment to extend coherence sweep ranges.
            # "CheckT1": {
            #     "time_range": {
            #         "value": (np.log10(100), np.log10(1000 * 1000), 51),  # 100 ns 〜 1 ms
            #         "value_type": "np.logspace",
            #     },
            # },
            # "CheckT2Echo": {
            #     "time_range": {
            #         "value": (np.log10(300), np.log10(500 * 1000), 51),  # 300 ns 〜 500 μs
            #         "value_type": "np.logspace",
            #     },
            # },
        },
        default_run_parameters={
            "readout_duration": {"value": 2048, "value_type": "int"},
            "interval": {"value": 150 * 1024, "value_type": "int"},
        },
    )
    return cal.run(targets, steps=steps)
