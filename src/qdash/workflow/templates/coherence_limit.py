"""Gate coherence limit calculation template.

Calculates theoretical fidelity limit of 1Q and 2Q gates
from T1, T2 coherence times and gate duration.

Example:
    coherence_limit(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1, 2, 3],
    )

    coherence_limit(
        username="alice",
        chip_id="64Qv3",
        qids=["0", "1", "2", "3"],
    )
"""

from typing import Any

from qdash.calibration import (
    CalibrationTargets,
    CustomOneQubit,
    CustomTwoQubit,
    GenerateCRSchedule,
    MuxTargets,
    OneQubitExecutionMode,
    QubitTargets,
    TaskCall,
)
from qdash.workflow import CalibrationSession, calibration_flow, resolve_calib_context


@calibration_flow(session_name="Gate Coherence Limit")
def coherence_limit(
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
    """Gate coherence limit calculation flow.

    Calculates the theoretical fidelity limit from coherence times (T1, T2)
    and gate duration for both 1Q and 2Q gates.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to calibrate (uses MUX-based scheduling)
        exclude_qids: Qubit IDs to exclude (only with mux_ids)
        qids: Qubit IDs to calibrate (fallback if mux_ids not set)
        execution_mode: How the one-qubit targets run (default: "parallel_by_mux"):
            - "parallel_by_mux": MUXes run in parallel within the scheduler's hardware
              stages; the qubits of one MUX run one after another
            - "parallel_by_round": the scheduler forms rounds of qubits from different
              MUXes; the next round starts after every qubit of the round has run
              all of its tasks
            - "sequential": one MUX and one qubit at a time
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results
    """
    # =========================================================================
    # Configuration
    # =========================================================================

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
        # 1Q coherence limit
        CustomOneQubit(
            step_name="coherence_limit_1q",
            tasks=[TaskCall(name="Check1QGateCoherenceLimit", run={"drag_hpi_duration": 16})],
            execution_mode=execution_mode,
        ),
        # 2Q coherence limit
        GenerateCRSchedule(),
        CustomTwoQubit(
            step_name="coherence_limit_2q", tasks=[TaskCall(name="Check2QGateCoherenceLimit")]
        ),
    ]

    # =========================================================================
    # Execution
    # =========================================================================

    context = resolve_calib_context(username, chip_id, project_id=project_id)
    session = CalibrationSession.from_context(context)
    return session.run(
        targets=targets,
        steps=steps,
        name=flow_name,
        tags=tags,
    )
