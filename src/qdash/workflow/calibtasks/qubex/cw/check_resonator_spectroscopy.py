from __future__ import annotations

import copy
import logging
import math
from typing import TYPE_CHECKING, Any, ClassVar

from qdash.analysis.spectroscopy import (
    NUM_RESONATORS,
    PEAK_POSITIONS,
    BareShiftBoundary,
    EstimateResonatorFrequencyConfig,
    RemoveFalseSpikeRange,
    create_bare_shift_boundary_estimator,
    create_marked_figure,
    estimate_local_bare_shift_boundary,
    estimate_minimum_usable_power,
    estimate_optimal_powers,
    estimate_resonator_frequency_from_figure,
    remove_false_spike_from_figure,
)
from qdash.common.visualization.figure_metadata import set_figure_role
from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask

if TYPE_CHECKING:
    import plotly.graph_objs as go

    from qdash.workflow.engine.backend.qubex import QubexBackend

logger = logging.getLogger(__name__)


def _guess_sorted_slots_for_partial_mux(
    xs: list[float],
    frequencies: list[float],
) -> tuple[list[int | None], str]:
    """Guess sorted-slot assignment when fewer than 4 resonator peaks are found."""
    count = len(frequencies)
    if count >= NUM_RESONATORS:
        return list(range(count)), "full"
    if count != 3:
        return [None] * count, "unassigned"

    left_gap = float(frequencies[1] - frequencies[0])
    right_gap = float(frequencies[2] - frequencies[1])
    min_gap = max(min(left_gap, right_gap), 1e-12)
    gap_ratio = max(left_gap, right_gap) / min_gap

    if gap_ratio >= 1.6:
        if left_gap > right_gap:
            return [0, 2, 3], "slot1-missing-large-left-gap"
        return [0, 1, 3], "slot2-missing-large-right-gap"

    scan_min = float(min(xs))
    scan_max = float(max(xs))
    scan_center = (scan_min + scan_max) / 2.0
    cluster_center = sum(frequencies) / len(frequencies)
    if cluster_center < scan_center:
        return [0, 1, 2], "right-edge-missing-cluster-left"
    return [1, 2, 3], "left-edge-missing-cluster-right"


