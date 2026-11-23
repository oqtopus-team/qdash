"""Readout waveform check flow template.

This template runs qubex CheckWaveform for selected MUXes or qubits.

Example:
    check_waveform(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1],
    )
"""

from typing import Any

from prefect import flow

from qdash.datamodel.one_qubit_execution_mode import OneQubitExecutionMode
from qdash.workflow import TaskCall
from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def check_waveform(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    execution_mode: OneQubitExecutionMode = "parallel_by_mux",
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Run readout waveform checks for selected targets.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to inspect (uses MUX-based scheduling)
        exclude_qids: Qubit IDs to exclude (only with mux_ids)
        qids: Qubit IDs to inspect (fallback if mux_ids not set)
        execution_mode: How the one-qubit targets run (default: "parallel_by_mux"):
            - "parallel_by_mux": MUXes run in parallel within the scheduler's hardware
              stages; the qubits of one MUX run one after another
            - "parallel_by_round": the scheduler forms rounds of qubits from different
              MUXes; the next round starts after every qubit of the round has run
              all of its tasks
            - "sequential": one MUX and one qubit at a time
        tags: Flow tags
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results
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

    steps = [
        CustomOneQubit(
            step_name="check_waveform",
            tasks=[TaskCall(name="CheckWaveform")],
            execution_mode=execution_mode,
        ),
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
