"""Qubit coherence check template.

This template applies the current hardware configuration, records a coarse
Chevron measurement without updating calibration parameters, then runs two
coherence-check passes for explicitly selected MUXes or qubits.

Example:
    coherence_check(username="alice", chip_id="64Qv3", mux_ids=[0, 1])
"""

import math
from typing import Any

from prefect import flow

from qdash.workflow import sweep
from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target

COHERENCE_CHECK_TASKS: list[str] = [
    "Configure",
    "CheckChevron",
    "CheckRabi",
    "CheckT1",
    "CheckT2Echo",
    "CheckRamsey",
]

LONG_RAMSEY_CHECK_TASKS: list[str] = [
    "Configure",
    "CheckRabi",
    "CheckRamsey",
]


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def coherence_check(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Run coherence checks for selected targets.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to check using MUX-based scheduling
        exclude_qids: Qubit IDs to exclude when using mux_ids
        qids: Qubit IDs to check when mux_ids is not set
        tags: Flow tags
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results with coherence_check output
    """
    targets: Target
    if mux_ids is not None:
        targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids or [])
    elif qids is not None:
        targets = QubitTargets(qids=qids)
    else:
        raise ValueError("mux_ids or qids is required; select targets before running this flow")

    steps = [
        CustomOneQubit(
            step_name="coherence_check",
            tasks=COHERENCE_CHECK_TASKS,
            mode="synchronized",
        ),
        CustomOneQubit(
            step_name="long_ramsey_check",
            tasks=LONG_RAMSEY_CHECK_TASKS,
            mode="synchronized",
            task_parameters={
                "CheckRamsey": {
                    "run": {
                        # Keep 101 points while extending the time scale by 5x.
                        "time_range": sweep.arange(0, 50_001, 500),
                        "detuning": 0.0002,
                    },
                },
            },
        ),
    ]

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        task_parameters={
            "CheckChevron": {
                "run": {
                    # Keep the measurement grid explicit so users can inspect and
                    # tune the coherence-check acquisition condition here.
                    "detuning_range": sweep.linspace(-0.05, 0.05, 41),
                    "time_range": sweep.linspace(0, 250, 26),
                    "shots": 256,
                },
                "update_calibration_parameters": False,
            },
            "CheckT1": {
                "run": {
                    "time_range": sweep.logspace(math.log10(300), math.log10(500_000), 51),
                },
            },
            "CheckT2Echo": {
                "run": {
                    "time_range": sweep.logspace(math.log10(300), math.log10(500_000), 51),
                },
            },
            "CheckRamsey": {
                "run": {
                    "time_range": sweep.arange(0, 10_001, 100),
                    "detuning": 0.001,
                },
            },
        },
        default_run_parameters={
            "readout_duration": 1024,
            "interval": 256 * 1024,
        },
    )
    return cal.run(targets, steps=steps)