def _qid_for_sorted_slot(mux_index: int, sorted_slot: int) -> int:
    inverse_peak_positions = {slot: pos for pos, slot in PEAK_POSITIONS.items()}
    return mux_index * NUM_RESONATORS + inverse_peak_positions[sorted_slot]


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
            value="high_frequency_strength",
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
        "minimum_usable_power_correlation_coefficient_min": RunParameterModel(
            unit="a.u.",
            value_type="float",
            value=0.9,
            description=(
                "Minimum adjacent-row correlation used to estimate the minimum "
                "usable power for optimal_power calculation."
            ),
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "readout_frequency": ParameterModel(
            unit="GHz", description="Estimated resonator frequency from spectroscopy"
        ),
        "optimal_power": ParameterModel(
            unit="dB",
            description=(
                "Estimated optimal readout power from the minimum usable power "
                "and local bare-shift boundary."
            ),
        ),
        "readout_amplitude": ParameterModel(
            unit="a.u.",
            description=(
                "Readout amplitude converted from optimal_power "
                "(amplitude = 10**(optimal_power/20))."
            ),
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
        analysis_fig = self._prepare_analysis_figure(raw_fig)

        # Estimate resonator frequency and create marked figure
        estimated_frequency = 0.0
        optimal_power: float | None = None
        readout_amplitude: float | None = None
        minimum_usable_power: float | None = None
        local_boundaries: list[BareShiftBoundary] | None = None
        optimal_powers: list[float] | None = None
        marked_fig = None
        try:
            config = EstimateResonatorFrequencyConfig(
                num_resonators=self.run_parameters["num_resonators"].get_value(),
                high_power_min=self.run_parameters["high_power_min"].get_value(),
                high_power_max=self.run_parameters["high_power_max"].get_value(),
                low_power=self.run_parameters["low_power"].get_value(),
                minimum_usable_power_correlation_coefficient_min=self.run_parameters[
                    "minimum_usable_power_correlation_coefficient_min"
                ].get_value(),
            )
            boundary = BareShiftBoundary(
                low_power=config.low_power,
                high_power_min=config.high_power_min,
                high_power_max=config.high_power_max,
            )

            estimator_type = self.run_parameters["bare_shift_estimator_type"].get_value()
            if estimator_type and estimator_type != "config":
                trace = analysis_fig.data[0]
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
                analysis_fig, config
            )
            trace = analysis_fig.data[0]
            ys = list(trace.y)
            zs = list(trace.z)
            minimum_usable_power = estimate_minimum_usable_power(
                ys,
                zs,
                boundary.low_power,
                correlation_coefficient_min=(
                    config.minimum_usable_power_correlation_coefficient_min
                ),
            )
            local_boundaries = [
                estimate_local_bare_shift_boundary(ys, resonance)
                for resonance in resonances + rejected
            ]
            selected_local_boundaries = local_boundaries[: len(resonances)]
            optimal_powers = estimate_optimal_powers(
                ys,
                selected_local_boundaries,
                minimum_usable_power,
            )
            marked_fig = create_marked_figure(
                analysis_fig,
                resonances,
                local_boundaries=selected_local_boundaries,
                optimal_powers=optimal_powers,
            )

            id_in_mux = int(qid) % 4
            sorted_slots, assignment_mode = _guess_sorted_slots_for_partial_mux(
                list(trace.x),
                frequencies,
            )
            if marked_fig is not None:
                for sorted_slot, frequency in zip(sorted_slots, frequencies, strict=False):
                    if sorted_slot is None:
                        continue
                    marked_fig.add_annotation(
                        x=frequency,
                        y=1.02,
                        yref="paper",
                        text=f"Q{_qid_for_sorted_slot(int(qid) // NUM_RESONATORS, sorted_slot):02d} / s{sorted_slot}",
                        showarrow=False,
                        font={"color": "red", "size": 11},
                        align="center",
                    )
                if assignment_mode != "full":
                    marked_fig.add_annotation(
                        xref="paper",
                        yref="paper",
                        x=0.01,
                        y=1.08,
                        text=assignment_mode,
                        showarrow=False,
                        font={"color": "red", "size": 11},
                        align="left",
                    )
            assigned_slot = PEAK_POSITIONS[id_in_mux]
            resonance_index = (
                sorted_slots.index(assigned_slot) if assigned_slot in sorted_slots else None
            )
            if resonance_index is not None and resonance_index < len(optimal_powers):
                estimated_frequency = frequencies[resonance_index]
                optimal_power = optimal_powers[resonance_index]
                readout_amplitude = float(10 ** (optimal_power / 20))
                # Use print for Prefect UI visibility (log_prints=True captures these)
                print(
                    f"Estimated resonator frequency for qid={qid}: "
                    f"{estimated_frequency:.6f} GHz (id_in_mux={id_in_mux}, "
                    f"assigned_slot={assigned_slot}, "
                    f"assignment_mode={assignment_mode}, "
                    f"optimal_power={optimal_power:.2f} dB, "
                    f"readout_amplitude={readout_amplitude:.6f} a.u., "
                    f"all={[f'{f:.6f}' for f in frequencies]})"
                )
            else:
                print(
                    f"[WARNING] Failed to detect resonator frequency for qid={qid}: "
                    f"assigned slot {assigned_slot} unavailable "
                    f"(mode={assignment_mode}, found {len(frequencies)}/{NUM_RESONATORS} peaks)"
                )
        except Exception:
            logger.warning(
                "Failed to estimate resonator frequency for qid=%s",
                qid,
                exc_info=True,
            )

        # Return the marked figure first (annotated resonances are the most
        # useful for review), then the raw figure.
        set_figure_role(raw_fig, "raw")
        figures: list[go.Figure] = []
        if marked_fig is not None:
            set_figure_role(marked_fig, "marked")
            figures.append(marked_fig)
        figures.append(raw_fig)

        # Create a deep copy of output_parameters to avoid sharing state
        # between multiple qids (output_parameters is a ClassVar)
        output_params_copy = copy.deepcopy(self.output_parameters)
        output_params_copy["readout_frequency"].value = estimated_frequency
        if optimal_power is not None:
            output_params_copy["optimal_power"].value = optimal_power
        if readout_amplitude is not None:
            output_params_copy["readout_amplitude"].value = readout_amplitude
        for value in output_params_copy.values():
            value.execution_id = execution_id

        error_msg: str | None = None
        if not math.isfinite(estimated_frequency) or estimated_frequency <= 0.0:
            error_msg = f"Invalid resonator frequency for qid={qid}: {estimated_frequency:.6f} GHz"
        elif optimal_power is None or not math.isfinite(optimal_power):
            error_msg = f"Invalid optimal_power for qid={qid}: {optimal_power}"
        elif (
            readout_amplitude is None
            or not math.isfinite(readout_amplitude)
            or readout_amplitude <= 0.0
        ):
            error_msg = f"Invalid readout_amplitude for qid={qid}: {readout_amplitude}"

        if error_msg is not None:
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

    def _prepare_analysis_figure(self, raw_fig: go.Figure) -> go.Figure:
        """Apply script-compatible denoising to a copy of the raw figure."""
        import plotly.graph_objects as pgo

        analysis_fig = pgo.Figure(raw_fig)
        trace = analysis_fig.data[0]
        xs = list(trace.x)
        if not xs:
            return analysis_fig

        spike_ranges = (
            [
                RemoveFalseSpikeRange(5.998, 6.000),
                RemoveFalseSpikeRange(6.498, 6.500),
            ]
            if max(xs) < 7.0
            else [
                RemoveFalseSpikeRange(9.998, 10.000),
                RemoveFalseSpikeRange(10.248, 10.250),
                RemoveFalseSpikeRange(10.498, 10.500),
            ]
        )
        return remove_false_spike_from_figure(analysis_fig, spike_ranges)

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
