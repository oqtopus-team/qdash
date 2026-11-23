import math
from typing import Any, ClassVar

import numpy as np
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL

from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
    TaskDocumentation,
)
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import (
    QubexTask,
    readout_duration_run_parameter,
    required_rabi_normalization_inputs,
)
from qdash.workflow.calibtasks.qubex.two_qubit.cr_controls import (
    DEFAULT_ADIABATIC_SAFE_FACTOR,
    DEFAULT_MAX_AMPLITUDE,
    copy_cr_entry,
    cr_pair_label,
    exceeds,
    finite_number,
    put_back_cr_entry,
    require_fresh_cr_entry,
    resolve_bound,
    validate_ramptime,
)
from qdash.workflow.calibtasks.qubex.validation import finite_value_error, first_validation_error
from qdash.workflow.engine.backend.qubex import QubexBackend

# Rough scan the task runs for a fixed duration without an explicit amplitude_range. It
# mirrors the Qubex rough stage (20 points from 0 to twice the input CR amplitude, then
# 50 points from 0.8 to 1.2 times the rough root) without the Qubex duration retry.
_ROUGH_POINTS = 20
_ROUGH_SPAN = 2.0
_FINE_POINTS = 50
_FINE_LOWER = 0.8
_FINE_UPPER = 1.2
# Qubex fits a degree-3 polynomial to each amplitude scan.
_MIN_SCAN_POINTS = 4

_CR_OUTPUT_NAMES = (
    "cr_duration",
    "cr_amplitude",
    "cr_phase",
    "cr_beta",
    "cancel_amplitude",
    "cancel_phase",
    "cancel_beta",
    "rotary_amplitude",
    "zx_rotation_rate",
    "zx90_gate_time",
    "cr_ramptime",
)


