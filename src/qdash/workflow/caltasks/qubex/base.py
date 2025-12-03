from contextlib import contextmanager
from typing import TYPE_CHECKING

from qdash.datamodel.task import InputParameterModel
from qdash.workflow.caltasks.base import (
    BaseTask,
    PreProcessResult,
    RunResult,
)

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend


class QubexTask(BaseTask):
    """Base class for Qubex-based tasks.

    This class provides common functionality for all tasks that use the Qubex backend.
    It eliminates code duplication by providing shared helper methods and default implementations.
    """

    backend: str = "qubex"
    # name is empty to prevent registration in BaseTask.registry
    # Only concrete subclasses with a name should be registered

    def preprocess(self, backend: "QubexBackend", qid: str) -> PreProcessResult:
        # System tasks don't need parameter preprocessing
        # They use qid="" and don't access qubit-specific parameters
        if self.task_type == "system" or qid == "":
            return PreProcessResult(input_parameters=self.input_parameters)

        exp = self.get_experiment(backend)

        # Check if this is a coupling task (qid format: "0-1")
        if "-" in qid:
            # Coupling task: add parameters for both qubits
            control_qid, target_qid = qid.split("-")
            control_label = exp.get_qubit_label(int(control_qid))
            target_label = exp.get_qubit_label(int(target_qid))

            # Add control qubit parameters
            if "control_readout_amplitude" not in self.input_parameters:
                self.input_parameters["control_readout_amplitude"] = InputParameterModel(
                    unit="a.u.",
                    description="Control Qubit Readout Amplitude",
                    value=exp.experiment_system.control_params.get_readout_amplitude(control_label),
                    value_type="float",
                )
            if "control_readout_frequency" not in self.input_parameters:
                self.input_parameters["control_readout_frequency"] = InputParameterModel(
                    unit="GHz",
                    description="Control Qubit Readout Frequency",
                    value=exp.experiment_system.quantum_system.get_resonator(
                        exp.get_resonator_label(int(control_qid))
                    ).frequency,
                    value_type="float",
                )
            if "control_control_amplitude" not in self.input_parameters:
                self.input_parameters["control_control_amplitude"] = InputParameterModel(
                    unit="a.u.",
                    description="Control Qubit Control Amplitude",
                    value=exp.experiment_system.control_params.get_control_amplitude(control_label),
                    value_type="float",
                )
            if "control_qubit_frequency" not in self.input_parameters:
                self.input_parameters["control_qubit_frequency"] = InputParameterModel(
                    unit="GHz",
                    description="Control Qubit Frequency",
                    value=exp.experiment_system.quantum_system.get_qubit(control_label).frequency,
                    value_type="float",
                )

            # Add target qubit parameters
            if "target_readout_amplitude" not in self.input_parameters:
                self.input_parameters["target_readout_amplitude"] = InputParameterModel(
                    unit="a.u.",
                    description="Target Qubit Readout Amplitude",
                    value=exp.experiment_system.control_params.get_readout_amplitude(target_label),
                    value_type="float",
                )
            if "target_readout_frequency" not in self.input_parameters:
                self.input_parameters["target_readout_frequency"] = InputParameterModel(
                    unit="GHz",
                    description="Target Qubit Readout Frequency",
                    value=exp.experiment_system.quantum_system.get_resonator(
                        exp.get_resonator_label(int(target_qid))
                    ).frequency,
                    value_type="float",
                )
            if "target_control_amplitude" not in self.input_parameters:
                self.input_parameters["target_control_amplitude"] = InputParameterModel(
                    unit="a.u.",
                    description="Target Qubit Control Amplitude",
                    value=exp.experiment_system.control_params.get_control_amplitude(target_label),
                    value_type="float",
                )
            if "target_qubit_frequency" not in self.input_parameters:
                self.input_parameters["target_qubit_frequency"] = InputParameterModel(
                    unit="GHz",
                    description="Target Qubit Frequency",
                    value=exp.experiment_system.quantum_system.get_qubit(target_label).frequency,
                    value_type="float",
                )
        else:
            # Single qubit task
            label = self.get_qubit_label(backend, qid)

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
                    value=exp.experiment_system.quantum_system.get_resonator(
                        exp.get_resonator_label(int(qid))
                    ).frequency,
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

    def batch_run(self, backend: "QubexBackend", qids: list[str]) -> RunResult:
        """Default implementation for batch run.

        Most Qubex tasks do not support batch execution and should use the run method instead.
        Override this method in subclasses that support batch processing.

        Args:
        ----
            backend: Qubex backend object
            qids: list of qubit IDs

        Raises:
        ------
            NotImplementedError: Always raised for tasks that don't support batch execution

        """
        raise NotImplementedError(f"Batch run is not implemented for {self.name} task. Use run method instead.")

    def get_experiment(self, backend: "QubexBackend"):
        """Get the experiment session from QubexBackend.

        Args:
        ----
            backend: Qubex backend object

        Returns:
        -------
            The underlying experiment session

        """
        return backend.get_session()

    def get_qubit_label(self, backend: "QubexBackend", qid: str) -> str:
        """Get the qubit label for a given qubit ID.

        Args:
        ----
            backend: Qubex backend object
            qid: Qubit ID (as string)

        Returns:
        -------
            The qubit label string

        """
        exp = self.get_experiment(backend)
        return exp.get_qubit_label(int(qid))

    def get_resonator_label(self, backend: "QubexBackend", qid: str) -> str:
        """Get the resonator label for a given qubit ID.

        Args:
        ----
            backend: Qubex backend object
            qid: Qubit ID (as string)

        Returns:
        -------
            The resonator label string

        """
        exp = self.get_experiment(backend)
        return exp.get_resonator_label(int(qid))

    def save_calibration(self, backend: "QubexBackend") -> None:
        """Save calibration notes after task execution.

        Args:
        ----
            backend: Qubex backend object

        """
        exp = self.get_experiment(backend)
        exp.calib_note.save()

    def _is_frequency_overridden(self, backend: "QubexBackend", qid: str) -> bool:
        """Check if qubit_frequency was explicitly overridden from default.

        This method compares the current qubit_frequency in input_parameters
        with the default frequency from the quantum system. If they differ,
        it indicates that the user explicitly provided a custom frequency.

        Args:
        ----
            backend: Qubex backend object
            qid: Qubit ID

        Returns:
        -------
            True if frequency was explicitly provided (differs from default)

        """
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)

        # Get current frequency from input_parameters
        current_freq = self.input_parameters["qubit_frequency"].get_value()

        # Get default frequency from quantum system
        default_freq = exp.experiment_system.quantum_system.get_qubit(label).frequency

        # Check if they differ (with small tolerance for floating point comparison)
        return abs(current_freq - default_freq) > 1e-9

    @contextmanager
    def _apply_parameter_overrides(self, backend: "QubexBackend", qid: str):
        """Context manager to apply multiple parameter overrides.

        This unified method handles all parameter types that can be overridden:
        - qubit_frequency: Uses exp.modified_frequencies() context manager
        - readout_amplitude: Direct modification with restoration
        - control_amplitude: Direct modification with restoration
        - readout_frequency: Direct modification with restoration

        All modified parameters are automatically restored when exiting the context,
        even if an exception occurs.

        Args:
        ----
            backend: Qubex backend object
            qid: Qubit ID

        Yields:
        ------
            Context with modified parameters (automatically restored on exit)

        Example:
        -------
            ```python
            # Single parameter override
            task_details = {
                "ChevronPattern": {
                    "input_parameters": {
                        "readout_amplitude": {"value": 0.15}
                    }
                }
            }

            # Multiple parameter overrides
            task_details = {
                "ChevronPattern": {
                    "input_parameters": {
                        "qubit_frequency": {"value": 5.2},
                        "readout_amplitude": {"value": 0.15}
                    }
                }
            }

            # Usage in task run method:
            with self._apply_parameter_overrides(session, qid):
                result = exp.chevron_pattern(...)
            ```

        """
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)

        # Track original values for restoration
        original_values = {}
        frequency_override = None

        try:
            # Check and apply readout_amplitude override
            if "readout_amplitude" in self.input_parameters:
                override_value = self.input_parameters["readout_amplitude"].get_value()
                default_value = exp.experiment_system.control_params.get_readout_amplitude(label)
                # Only override if different from default
                if abs(override_value - default_value) > 1e-9:
                    original_values["readout_amplitude"] = exp.params.readout_amplitude[label]
                    exp.params.readout_amplitude[label] = override_value

            # Check and apply control_amplitude override
            if "control_amplitude" in self.input_parameters:
                override_value = self.input_parameters["control_amplitude"].get_value()
                default_value = exp.experiment_system.control_params.get_control_amplitude(label)
                # Only override if different from default
                if abs(override_value - default_value) > 1e-9:
                    original_values["control_amplitude"] = exp.params.control_amplitude[label]
                    exp.params.control_amplitude[label] = override_value

            # Check and apply readout_frequency override
            if "readout_frequency" in self.input_parameters:
                resonator_label = exp.get_resonator_label(int(qid))
                resonator = exp.experiment_system.quantum_system.get_resonator(resonator_label)
                override_value = self.input_parameters["readout_frequency"].get_value()
                default_value = resonator.frequency
                # Only override if different from default
                if abs(override_value - default_value) > 1e-9:
                    original_values["readout_frequency"] = resonator.frequency
                    resonator.frequency = override_value

            # Check qubit_frequency override (handled specially via modified_frequencies)
            if self._is_frequency_overridden(backend, qid):
                frequency_override = self.input_parameters["qubit_frequency"].get_value()

            # Execute with frequency override if needed
            if frequency_override is not None:
                with exp.modified_frequencies({label: frequency_override}):
                    yield
            else:
                yield

        finally:
            # Restore all modified parameters
            if "readout_amplitude" in original_values:
                exp.params.readout_amplitude[label] = original_values["readout_amplitude"]
            if "control_amplitude" in original_values:
                exp.params.control_amplitude[label] = original_values["control_amplitude"]
            if "readout_frequency" in original_values:
                resonator_label = exp.get_resonator_label(int(qid))
                resonator = exp.experiment_system.quantum_system.get_resonator(resonator_label)
                resonator.frequency = original_values["readout_frequency"]

    @contextmanager
    def _apply_frequency_override(self, backend: "QubexBackend", qid: str):
        """Context manager to apply frequency override if needed.

        DEPRECATED: Use _apply_parameter_overrides() instead for better flexibility.

        This method checks if the qubit_frequency was explicitly overridden
        via task_details. If so, it uses exp.modified_frequencies() to
        temporarily modify the qubit frequency during task execution.

        Args:
        ----
            backend: Qubex backend object
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
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)

        if self._is_frequency_overridden(backend, qid):
            override_freq = self.input_parameters["qubit_frequency"].get_value()
            with exp.modified_frequencies({label: override_freq}):
                yield
        else:
            # No override: just execute normally
            yield
