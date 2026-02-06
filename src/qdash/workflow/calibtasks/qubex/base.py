from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from qdash.datamodel.task import ParameterModel
from qdash.repository.coupling import MongoCouplingCalibrationRepository
from qdash.repository.qubit import MongoQubitCalibrationRepository
from qdash.workflow.calibtasks.base import (
    BaseTask,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.engine.task.provenance_recorder import resolve_qid

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
        """Preprocess the task by loading calibration parameters from DB.

        This method populates input_parameters with calibration values from QDash DB.

        Behavior:
        - If input_parameters is empty: No input dependencies (nothing to load)
        - If input_parameters has declarations: Load values from QDash DB

        Args:
        ----
            backend: Qubex backend object
            qid: Qubit ID (or "control-target" for coupling tasks)

        Returns:
        -------
            PreProcessResult with populated input_parameters

        """
        # System tasks don't need parameter preprocessing
        if self.task_type == "system" or qid == "":
            return PreProcessResult(
                input_parameters=self.input_parameters,
                run_parameters=self.run_parameters,
            )

        # Load declared input_parameters from DB
        if self.input_parameters:
            self._load_parameters_from_db(backend, qid)

        return PreProcessResult(
            input_parameters=self.input_parameters,
            run_parameters=self.run_parameters,
        )

    def _load_parameters_from_db(self, backend: "QubexBackend", qid: str) -> None:
        """Load declared parameter values from QDash database.

        This method fetches calibration data from QubitDocument and/or CouplingDocument
        and populates the declared input_parameters with actual values.

        For coupling tasks (qid like "0-1"), data is fetched from three sources:
        - Control qubit's QubitDocument (for qid_role="control")
        - Target qubit's QubitDocument (for qid_role="target")
        - CouplingDocument (for qid_role="coupling", and as fallback)

        For qubit tasks, data is fetched from a single QubitDocument.

        Behavior for each parameter:
        - If value is None: Create ParameterModel entirely from DB data
        - If value is ParameterModel: Use DB value if available, else use as fallback

        Args:
        ----
            backend: Qubex backend object
            qid: Qubit ID (or "control-target" for coupling tasks)

        """
        project_id = backend.config.get("project_id")
        chip_id = backend.config.get("chip_id")

        if not project_id or not chip_id:
            # Cannot fetch from DB without project_id and chip_id
            return

        # Fetch calibration data based on task type
        if "-" in qid:
            # Coupling task: fetch from all three sources
            control_qid = resolve_qid(qid, "control")
            target_qid = resolve_qid(qid, "target")

            qubit_repo = MongoQubitCalibrationRepository()
            coupling_repo = MongoCouplingCalibrationRepository()

            control_data = qubit_repo.get_calibration_data(
                project_id=project_id, chip_id=chip_id, qid=control_qid
            )
            target_data = qubit_repo.get_calibration_data(
                project_id=project_id, chip_id=chip_id, qid=target_qid
            )
            coupling_data = coupling_repo.get_calibration_data(
                project_id=project_id, chip_id=chip_id, qid=qid
            )

            # Map qid_role to [primary_source, fallback_source]
            role_data_sources: dict[str, list[dict[str, Any]]] = {
                "control": [control_data, coupling_data],
                "target": [target_data, coupling_data],
                "coupling": [coupling_data],
                "": [coupling_data],
                "self": [coupling_data],
            }

            self._populate_parameters(role_data_sources)
        else:
            # Qubit task: single source
            qubit_repo = MongoQubitCalibrationRepository()
            calib_data = qubit_repo.get_calibration_data(
                project_id=project_id, chip_id=chip_id, qid=qid
            )

            role_data_sources = {
                "": [calib_data],
                "self": [calib_data],
            }

            self._populate_parameters(role_data_sources)

    def _populate_parameters(self, role_data_sources: dict[str, list[dict[str, Any]]]) -> None:
        """Populate input_parameters from data sources based on qid_role.

        For each declared parameter, determines the lookup key from parameter_name
        (falling back to the dict key), then searches the data sources associated
        with the parameter's qid_role in order.

        Args:
        ----
            role_data_sources: Mapping of qid_role to list of data source dicts
                to search (in priority order).

        """
        for param_name, param in list(self.input_parameters.items()):
            # Determine the DB lookup key
            if isinstance(param, ParameterModel) and param.parameter_name:
                lookup_key = param.parameter_name
            else:
                lookup_key = param_name

            # Determine the qid_role for source selection
            qid_role = ""
            if isinstance(param, ParameterModel):
                qid_role = param.qid_role

            # Get the ordered list of data sources for this role
            sources = role_data_sources.get(qid_role, role_data_sources.get("", []))

            # Search sources in order for the lookup key
            db_value = None
            for source in sources:
                if lookup_key in source:
                    db_value = source[lookup_key]
                    break

            if db_value is not None:
                if isinstance(db_value, dict):
                    if param is None:
                        # Create ParameterModel entirely from DB
                        self.input_parameters[param_name] = ParameterModel(
                            value=db_value.get("value", 0),
                            unit=db_value.get("unit", ""),
                            description=db_value.get("description", ""),
                        )
                    else:
                        # Update existing ParameterModel with DB value
                        if "value" in db_value:
                            param.value = db_value["value"]
            elif param is None:
                # Parameter not in any source and no fallback - create empty
                self.input_parameters[param_name] = ParameterModel(
                    unit="",
                    description=f"Parameter {param_name} not found in DB",
                )

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
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )

    def get_experiment(self, backend: "QubexBackend") -> Any:
        """Get the experiment session from QubexBackend.

        Args:
        ----
            backend: Qubex backend object

        Returns:
        -------
            The underlying experiment session

        """
        return backend.get_instance()

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
        return str(exp.get_qubit_label(int(qid)))

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
        return str(exp.get_resonator_label(int(qid)))

    def save_calibration(self, backend: "QubexBackend") -> None:
        """Save calibration notes after task execution.

        Args:
        ----
            backend: Qubex backend object

        """
        exp = self.get_experiment(backend)
        exp.calib_note.save()

    def _get_calibration_value(self, param_name: str) -> float:
        """Get value from calibration input parameter.

        Args:
        ----
            param_name: Name of the parameter

        Returns:
        -------
            The parameter value as float

        """
        param = self.input_parameters[param_name]
        if param is None:
            raise ValueError(f"Parameter {param_name} not found or not loaded")
        # ParameterModel has .value, RunParameterModel has .get_value()
        if hasattr(param, "get_value"):
            return float(param.get_value())
        return float(param.value)

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
        # If qubit_frequency is not in input_parameters, there's no override
        if "qubit_frequency" not in self.input_parameters:
            return False

        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)

        # Get current frequency from input_parameters
        current_freq = self._get_calibration_value("qubit_frequency")

        # Get default frequency from quantum system
        default_freq = exp.experiment_system.quantum_system.get_qubit(label).frequency

        # Check if they differ (with small tolerance for floating point comparison)
        return bool(abs(float(current_freq) - float(default_freq)) > 1e-9)

    @contextmanager
    def _apply_parameter_overrides(
        self, backend: "QubexBackend", qid: str
    ) -> Generator[None, None, None]:
        """Context manager to apply multiple parameter overrides.

        This unified method handles parameter types that can be overridden:
        - qubit_frequency: Uses exp.modified_frequencies() context manager
        - readout_amplitude: Direct modification with restoration
        - control_amplitude: Direct modification with restoration

        Note: readout_frequency is NOT handled here. Tasks that need to override
        readout_frequency should pass it as a method argument (e.g.,
        exp.qubit_spectroscopy(readout_frequency=...)) because resonator.frequency
        is a read-only property in qubex.

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
                override_value = self._get_calibration_value("readout_amplitude")
                default_value = exp.experiment_system.control_params.get_readout_amplitude(label)
                # Only override if different from default
                if abs(override_value - default_value) > 1e-9:
                    original_values["readout_amplitude"] = exp.params.readout_amplitude[label]
                    exp.params.readout_amplitude[label] = override_value

            # Check and apply control_amplitude override
            if "control_amplitude" in self.input_parameters:
                override_value = self._get_calibration_value("control_amplitude")
                default_value = exp.experiment_system.control_params.get_control_amplitude(label)
                # Only override if different from default
                if abs(override_value - default_value) > 1e-9:
                    original_values["control_amplitude"] = exp.params.control_amplitude[label]
                    exp.params.control_amplitude[label] = override_value

            # Note: readout_frequency override is NOT handled here.
            # Tasks that need to override readout_frequency should pass it as
            # a method argument (e.g., exp.qubit_spectroscopy(readout_frequency=...))
            # because resonator.frequency is a read-only property in qubex.

            # Check qubit_frequency override (handled specially via modified_frequencies)
            if self._is_frequency_overridden(backend, qid):
                frequency_override = self._get_calibration_value("qubit_frequency")

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

    @contextmanager
    def _apply_frequency_override(
        self, backend: "QubexBackend", qid: str
    ) -> Generator[None, None, None]:
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
            override_freq = self._get_calibration_value("qubit_frequency")
            with exp.modified_frequencies({label: override_freq}):
                yield
        else:
            # No override: just execute normally
            yield
