import copy
import logging
from typing import TYPE_CHECKING, Any, ClassVar

from qdash.analysis.spectroscopy import (
    NUM_RESONATORS,
    PEAK_POSITIONS,
    EstimateResonatorFrequencyConfig,
    create_bare_shift_boundary_estimator,
    create_marked_figure,
    estimate_resonator_frequency_from_figure,
)
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


class CheckResonatorSpectroscopy(QubexTask):
    """Task to check the resonator spectroscopy.

    This is a MUX-level task that performs spectroscopy on all resonators
    in a MUX simultaneously. The scheduler should execute this task once
    per MUX, and the result will be used by all qubits in that MUX.

    Note: task_type remains "qubit" for frontend compatibility, but
    is_mux_level=True indicates this task runs once per MUX.
    """

    name: str = "CheckResonatorSpectroscopy"
    task_type: str = "qubit"
    is_mux_level: bool = True
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {}
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "frequency_range": RunParameterModel(
            unit="GHz",
            value_type="np.arange",
            value=(9.75, 10.75, 0.002),
            description=(
                "Frequency range for resonator spectroscopy on the high band "
                "(64Q chips). Used when chip_id does not contain '144'."
            ),
        ),
        "frequency_range_low_band": RunParameterModel(
            unit="GHz",
            value_type="np.arange",
            value=(5.75, 6.75, 0.002),
            description=(
                "Frequency range for resonator spectroscopy on the low band "
                "(144Q chips). Used when chip_id contains '144'."
            ),
        ),
        "power_range": RunParameterModel(
            unit="dB",
            value_type="np.arange",
            value=(-60, 5, 5),
            description="Power range for resonator spectroscopy",
        ),
        "shots": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=1024,
            description="Number of shots for resonator spectroscopy",
        ),
        "num_resonators": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=NUM_RESONATORS,
            description="Number of resonators to detect",
        ),
        "high_power_min": RunParameterModel(
            unit="dB",
            value_type="float",
            value=-20.0,
            description="Minimum power for high-power peak detection",
        ),
        "high_power_max": RunParameterModel(
            unit="dB",
            value_type="float",
            value=0.0,
            description="Maximum power for high-power peak detection",
        ),
        "low_power": RunParameterModel(
            unit="dB",
            value_type="float",
            value=-30.0,
            description="Power level for low-power peak detection",
        ),
        "bare_shift_estimator_type": RunParameterModel(
            unit="",
            value_type="str",
            value="config",
            description=(
                "How to pick the bare-shift boundary. "
                "'config' uses high_power_min/max/low_power; "
                "'high_frequency_strength' detects it from the FFT of each row."
            ),
        ),
        "bare_shift_strength_limit": RunParameterModel(
            unit="a.u.",
            value_type="float",
            value=4.0,
            description=(
                "Maximum high-frequency FFT strength accepted as the bare-shift "
                "boundary. Only used when bare_shift_estimator_type="
                "'high_frequency_strength'."
            ),
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "readout_frequency": ParameterModel(
            unit="GHz", description="Estimated resonator frequency from spectroscopy"
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task.

        Returns two figures:
        1. Raw figure (original spectroscopy data)
        2. Marked figure (with detected resonances annotated)

        This method can be called for any qid in the MUX, and it will extract
        the appropriate resonator frequency based on the qid's position in the MUX.
        """
        result = run_result.raw_result
        raw_fig: go.Figure = result["fig"]

        # Estimate resonator frequency and create marked figure
        estimated_frequency = 0.0
        marked_fig = None
        try:
            config = EstimateResonatorFrequencyConfig(
                num_resonators=self.run_parameters["num_resonators"].get_value(),
                high_power_min=self.run_parameters["high_power_min"].get_value(),
                high_power_max=self.run_parameters["high_power_max"].get_value(),
                low_power=self.run_parameters["low_power"].get_value(),
            )

            estimator_type = self.run_parameters["bare_shift_estimator_type"].get_value()
            if estimator_type and estimator_type != "config":
                trace = raw_fig.data[0]
                estimator = create_bare_shift_boundary_estimator(
                    type=estimator_type,
                    args={
                        "strength_limit": self.run_parameters[
                            "bare_shift_strength_limit"
                        ].get_value(),
                    },
                )
                boundary = estimator.estimate_bare_shift_boundary(
                    list(trace.x), list(trace.y), list(trace.z)
                )
                config = config.with_boundary(boundary)
                print(
                    f"[BareShift] qid={qid} estimator={estimator_type} "
                    f"low={boundary.low_power} high=[{boundary.high_power_min}, "
                    f"{boundary.high_power_max}]"
                )

            resonances, rejected, frequencies = estimate_resonator_frequency_from_figure(
                raw_fig, config
            )
            marked_fig = create_marked_figure(raw_fig, resonances, rejected_resonances=rejected)

            if len(frequencies) == NUM_RESONATORS:
                # Get frequency for current qid based on its position in the MUX
                id_in_mux = int(qid) % 4
                resonance_index = PEAK_POSITIONS[id_in_mux]
                estimated_frequency = frequencies[resonance_index]
                # Use print for Prefect UI visibility (log_prints=True captures these)
                print(
                    f"Estimated resonator frequency for qid={qid}: "
                    f"{estimated_frequency:.6f} GHz (id_in_mux={id_in_mux}, "
                    f"all={[f'{f:.6f}' for f in frequencies]})"
                )
            else:
                print(
                    f"[WARNING] Failed to detect resonator frequency for qid={qid}: "
                    f"expected {NUM_RESONATORS} peaks, found {len(frequencies)}"
                )
        except Exception:
            logger.warning(
                "Failed to estimate resonator frequency for qid=%s",
                qid,
                exc_info=True,
            )

        # Return both raw and marked figures
        figures: list[go.Figure] = [raw_fig]
        if marked_fig is not None:
            figures.append(marked_fig)

        # Create a deep copy of output_parameters to avoid sharing state
        # between multiple qids (output_parameters is a ClassVar)
        output_params_copy = copy.deepcopy(self.output_parameters)
        output_params_copy["readout_frequency"].value = estimated_frequency
        for value in output_params_copy.values():
            value.execution_id = execution_id

        return PostProcessResult(
            output_parameters=output_params_copy,
            figures=figures,
        )

    def _select_frequency_range(self, backend: QubexBackend) -> Any:
        """Pick the resonator-spectroscopy frequency range for the current chip.

        144Q chips (low band, ~5.75-6.75 GHz) use ``frequency_range_low_band``;
        any other chip (64Q etc., high band ~9.75-10.75 GHz) uses
        ``frequency_range``. Selection follows the same convention used by the
        scheduler plugins (``"144" in chip_id``).
        """
        chip_id = backend.config.get("chip_id") or ""
        param_name = "frequency_range_low_band" if "144" in chip_id else "frequency_range"
        return self.run_parameters[param_name].get_value()

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        frequency_range = self._select_frequency_range(backend)
        result = exp.resonator_spectroscopy(
            target=label,
            frequency_range=frequency_range,
            power_range=self.run_parameters["power_range"].get_value(),
            n_shots=self.run_parameters["shots"].get_value(),
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)

    def batch_run(self, backend: QubexBackend, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits."""
        exp = self.get_experiment(backend)
        labels = [self.get_qubit_label(backend, qid) for qid in qids]
        frequency_range = self._select_frequency_range(backend)
        result = exp.resonator_spectroscopy(
            labels[0],
            frequency_range=frequency_range,
            power_range=self.run_parameters["power_range"].get_value(),
            n_shots=1024,
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)
