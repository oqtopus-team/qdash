"""Coarse 1-qubit calibration through Ramsey, based on the one_qubit check stage.

Run this after bring-up has established the qubit frequency, control amplitude,
and readout settings. The flow applies the current hardware configuration,
refines readout settings, runs Rabi and calibrates/checks HPI, PI, DRAG HPI, and
DRAG PI, then measures T1/T2Echo and Ramsey
for explicitly selected MUXes or qubits.

Example:
    coarse_one(username="alice", chip_id="64Qv3", mux_ids=[0, 1])
"""

from typing import Any

from qdash.calibration import CalibrationTargets, MuxTargets, OneQubitCheck, QubitTargets, TaskCall
from qdash.workflow import CalibrationSession, calibration_flow, resolve_calib_context


@calibration_flow(session_name="Coarse 1Q Calibration")
def coarse_one(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Run the coarse 1-qubit check stage through Ramsey.

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
        Pipeline results with one_qubit_check output
    """
    targets: CalibrationTargets
    if mux_ids is not None:
        targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids or [])
    elif qids is not None:
        targets = QubitTargets(qids=qids)
    else:
        raise ValueError("mux_ids or qids is required; select targets before running this flow")

    steps = [
        OneQubitCheck(
            execution_mode="parallel_by_round",
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
                TaskCall(name="CreateHPIPulse", run={"hpi_duration": 32}),
                TaskCall(name="CheckHPIPulse"),
                TaskCall(name="CreatePIPulse", run={"pi_duration": 32}),
                TaskCall(name="CheckPIPulse"),
                TaskCall(name="CreateDRAGHPIPulse", run={"drag_hpi_duration": 16}),
                TaskCall(name="CheckDRAGHPIPulse"),
                TaskCall(name="CreateDRAGPIPulse", run={"drag_pi_duration": 24}),
                TaskCall(name="CheckDRAGPIPulse"),
                TaskCall(name="CheckT1"),
                TaskCall(name="CheckT2Echo"),
                TaskCall(name="CheckRamsey"),
            ],
        )
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
        name=flow_name,
        tags=tags,
    )
