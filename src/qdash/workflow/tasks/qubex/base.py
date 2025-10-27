from contextlib import contextmanager
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
        
        # Add default parameters only if they don't exist yet
        # This preserves any overrides provided via task_details
        if "readout_amplitude" not in self.input_parameters:
            self.input_parameters["readout_amplitude"] = InputParameterModel(
                unit="a.u.",
                description="Readout Amplitude",
                value=exp.experiment_system.control_params.get_readout_amplitude(label),
                value_type="float",
            )
        if "readout_frequency" not in self.input_parameters:
            self.input_parameters["readout_frequency"] = InputParameterModel(
                unit="GHz",
                description="Readout Frequency",
                value=exp.experiment_system.quantum_system.get_resonator(exp.get_resonator_label(int(qid))).frequency,
                value_type="float",
            )
        if "control_amplitude" not in self.input_parameters:
            self.input_parameters["control_amplitude"] = InputParameterModel(
                unit="a.u.",
                description="Qubit Control Amplitude",
                value=exp.experiment_system.control_params.get_control_amplitude(label),
                value_type="float",
            )
        if "qubit_frequency" not in self.input_parameters:
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

    def _is_frequency_overridden(self, session: "QubexSession", qid: str) -> bool:
        """Check if qubit_frequency was explicitly overridden from default.

        This method compares the current qubit_frequency in input_parameters
        with the default frequency from the quantum system. If they differ,
        it indicates that the user explicitly provided a custom frequency.

        Args:
        ----
            session: Qubex session object
            qid: Qubit ID

        Returns:
        -------
            True if frequency was explicitly provided (differs from default)

        """
        exp = self.get_experiment(session)
        label = self.get_qubit_label(session, qid)

        # Get current frequency from input_parameters
        current_freq = self.input_parameters["qubit_frequency"].get_value()

        # Get default frequency from quantum system
        default_freq = exp.experiment_system.quantum_system.get_qubit(label).frequency

        # Check if they differ (with small tolerance for floating point comparison)
        return abs(current_freq - default_freq) > 1e-9

    @contextmanager
    def _apply_frequency_override(self, session: "QubexSession", qid: str):
        """Context manager to apply frequency override if needed.

        This method checks if the qubit_frequency was explicitly overridden
        via task_details. If so, it uses exp.modified_frequencies() to
        temporarily modify the qubit frequency during task execution.

        Args:
        ----
            session: Qubex session object
            qid: Qubit ID

        Yields:
        ------
            Context with modified frequencies (or no-op if not overridden)

        Example:
        -------
            ```python
            with self._apply_frequency_override(session, qid):
                result = exp.obtain_rabi_params(...)
            ```

        """
        exp = self.get_experiment(session)
        label = self.get_qubit_label(session, qid)

        if self._is_frequency_overridden(session, qid):
            override_freq = self.input_parameters["qubit_frequency"].get_value()
            with exp.modified_frequencies({label: override_freq}):
                yield
        else:
            # No override: just execute normally
            yield
