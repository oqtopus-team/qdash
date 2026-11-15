"""Full calibration using step-based pipeline.

This template demonstrates the step-based calibration API.

Execution flow:
    1. ConfigureAll: Push the current full-chip configuration to the selected MUXes
    2. OneQubitCheck: Basic 1Q characterization (Rabi, HPI, T1, T2, Ramsey)
    3. FilterByStatus: Filter to only successful qubits
    4. OneQubitFineTune: Advanced 1Q calibration (DRAG, RB, X90 IRB)
    5. FilterByMetric: Filter by X90 fidelity threshold
    6. GenerateCRSchedule: Generate 2Q execution schedule
    7. TwoQubitCalibration: 2Q coupling calibration

Example:
    full_calibration(
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
    ConfigureAll,
    FilterByMetric,
    FilterByStatus,
    GenerateCRSchedule,
    OneQubitCheck,
    OneQubitFineTune,
    TwoQubitCalibration,
)
from qdash.workflow.service.targets import MuxTargets

FULL_1Q_CHECK_TASKS: list[TaskCall] = [
    # Update control amplitude, then measure again at the updated amplitude.
    TaskCall(name="CheckRabi", call_id="rabi_amplitude_update"),
    TaskCall(name="CheckRabi", call_id="rabi_at_updated_amplitude"),
    TaskCall(name="CreateHPIPulse", call_id="hpi_create_first", run={"hpi_duration": 32}),
    TaskCall(name="CheckHPIPulse", call_id="hpi_check_first"),
    # TaskCall(name="CheckOptimalReadoutFrequency"),
    # Second pass at the settings the first pass produced.
    TaskCall(name="CheckRabi", call_id="rabi_second_pass"),
    TaskCall(name="CreateHPIPulse", call_id="hpi_create_second", run={"hpi_duration": 32}),
    TaskCall(name="CheckHPIPulse", call_id="hpi_check_second"),
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
]

FULL_1Q_FINE_TUNE_TASKS: list[TaskCall] = [
    TaskCall(name="CheckRabi"),
    TaskCall(name="CreateHPIPulse", run={"hpi_duration": 32}),
    TaskCall(name="CheckHPIPulse"),
    TaskCall(name="CreatePIPulse", run={"pi_duration": 32}),
    TaskCall(name="CheckPIPulse"),
    TaskCall(name="CreateDRAGHPIPulse", run={"drag_hpi_duration": 16}),
    TaskCall(name="CheckDRAGHPIPulse"),
    TaskCall(name="CreateDRAGPIPulse", run={"drag_pi_duration": 24}),
    TaskCall(name="CheckDRAGPIPulse"),
    TaskCall(name="ReadoutClassification"),
    TaskCall(name="CheckT1Average"),
    TaskCall(name="CheckT2EchoAverage"),
    TaskCall(name="Check1QGateCoherenceLimit"),
    TaskCall(name="RandomizedBenchmarking"),
    TaskCall(name="X90InterleavedRandomizedBenchmarking"),
]

FULL_2Q_TASKS: list[TaskCall] = [
    TaskCall(
        name="CheckCrossResonance",
        # Uncomment to tune the CR parameter search.
        # run={
        #     "adiabatic_safe_factor": 0.65,
        #     "max_amplitude": 0.85,
        #     "max_time_range": 8192,
        # },
    ),
    TaskCall(name="CreateZX90"),
    TaskCall(name="CheckZX90"),
    TaskCall(name="CheckBellState"),
    TaskCall(name="CheckBellStateTomography"),
    TaskCall(name="Check2QGateCoherenceLimit"),
    TaskCall(name="ZX90InterleavedRandomizedBenchmarking"),
]


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def full_calibration(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
    fidelity_threshold: float = 0.90,
    max_parallel_ops: int = 10,
    inverse: bool = False,
) -> Any:
    """Full calibration using step-based pipeline.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to calibrate (required)
        exclude_qids: Qubit IDs to exclude
        qids: Not used (for UI compatibility)
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)
        fidelity_threshold: Minimum X90 fidelity for 2Q candidates (default: 0.90)
        max_parallel_ops: Max parallel CR operations (default: 10)
        inverse: CR direction control based on checkerboard pattern.
            False (default): Forward direction - control qubit is at even parity
            position (lower design frequency).
            True: Reverse direction - control qubit is at odd parity position
            (higher design frequency).

    Returns:
        Pipeline results with typed step outputs
    """
    # =========================================================================
    # Configuration
    # =========================================================================

    if mux_ids is None:
        raise ValueError("mux_ids is required; select MUX targets before running this flow")
    if exclude_qids is None:
        exclude_qids = []

    # =========================================================================
    # Define Targets
    # =========================================================================

    targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids)

    # =========================================================================
    # Define Pipeline Steps
    # =========================================================================

    steps = [
        # Stage 0: Push current configuration to all selected MUXes
        ConfigureAll(),
        # Stage 1: Basic 1Q characterization
        OneQubitCheck(execution_mode="parallel_by_round", tasks=FULL_1Q_CHECK_TASKS),
        FilterByStatus(),  # Only proceed with successful qubits
        # Stage 2: Advanced 1Q calibration (DRAG, RB, IRB)
        OneQubitFineTune(execution_mode="parallel_by_round", tasks=FULL_1Q_FINE_TUNE_TASKS),
        # Stage 3: Filter by X90 fidelity
        FilterByMetric(metric="x90_fidelity", threshold=fidelity_threshold),
        # Stage 4: Generate 2Q schedule with explicit direction
        GenerateCRSchedule(max_parallel_ops=max_parallel_ops, inverse=inverse),
        # Stage 5: 2Q calibration
        TwoQubitCalibration(tasks=FULL_2Q_TASKS),
    ]

    # =========================================================================
    # Execute Pipeline
    # =========================================================================

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
