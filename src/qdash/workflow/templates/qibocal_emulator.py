"""Qibocal emulator flow template.

Runs Qibocal's ``rabi_amplitude`` protocol on the upstream Qibolab ``qubit`` emulator
platform through the qibocal backend. Acquisition, fit, and figure are Qibocal's own; QDash
stores the history, figure, raw data, and provenance. Results are synthetic and
adopted only into the matching simulation chip's QDash calibration database.

The emulator platform has exactly one qubit, ``0``, and the Create Chip dialog of a qibocal
deployment creates a one-qubit chip for it. Any other qubit ID fails before acquisition; the
template never maps a QDash qubit onto another emulator qubit.

Example:
    qibocal_rabi_amplitude(username="alice", chip_id="QIBOCAL", backend_name="qibocal")

    # A finer sweep with more shots
    qibocal_rabi_amplitude(
        username="alice",
        chip_id="QIBOCAL",
        backend_name="qibocal",
        tasks=[
            TaskCall(
                name="QibocalRabiAmplitude",
                run={"step_amp": 0.005, "nshots": 4096},
            )
        ],
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
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import QubitTargets

# Tasks the template runs when none are given; each is listed for the qibocal backend in
# config/app/backend.yaml.
QIBOCAL_TASKS: list[TaskCall] = [
    TaskCall(name=name) for name in ("QibocalBringUp", "QibocalRabiAmplitude", "QibocalFlipping")
]

# The only qubit of the upstream Qibolab `qubit` emulator platform. Keep it a literal list so
# the execution dialog can show the default targets.
QIDS: list[str] = ["0"]


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def qibocal_rabi_amplitude(
    username: str,
    chip_id: str,
    qids: list[str] | None = None,
    tasks: list[TaskCall] | None = None,
    backend_name: str | None = "qibocal",
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Run Qibocal protocols on the one-qubit Qibolab emulator.

    Args:
        username: User name (from UI)
        chip_id: Chip ID of a chip created from the qibocal preset
        qids: Qubit IDs; default QIDS, the emulator's only qubit
        tasks: Task calls to run, e.g. [TaskCall(name="QibocalRabiAmplitude")]; flow runs
            pass [{"name": "QibocalRabiAmplitude"}]. Default: QIBOCAL_TASKS.
        backend_name: Backend to use; "qibocal"
        tags: Flow tags
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results
    """
    targets = QubitTargets(qids=list(QIDS if qids is None else qids))
    steps = [
        CustomOneQubit(
            step_name="qibocal",
            tasks=list(QIBOCAL_TASKS if tasks is None else tasks),
            mode="serial",
        ),
    ]
    context = resolve_calib_context(username, chip_id, project_id=project_id, backend=backend_name)
    cal = CalibService.from_context(context, flow_name=flow_name, tags=tags)
    return cal.run(targets, steps=steps)
