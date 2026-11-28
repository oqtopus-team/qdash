"""Measure the FH transition frequency and estimate transmon harmonic energies."""

import logging
import math
from typing import ClassVar

from numpy.linalg import LinAlgError
from prefect import get_run_logger
from prefect.exceptions import MissingContextError
from qubex.contrib.experiment import estimate_fh_frequency_from_chevron_adaptive
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL, DEFAULT_SHOTS

from qdash.analysis.transmon_harmonics import TransmonHarmonicsFit, fit_transmon_harmonics
from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
    TaskDocumentation,
)
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import QubexTask, readout_duration_run_parameter
from qdash.workflow.calibtasks.qubex.validation import (
    finite_value_error,
    first_validation_error,
    require_fh_configuration,
)
from qdash.workflow.engine.backend.qubex import QubexBackend

logger = logging.getLogger(__name__)


class CheckAdaptiveFHChevron(QubexTask):
    """Adaptively measure the FH transition using stored Qubex GE and EF pulses.

    The recorded HPI and EF pi inputs enforce the calibration prerequisites. Qubex resolves the
    actual preparation waveforms from the synchronized session when it constructs each sequence.
    """

    name: str = "CheckAdaptiveFHChevron"
    task_type: str = "qubit"
    documentation: ClassVar[TaskDocumentation] = TaskDocumentation(
        description=(
            "Prepares the second excited state with the session's GE and EF pulses and runs an "
            "adaptive chevron on the f-to-h transition. It writes fh_frequency (also published "
            "as control_frequency_fh) and estimates EC, EJ1, and EJ2 from the GE, EF, and FH "
            "frequencies when the fit meets the residual limit. It skips the energy outputs "
            "when different energies reproduce the same transition spectrum."
        ),
        when_to_use=(
            "Run it after EF pulses are calibrated when the third transition is needed. The "
            "search starts from the configured FH frequency or 2*ef - ge, with the GE amplitude"
            " divided by sqrt(3)."
        ),
        prerequisites=(
            ("GE, EF, and FH drive targets in the current session: configuration_mode ge-ef-fh."),
            (
                "control_frequency, control_amplitude, readout_frequency, and readout_amplitude"
                " are stored; hpi_amplitude and hpi_duration stored by CreateHPIPulse."
            ),
            "control_frequency_ef (or ef_frequency) stored by CheckAdaptiveEFChevron.",
            "ef_pi_amplitude and ef_pi_duration stored by CreateEFPIPulse.",
        ),
    )
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "control_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("qubit_frequency",), unit="GHz"
        ),
        "control_frequency_ef": InputParameterSpec.required_database(
            fallback_parameter_names=("ef_frequency",), unit="GHz"
        ),
        "qubit_frequency": InputParameterSpec.database_optional(
            user_override="forbidden",
            unit="GHz",
            description="Measured GE resonance preferred for the harmonic fit",
        ),
        "ef_frequency": InputParameterSpec.database_optional(
            user_override="forbidden",
            unit="GHz",
            description="Measured EF resonance preferred for the harmonic fit",
        ),
        "control_amplitude": InputParameterSpec.required_database(
            unit="a.u.",
            description="Calibrated GE amplitude used to derive the initial FH drive amplitude",
        ),
        "hpi_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "hpi_duration": InputParameterSpec.required_database(unit="ns"),
        "ef_pi_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "ef_pi_duration": InputParameterSpec.required_database(unit="ns"),
        "readout_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "readout_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("resonator_frequency",), unit="GHz"
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_duration": readout_duration_run_parameter(),
        "detuning_range": RunParameterSpec(
            unit="GHz",
            value_type="np.linspace",
            default=(-0.05, 0.05, 41),
            description="Final FH detuning sweep around the adaptively estimated frequency",
        ),
        "time_range": RunParameterSpec(
            unit="ns",
            value_type="range",
            default=(0, 257, 8),
            description="Final FH drive duration sweep",
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=DEFAULT_SHOTS // 4,
            description="Number of shots per FH chevron point",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=DEFAULT_INTERVAL,
            description="Time interval between shots",
        ),
        "minimum_peak_background_rms_ratio": RunParameterSpec(
            unit="a.u.",
            value_type="float",
            default=5.0,
            description="Minimum matched-transform peak/background RMS ratio",
        ),
        "maximum_harmonic_fit_residual": RunParameterSpec(
            unit="GHz",
            value_type="float",
            default=0.005,
            description="Maximum absolute GE, EF, or FH residual for publishing EC, EJ1, and EJ2",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "fh_frequency": OutputParameterSpec(
            unit="GHz",
            description="Measured f-to-h transition frequency",
            publish_targets=("fh_frequency", "control_frequency_fh"),
        ),
        "charging_energy": OutputParameterSpec(
            unit="GHz",
            default=None,
            description="Charging energy EC estimated from GE, EF, and FH",
        ),
        "josephson_energy_first_harmonic": OutputParameterSpec(
            unit="GHz",
            default=None,
            description="First Josephson harmonic EJ1 estimated from GE, EF, and FH",
        ),
        "josephson_energy_second_harmonic": OutputParameterSpec(
            unit="GHz",
            default=None,
            description="Second Josephson harmonic EJ2 estimated from GE, EF, and FH",
        ),
    }

    def resolve_run_parameters(self, backend: QubexBackend, qid: str) -> None:
        """Restore the harmonic fit limit when replaying an older parameter snapshot."""
        super().resolve_run_parameters(backend, qid)
        name = "maximum_harmonic_fit_residual"
        if name not in self.run_parameters:
            self.run_parameters[name] = self.run_spec[name].create_model()

    def _measured_frequency(self, name: str) -> float | None:
        measured = self.input_parameters.get(name)
        if measured is None or measured.value is None:
            return None
        frequency = float(measured.value)
        return frequency if math.isfinite(frequency) and frequency > 0 else None

    def _harmonic_fit_frequency(self, measured_name: str, drive_name: str) -> float:
        measured = self._measured_frequency(measured_name)
        if measured is not None:
            return measured
        if self.input_parameters_from_snapshot:
            raise ValueError(f"the snapshot lacks a valid {measured_name} resonance")
        if drive_name in self.input_overrides:
            raise ValueError(f"{measured_name} is unavailable and {drive_name} was overridden")
        return self._get_calibration_value(drive_name)

    def _fit_harmonics(self, qid: str, fh_frequency: float) -> TransmonHarmonicsFit | None:
        try:
            run_logger = get_run_logger()
        except MissingContextError:
            run_logger = logger
        try:
            limit_name = "maximum_harmonic_fit_residual"
            raw_limit = self.run_parameters[limit_name].get_value()
            limit_error = finite_value_error(raw_limit, limit_name, minimum=0)
            if limit_error is not None:
                raise ValueError(limit_error)
            limit = float(raw_limit)
            fit = fit_transmon_harmonics(
                ge_frequency=self._harmonic_fit_frequency("qubit_frequency", "control_frequency"),
                ef_frequency=self._harmonic_fit_frequency("ef_frequency", "control_frequency_ef"),
                fh_frequency=fh_frequency,
            )
            if fit.active_bounds:
                run_logger.warning(
                    "Harmonic fit for qid=%s reached parameter bounds for %s",
                    qid,
                    ", ".join(fit.active_bounds),
                )
            if not fit.success:
                raise ValueError(fit.message)
            if fit.max_abs_residual > limit:
                raise ValueError(
                    f"maximum transition residual {fit.max_abs_residual:.6g} GHz "
                    f"exceeds the {limit:.6g} GHz limit"
                )
        except (ValueError, LinAlgError, OverflowError) as exc:
            run_logger.warning("Skipping transmon harmonic energies for qid=%s: %s", qid, exc)
            return None
        return fit

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = self.get_experiment(backend)
        label = exp.ctx.resolve_fh_label(self.get_qubit_label(backend, qid))
        result = run_result.raw_result
        frequency = result.data["resonant_frequencies"].get(label)
        ef_frequency = self._measured_frequency("ef_frequency")
        if ef_frequency is None:
            ef_frequency = self._get_calibration_value("control_frequency_ef")
        threshold = self.run_parameters["minimum_peak_background_rms_ratio"].get_value()
        threshold_error = finite_value_error(
            threshold, "minimum_peak_background_rms_ratio", minimum=0
        )
        frequency_error = finite_value_error(
            frequency, "fh_frequency", minimum=0, maximum=ef_frequency
        )
        if frequency_error is None and float(frequency) == 0:
            frequency_error = "fh_frequency must be positive"
        validation_error = first_validation_error(
            frequency_error,
            threshold_error,
            finite_value_error(
                result.data["peak_background_rms_ratios"].get(label),
                "FH chevron peak/background RMS ratio",
                minimum=threshold if threshold_error is None else None,
            ),
        )
        self.output_parameters["fh_frequency"].value = frequency
        declared_outputs = self.attach_execution_id(execution_id)
        output_parameters = {"fh_frequency": declared_outputs["fh_frequency"]}
        if validation_error is None:
            fit = self._fit_harmonics(qid, float(frequency))
            if fit is not None:
                for name, energy in (
                    ("charging_energy", fit.ec),
                    ("josephson_energy_first_harmonic", fit.ej1),
                    ("josephson_energy_second_harmonic", fit.ej2),
                ):
                    output_parameters[name] = declared_outputs[name].model_copy(
                        update={"value": energy}
                    )

        final_keys = (f"{label}_measurement", f"{label}_transform")
        figures = [result.figures[key] for key in final_keys if key in result.figures]
        figures.extend(figure for key, figure in result.figures.items() if key not in final_keys)
        return PostProcessResult(
            output_parameters=output_parameters,
            figures=figures,
            validation_error=validation_error,
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        require_fh_configuration(exp, label)
        control_amplitude = self._get_calibration_value("control_amplitude")
        exp.params.control_amplitude[label] = control_amplitude
        exp.params.readout_amplitude[label] = self._get_calibration_value("readout_amplitude")
        ge_frequency = self._get_calibration_value("control_frequency")
        ef_frequency = self._get_calibration_value("control_frequency_ef")
        configured_fh_frequency = exp.quantum_system.get_qubit(label).control_frequency_fh_value
        if configured_fh_frequency is not None and math.isfinite(configured_fh_frequency):
            fh_frequency = float(configured_fh_frequency)
        else:
            fh_frequency = 2 * ef_frequency - ge_frequency
        with exp.modified_frequencies(
            {
                exp.ctx.resolve_ge_label(label): ge_frequency,
                exp.ctx.resolve_ef_label(label): ef_frequency,
                exp.ctx.resolve_read_label(label): self._get_calibration_value("readout_frequency"),
            }
        ):
            result = estimate_fh_frequency_from_chevron_adaptive(
                exp=exp,
                targets=[label],
                frequencies={label: fh_frequency},
                amplitudes={label: control_amplitude / math.sqrt(3)},
                final_detuning_range=self.run_parameters["detuning_range"].get_value(),
                final_time_range=self.run_parameters["time_range"].get_value(),
                n_shots=self.run_parameters["shots"].get_value(),
                shot_interval=self.run_parameters["interval"].get_value(),
                plot=False,
                save_image=False,
            )
        return RunResult(raw_result=result)

    def batch_run(self, backend: QubexBackend, qids: list[str]) -> RunResult:
        raise NotImplementedError(f"{self.name} does not support batch execution")
