from __future__ import annotations

import copy
import logging
import math
from typing import TYPE_CHECKING, Any, ClassVar

from qdash.analysis.spectroscopy import (
    NUM_RESONATORS,
    BareShiftBoundary,
    EstimateResonatorFrequencyConfig,
    RemoveFalseSpikeRange,
    create_bare_shift_boundary_estimator,
    create_marked_figure,
    estimate_local_bare_shift_boundary,
    estimate_minimum_usable_power,
    estimate_optimal_powers,
    estimate_resonator_frequency_from_figure,
    guess_sorted_slots_for_partial_mux,
    peak_positions_from_assignment_order,
    qid_for_sorted_slot,
    remove_false_spike_from_figure,
)
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
from qdash.workflow.calibtasks.qubex.base import QubexTask

if TYPE_CHECKING:
    import plotly.graph_objs as go

    from qdash.workflow.engine.backend.qubex import QubexBackend

logger = logging.getLogger(__name__)

_guess_sorted_slots_for_partial_mux = guess_sorted_slots_for_partial_mux
_qid_for_sorted_slot = qid_for_sorted_slot
_peak_positions_from_assignment_order = peak_positions_from_assignment_order


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
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {}
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "frequency_range": RunParameterSpec(
            unit="GHz",
            value_type="np.arange",
            default=None,
            description=(
                "Frequency range as [start, stop, step] in GHz. Leave blank to use "
                "the connected readout box default. Examples: low band "
                "[5.75, 6.75, 0.002], high band [9.75, 10.75, 0.002]."
            ),
        ),
        "power_range": RunParameterSpec(
            unit="dB",
            value_type="np.arange",
            default=(-60, 5, 5),
            description="Power range for resonator spectroscopy",
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=1024,
            description="Number of shots for resonator spectroscopy",
        ),
        "resonator_assignment_order": RunParameterSpec(
            unit="",
            value_type="list",
            default=[3, 0, 2, 1],
            description=(
                "Qubit offsets in increasing resonator-frequency order. "
                "Must contain each offset from 0 to 3 exactly once."
            ),
        ),
    }
    _analysis_config: ClassVar[EstimateResonatorFrequencyConfig] = (
        EstimateResonatorFrequencyConfig()
    )
    _bare_shift_estimator_type: ClassVar[str] = "high_frequency_strength"
    _bare_shift_strength_limit: ClassVar[float] = 4.0
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "readout_frequency": OutputParameterSpec(
            unit="GHz", description="Estimated resonator frequency from spectroscopy"
        ),
        "optimal_power": OutputParameterSpec(
            unit="dB",
            description=(
                "Estimated optimal readout power from the minimum usable power "
                "and local bare-shift boundary."
            ),
        ),
        "readout_amplitude": OutputParameterSpec(
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
        analysis_error: str | None = None
        assignment_error: str | None = None
        try:
            config = self._analysis_config
            boundary = BareShiftBoundary(
                low_power=config.low_power,
                high_power_min=config.high_power_min,
                high_power_max=config.high_power_max,
            )

            estimator_type = self._bare_shift_estimator_type
            if estimator_type and estimator_type != "config":
                trace = analysis_fig.data[0]
                estimator = create_bare_shift_boundary_estimator(
                    type=estimator_type,
                    args={"strength_limit": self._bare_shift_strength_limit},
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
            assignment_order = self._resonator_assignment_order()
            peak_positions = peak_positions_from_assignment_order(assignment_order)
            sorted_slots, assignment_mode = guess_sorted_slots_for_partial_mux(
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
                        text=(
                            f"Q{qid_for_sorted_slot(int(qid) // NUM_RESONATORS, sorted_slot, peak_positions):02d} "
                            f"/ s{sorted_slot}"
                        ),
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
            assigned_slot = peak_positions[id_in_mux]
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
                assignment_error = (
                    f"Resonator assignment failed for qid={qid}: "
                    f"assignment_order={list(assignment_order)}, "
                    f"assigned_slot={assigned_slot}, detected_slots={sorted_slots}, "
                    f"mode={assignment_mode}, "
                    f"detected_frequencies={[float(frequency) for frequency in frequencies]}"
                )
                print(f"[WARNING] {assignment_error}")
        except Exception as exc:
            analysis_error = f"Resonator analysis failed for qid={qid}: {type(exc).__name__}: {exc}"
            print(f"[ERROR] {analysis_error}")
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
        if analysis_error is not None:
            error_msg = analysis_error
        elif assignment_error is not None:
            error_msg = assignment_error
        elif not math.isfinite(estimated_frequency) or estimated_frequency <= 0.0:
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
        rounded_xs = {f"{x:.3f}": index for index, x in enumerate(xs)}
        applicable_ranges = []
        for spike_range in spike_ranges:
            idx_min = rounded_xs.get(f"{spike_range.x_min:.3f}")
            idx_max = rounded_xs.get(f"{spike_range.x_max:.3f}")
            if idx_min not in (None, 0) and idx_max not in (None, len(xs) - 1):
                applicable_ranges.append(spike_range)
        return remove_false_spike_from_figure(analysis_fig, applicable_ranges)

    def _frequency_range(self) -> Any:
        """Return an explicit override, or let qubex select by readout box type."""
        parameter = self.run_parameters["frequency_range"]
        return None if parameter.value is None else parameter.get_value()

    def _resonator_assignment_order(self) -> list[int]:
        """Return a validated frequency-sorted permutation of MUX offsets."""
        value = self.run_parameters["resonator_assignment_order"].get_value()
        peak_positions_from_assignment_order(value)
        return [int(offset) for offset in value]

    def resolve_run_parameters(self, backend: QubexBackend, qid: str) -> None:
        """Populate the effective device-specific sweep before it is recorded."""
        parameter = self.run_parameters["frequency_range"]
        if parameter.value is not None:
            return

        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        box = exp.ctx.experiment_system.get_readout_box_for_qubit(label)
        parameter.value = tuple(box.traits.default_readout_frequency_range)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        self._resonator_assignment_order()
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        frequency_range = self._frequency_range()
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
        self._resonator_assignment_order()
        exp = self.get_experiment(backend)
        labels = [self.get_qubit_label(backend, qid) for qid in qids]
        frequency_range = self._frequency_range()
        result = exp.resonator_spectroscopy(
            labels[0],
            frequency_range=frequency_range,
            power_range=self.run_parameters["power_range"].get_value(),
            n_shots=self.run_parameters["shots"].get_value(),
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)
