"""Fine 1-qubit calibration based on the one_qubit fine-tuning stage.

Run this after coarse_one or an equivalent calibration has established the
qubit frequency, control amplitude, and readout settings. The flow applies
those settings, calibrates HPI/PI and DRAG pulses, classifies readout, and
measures coherence and randomized benchmarking for selected MUXes or qubits.

Example:
    fine_one(username="alice", chip_id="64Qv3", mux_ids=[0, 1])
"""

from typing import Any

from prefect import flow

from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import OneQubitFineTune
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target

FINE_ONE_TASKS: list[str] = [
    "Configure",  # Apply the current calibrated settings before fine-tuning.
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
    "CheckT1Average",
    "CheckT2EchoAverage",
    "Check1QGateCoherenceLimit",
    "RandomizedBenchmarking",
    "X90InterleavedRandomizedBenchmarking",
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
            "hpi_duration": {"value": 32, "value_type": "int"},
            "pi_duration": {"value": 32, "value_type": "int"},
            "drag_hpi_duration": {"value": 16, "value_type": "int"},
            "drag_pi_duration": {"value": 24, "value_type": "int"},
            "interval": {"value": 150 * 1024, "value_type": "int"},
        },
    )
    return cal.run(targets, steps=steps)
