"""Fake backend calibration flow template.

Runs a short calibration on the fake backend, a QUBEX-compatible simulator, so workflows,
persistence and result handling can be exercised without hardware. Apart from the first task
the chain is the production qubex task code: the fake backend routes the task names below to
the qubex implementations.

Default task order:
    - FakeBringUp: seeds the simulator's qubit and readout parameters (fake only)
    - CheckChevron: measures the chevron pattern around the seeded qubit frequency
    - CheckRabi: Rabi oscillation, outputs the rabi parameters and control amplitude
    - CreateHPIPulse / CreatePIPulse: pulse calibration
    - CheckT1 / CheckT2Echo / CheckRamsey: coherence checks

Targets are MUXes, as on hardware. The flow resolves each MUX to its qubits from the chip's
wiring and schedules them with the same box-aware scheduler the hardware templates use
(``execution_mode="parallel_by_mux"``): MUX groups that share no box run in parallel, and the qubits of a MUX
run one after another. Target arguments follow the hardware templates: ``mux_ids`` selects
MUXes, otherwise ``qids`` selects qubits. With neither, the flow calibrates ``MUX_IDS``, MUX 0
to 15, every qubit of the 64-qubit, 16-MUX virtual device that the Create Chip dialog
configures on a fake deployment.

Example:
    fake_calibration(username="alice", chip_id="64Q", backend_name="fake")

    # Calibrate MUX 9 and 15 (qubits 36-39 and 60-63), skipping qubit 37
    fake_calibration(
        username="alice",
        chip_id="64Q",
        mux_ids=[9, 15],
        exclude_qids=["37"],
        backend_name="fake",
    )

    # Run only the pulse checks after an earlier bring-up
    fake_calibration(
        username="alice",
        chip_id="64Q",
        mux_ids=[0],
        backend_name="fake",
        tasks=[TaskCall(name="CheckHPIPulse"), TaskCall(name="CheckPIPulse")],
    )
"""

from typing import Any

from prefect import flow

from qdash.workflow import TaskCall
from qdash.workflow.service import CalibService, resolve_calib_context
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import CustomOneQubit, resolve_execution_mode
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target

# Tasks the template runs when none are given; every name is listed for the fake backend in
# config/app/backend.yaml and resolves its inputs from the tasks before it.
FAKE_CALIBRATION_TASKS: list[TaskCall] = [
    TaskCall(name="FakeBringUp"),
    TaskCall(name="CheckChevron"),
    TaskCall(name="CheckRabi"),
    TaskCall(name="CreateHPIPulse"),
    TaskCall(name="CreatePIPulse"),
    TaskCall(name="CheckT1"),
    TaskCall(name="CheckT2Echo"),
    TaskCall(name="CheckRamsey"),
]

# MUXes the template calibrates when neither mux_ids nor qids is given: MUX 0 to 15 is the
# whole fake device. Edit this list to calibrate a subset, for example [9, 15]. Keep it a
# literal list so the execution dialog can show these default targets.
MUX_IDS: list[int] = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def fake_calibration(
    username: str,
    chip_id: str = "64Q",
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    execution_mode: str | None = None,
    tasks: list[TaskCall] | None = None,
    backend_name: str | None = None,
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
    mode: str | None = None,
) -> Any:
    """Calibration flow on the fake backend, scheduled like a hardware run.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (default: "64Q")
        mux_ids: MUX IDs to calibrate with MUX-based scheduling. Default: MUX_IDS (MUX 0 to
            15) when qids is not given either.
        exclude_qids: Qubit IDs to leave out of the selected MUXes
        qids: Qubit IDs to calibrate when mux_ids is not set
        execution_mode: How the one-qubit targets run (default: "parallel_by_mux"):
            - "parallel_by_mux": MUXes run in parallel within the scheduler's hardware
              stages; the qubits of one MUX run one after another
            - "parallel_by_round": the scheduler forms rounds of qubits from different
              MUXes; the next round starts after every qubit of the round has run
              all of its tasks
            - "sequential": one MUX and one qubit at a time
        tasks: Task calls to run, e.g. [TaskCall(name="CheckRabi")]; flow runs pass
            [{"name": "CheckRabi"}]. Default: FAKE_CALIBRATION_TASKS.
        backend_name: Backend to use ("fake" for testing, "qubex" for production,
                      None for default from config/app/backend.yaml)
        tags: Flow tags
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)
        mode: Deprecated alias of execution_mode. The old names "scheduled",
            "synchronized" and "serial" are still accepted with a deprecation warning.

    Returns:
        Pipeline results
    """
    if exclude_qids is None:
        exclude_qids = []
    if tasks is None:
        tasks = list(FAKE_CALIBRATION_TASKS)

    targets: Target
    if mux_ids is not None:
        targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids)
    elif qids is not None:
        targets = QubitTargets(qids=qids)
    else:
        targets = MuxTargets(mux_ids=MUX_IDS, exclude_qids=exclude_qids)
    steps = [
        CustomOneQubit(
            step_name="calibration",
            tasks=tasks,
            execution_mode=resolve_execution_mode(execution_mode, mode, default="parallel_by_mux"),
        ),
    ]

    # The backend is part of the execution context; the default comes from
    # config/app/backend.yaml.
    context = resolve_calib_context(username, chip_id, project_id=project_id, backend=backend_name)
    cal = CalibService.from_context(context, flow_name=flow_name, tags=tags)
    return cal.run(targets, steps=steps)
