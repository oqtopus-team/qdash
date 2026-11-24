"""Qubit coherence check template.

This template applies the current hardware configuration, records a coarse
Chevron measurement without updating calibration parameters, and runs Rabi,
T1, T2Echo, and Ramsey for explicitly selected MUXes or qubits. The same step
then applies the configuration again, re-measures Rabi, and runs Ramsey on a
five times longer time scale with a smaller detuning.

Example:
    coherence_check(username="alice", chip_id="64Qv3", mux_ids=[0, 1])
"""

import math
from typing import Any

from qdash.calibration import (
    CalibrationTargets,
    CustomOneQubit,
    MuxTargets,
    QubitTargets,
    TaskCall,
    sweep,
)
from qdash.workflow import CalibrationSession, calibration_flow, resolve_calib_context


@calibration_flow(session_name="Coherence Check")
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
    targets: CalibrationTargets
    if mux_ids is not None:
        targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids or [])
    elif qids is not None:
        targets = QubitTargets(qids=qids)
    else:
        raise ValueError("mux_ids or qids is required; select targets before running this flow")

    steps = [
        CustomOneQubit(
            step_name="coherence_check",
            tasks=[
                TaskCall(name="Configure", call_id="configure_initial"),
                TaskCall(
                    name="CheckChevron",
                    run={
                        # Keep the measurement grid explicit so users can inspect and
                        # tune the coherence-check acquisition condition here.
                        "detuning_range": sweep.linspace(-0.05, 0.05, 41),
                        "time_range": sweep.linspace(0, 250, 26),
                        "shots": 256,
                    },
                    update_calibration_parameters=False,
                ),
                TaskCall(name="CheckRabi", call_id="rabi_initial"),
                TaskCall(
                    name="CheckT1",
                    run={"time_range": sweep.logspace(math.log10(300), math.log10(500_000), 51)},
                ),
                TaskCall(
                    name="CheckT2Echo",
                    run={"time_range": sweep.logspace(math.log10(300), math.log10(500_000), 51)},
                ),
                TaskCall(
                    name="CheckRamsey",
                    call_id="ramsey_short",
                    run={
                        "time_range": sweep.arange(0, 10_001, 100),
                        "detuning": 0.001,
                    },
                ),
                # Configure and CheckRabi run again on fresh hardware state before the
                # long Ramsey. A target that fails an earlier call stops here; other
                # targets continue without waiting for every target's short pass.
                TaskCall(name="Configure", call_id="configure_long_ramsey"),
                TaskCall(name="CheckRabi", call_id="rabi_long_ramsey"),
                TaskCall(
                    name="CheckRamsey",
                    call_id="ramsey_long",
                    run={
                        # Keep 101 points while extending the time scale by 5x.
                        "time_range": sweep.arange(0, 50_001, 500),
                        "detuning": 0.0002,
                    },
                ),
            ],
            execution_mode="parallel_by_round",
        ),
    ]

    context = resolve_calib_context(username, chip_id, project_id=project_id)
    session = CalibrationSession.from_context(context)
    return session.run(
        targets=targets,
        steps=steps,
        default_run_parameters={
            "readout_duration": 1024,
            "interval": 256 * 1024,
        },
        name=flow_name,
        tags=tags,
    )
