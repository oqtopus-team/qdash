import copy
import logging
from typing import TYPE_CHECKING, Any, ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.analysis import (
    EstimateQubitFrequencyConfig,
    estimate_and_mark_qubit_figure,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend

if TYPE_CHECKING:
    import plotly.graph_objs as go

logger = logging.getLogger(__name__)


class CheckQubitSpectroscopy(QubexTask):
    """Task to check the qubit frequencies.

    This task performs qubit spectroscopy and estimates the qubit frequency (f01)
    and optionally the f12 transition frequency from the spectroscopy data.
    """

    name: str = "CheckQubitSpectroscopy"
    task_type: str = "qubit"
    timeout: int = 60 * 120
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        "readout_frequency": None,  # Load from DB
        "readout_amplitude": None,  # Load from DB
    }
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "frequency_range": RunParameterModel(
            unit="GHz",
            value_type="np.arange",
            value=(6.5, 9.75, 0.005),
            description=(
                "Frequency range for qubit spectroscopy on the high band "
                "(64Q chips). Used when chip_id does not contain '144'."
            ),
        ),
        "frequency_range_low_band": RunParameterModel(
            unit="GHz",
            value_type="np.arange",
            value=(3.0, 5.75, 0.005),
            description=(
                "Frequency range for qubit spectroscopy on the low band "
                "(144Q chips). Used when chip_id contains '144'."
            ),
        ),
        "readout_amplitude": RunParameterModel(
            unit="a.u.",
            value_type="float",
            value=0.04,
            description="Readout amplitude used during the qubit spectroscopy sweep",
        ),
        "binarize_threshold_sigma_plus": RunParameterModel(
            unit="a.u.",
            value_type="float",
            value=3.0,
            description="Positive threshold for binarization (in sigma units)",
        ),
        "binarize_threshold_sigma_minus": RunParameterModel(
            unit="a.u.",
            value_type="float",
            value=-2.0,
            description="Negative threshold for binarization (in sigma units)",
        ),
        "top_power": RunParameterModel(
            unit="dB",
            value_type="float",
            value=0.0,
            description="Reference power for height and moment calculation (should be > max(ys))",
        ),
        "f01_height_min": RunParameterModel(
            unit="dB",
            value_type="float",
            value=14.9,
            description="Minimum height for f01 peak detection (in dB)",
        ),
        "f12_distance_min": RunParameterModel(
            unit="GHz",
            value_type="float",
            value=0.125,
            description="Minimum distance from f01 for f12 detection (in GHz)",
        ),
        "f12_distance_max": RunParameterModel(
            unit="GHz",
            value_type="float",
            value=0.5,
            description="Maximum distance from f01 for f12 detection (in GHz)",
        ),
        "f12_height_min": RunParameterModel(
            unit="dB",
            value_type="float",
            value=14.9,
            description="Minimum height for f12 peak detection (in dB)",
        ),
        "retry_with_trim": RunParameterModel(
            unit="",
            value_type="str",
            value="false",
            description=(
                "If 'true', drop the highest-power row and retry when no f01 is "
                "detected on the first pass. Useful when the top row is noisy."
            ),
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "coarse_qubit_frequency": ParameterModel(
            unit="GHz",
            description=(
                "Coarse f01 estimate from spectroscopy (5 MHz grid). NOT a calibrated "
                "qubit_frequency (those come from a Rabi-detuning fit such as "
                "CheckCoarseChevron); this is intended as a seed for downstream "
                "frequency-refinement tasks."
            ),
        ),
        "anharmonicity": ParameterModel(
            unit="GHz",
            description="Anharmonicity alpha = f12 - f01 (typically negative for transmon)",
        ),
        "f01_repr_db": ParameterModel(
            unit="dB",
            description=(
                "Representative power level of the detected f01 peak; "
                "the y-row at which the f01 mountain first develops a non-trivial width."
            ),
        ),
        "f01_quality_level": ParameterModel(
            unit="a.u.",
            description=(
                "Discrete quality score (0..len(f01_moment_thresholds)) for the "
                "detected f01 peak. Higher = more confident."
            ),
        ),
        "coarse_control_amplitude": ParameterModel(
            unit="a.u.",
            description=(
                "Coarse drive-amplitude threshold derived from f01_repr_db "
                "(amplitude = 10**(repr_db/20)). NOT a calibrated control_amplitude "
                "(those come from a Rabi-rate-based fit such as CheckControlAmplitude); "
                "this is the lowest drive amplitude at which the f01 peak first "
                "appears, intended as a seed for downstream amplitude calibration."
            ),
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task.

        Returns two figures:
        1. Raw figure (original spectroscopy data)
        2. Marked figure (with detected frequencies annotated)
        """
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        raw_fig: go.Figure = result[label]["fig"]

        # Estimate qubit frequency and create marked figure
        estimated_frequency = 0.0
        estimated_anharmonicity: float | None = None
        estimated_repr_db: float | None = None
        estimated_quality_level: int | None = None
        marked_fig = None
        try:
            config = EstimateQubitFrequencyConfig(
                binarize_threshold_sigma_plus=self.run_parameters[
                    "binarize_threshold_sigma_plus"
                ].get_value(),
                binarize_threshold_sigma_minus=self.run_parameters[
                    "binarize_threshold_sigma_minus"
                ].get_value(),
                top_power=self.run_parameters["top_power"].get_value(),
                f01_height_min=self.run_parameters["f01_height_min"].get_value(),
                f12_distance_min=self.run_parameters["f12_distance_min"].get_value(),
                f12_distance_max=self.run_parameters["f12_distance_max"].get_value(),
                f12_height_min=self.run_parameters["f12_height_min"].get_value(),
            )
            retry_flag = (
                str(self.run_parameters["retry_with_trim"].get_value()).strip().lower() == "true"
            )
            marked_fig, freq_result = estimate_and_mark_qubit_figure(
                raw_fig, config, retry_with_trim=retry_flag
            )

            if freq_result.f01 is not None:
                estimated_frequency = freq_result.f01.frequency
                estimated_repr_db = freq_result.f01.repr_db
                estimated_quality_level = freq_result.f01.quality_level
                quality_level = freq_result.f01.quality_level

                # Use print for Prefect UI visibility (log_prints=True captures these)
                if quality_level <= 2:
                    print(
                        f"[WARNING] Low quality qubit frequency for qid={qid}: "
                        f"f01={estimated_frequency:.6f} GHz (quality_level={quality_level}/5)"
                    )
                else:
                    print(
                        f"Estimated qubit frequency for qid={qid}: "
                        f"f01={estimated_frequency:.6f} GHz (quality_level={quality_level}/5)"
                    )

                if freq_result.f12 is not None:
                    print(
                        f"Estimated f12 frequency for qid={qid}: "
                        f"{freq_result.f12.frequency:.6f} GHz"
                    )
                    # Calculate anharmonicity: α = f12 - f01
                    estimated_anharmonicity = freq_result.anharmonicity
                    if estimated_anharmonicity is not None:
                        print(
                            f"Estimated anharmonicity for qid={qid}: "
                            f"{estimated_anharmonicity:.6f} GHz ({estimated_anharmonicity * 1000:.1f} MHz)"
                        )
            else:
                print(
                    f"[WARNING] Failed to detect qubit frequency for qid={qid}: "
                    "no f01 peak found"
                )
        except Exception:
            logger.warning(
                "Failed to estimate qubit frequency for qid=%s",
                qid,
                exc_info=True,
            )

        # Return both raw and marked figures
        figures: list[go.Figure] = [raw_fig]
        if marked_fig is not None:
            figures.append(marked_fig)

        # Create a deep copy of output_parameters to avoid sharing state
        output_params_copy = copy.deepcopy(self.output_parameters)
        output_params_copy["coarse_qubit_frequency"].value = estimated_frequency
        if estimated_anharmonicity is not None:
            output_params_copy["anharmonicity"].value = estimated_anharmonicity
        if estimated_repr_db is not None:
            output_params_copy["f01_repr_db"].value = estimated_repr_db
            # Coarse drive amplitude from the lowest power where the f01 peak
            # first appears. qubit_spectroscopy uses
            #   amplitude = sqrt(10**(power_db/10)) = 10**(power_db/20)
            # to map its dB y-axis to the drive amplitude, so we invert that.
            coarse_control_amplitude = float(10 ** (estimated_repr_db / 20))
            output_params_copy["coarse_control_amplitude"].value = coarse_control_amplitude
            print(
                f"Coarse control amplitude for qid={qid}: "
                f"{coarse_control_amplitude:.6f} a.u. "
                f"(from f01_repr_db={estimated_repr_db:.2f} dB)"
            )
        if estimated_quality_level is not None:
            output_params_copy["f01_quality_level"].value = estimated_quality_level
        for value in output_params_copy.values():
            value.execution_id = execution_id

        # Validate qubit frequency range.
        # We still return figures so they are saved before the task is marked failed.
        if estimated_frequency < 3.0:
            error_msg = (
                f"Qubit frequency too low for qid={qid}: "
                f"{estimated_frequency:.6f} GHz < 3.0 GHz"
            )
            print(f"[ERROR] {error_msg}")
            return PostProcessResult(
                output_parameters=output_params_copy,
                figures=figures,
                validation_error=error_msg,
            )

        return PostProcessResult(
            output_parameters=output_params_copy,
            figures=figures,
        )

    def _select_frequency_range(self, backend: QubexBackend) -> Any:
        """Pick the qubit-spectroscopy frequency range for the current chip.

        144Q chips use ``frequency_range_low_band`` (~3.0-5.75 GHz); other
        chips (64Q etc.) use ``frequency_range`` (~6.5-9.75 GHz). Same
        ``"144" in chip_id`` convention as the resonator task and the
        scheduler plugins.
        """
        chip_id = backend.config.get("chip_id") or ""
        param_name = "frequency_range_low_band" if "144" in chip_id else "frequency_range"
        return self.run_parameters[param_name].get_value()

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)

        readout_freq_param = self.input_parameters["readout_frequency"]
        if readout_freq_param is None:
            raise ValueError("readout_frequency input parameter is required")

        result = exp.qubit_spectroscopy(
            label,
            frequency_range=self._select_frequency_range(backend),
            readout_amplitude=self._get_readout_amplitude_value(),
            readout_frequency=readout_freq_param.value,
        )

        self.save_calibration(backend)

        return RunResult(raw_result={label: result})

    def batch_run(self, backend: QubexBackend, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits.

        Note: batch_run does not support parameter overrides via task_details.
        Use individual run() calls if you need per-qubit parameter customization.
        """
        exp = self.get_experiment(backend)
        labels = [self.get_qubit_label(backend, qid) for qid in qids]
        frequency_range = self._select_frequency_range(backend)
        readout_amplitude = self.run_parameters["readout_amplitude"].get_value()
        results = {}
        for label in labels:
            result = exp.qubit_spectroscopy(
                label,
                frequency_range=frequency_range,
                readout_amplitude=readout_amplitude,
            )
            results[label] = result
        self.save_calibration(backend)
        return RunResult(raw_result=results)
