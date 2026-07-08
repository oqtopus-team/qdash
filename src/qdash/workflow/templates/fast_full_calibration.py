"""Fast full calibration using a shortened step-based pipeline.

This template keeps the end-to-end 1Q-to-2Q flow from full_calibration, but
skips long or duplicated 1Q coherence checks. It is intended for quicker daily
passes when the chip is already close to a calibrated state.

Execution flow:
    1. ConfigureAll: Push the current full-chip configuration to the selected MUXes
    2. OneQubitCheck: Fast pulse sanity check
    3. FilterByStatus: Filter to only successful qubits
    4. OneQubitFineTune: Pulse/readout/RB/X90 IRB tune without T1/T2 averages
    5. FilterByMetric: Filter by X90 fidelity threshold
    6. GenerateCRSchedule: Generate 2Q execution schedule
    7. TwoQubitCalibration: 2Q coupling calibration

Example:
    fast_full_calibration(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1, 2, 3],
    )
"""

from typing import Any

from prefect import flow

from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import on_flow_cancellation
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

FAST_1Q_CHECK_TASKS: list[str] = [
    "CheckRabi",
    "CreateHPIPulse",
    "CheckHPIPulse",
]

FAST_1Q_FINE_TUNE_TASKS: list[str] = [
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


@flow(on_cancellation=[on_flow_cancellation])
def fast_full_calibration(
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
    """Fast full calibration using a shortened step-based pipeline.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to calibrate (default: all 16)
        exclude_qids: Qubit IDs to exclude
        qids: Not used (for UI compatibility)
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)
        fidelity_threshold: Minimum X90 fidelity for 2Q candidates (default: 0.90)
        max_parallel_ops: Max parallel CR operations (default: 10)
        inverse: CR direction control based on checkerboard pattern.
            False (default): forward direction. True: reverse direction.

    Returns:
        Pipeline results with typed step outputs.
    """
    _ = qids

    if mux_ids is None:
        mux_ids = list(range(16))
    if exclude_qids is None:
        exclude_qids = []

    targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids)

    steps = [
        ConfigureAll(),
        OneQubitCheck(mode="synchronized", tasks=FAST_1Q_CHECK_TASKS),
        FilterByStatus(),
        OneQubitFineTune(mode="synchronized", tasks=FAST_1Q_FINE_TUNE_TASKS),
        FilterByMetric(metric="x90_fidelity", threshold=fidelity_threshold),
        GenerateCRSchedule(max_parallel_ops=max_parallel_ops, inverse=inverse),
        TwoQubitCalibration(),
    ]

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        skip_execution=True,
        default_run_parameters={
            "hpi_duration": {"value": 32, "value_type": "int"},
            "pi_duration": {"value": 32, "value_type": "int"},
            "drag_hpi_duration": {"value": 16, "value_type": "int"},
            "drag_pi_duration": {"value": 24, "value_type": "int"},
            "interval": {"value": 150 * 1024, "value_type": "int"},
        },
    )
    return cal.run(targets, steps=steps)