class CreateZX90(QubexTask):
    """Task to create ZX90 gate.

    Qubex ``calibrate_zx90`` scans the CR amplitude at a CR duration and fits the root.
    Without ``duration`` and ``amplitude_range`` Qubex starts from the input
    ``cr_duration`` and lengthens it once when its rough scan finds no root. With
    ``duration`` the task runs the rough scan itself at that duration and fails when no
    root is found, so the duration is never lengthened.

    The accepted amplitude must be the fitted root Qubex reports, inside the scanned
    range, and at or below the approved cap ``min(max_amplitude,
    amplitude(adiabatic_safe_factor * |f_control - f_target|))``. When the final fit has
    no root Qubex stores 1.0; the task rejects that result from the missing root, puts
    the pair's Qubex CR note entry back, and does not save the note file.
    """

    name: str = "CreateZX90"
    task_type: str = "coupling"
    documentation: ClassVar[TaskDocumentation] = TaskDocumentation(
        description=(
            "Builds an echoed CR ZX90 gate with a DRAG pi echo on the control qubit, calibrates"
            " its CR amplitude by sweeping and fitting the target response, and writes the CR "
            "parameters plus zx90_gate_time."
        ),
        when_to_use=(
            "Run it after CheckCrossResonance. CheckZX90, the Bell tasks, "
            "ZX90InterleavedRandomizedBenchmarking, and Check2QGateCoherenceLimit use its "
            "result."
        ),
        prerequisites=(
            (
                "The coupling qid is control-target; control-qubit and target-qubit inputs are "
                "read from each qubit's stored calibration."
            ),
            (
                "DRAG half-pi pulses (CreateDRAGHPIPulse) on both qubits and a DRAG pi pulse "
                "(CreateDRAGPIPulse) on the control qubit."
            ),
            (
                "CR parameters (cr_*, cancel_*, rotary_amplitude, zx_rotation_rate, "
                "cr_ramptime) stored by CheckCrossResonance."
            ),
        ),
    )
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_duration": readout_duration_run_parameter(),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=CALIBRATION_SHOTS,
            description="Number of shots",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="int",
            default=DEFAULT_INTERVAL,
            description="Time interval",
        ),
        "duration": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=None,
            description=(
                "Fixed CR duration. The amplitude is fitted at this duration only; the task "
                "fails instead of lengthening it. Unset keeps the Qubex duration behavior."
            ),
        ),
        "ramptime": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=None,
            description="CR ramp time. Unset uses the input cr_ramptime.",
        ),
        "amplitude_range": RunParameterSpec(
            unit="a.u.",
            value_type="np.linspace",
            default=None,
            description=(
                "CR amplitude scan as (start, stop, num). Skips the rough scan and its "
                "duration retry. Unset derives the scan from the input cr_amplitude."
            ),
        ),
        "adiabatic_safe_factor": RunParameterSpec(
            unit="a.u.",
            value_type="float",
            default=None,
            description=(
                "Safety factor for the adiabatic amplitude cap. Unset inherits "
                "cr_adiabatic_safe_factor from CheckCrossResonance, else 0.75. A looser "
                "value than the inherited one is rejected."
            ),
        ),
        "max_amplitude": RunParameterSpec(
            unit="a.u.",
            value_type="float",
            default=None,
            description=(
                "Maximum CR amplitude. Unset inherits cr_max_amplitude from "
                "CheckCrossResonance, else 1.0. A looser value than the inherited one is "
                "rejected."
            ),
        ),
        "rotary_multiple": RunParameterSpec(
            unit="a.u.",
            value_type="float",
            default=None,
            description=(
                "Rotary tone Rabi rate as a multiple of the ZX rate. Unset uses the Qubex "
                "default (9)."
            ),
        ),
        "duration_buffer": RunParameterSpec(
            unit="a.u.",
            value_type="float",
            default=None,
            description=(
                "Factor Qubex applies when it derives the duration (input cr_duration is 0) "
                "or lengthens it on retry. Unset uses the Qubex default (1.05)."
            ),
        ),
    }

    # Input parameters from control and target qubits
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        # Control/target RabiParams calibrate ZX90 and normalize IQ; validate both contexts.
        **required_rabi_normalization_inputs(prefix="control_", qid_role="control"),
        **required_rabi_normalization_inputs(prefix="target_", qid_role="target"),
        # Control qubit parameters
        "control_qubit_frequency": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="control_frequency",
            fallback_parameter_names=("qubit_frequency",),
            qid_role="control",
            unit="GHz",
        ),
        "control_drag_hpi_amplitude": InputParameterSpec.required_database(
            parameter_name="drag_hpi_amplitude",
            qid_role="control",
            unit="a.u.",
        ),
        "control_drag_hpi_duration": InputParameterSpec.required_database(
            parameter_name="drag_hpi_duration",
            parameter_aliases=("drag_hpi_length",),
            qid_role="control",
            unit="ns",
        ),
        "control_drag_hpi_beta": InputParameterSpec.required_database(
            parameter_name="drag_hpi_beta",
            qid_role="control",
            unit="a.u.",
        ),
        "control_drag_pi_amplitude": InputParameterSpec.required_database(
            parameter_name="drag_pi_amplitude",
            qid_role="control",
            unit="a.u.",
        ),
        "control_drag_pi_duration": InputParameterSpec.required_database(
            parameter_name="drag_pi_duration",
            parameter_aliases=("drag_pi_length",),
            qid_role="control",
            unit="ns",
        ),
        "control_drag_pi_beta": InputParameterSpec.required_database(
            parameter_name="drag_pi_beta",
            qid_role="control",
            unit="a.u.",
        ),
        "control_readout_frequency": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="readout_frequency",
            fallback_parameter_names=("resonator_frequency",),
            qid_role="control",
            unit="GHz",
        ),
        "control_readout_amplitude": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="readout_amplitude",
            qid_role="control",
            unit="a.u.",
        ),
        # Target qubit parameters
        "target_qubit_frequency": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="control_frequency",
            fallback_parameter_names=("qubit_frequency",),
            qid_role="target",
            unit="GHz",
        ),
        "target_readout_frequency": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="readout_frequency",
            fallback_parameter_names=("resonator_frequency",),
            qid_role="target",
            unit="GHz",
        ),
        "target_readout_amplitude": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="readout_amplitude",
            qid_role="target",
            unit="a.u.",
        ),
        # CR parameters (from CheckCrossResonance)
        "cr_duration": InputParameterSpec.required_database(
            parameter_name="cr_duration",
            qid_role="coupling",
            unit="ns",
        ),
        "cr_amplitude": InputParameterSpec.required_database(
            parameter_name="cr_amplitude",
            qid_role="control",
            unit="a.u.",
        ),
        "cr_phase": InputParameterSpec.required_database(
            parameter_name="cr_phase",
            qid_role="control",
            unit="a.u.",
        ),
        "cr_beta": InputParameterSpec.required_database(
            parameter_name="cr_beta",
            qid_role="control",
            unit="a.u.",
        ),
        "cancel_amplitude": InputParameterSpec.required_database(
            parameter_name="cancel_amplitude",
            qid_role="target",
            unit="a.u.",
        ),
        "cancel_phase": InputParameterSpec.required_database(
            parameter_name="cancel_phase",
            qid_role="target",
            unit="a.u.",
        ),
        "cancel_beta": InputParameterSpec.required_database(
            parameter_name="cancel_beta",
            qid_role="target",
            unit="a.u.",
        ),
        "rotary_amplitude": InputParameterSpec.required_database(
            parameter_name="rotary_amplitude",
            qid_role="control",
            unit="a.u.",
        ),
        "zx_rotation_rate": InputParameterSpec.required_database(
            parameter_name="zx_rotation_rate",
            qid_role="coupling",
            unit="a.u.",
        ),
        "cr_ramptime": InputParameterSpec.required_database(
            parameter_name="cr_ramptime",
            qid_role="coupling",
            unit="ns",
        ),
        # Bounds approved by CheckCrossResonance; absent for pairs characterized before
        # CheckCrossResonance recorded them.
        "cr_max_amplitude": InputParameterSpec.database_optional(
            parameter_name="cr_max_amplitude",
            qid_role="coupling",
            unit="a.u.",
        ),
        "cr_adiabatic_safe_factor": InputParameterSpec.database_optional(
            parameter_name="cr_adiabatic_safe_factor",
            qid_role="coupling",
            unit="a.u.",
        ),
    }

    # Output parameters with qid_role specifying where each is stored
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "cr_duration": OutputParameterSpec(
            qid_role="coupling", unit="ns", description="Duration of the CR pulse."
        ),
        "cr_amplitude": OutputParameterSpec(
            qid_role="control", unit="a.u.", description="Amplitude of the CR pulse."
        ),
        "cr_phase": OutputParameterSpec(
            qid_role="control", unit="a.u.", description="Phase of the CR pulse."
        ),
        "cr_beta": OutputParameterSpec(
            qid_role="control", unit="a.u.", description="Beta of the CR pulse."
        ),
        "cancel_amplitude": OutputParameterSpec(
            qid_role="target", unit="a.u.", description="Amplitude of the cancel pulse."
        ),
        "cancel_phase": OutputParameterSpec(
            qid_role="target", unit="a.u.", description="Phase of the cancel pulse."
        ),
        "cancel_beta": OutputParameterSpec(
            qid_role="target", unit="a.u.", description="Beta of the cancel pulse."
        ),
        "rotary_amplitude": OutputParameterSpec(
            qid_role="control", unit="a.u.", description="Amplitude of the rotary pulse."
        ),
        "zx_rotation_rate": OutputParameterSpec(
            qid_role="coupling", unit="a.u.", description="ZX rotation rate."
        ),
        "zx90_gate_time": OutputParameterSpec(
            qid_role="coupling", unit="ns", description="Duration of the ZX90 pulse."
        ),
        "cr_ramptime": OutputParameterSpec(
            qid_role="coupling", unit="ns", description="CR pulse ramp time."
        ),
    }

    # The pair's CR note entry before this run's fit, put back when the fit is rejected.
    _previous_cr_entry: dict[str, Any] | None = None

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        result = run_result.raw_result
        for name in _CR_OUTPUT_NAMES:
            self.output_parameters[name].value = result[name]
        output_parameters = self.attach_execution_id(execution_id)
        figures: list[Any] = [*result["rough_figures"], result["n1"], result["n3"], result["fig"]]
        nonnegative = {"cr_duration", "zx90_gate_time"}
        validation_error = first_validation_error(
            result["rejection"],
            *(
                finite_value_error(
                    self.output_parameters[name].value,
                    f"CreateZX90 {name} for {qid}",
                    minimum=0.0 if name in nonnegative else None,
                )
                for name in _CR_OUTPUT_NAMES
            ),
        )
        if validation_error is None:
            self.save_calibration(backend)
        else:
            # Keep the rejected fit out of the Qubex note before the executor records it.
            exp = self.get_experiment(backend)
            put_back_cr_entry(exp.calib_note, cr_pair_label(exp, qid), self._previous_cr_entry)
        return PostProcessResult(
            output_parameters=output_parameters,
            figures=figures,
            raw_data=[],
            validation_error=validation_error,
        )

    def _input_value(self, name: str) -> Any:
        parameter = self.input_parameters.get(name)
        return None if parameter is None else parameter.value

    def _amplitude_range(self) -> tuple[float, float, int] | None:
        raw = self.run_parameters["amplitude_range"].value
        if raw is None:
            return None
        if not isinstance(raw, (list, tuple)) or len(raw) != 3:
            raise ValueError(f"amplitude_range must be (start, stop, num), got {raw!r}")
        start = finite_number(raw[0], "amplitude_range start")
        stop = finite_number(raw[1], "amplitude_range stop")
        num = finite_number(raw[2], "amplitude_range num")
        if not num.is_integer() or num < _MIN_SCAN_POINTS:
            raise ValueError(
                f"amplitude_range num must be an integer of at least {_MIN_SCAN_POINTS}, "
                f"got {raw[2]!r}"
            )
        if start < 0 or stop <= start:
            raise ValueError(f"amplitude_range must satisfy 0 <= start < stop, got {raw!r}")
        return start, stop, int(num)

    def _qubex_kwargs(self) -> dict[str, Any]:
        """Validate the run controls and return the calibrate_zx90 keyword arguments.

        Every check runs before any acquisition.
        """
        run = self.run_parameters
        kwargs: dict[str, Any] = {}
        if run["duration"].value is not None:
            duration = finite_number(run["duration"].value, "duration")
            if duration <= 0:
                raise ValueError(f"duration must be positive (ns), got {duration}")
            kwargs["duration"] = duration
        if run["ramptime"].value is not None:
            kwargs["ramptime"] = validate_ramptime(run["ramptime"].value)
        else:
            kwargs["ramptime"] = validate_ramptime(
                self._input_value("cr_ramptime"), "input cr_ramptime"
            )
        input_duration = finite_number(self._input_value("cr_duration"), "input cr_duration")
        if input_duration < 0:
            raise ValueError(f"input cr_duration must not be negative, got {input_duration}")
        duration = kwargs.get("duration", input_duration)
        # An input cr_duration of 0 lets Qubex derive a duration that includes the ramps.
        if duration > 0 and 2 * kwargs["ramptime"] > duration:
            raise ValueError(
                f"CR duration {duration} ns must be at least 2 * ramptime "
                f"({2 * kwargs['ramptime']} ns)"
            )
        kwargs["adiabatic_safe_factor"] = resolve_bound(
            run["adiabatic_safe_factor"].value,
            self._input_value("cr_adiabatic_safe_factor"),
            "adiabatic_safe_factor",
            DEFAULT_ADIABATIC_SAFE_FACTOR,
        )
        kwargs["max_amplitude"] = resolve_bound(
            run["max_amplitude"].value,
            self._input_value("cr_max_amplitude"),
            "max_amplitude",
            DEFAULT_MAX_AMPLITUDE,
        )
        if run["rotary_multiple"].value is not None:
            rotary_multiple = finite_number(run["rotary_multiple"].value, "rotary_multiple")
            if rotary_multiple <= 0:
                raise ValueError(f"rotary_multiple must be positive, got {rotary_multiple}")
            kwargs["rotary_multiple"] = rotary_multiple
        if run["duration_buffer"].value is not None:
            duration_buffer = finite_number(run["duration_buffer"].value, "duration_buffer")
            if duration_buffer < 1:
                raise ValueError(f"duration_buffer must be at least 1, got {duration_buffer}")
            kwargs["duration_buffer"] = duration_buffer
        return kwargs

    @staticmethod
    def _fit_root(payload: Any, what: str) -> float:
        """Return the polynomial-fit root Qubex reported, NaN when it found none."""
        try:
            root = payload["root"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError(
                f"The Qubex calibrate_zx90 result has no {what} root, so the fit cannot be verified"
            ) from exc
        return math.nan if root is None else float(root)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        kwargs = self._qubex_kwargs()
        explicit_range = self._amplitude_range()
        cr_amplitude = finite_number(self._input_value("cr_amplitude"), "input cr_amplitude")
        if cr_amplitude <= 0:
            raise ValueError(f"input cr_amplitude must be positive, got {cr_amplitude}")
        exp = self.get_experiment(backend)
        control, target = (
            exp.get_qubit_label(int(q)) for q in qid.split("-")
        )  # e.g., "0-1" → "Q00","Q01"
        label = cr_pair_label(exp, qid)  # e.g., "Q00-Q01"
        # Same cap as the Qubex scan clip.
        f_delta = abs(float(exp.qubits[target].frequency) - float(exp.qubits[control].frequency))
        adiabatic_cap = finite_number(
            exp.calc_control_amplitude(control, kwargs["adiabatic_safe_factor"] * f_delta),
            "adiabatic CR amplitude cap",
        )
        cap = min(max(adiabatic_cap, 0.0), kwargs["max_amplitude"])
        if cap <= 0:
            raise ValueError(f"The approved CR amplitude cap for {label} is {cap}")
        if explicit_range is not None and exceeds(explicit_range[1], cap):
            raise ValueError(
                f"amplitude_range stop {explicit_range[1]} exceeds the approved CR amplitude "
                f"cap {cap} for {label}"
            )
        x180 = {control: exp.drag_pi_pulse[control]}
        kwargs.update(
            x180=x180,
            n_shots=self.run_parameters["shots"].get_value(),
            shot_interval=self.run_parameters["interval"].get_value(),
        )

        rough_figures: list[Any] = []
        scan = explicit_range
        if "duration" in kwargs and scan is None:
            rough_stop = min(_ROUGH_SPAN * cr_amplitude, cap)
            rough = exp.calibrate_zx90(
                control,
                target,
                amplitude_range=np.linspace(0.0, rough_stop, _ROUGH_POINTS),
                store_params=False,
                **kwargs,
            )
            # The Qubex rough stage uses the n_repetitions = 1 root.
            rough_root = self._fit_root(rough["n1"], "rough n1")
            if rough["n1"].get("fig") is not None:
                rough_figures.append(rough["n1"]["fig"])
            if math.isnan(rough_root) or rough_root <= 0:
                raise ValueError(
                    f"No ZX90 amplitude root for {label} at the fixed duration "
                    f"{kwargs['duration']} ns in the rough scan [0, {rough_stop}]"
                )
            scan = (_FINE_LOWER * rough_root, min(_FINE_UPPER * rough_root, cap), _FINE_POINTS)
        if scan is not None:
            kwargs["amplitude_range"] = np.linspace(*scan)

        previous = copy_cr_entry(exp.calib_note, label)
        self._previous_cr_entry = previous
        try:
            raw_result = exp.calibrate_zx90(control, target, store_params=True, **kwargs)
            fit_result = require_fresh_cr_entry(previous, exp.calib_note.get_cr_param(label), label)
            root = self._fit_root(raw_result, "final")
            scanned = np.asarray(raw_result["amplitude_range"], dtype=float)
            rejection = self._rejection(label, root, scanned, cap, fit_result, kwargs)
            zx90_gate_time = math.nan
            if rejection is None:
                zx90 = exp.zx90(
                    control_qubit=control,
                    target_qubit=target,
                    x180=x180,
                    cr_duration=float(fit_result["duration"]),
                    cr_ramptime=float(fit_result["ramptime"]),
                    cr_amplitude=float(fit_result["cr_amplitude"]),
                    cr_phase=float(fit_result["cr_phase"]),
                    cr_beta=float(fit_result["cr_beta"]),
                    cancel_amplitude=float(fit_result["cancel_amplitude"]),
                    cancel_phase=float(fit_result["cancel_phase"]),
                    cancel_beta=float(fit_result["cancel_beta"]),
                    rotary_amplitude=float(fit_result["rotary_amplitude"]),
                )
                zx90_gate_time = zx90.duration
        except BaseException:
            put_back_cr_entry(exp.calib_note, label, previous)
            raise

        result = {
            "cr_duration": fit_result["duration"],
            "cr_amplitude": fit_result["cr_amplitude"],
            "cr_phase": fit_result["cr_phase"],
            "cr_beta": fit_result["cr_beta"],
            "cancel_amplitude": fit_result["cancel_amplitude"],
            "cancel_phase": fit_result["cancel_phase"],
            "cancel_beta": fit_result["cancel_beta"],
            "rotary_amplitude": fit_result["rotary_amplitude"],
            "zx_rotation_rate": fit_result["zx_rotation_rate"],
            "cr_ramptime": fit_result["ramptime"],
            "zx90_gate_time": zx90_gate_time,
            "n1": raw_result["n1"]["fig"],
            "n3": raw_result["n3"]["fig"],
            "fig": raw_result["fig"],
            "rough_figures": rough_figures,
            "rejection": rejection,
        }
        return RunResult(raw_result=result)

    @staticmethod
    def _rejection(
        label: str,
        root: float,
        scanned: np.ndarray,
        cap: float,
        fit_result: dict[str, Any],
        kwargs: dict[str, Any],
    ) -> str | None:
        """Return why the Qubex result must not be accepted, or None."""
        stored_amplitude = finite_number(fit_result["cr_amplitude"], "stored cr_amplitude")
        if math.isnan(root):
            return (
                f"ZX90 amplitude fit for {label} found no root in "
                f"[{scanned.min()}, {scanned.max()}]; Qubex stored the fallback cr_amplitude "
                f"{stored_amplitude}, which was rejected"
            )
        if not math.isclose(stored_amplitude, root, rel_tol=1e-9, abs_tol=1e-12):
            return (
                f"Qubex stored cr_amplitude {stored_amplitude} for {label}, not the fitted "
                f"root {root}"
            )
        if exceeds(scanned.min(), root) or exceeds(root, scanned.max()):
            return (
                f"ZX90 amplitude root {root} for {label} is outside the scanned range "
                f"[{scanned.min()}, {scanned.max()}]"
            )
        if exceeds(root, cap):
            return f"ZX90 amplitude {root} for {label} exceeds the approved CR amplitude cap {cap}"
        final_duration = finite_number(fit_result["duration"], "stored duration")
        if "duration" in kwargs and not math.isclose(final_duration, kwargs["duration"]):
            return (
                f"Qubex used CR duration {final_duration} ns for {label}, not the requested "
                f"{kwargs['duration']} ns"
            )
        stored_ramptime = finite_number(fit_result["ramptime"], "stored ramptime")
        if not math.isclose(stored_ramptime, kwargs["ramptime"]):
            return (
                f"Qubex used CR ramptime {stored_ramptime} ns for {label}, not the requested "
                f"{kwargs['ramptime']} ns"
            )
        return None
