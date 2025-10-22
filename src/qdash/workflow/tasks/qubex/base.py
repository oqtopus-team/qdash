from typing import TYPE_CHECKING

from qdash.workflow.tasks.base import BaseTask, RunResult

if TYPE_CHECKING:
    from qdash.workflow.core.session.qubex import QubexSession


class QubexTask(BaseTask):
    """Base class for Qubex-based tasks.

    This class provides common functionality for all tasks that use the Qubex backend.
    It eliminates code duplication by providing shared helper methods and default implementations.
    """

    backend: str = "qubex"

    def batch_run(self, session: "QubexSession", qids: list[str]) -> RunResult:
        """Default implementation for batch run.

        Most Qubex tasks do not support batch execution and should use the run method instead.
        Override this method in subclasses that support batch processing.

        Args:
        ----
            session: Qubex session object
            qids: list of qubit IDs

        Raises:
        ------
            NotImplementedError: Always raised for tasks that don't support batch execution

        """
        raise NotImplementedError(f"Batch run is not implemented for {self.name} task. Use run method instead.")

    def get_experiment(self, session: "QubexSession"):
        """Get the experiment session from QubexSession.

        Args:
        ----
            session: Qubex session object

        Returns:
        -------
            The underlying experiment session

        """
        return session.get_session()

    def get_qubit_label(self, session: "QubexSession", qid: str) -> str:
        """Get the qubit label for a given qubit ID.

        Args:
        ----
            session: Qubex session object
            qid: Qubit ID (as string)

        Returns:
        -------
            The qubit label string

        """
        exp = self.get_experiment(session)
        return exp.get_qubit_label(int(qid))

    def get_resonator_label(self, session: "QubexSession", qid: str) -> str:
        """Get the resonator label for a given qubit ID.

        Args:
        ----
            session: Qubex session object
            qid: Qubit ID (as string)

        Returns:
        -------
            The resonator label string

        """
        exp = self.get_experiment(session)
        return exp.get_resonator_label(int(qid))

    def save_calibration(self, session: "QubexSession") -> None:
        """Save calibration notes after task execution.

        Args:
        ----
            session: Qubex session object

        """
        exp = self.get_experiment(session)
        exp.calib_note.save()
