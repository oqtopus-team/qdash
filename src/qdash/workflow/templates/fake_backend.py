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

Example:
    fake_calibration(username="alice", chip_id="64Q", qids=["0", "1"], backend_name="fake")

    # Run only the pulse checks after an earlier bring-up
    fake_calibration(
        username="alice",
        chip_id="64Q",
        qids=["0"],
        backend_name="fake",
        tasks=["CheckHPIPulse", "CheckPIPulse"],
    )
"""

from typing import Any

from prefect import flow

from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import QubitTargets

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


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def fake_calibration(
    username: str,
    chip_id: str = "64Q",
    qids: list[str] | None = None,
    tasks: list[str] | None = None,
    backend_name: str | None = None,
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Calibration flow with backend switching support.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (default: "64Q")
        qids: Qubit IDs to calibrate (default: ["0", "1", "2", "3"])
        tasks: Task names to run. Default: FAKE_CALIBRATION_TASKS.
        backend_name: Backend to use ("fake" for testing, "qubex" for production,
                      None for default from config/app/backend.yaml)
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results
    """
    if qids is None:
        qids = ["0", "1", "2", "3"]

    if tasks is None:
        tasks = list(FAKE_CALIBRATION_TASKS)

    targets = QubitTargets(qids=qids)
    steps = [
        CustomOneQubit(step_name="calibration", tasks=tasks),
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
