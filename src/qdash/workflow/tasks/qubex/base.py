from typing import TYPE_CHECKING

from qdash.datamodel.task import InputParameterModel
from qdash.workflow.tasks.base import (
    BaseTask,
    PreProcessResult,
    RunResult,
)

if TYPE_CHECKING:
    from qdash.workflow.core.session.qubex import QubexSession


class QubexTask(BaseTask):
    """Base class for Qubex-based tasks.

    This class provides common functionality for all tasks that use the Qubex backend.
    It eliminates code duplication by providing shared helper methods and default implementations.
    """

    backend: str = "qubex"
    # name is empty to prevent registration in BaseTask.registry
    # Only concrete subclasses with a name should be registered

    def preprocess(self, session: "QubexSession", qid: str) -> PreProcessResult:
        exp = self.get_experiment(session)
        label = self.get_qubit_label(session, qid)
        self.input_parameters["readout_amplitude"] = InputParameterModel(
            unit="a.u.",
            description="Readout Amplitude",
            value=exp.experiment_system.control_params.get_readout_amplitude(label),
            value_type="float",
        )
        self.input_parameters["readout_frequency"] = InputParameterModel(
            unit="GHz",
            description="Readout Frequency",
            value=exp.experiment_system.quantum_system.get_resonator(exp.get_resonator_label(int(qid))).frequency,
            value_type="float",
        )
        self.input_parameters["control_amplitude"] = InputParameterModel(
            unit="a.u.",
            description="Qubit Control Amplitude",
            value=exp.experiment_system.control_params.get_control_amplitude(label),
            value_type="float",
        )
        self.input_parameters["qubit_frequency"] = InputParameterModel(
            unit="GHz",
            description="Qubit Frequency",
            value=exp.experiment_system.quantum_system.get_qubit(label).frequency,
            value_type="float",
        )
        return PreProcessResult(input_parameters=self.input_parameters)

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
