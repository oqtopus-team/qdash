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

    # Pulse durations (ns) shared by every pulse calibration in both stages.
    hpi_duration = 32
    pi_duration = 32
    drag_hpi_duration = 16
    drag_pi_duration = 24

    # Task lists are explicit so this template can be reviewed and edited on its own.
    # Tests keep these stages aligned with coarse_one and fine_one.
    # Step 1: coarse calibration through Ramsey, calibrating and checking all four pulse types.
    steps: list[Step] = [
        OneQubitCheck(
            mode="synchronized",
            tasks=[
                # Apply the starting configuration before the readout search.
                TaskCall(name="Configure", call_id="configure_initial"),
                TaskCall(name="CheckCoarseReadoutParams"),
                # Apply the updated readout settings before pulse calibration.
                TaskCall(name="Configure", call_id="configure_readout"),
                # Update control amplitude from the measured Rabi frequency.
                TaskCall(name="CheckRabi", call_id="rabi_amplitude_update"),
                # Measure again at the updated amplitude for HPI creation.
                TaskCall(name="CheckRabi", call_id="rabi_at_updated_amplitude"),
                TaskCall(name="CreateHPIPulse", run={"hpi_duration": hpi_duration}),
                TaskCall(name="CheckHPIPulse"),
                TaskCall(name="CreatePIPulse", run={"pi_duration": pi_duration}),
                TaskCall(name="CheckPIPulse"),
                TaskCall(name="CreateDRAGHPIPulse", run={"drag_hpi_duration": drag_hpi_duration}),
                TaskCall(name="CheckDRAGHPIPulse"),
                TaskCall(name="CreateDRAGPIPulse", run={"drag_pi_duration": drag_pi_duration}),
                TaskCall(name="CheckDRAGPIPulse"),
                TaskCall(
                    name="CheckT1",
                    # Uncomment to make the sweep range explicit (100 ns to 500 us).
                    # run={"time_range": sweep.logspace(math.log10(100), math.log10(500_000), 51)},
                ),
                TaskCall(
                    name="CheckT2Echo",
                    # Uncomment to make the sweep range explicit (300 ns to 100 us).
                    # run={"time_range": sweep.logspace(math.log10(300), math.log10(100_000), 51)},
                ),
                TaskCall(name="CheckRamsey"),
            ],
        ),
    ]
    if not check_only:
        # Step 3: fine calibration after the successful-qubit filter.
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
                        name="CheckOptimalReadoutAmplitude",
                        call_id=f"readout_amplitude_{round_name}",
                    ),
                    TaskCall(
                        name="CheckOptimalReadoutFrequency",
                        call_id=f"readout_frequency_{round_name}",
                    ),
                    TaskCall(name="Configure", call_id=f"configure_{next_round}"),
                ]
        # Classify readout and benchmark only after the final pulse calibration.
        fine_tasks += [
            TaskCall(name="ReadoutClassification"),
            TaskCall(name="RandomizedBenchmarking"),
            TaskCall(name="X90InterleavedRandomizedBenchmarking"),
        ]

        # Run coarse -> filter successful qubits -> fine, with one Execution per stage.
        steps += [
            FilterByStatus(),  # Only proceed with successful qubits
            OneQubitFineTune(mode="synchronized", tasks=fine_tasks),
        ]

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
