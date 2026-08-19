import math
from collections.abc import Generator, Mapping
from contextlib import ExitStack, contextmanager
from typing import TYPE_CHECKING, Any

from qubex.experiment.experiment_constants import HPI_RAMPTIME, PI_RAMPTIME
from qubex.experiment.models.rabi_param import RabiParam

from qdash.datamodel.task import InputParameterModel, InputParameterSpec, ParameterModel
from qdash.repository.coupling import MongoCouplingCalibrationRepository
from qdash.repository.qubit import MongoQubitCalibrationRepository
from qdash.workflow.calibtasks.base import (
    BaseTask,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.raw_data import extract_qubex_raw_data
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

        # Fresh executions resolve declarations from current calibration state.
        # Re-executions arrive with a complete snapshot and must not read current DB values.
        if self.input_parameters and not self.input_parameters_from_snapshot:
            self._load_parameters_from_db(backend, qid)

        self._restore_calibration_context(backend, qid)

        return PreProcessResult(
            input_parameters=self.input_parameters,
            run_parameters=self.run_parameters,
        )

    def _resolved_input_values(self, names: tuple[str, ...]) -> dict[str, float] | None:
        """Return a complete group of numeric inputs, or None when it is undeclared."""
        if not all(name in self.input_parameters for name in names):
            return None
        values: dict[str, float] = {}
        missing: list[str] = []
        for name in names:
            value = self.input_parameters[name].value
            if value is None:
                missing.append(name)
            else:
                values[name] = float(value)
        if missing:
            raise ValueError(
                f"{self.name} requires resolved calibration inputs: " + ", ".join(missing)
            )
        return values

    def _restore_rabi_context(self, backend: "QubexBackend", qid: str) -> None:
        """Restore Qubex Rabi context from successful QDash calibration inputs."""
        names = (
            "control_amplitude",
            "rabi_amplitude",
            "rabi_phase",
            "rabi_offset",
            "rabi_angle",
            "rabi_noise",
            "rabi_distance",
            "rabi_reference_phase",
            "rabi_r2",
            "maximum_rabi_frequency",
        )
        values = self._resolved_input_values(names)
        if values is None:
            return
        rabi_r2 = values["rabi_r2"]
        if not math.isfinite(rabi_r2) or rabi_r2 < 0.6:
            raise ValueError(
                f"{self.name} requires finite rabi_r2 greater than or equal to 0.6; "
                f"got {rabi_r2}"
            )
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        rabi_param = RabiParam(
            target=label,
            amplitude=values["rabi_amplitude"],
            frequency=(values["maximum_rabi_frequency"] * values["control_amplitude"] / 1000),
            phase=values["rabi_phase"],
            offset=values["rabi_offset"],
            noise=values["rabi_noise"],
            angle=values["rabi_angle"],
            distance=values["rabi_distance"],
            r2=rabi_r2,
            reference_phase=values["rabi_reference_phase"],
        )
        exp.store_rabi_params({label: rabi_param})

    def _restore_qubit_pulse_context(self, backend: "QubexBackend", qid: str) -> None:
        """Restore pulse parameters consumed implicitly by Qubex experiment methods."""
        pulse_suffixes = (
            "hpi_amplitude",
            "pi_amplitude",
            "drag_hpi_amplitude",
            "drag_pi_amplitude",
        )
        if not any(name.endswith(pulse_suffixes) for name in self.input_parameters):
            return
        exp = self.get_experiment(backend)
        role_labels = {"": self.get_qubit_label(backend, qid)}
        if "-" in qid:
            control_qid, target_qid = qid.split("-", maxsplit=1)
            role_labels = {
                "control_": self.get_qubit_label(backend, control_qid),
                "target_": self.get_qubit_label(backend, target_qid),
            }

        for prefix, label in role_labels.items():
            hpi = self._resolved_input_values((f"{prefix}hpi_amplitude", f"{prefix}hpi_length"))
            if hpi is not None:
                exp.calib_note.update_hpi_param(
                    label,
                    {
                        "target": label,
                        "duration": hpi[f"{prefix}hpi_length"],
                        "amplitude": hpi[f"{prefix}hpi_amplitude"],
                        "tau": HPI_RAMPTIME,
                    },
                )

            pi = self._resolved_input_values((f"{prefix}pi_amplitude", f"{prefix}pi_length"))
            if pi is not None:
                exp.calib_note.update_pi_param(
                    label,
                    {
                        "target": label,
                        "duration": pi[f"{prefix}pi_length"],
                        "amplitude": pi[f"{prefix}pi_amplitude"],
                        "tau": PI_RAMPTIME,
                    },
                )

            for pulse_type in ("drag_hpi", "drag_pi"):
                drag = self._resolved_input_values(
                    (
                        f"{prefix}{pulse_type}_amplitude",
                        f"{prefix}{pulse_type}_length",
                        f"{prefix}{pulse_type}_beta",
                    )
                )
                if drag is None:
                    continue
                getattr(exp.calib_note, f"update_{pulse_type}_param")(
                    label,
                    {
                        "target": label,
                        "duration": drag[f"{prefix}{pulse_type}_length"],
                        "amplitude": drag[f"{prefix}{pulse_type}_amplitude"],
                        "beta": drag[f"{prefix}{pulse_type}_beta"],
                    },
                )

    def _restore_cr_context(self, backend: "QubexBackend", qid: str) -> None:
        """Restore CR parameters consumed implicitly by Qubex two-qubit methods."""
        if "-" not in qid:
            return
        names = (
            "cr_amplitude",
            "cr_phase",
            "cancel_amplitude",
            "cancel_phase",
            "cancel_beta",
            "rotary_amplitude",
            "zx_rotation_rate",
            "cr_ramptime",
        )
        values = self._resolved_input_values(names)
        if values is None:
            return
        exp = self.get_experiment(backend)
        control_qid, target_qid = qid.split("-", maxsplit=1)
        label = "-".join(
            (
                self.get_qubit_label(backend, control_qid),
                self.get_qubit_label(backend, target_qid),
            )
        )
        duration = 0.0
        zx90_gate_time = self.input_parameters.get("zx90_gate_time")
        if zx90_gate_time is not None and zx90_gate_time.value is not None:
            duration = float(zx90_gate_time.value)
        exp.calib_note.update_cr_param(
            label,
            {
                "target": label,
                "duration": duration,
                "ramptime": values["cr_ramptime"],
                "cr_amplitude": values["cr_amplitude"],
                "cr_phase": values["cr_phase"],
                "cr_beta": 0.0,
                "cancel_amplitude": values["cancel_amplitude"],
                "cancel_phase": values["cancel_phase"],
                "cancel_beta": values["cancel_beta"],
                "rotary_amplitude": values["rotary_amplitude"],
                "zx_rotation_rate": values["zx_rotation_rate"],
            },
        )

    def _restore_calibration_context(self, backend: "QubexBackend", qid: str) -> None:
        """Synchronize resolved task inputs into the Qubex in-memory context."""
        self._restore_rabi_context(backend, qid)
        self._restore_qubit_pulse_context(backend, qid)
        self._restore_cr_context(backend, qid)

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
        - If resolution="database_required": Load from DB or raise an error
        - If resolution="database_or_default": Prefer DB, otherwise use default
        - If resolution="default_only": Do not use a DB value
        - If value is None: Deprecated compatibility behavior; create from DB data
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
        declarations = self.__class__.input_spec or self.input_parameters
        for param_name, declaration in declarations.items():
            param = self.input_parameters[param_name]
            # Determine the DB lookup key
            if (
                isinstance(declaration, (InputParameterSpec, ParameterModel))
                and declaration.parameter_name
            ):
                lookup_key = declaration.parameter_name
            else:
                lookup_key = param_name

            # Determine the qid_role for source selection
            qid_role = ""
            if isinstance(declaration, (InputParameterSpec, ParameterModel)):
                qid_role = declaration.qid_role

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
                    if isinstance(declaration, InputParameterSpec):
                        if declaration.resolution == "default_only":
                            continue
                        self.input_parameters[param_name] = InputParameterModel(
                            value=db_value.get("value", declaration.default),
                            value_type=declaration.value_type,
                            unit=db_value.get("unit", declaration.unit),
                            description=db_value.get("description", declaration.description),
                        )
                    elif declaration is None:
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
            elif isinstance(declaration, InputParameterSpec):
                if declaration.resolution == "database_required":
                    raise ValueError(
                        f"Required input parameter '{lookup_key}' for role "
                        f"'{qid_role or 'self'}' was not found in the calibration database"
                    )
                # The instance was initialized with the explicit default value.
            elif (
                isinstance(declaration, ParameterModel)
                and declaration.source == "database"
                and declaration.required
            ):
                raise ValueError(
                    f"Required input parameter '{lookup_key}' for role "
                    f"'{qid_role or 'self'}' was not found in the calibration database"
                )
            elif declaration is None:
                # Deprecated compatibility behavior for legacy declarations.
                self.input_parameters[param_name] = ParameterModel(
                    unit="",
                    description=f"Parameter {param_name} not found in DB",
                )

    @contextmanager
    def _modified_qubit_readout_frequencies(
        self,
        exp: Any,
        *,
        qubit_label: str,
        frequency_overrides: dict[str, float],
        resonator_label: str | None = None,
    ) -> Generator[None, None, None]:
        """Apply Qubex backend settings and logical frequency overrides together.

        ``modified_frequencies`` updates the experiment model, but Qblox/Quel1
        backend LO/CNCO settings also need to follow explicit spectroscopy and
        chevron frequency overrides. Unit-test dummy experiments do not expose
        ``ctx``/``system_manager``, so they fall back to ``modified_frequencies`` only.
        """
        with ExitStack() as stack:
            if hasattr(exp, "ctx") and hasattr(exp, "system_manager"):
                for target_label, frequency in frequency_overrides.items():
                    backend_settings = self._backend_settings_for_frequency(
                        exp,
                        qubit_label=qubit_label,
                        resonator_label=resonator_label,
                        target_label=target_label,
                        frequency=float(frequency),
                    )
                    print(f"[backend_settings] {backend_settings}")
                    stack.enter_context(
                        exp.system_manager.modified_backend_settings(**backend_settings)
                    )

            stack.enter_context(exp.modified_frequencies(frequency_overrides))
            yield

    def _backend_settings_for_frequency(
        self,
        exp: Any,
        *,
        qubit_label: str,
        resonator_label: str | None,
        target_label: str,
        frequency: float,
    ) -> dict[str, Any]:
        from qubex.system import MixingUtil
        from qubex.system.quel1.quel1_system_constants import CNCO_CENTER_CTRL_HZ

        resonator_label = resonator_label or "R" + qubit_label
        experiment_system = exp.ctx.experiment_system
        if target_label == qubit_label:
            box = experiment_system.get_control_box_for_qubit(qubit_label)
            ssb = box.traits.ctrl_ssb
            cnco_center = CNCO_CENTER_CTRL_HZ
        elif target_label == resonator_label:
            box = experiment_system.get_readout_box_for_qubit(qubit_label)
            ssb = box.traits.readout_ssb
            cnco_center = box.traits.readout_cnco_center
        else:
            raise ValueError(f"Unsupported target label for {qubit_label}: {target_label}")

        lo_freq, cnco_freq, _ = MixingUtil.calc_lo_cnco(
            frequency * 1e9,
            ssb=ssb,
            cnco_center=cnco_center,
        )
        return {
            "label": target_label,
            "lo_freq": lo_freq,
            "cnco_freq": cnco_freq,
            "fnco_freq": 0,
        }

    def extract_raw_data(self, run_result: RunResult) -> list[Any]:
        """Return NetCDF-serializable artifacts from the unprocessed Qubex result."""
        return extract_qubex_raw_data(run_result.raw_result)

    def extract_batch_raw_data(
        self, backend: "QubexBackend", run_result: RunResult, qids: list[str]
    ) -> dict[str, list[Any]]:
        """Return NetCDF artifacts grouped by the qid represented in a batch result."""
        raw_result = run_result.raw_result
        result_by_label = raw_result if isinstance(raw_result, Mapping) else None
        if result_by_label is None:
            nested_data = getattr(raw_result, "data", None)
            if isinstance(nested_data, Mapping):
                result_by_label = nested_data

        artifacts: dict[str, list[Any]] = {}
        for qid in qids:
            label = self.get_qubit_label(backend, qid)
            if result_by_label is not None and label in result_by_label:
                artifacts[qid] = extract_qubex_raw_data(result_by_label[label])
            elif len(qids) == 1:
                artifacts[qid] = extract_qubex_raw_data(raw_result)
            else:
                artifacts[qid] = []
        return artifacts

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
        if param is None or param.value is None:
            raise ValueError(f"Parameter {param_name} not found or not loaded")
        # ParameterModel has .value, RunParameterModel has .get_value()
        if hasattr(param, "get_value"):
            return float(param.get_value())
        return float(param.value)

    def _get_readout_amplitude_value(self) -> float:
        """Return readout_amplitude from loaded inputs, falling back to run defaults."""
        input_param = self.input_parameters.get("readout_amplitude")
        if input_param is not None and input_param.value is not None:
            return float(input_param.value)

        run_param = self.run_parameters.get("readout_amplitude")
        if run_param is not None:
            return float(run_param.get_value())

        raise ValueError("readout_amplitude parameter is required")

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
                "CheckFineChevron": {
                    "input_parameters": {
                        "readout_amplitude": {"value": 0.15}
                    }
                }
            }

            # Multiple parameter overrides
            task_details = {
                "CheckFineChevron": {
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
