import copy
import logging
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np
from qubex.experiment.experiment_constants import DEFAULT_RABI_FREQUENCY
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend

if TYPE_CHECKING:
    import plotly.graph_objs as go

logger = logging.getLogger(__name__)


class CheckControlAmplitude(QubexTask):
    """Task to estimate the control amplitude.

    Sweeps the drive frequency around the calibrated qubit frequency
    (``qubit_frequency`` ± ``frequency_span``) and fits a sqrt-Lorentzian
    to scale the drive amplitude so that the resulting Rabi rate matches
    ``target_rabi_rate``.
    """

    name: str = "CheckControlAmplitude"
    task_type: str = "qubit"
    timeout: int = 60 * 60
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        # Coarse f01 from CheckQubitSpectroscopy (5 MHz grid). The sqrt-Lorentzian
        # fit refines this to sub-MHz precision and writes back coarse_qubit_frequency.
        "coarse_qubit_frequency": None,
        "readout_frequency": None,  # Load from DB
        "readout_amplitude": None,  # Load from DB
        # Seed drive amplitude. Comes from CheckQubitSpectroscopy and is the
        # threshold amplitude where f01 first appears in the spectroscopy heatmap
        # — NOT a Rabi-rate-derived control_amplitude.
        "coarse_control_amplitude": None,
    }
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "frequency_span": RunParameterModel(
            unit="GHz",
            value_type="float",
            value=0.15,
            description="Half-span around qubit_frequency for the sweep (±span, default ±150 MHz)",
        ),
        "frequency_step": RunParameterModel(
            unit="GHz",
            value_type="float",
            value=0.0025,
            description="Frequency step (default 2.5 MHz, ~120 points over ±150 MHz)",
        ),
        "readout_amplitude": RunParameterModel(
            unit="a.u.",
            value_type="float",
            value=0.04,
            description=(
                "Readout amplitude used during the sweep. Matches the "
                "CheckQubitSpectroscopy default so the qubit response is "
                "probed under the same readout conditions."
            ),
        ),
        "target_rabi_rate": RunParameterModel(
            unit="GHz",
            value_type="float",
            value=DEFAULT_RABI_FREQUENCY,
            description="Target Rabi rate used to scale the estimated control amplitude",
        ),
        "shots": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=8192,
            description=(
                "Number of shots per frequency point. Higher than the usual "
                "CALIBRATION_SHOTS (2048) because this is a 1D scan and the "
                "phase response can still be small near the spectroscopy-derived "
                "seed amplitude — extra averaging is needed to get the signal "
                "above the noise floor for a stable sqrt-Lorentzian fit."
            ),
        ),
        "interval": RunParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Shot interval",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "control_amplitude": ParameterModel(
            unit="a.u.",
            description="Estimated control amplitude scaled to target Rabi rate",
        ),
        "coarse_control_amplitude": ParameterModel(
            unit="a.u.",
            description=(
                "Refined coarse drive-amplitude seed for downstream chevron tasks. "
                "Still a coarse calibration value, but improved over the spectroscopy seed."
            ),
        ),
        "coarse_qubit_frequency": ParameterModel(
            unit="GHz",
            description=(
                "Refined f01 estimate from the bounded sqrt-Lorentzian fit "
                "(better than the spectroscopy 5 MHz grid, but still NOT a "
                "calibrated qubit_frequency — that comes from CheckCoarseChevron's "
                "Rabi-detuning fit)."
            ),
        ),
    }

    def _build_frequency_range(self, qubit_frequency: float) -> Any:
        span = float(self.run_parameters["frequency_span"].get_value())
        step = float(self.run_parameters["frequency_step"].get_value())
        return np.arange(qubit_frequency - span, qubit_frequency + span, step)

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result[label]

        estimated_amplitude = result.get("estimated_amplitude")
        rabi_rate = result.get("rabi_rate")
        f0 = result.get("f0")
        r2 = result.get("r2")
        fig: go.Figure | None = result.get("fig")

        figures: list[go.Figure] = []
        if fig is not None:
            figures.append(fig)

        output_params_copy = copy.deepcopy(self.output_parameters)
        coarse_input_param = self.input_parameters["coarse_control_amplitude"]
        coarse_floor = (
            float(coarse_input_param.value)
            if coarse_input_param is not None and coarse_input_param.value is not None
            else None
        )
        coarse_frequency_param = self.input_parameters["coarse_qubit_frequency"]
        coarse_frequency = (
            float(coarse_frequency_param.value)
            if coarse_frequency_param is not None and coarse_frequency_param.value is not None
            else None
        )
        if estimated_amplitude is not None:
            calibrated_amplitude = float(estimated_amplitude)
            if coarse_floor is not None and calibrated_amplitude < coarse_floor:
                print(
                    f"Estimated control amplitude for qid={qid} was below "
                    f"coarse_control_amplitude; using floor {coarse_floor:.6f} a.u. "
                    f"instead of {calibrated_amplitude:.6f} a.u."
                )
                calibrated_amplitude = coarse_floor
            output_params_copy["control_amplitude"].value = calibrated_amplitude
            output_params_copy["coarse_control_amplitude"].value = calibrated_amplitude
            rabi_rate_msg = (
                f", rabi_rate={float(rabi_rate) * 1e3:.3f} MHz" if rabi_rate is not None else ""
            )
            print(
                f"Estimated control amplitude for qid={qid}: "
                f"{calibrated_amplitude:.6f} a.u.{rabi_rate_msg}"
            )
        else:
            print(
                f"[WARNING] Failed to estimate control amplitude for qid={qid}: "
                "sqrt-Lorentzian fit did not converge; propagating spectroscopy coarse values"
            )
            if coarse_floor is not None:
                output_params_copy["control_amplitude"].value = coarse_floor
                output_params_copy["coarse_control_amplitude"].value = coarse_floor
            if coarse_frequency is not None:
                output_params_copy["coarse_qubit_frequency"].value = coarse_frequency

        # Refine coarse_qubit_frequency from the bounded sqrt-Lorentzian fit center.
        # The fit's f0 is constrained to [sweep_min, sweep_max] (see
        # qubex/analysis/fitting.py:1318-1322), so we never extrapolate outside
        # the sweep — unlike fit_detuned_rabi.
        if f0 is not None:
            output_params_copy["coarse_qubit_frequency"].value = float(f0)
            r2_msg = f", R²={float(r2):.3f}" if r2 is not None else ""
            print(f"Refined coarse_qubit_frequency for qid={qid}: {float(f0):.6f} GHz{r2_msg}")

        for value in output_params_copy.values():
            value.execution_id = execution_id

        return PostProcessResult(
            output_parameters=output_params_copy,
            figures=figures,
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        resonator_label = self.get_resonator_label(backend, qid)

        qubit_freq_param = self.input_parameters["coarse_qubit_frequency"]
        readout_freq_param = self.input_parameters["readout_frequency"]
        seed_amp_param = self.input_parameters["coarse_control_amplitude"]
        if qubit_freq_param is None or qubit_freq_param.value is None:
            raise ValueError("coarse_qubit_frequency input parameter is required")
        if readout_freq_param is None or readout_freq_param.value is None:
            raise ValueError("readout_frequency input parameter is required")
        if seed_amp_param is None or seed_amp_param.value is None:
            raise ValueError("coarse_control_amplitude input parameter is required")

        qubit_frequency = float(qubit_freq_param.value)
        readout_frequency = float(readout_freq_param.value)
        readout_amplitude = self._get_readout_amplitude_value()
        coarse_control_amplitude = float(seed_amp_param.value)
        frequency_range = self._build_frequency_range(qubit_frequency)

        print(
            f"[run] CheckControlAmplitude params for {label}: "
            f"qubit_frequency={qubit_frequency:.6f} GHz, "
            f"sweep=[{frequency_range[0]:.6f}, {frequency_range[-1]:.6f}] GHz "
            f"({len(frequency_range)} points), "
            f"coarse_control_amplitude={coarse_control_amplitude:.6f}, "
            f"readout_frequency={readout_frequency:.6f} GHz, "
            f"readout_amplitude={readout_amplitude:.6f}"
        )

        # `measure_qubit_resonance` does not accept readout_frequency, so we
        # apply it via the modified_frequencies context manager.
        # Note: we use measure_qubit_resonance (not the deprecated
        # estimate_control_amplitude) because it applies np.unwrap to the
        # phases before fitting — the deprecated version fits raw phases that
        # wrap at ±π near resonance, which makes fit_sqrt_lorentzian unstable
        # (e.g. R²≈0 with nonsensical Omega).
        with exp.modified_frequencies({resonator_label: readout_frequency}):
            result = exp.measure_qubit_resonance(
                label,
                frequency_range=frequency_range,
                control_amplitude=coarse_control_amplitude,
                readout_amplitude=readout_amplitude,
                target_rabi_rate=float(self.run_parameters["target_rabi_rate"].get_value()),
                n_shots=int(self.run_parameters["shots"].get_value()),
                shot_interval=float(self.run_parameters["interval"].get_value()),
            )

        self.save_calibration(backend)
        return RunResult(raw_result={label: result})
