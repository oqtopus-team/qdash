import copy
import logging
from typing import TYPE_CHECKING, ClassVar

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
    }
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
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
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "qubit_frequency": ParameterModel(
            unit="GHz", description="Estimated qubit frequency (f01) from spectroscopy"
        ),
        "anharmonicity": ParameterModel(
            unit="GHz",
            description="Anharmonicity alpha = f12 - f01 (typically negative for transmon)",
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
            marked_fig, freq_result = estimate_and_mark_qubit_figure(raw_fig, config)

            if freq_result.f01 is not None:
                estimated_frequency = freq_result.f01.frequency
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
        output_params_copy["qubit_frequency"].value = estimated_frequency
        if estimated_anharmonicity is not None:
            output_params_copy["anharmonicity"].value = estimated_anharmonicity
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

        readout_freq_param = self.input_parameters["readout_frequency"]
        if readout_freq_param is None:
            raise ValueError("readout_frequency input parameter is required")

        result = exp.qubit_spectroscopy(
            label,
            readout_amplitude=0.01,
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
        results = {}
        for label in labels:
            result = exp.qubit_spectroscopy(label)
            results[label] = result
        self.save_calibration(backend)
        return RunResult(raw_result=results)
