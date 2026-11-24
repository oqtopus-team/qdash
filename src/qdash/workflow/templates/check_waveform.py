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

from qdash.calibration import (
    CalibrationTargets,
    CustomOneQubit,
    MuxTargets,
    OneQubitExecutionMode,
    QubitTargets,
    TaskCall,
)
from qdash.workflow import CalibrationSession, calibration_flow, resolve_calib_context


@calibration_flow(session_name="Check Waveform")
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
        flow_name: Saved flow name QDash injects at launch; keep it in the signature
            and do not pass it on (session.run reads the launch name itself)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results
    """
    if exclude_qids is None:
        exclude_qids = []

    targets: CalibrationTargets
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

    context = resolve_calib_context(username, chip_id, project_id=project_id)
    session = CalibrationSession.from_context(context)
    return session.run(
        targets=targets,
        steps=steps,
        default_run_parameters={
            "readout_duration": 1024,
            "interval": 150 * 1024,
        },
        tags=tags,
    )
