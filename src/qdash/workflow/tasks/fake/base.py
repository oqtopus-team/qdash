from typing import TYPE_CHECKING

from qdash.workflow.core.calibration.util import qid_to_label
from qdash.workflow.tasks.base import BaseTask, RunResult

if TYPE_CHECKING:
    from qdash.workflow.core.session.fake import FakeSession


class FakeTask(BaseTask):
    """Base class for Fake simulation-based tasks.

    This class provides common functionality for all tasks that use the Fake backend
    (quantum simulation). It eliminates code duplication by providing shared helper
    methods and default implementations.
    """

    backend: str = "fake"
    # name is empty to prevent registration in BaseTask.registry
    # Only concrete subclasses with a name should be registered

    def batch_run(self, session: "FakeSession", qids: list[str]) -> RunResult:
        """Default implementation for batch run.

        Most Fake tasks do not support batch execution and should use the run method instead.
        Override this method in subclasses that support batch processing.

        Args:
        ----
            session: Fake session object
            qids: list of qubit IDs

        Raises:
        ------
            NotImplementedError: Always raised for tasks that don't support batch execution

        """
        raise NotImplementedError(f"Batch run is not implemented for {self.name} task. Use run method instead.")

    def get_label(self, qid: str) -> str:
        """Convert qubit ID to label.

        Args:
        ----
            qid: Qubit ID (as string)

        Returns:
        -------
            The qubit label string (e.g., "Q00", "Q01", etc.)

        """
        return qid_to_label(qid)
