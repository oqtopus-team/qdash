"""1-Qubit calibration using step-based pipeline.

This template demonstrates the step-based API for 1-qubit calibration.

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
from qdash.workflow.service.calib_service import on_flow_cancellation, on_flow_crash
from qdash.workflow.service.steps import (
    FilterByStatus,
    OneQubitCheck,
    OneQubitFineTune,
    Step,
)
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target


@flow(on_cancellation=[on_flow_cancellation], on_crashed=[on_flow_crash])
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
        mux_ids: MUX IDs to calibrate (default: all 16)
        exclude_qids: Qubit IDs to exclude
        qids: Qubit IDs to calibrate when mux_ids is not set
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)
        check_only: If True, only run basic check (no fine-tune)

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
        targets = MuxTargets(mux_ids=list(range(16)), exclude_qids=exclude_qids)

    steps: list[Step]
    if check_only:
        # Basic check only
        steps = [
            OneQubitCheck(mode="synchronized"),
        ]
    else:
        # Full 1Q calibration
        steps = [
            OneQubitCheck(mode="synchronized"),
            FilterByStatus(),  # Only proceed with successful qubits
            OneQubitFineTune(mode="synchronized"),
        ]

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        skip_execution=True,  # Child sessions create their own Executions
        default_run_parameters={
            "hpi_duration": {"value": 32, "value_type": "int"},
            "pi_duration": {"value": 32, "value_type": "int"},
            "drag_hpi_duration": {"value": 16, "value_type": "int"},
            "drag_pi_duration": {"value": 24, "value_type": "int"},
            "interval": {"value": 150 * 1024, "value_type": "int"},
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
    )
    return cal.run(targets, steps=steps)
