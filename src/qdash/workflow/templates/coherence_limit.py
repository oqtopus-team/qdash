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

from prefect import flow
from qdash.workflow.service import CalibService
from qdash.workflow.service.steps import CustomOneQubit, CustomTwoQubit, GenerateCRSchedule
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target


@flow
def coherence_limit(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    mode: str = "scheduled",
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
        mode: Execution mode:
            - "scheduled": Box-based parallelism with hardware constraints (default)
            - "serial": Fully sequential execution
            - "synchronized": Step-based synchronized execution
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

    targets: Target
    if mux_ids is not None:
        targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids)
    elif qids is not None:
        targets = QubitTargets(qids=qids)
    else:
        targets = MuxTargets(mux_ids=list(range(4)), exclude_qids=exclude_qids)

    steps = [
        # 1Q coherence limit
        CustomOneQubit(
            step_name="coherence_limit_1q", tasks=["Check1QGateCoherenceLimit"], mode=mode
        ),
        # 2Q coherence limit
        GenerateCRSchedule(),
        CustomTwoQubit(step_name="coherence_limit_2q", tasks=["Check2QGateCoherenceLimit"]),
    ]

    # =========================================================================
    # Execution
    # =========================================================================

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        skip_execution=True,
        default_run_parameters={
            "drag_hpi_duration": {"value": 16, "value_type": "int"},
        },
    )
    return cal.run(targets, steps=steps)
