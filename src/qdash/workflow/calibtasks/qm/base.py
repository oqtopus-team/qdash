from typing import TYPE_CHECKING

from qdash.workflow.calibtasks.base import BaseTask, RunResult

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qm import QMBackend
    from qdash.workflow.engine.backend.qm_fake import QMFakeBackend


class QMTask(BaseTask):
    """Base class for tasks of the Quantum Machines (``qm``) backend.

    Subclasses register under ``qm``. The ``qm-fake`` backend runs the same classes,
    routed in ``calibtasks/qm/__init__.py``, so ``backend`` stays ``qm`` for both:
    it names the task family, while ``BaseBackend.name`` names the backend a run used.
    """

    backend: str = "qm"
    # name is empty to prevent registration in BaseTask.registry

    def batch_run(self, backend: "QMBackend | QMFakeBackend", qids: list[str]) -> RunResult:
        """QM tasks run one qubit at a time."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
