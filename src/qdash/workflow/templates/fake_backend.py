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
(``mode="scheduled"``): MUX groups that share no box run in parallel, and the qubits of a MUX
run one after another. By default the flow calibrates MUX 0 to 15, every qubit of the
64-qubit, 16-MUX virtual device that the Create Chip dialog configures on a fake deployment.

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
        tasks=["CheckHPIPulse", "CheckPIPulse"],
    )
"""

from typing import Any

from prefect import flow, get_run_logger

from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import MuxTargets

# Tasks the template runs when none are given; every name is listed for the fake backend in
# config/app/backend.yaml and resolves its inputs from the tasks before it.
FAKE_CALIBRATION_TASKS: list[str] = [
    "FakeBringUp",
    "CheckChevron",
    "CheckRabi",
    "CreateHPIPulse",
    "CreatePIPulse",
    "CheckT1",
    "CheckT2Echo",
    "CheckRamsey",
]

# MUXes the template calibrates when no mux_ids are given: MUX 0 to 15 is the whole fake device.
# Edit this list to calibrate a subset, for example [9, 15].
MUX_IDS: list[int] = list(range(16))


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
    mode: str = "scheduled",
    tasks: list[str] | None = None,
    backend_name: str | None = None,
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Calibration flow on the fake backend, scheduled like a hardware run.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (default: "64Q")
        mux_ids: MUX IDs to calibrate (default: MUX_IDS, MUX 0 to 15)
        exclude_qids: Qubit IDs to leave out of the selected MUXes
        qids: Not used; accepted so callers that pass qubit IDs keep working. The MUX
            selection decides the qubits, so passing qids never changes the run.
        mode: Execution mode, as in the hardware templates:
            - "scheduled": Box-based parallelism with hardware constraints (default)
            - "synchronized": Step-based synchronized execution
            - "serial": One MUX at a time
        tasks: Task names to run. Default: FAKE_CALIBRATION_TASKS.
        backend_name: Backend to use ("fake" for testing, "qubex" for production,
                      None for default from config/app/backend.yaml)
        tags: Flow tags
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results
    """
    if mux_ids is None:
        mux_ids = list(MUX_IDS)
    if exclude_qids is None:
        exclude_qids = []
    if tasks is None:
        tasks = list(FAKE_CALIBRATION_TASKS)
    if qids is not None:
        get_run_logger().warning(
            "fake_calibration ignores qids=%s; the run targets mux_ids=%s. "
            "Use mux_ids and exclude_qids to choose qubits.",
            qids,
            mux_ids,
        )

    targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids)
    steps = [
        CustomOneQubit(step_name="calibration", tasks=tasks, mode=mode),
    ]

    cal = CalibService(
        username,
        chip_id,
        backend_name=backend_name,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
    )
    return cal.run(targets, steps=steps)
