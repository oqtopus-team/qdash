import copy
import logging
import math
from typing import TYPE_CHECKING, Any, ClassVar

from qdash.common.visualization.figure_metadata import set_figure_role
from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
)
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
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "readout_frequency": InputParameterSpec.required_database(),
        "readout_amplitude": InputParameterSpec.required_database(),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "frequency_range": RunParameterSpec(
            unit="GHz",
            value_type="np.arange",
            default=None,
            description=(
                "Frequency range as [start, stop, step] in GHz. Leave blank to use "
                "the connected control box default. Examples: low band "
                "[3.0, 5.75, 0.005], high band [6.5, 9.75, 0.005]."
            ),
        ),
        "readout_amplitude": RunParameterSpec(
            unit="a.u.",
            value_type="float",
            default=0.04,
            description="Readout amplitude used during the qubit spectroscopy sweep",
        ),
    }
    _analysis_config: ClassVar[EstimateQubitFrequencyConfig] = EstimateQubitFrequencyConfig()
    _retry_with_trim: ClassVar[bool] = True
    _seed_amplitude_headroom_db: ClassVar[float] = 10.0
    _max_coarse_control_amplitude: ClassVar[float] = 1.0
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "coarse_qubit_frequency": OutputParameterSpec(
            unit="GHz",
            description=(
                "Coarse f01 estimate from spectroscopy (5 MHz grid). NOT a calibrated "
                "qubit_frequency (those come from a Rabi-detuning fit such as "
                "CheckChevron); this is intended as a seed for downstream "
                "frequency-refinement tasks."
            ),
        ),
        "anharmonicity": OutputParameterSpec(
            unit="GHz",
            description="Anharmonicity alpha = f12 - f01 (typically negative for transmon)",
        ),
        "f01_repr_db": OutputParameterSpec(
            unit="dB",
            description=(
                "Representative power level of the detected f01 peak; "
                "the y-row at which the f01 mountain first develops a non-trivial width."
            ),
        ),
        "f01_quality_level": OutputParameterSpec(
            unit="a.u.",
            description=(
                "Discrete quality score (0..len(f01_moment_thresholds)) for the "
                "detected f01 peak. Higher = more confident."
            ),
        ),
        "coarse_control_amplitude": OutputParameterSpec(
            unit="a.u.",
            description=(
                "Coarse drive-amplitude threshold derived from f01_repr_db "
                "with an additional headroom uplift. NOT a calibrated "
                "control_amplitude (those come from a Rabi-rate-based fit such as "
                "CheckControlAmplitude); this is a spectroscopy-derived seed for "
                "downstream chevron/amplitude calibration."
            ),
        ),
    }

    def _compute_coarse_control_amplitude(self, repr_db: float) -> tuple[float, float]:
        raw_amplitude = float(10 ** (repr_db / 20))
        headroom_db = self._seed_amplitude_headroom_db
        max_amplitude = self._max_coarse_control_amplitude
        uplifted_amplitude = raw_amplitude * (10 ** (headroom_db / 20))
        coarse_control_amplitude = min(uplifted_amplitude, max_amplitude)
        marker_db = float(20 * math.log10(coarse_control_amplitude))
        return coarse_control_amplitude, marker_db

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
            marked_fig, freq_result = estimate_and_mark_qubit_figure(
                raw_fig, self._analysis_config, retry_with_trim=self._retry_with_trim
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
                    f"[WARNING] Failed to detect qubit frequency for qid={qid}: no f01 peak found"
                )
        except Exception:
            logger.warning(
                "Failed to estimate qubit frequency for qid=%s",
                qid,
                exc_info=True,
            )

        # Return the marked figure first (annotated frequencies are the most
        # useful for review), then the raw figure.
        set_figure_role(raw_fig, "raw")
        figures: list[go.Figure] = []
        if marked_fig is not None:
            set_figure_role(marked_fig, "marked")
            figures.append(marked_fig)
        figures.append(raw_fig)

        # Create a deep copy of output_parameters to avoid sharing state
        output_params_copy = copy.deepcopy(self.output_parameters)
        output_params_copy["coarse_qubit_frequency"].value = estimated_frequency
        if estimated_anharmonicity is not None:
            output_params_copy["anharmonicity"].value = estimated_anharmonicity
        if estimated_repr_db is not None:
            output_params_copy["f01_repr_db"].value = estimated_repr_db
            coarse_control_amplitude, coarse_control_marker_db = (
                self._compute_coarse_control_amplitude(estimated_repr_db)
            )
            output_params_copy["coarse_control_amplitude"].value = coarse_control_amplitude
            if marked_fig is not None:
                marked_fig.add_hline(
                    y=coarse_control_marker_db,
                    line_width=1,
                    line_color="red",
                    line_dash="dash",
                    annotation_text=f"coarse A = {coarse_control_amplitude:.4f} a.u.",
                    annotation_position="top left",
                    annotation_font_color="red",
                )
            print(
                f"Coarse control amplitude for qid={qid}: "
                f"{coarse_control_amplitude:.6f} a.u. "
                f"(from f01_repr_db={estimated_repr_db:.2f} dB, "
                f"marker={coarse_control_marker_db:.2f} dB)"
            )
        if estimated_quality_level is not None:
            output_params_copy["f01_quality_level"].value = estimated_quality_level
        for value in output_params_copy.values():
            value.execution_id = execution_id

        # Validate qubit frequency range.
        # We still return figures so they are saved before the task is marked failed.
        # Invalid outputs are excluded so they are not persisted to the DB.
        if estimated_frequency < 2.5:
            error_msg = (
                f"Qubit frequency too low for qid={qid}: {estimated_frequency:.6f} GHz < 2.5 GHz"
            )
            print(f"[ERROR] {error_msg}")
            return PostProcessResult(
                output_parameters={},
                figures=figures,
                validation_error=error_msg,
            )

        return PostProcessResult(
            output_parameters=output_params_copy,
            figures=figures,
        )

    def _frequency_range(self) -> Any:
        """Return an explicit override, or let qubex select by control box type."""
        parameter = self.run_parameters["frequency_range"]
        return None if parameter.value is None else parameter.get_value()

    def resolve_run_parameters(self, backend: QubexBackend, qid: str) -> None:
        """Populate the effective device-specific sweep before it is recorded."""
        parameter = self.run_parameters["frequency_range"]
        if parameter.value is not None:
            return

        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        box = exp.ctx.experiment_system.get_control_box_for_qubit(label)
        parameter.value = tuple(box.traits.default_control_frequency_range)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)

        readout_freq_param = self.input_parameters["readout_frequency"]
        if readout_freq_param is None or readout_freq_param.value is None:
            raise ValueError("readout_frequency input parameter is required")

        with self._modified_qubit_readout_frequencies(
            exp,
            qubit_label=label,
            frequency_overrides={"R" + label: float(readout_freq_param.value)},
        ):
            result = exp.qubit_spectroscopy(
                label,
                frequency_range=self._frequency_range(),
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
        frequency_range = self._frequency_range()
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
