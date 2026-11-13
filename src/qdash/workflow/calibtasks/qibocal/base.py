"""Base class of tasks that run on the qibocal backend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from qdash.workflow.calibtasks.base import BaseTask, RunResult

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qibocal import QibocalBackend

EMULATOR_MEASUREMENT_ONLY_REASON = (
    "Synthetic result from the Qibolab emulator; emulator outputs never update "
    "accepted calibration state"
)


class QibocalTask(BaseTask):
    """Task that runs a Qibocal protocol through the isolated runner.

    Every qibocal task is measurement-only: ``measurement_only_reason`` makes the
    orchestrator and ``BackendSaver`` ignore every write-back setting.
    """

    backend: str = "qibocal"
    measurement_only_reason: ClassVar[str] = EMULATOR_MEASUREMENT_ONLY_REASON
    # The runner enforces its own timeout from config/app/qibocal.yaml.
    timeout: int = 60 * 30

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        super().__init__(params)
        # Set in postprocess and stored with every output in task-result history.
        self.output_provenance: dict[str, Any] = {}

    def batch_run(self, backend: QibocalBackend, qids: list[str]) -> RunResult:
        raise NotImplementedError(f"{self.name} runs one qubit at a time")
