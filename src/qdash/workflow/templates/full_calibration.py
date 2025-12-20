"""Full calibration using step-based pipeline.

This template demonstrates the step-based calibration API.

Execution flow:
    1. OneQubitCheck: Basic 1Q characterization (Rabi, HPI, T1, T2, Ramsey)
    2. FilterByStatus: Filter to only successful qubits
    3. OneQubitFineTune: Advanced 1Q calibration (DRAG, RB, X90 IRB)
    4. FilterByMetric: Filter by X90 fidelity threshold
    5. GenerateCRSchedule: Generate 2Q execution schedule
    6. TwoQubitCalibration: 2Q coupling calibration

Example:
    full_calibration(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1, 2, 3],
    )
"""

from typing import Any

from prefect import flow

from qdash.workflow.service import CalibService
from qdash.workflow.service.steps import (
    FilterByMetric,
    FilterByStatus,
    GenerateCRSchedule,
    OneQubitCheck,
    OneQubitFineTune,
    TwoQubitCalibration,
)
from qdash.workflow.service.targets import MuxTargets


@flow
def full_calibration(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
    fidelity_threshold: float = 0.90,
    max_parallel_ops: int = 10,
) -> Any:
    """Full calibration using step-based pipeline.

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

    Returns:
        Pipeline results with typed step outputs
    """
    # =========================================================================
    # Configuration
    # =========================================================================

    if mux_ids is None:
        mux_ids = list(range(16))
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
        # Stage 1: Basic 1Q characterization
        OneQubitCheck(mode="synchronized"),
        FilterByStatus(),  # Only proceed with successful qubits
        # Stage 2: Advanced 1Q calibration (DRAG, RB, IRB)
        OneQubitFineTune(mode="synchronized"),
        # Stage 3: Filter by X90 fidelity
        FilterByMetric(metric="x90_fidelity", threshold=fidelity_threshold),
        # Stage 4: Generate 2Q schedule
        GenerateCRSchedule(max_parallel_ops=max_parallel_ops),
        # Stage 5: 2Q calibration
        TwoQubitCalibration(),
    ]

    # =========================================================================
    # Execute Pipeline
    # =========================================================================

    cal = CalibService(username, chip_id, flow_name=flow_name, project_id=project_id)
    return cal.run(targets, steps=steps)
