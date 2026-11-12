from typing import TYPE_CHECKING

from qdash.workflow.calibtasks.base import BaseTask, RunResult

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qm import QMBackend


class QMTask(BaseTask):
    """Base class for tasks that run on the Quantum Machines (``qm``) backend."""

    backend: str = "qm"
    # name is empty to prevent registration in BaseTask.registry

    def batch_run(self, backend: "QMBackend", qids: list[str]) -> RunResult:
        """QM tasks run one qubit at a time."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
