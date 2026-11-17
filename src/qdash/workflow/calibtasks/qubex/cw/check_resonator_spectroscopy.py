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
    OutputParameterModel,
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

DEFAULT_RESONATOR_SPECTROSCOPY_INTERVAL = 0.0

_guess_sorted_slots_for_partial_mux = guess_sorted_slots_for_partial_mux
_qid_for_sorted_slot = qid_for_sorted_slot
_peak_positions_from_assignment_order = peak_positions_from_assignment_order


def resonator_candidates(
    frequencies: list[float], optimal_powers: list[float]
) -> list[tuple[float, float]]:
    """Return detected peaks as frequency-sorted ``(frequency, readout_amplitude)`` pairs.

    Each amplitude is converted from the optimal power of the same peak. The set is
    empty when the detection holds more than ``NUM_RESONATORS`` peaks, when the two
    lists differ in length, or when any frequency or amplitude is not finite and
    positive, so a consumer never receives a partial or mispaired set.
    """
    if len(frequencies) != len(optimal_powers) or len(frequencies) > NUM_RESONATORS:
        return []
    pairs: list[tuple[float, float]] = []
    for raw_frequency, raw_power in zip(frequencies, optimal_powers, strict=True):
        frequency = float(raw_frequency)
        power = float(raw_power)
        if not math.isfinite(frequency) or frequency <= 0.0 or not math.isfinite(power):
            return []
        amplitude = float(10 ** (power / 20))
        if not math.isfinite(amplitude) or amplitude <= 0.0:
            return []
        pairs.append((frequency, amplitude))
    return sorted(pairs)


CANDIDATE_OUTPUT_NAMES = (
    "resonator_candidate_count",
    *(
        f"resonator_candidate_{index}_{kind}"
        for index in range(NUM_RESONATORS)
        for kind in ("frequency", "readout_amplitude")
    ),
)


class CheckResonatorSpectroscopy(QubexTask):
    """Task to check the resonator spectroscopy.

    This is a MUX-level task that performs spectroscopy on all resonators
    with the dedicated 8192 ns Qubex spectroscopy pulse. The scheduler executes it once
    per MUX, and the result will be used by all qubits in that MUX.

    Note: task_type remains "qubit" for frontend compatibility, but
    is_mux_level=True indicates this task runs once per MUX.

    With the ``detection_only`` run parameter set, the task publishes only the
    unassigned candidate set of the MUX (``resonator_candidate_*``) for
    CheckQubitFrequencyMapping and assigns no resonator, readout frequency, or
    readout amplitude to any qid. Every qid of the MUX then gets the same result,
    and a run without a usable candidate set fails for every qid.
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
                "the connected readout box's qubex default: low band "
                "[5.75, 6.75, 0.002], high band [9.75, 10.75, 0.002]."
            ),
        ),
        "power_range": RunParameterSpec(
            unit="dB",
            value_type="np.arange",
            default=(-60, 5, 5),
            description=(
                "Power range as [start, stop, step] in dB. The qubex default is "
                "[-60, 5, 5] dB. The stop value is exclusive."
            ),
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=1024,
            description="Number of shots for resonator spectroscopy",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=DEFAULT_RESONATOR_SPECTROSCOPY_INTERVAL,
            description="Time interval between shots",
        ),
        "resonator_assignment_order": RunParameterSpec(
            unit="",
            value_type="list",
            default=[3, 0, 2, 1],
            description=(
                "Qubit offsets within each MUX in increasing resonator-frequency order. "
                "Enter a JSON array containing each offset from 0 to 3 exactly once. "
                "The default is [3, 0, 2, 1]. For 16Q, use [0, 3, 1, 2] when the "
                "frequency order is mux[0] < mux[3] < mux[1] < mux[2]. Ignored when "
                "detection_only is true."
            ),
        ),
        "detection_only": RunParameterSpec(
            unit="",
            value_type="bool",
            default=False,
            description=(
                "Publish only the unassigned resonator candidates of the MUX for "
                "CheckQubitFrequencyMapping, without assigning a resonator, readout "
                "frequency, or readout amplitude to any qubit. The run fails for every "
                "qubit of the MUX when it detects no usable candidate set. False keeps "
                "the per-qubit assignment and publishes no candidates."
            ),
        ),
    }
    _analysis_config: ClassVar[EstimateResonatorFrequencyConfig] = (
        EstimateResonatorFrequencyConfig()
    )
    _bare_shift_estimator_type: ClassVar[str] = "high_frequency_strength"
    _bare_shift_strength_limit: ClassVar[float] = 4.0
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "resonator_frequency": OutputParameterSpec(
            unit="GHz",
            description="Estimated resonator frequency from spectroscopy",
            publish_targets=(
                "resonator_frequency",
                "readout_frequency",
            ),
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
        "resonator_candidate_count": OutputParameterSpec(
            unit="",
            value_type="int",
            description=(
                "Number of detected resonator candidates in this MUX run, from 1 to 4. "
                "Published only when detection_only is true."
            ),
        ),
        "resonator_candidate_0_frequency": OutputParameterSpec(
            unit="GHz",
            description=(
                "Frequency of detected resonator candidate 0 in increasing-frequency "
                "order. Not assigned to this qubit."
            ),
        ),
        "resonator_candidate_0_readout_amplitude": OutputParameterSpec(
            unit="a.u.",
            description=(
                "Readout amplitude from the optimal power of resonator candidate 0. "
                "Not assigned to this qubit."
            ),
        ),
        "resonator_candidate_1_frequency": OutputParameterSpec(
            unit="GHz",
            description=(
                "Frequency of detected resonator candidate 1 in increasing-frequency "
                "order. Not assigned to this qubit."
            ),
        ),
        "resonator_candidate_1_readout_amplitude": OutputParameterSpec(
            unit="a.u.",
            description=(
                "Readout amplitude from the optimal power of resonator candidate 1. "
                "Not assigned to this qubit."
            ),
        ),
        "resonator_candidate_2_frequency": OutputParameterSpec(
            unit="GHz",
            description=(
                "Frequency of detected resonator candidate 2 in increasing-frequency "
                "order. Not assigned to this qubit."
            ),
        ),
        "resonator_candidate_2_readout_amplitude": OutputParameterSpec(
            unit="a.u.",
            description=(
                "Readout amplitude from the optimal power of resonator candidate 2. "
                "Not assigned to this qubit."
            ),
        ),
        "resonator_candidate_3_frequency": OutputParameterSpec(
            unit="GHz",
            description=(
                "Frequency of detected resonator candidate 3 in increasing-frequency "
                "order. Not assigned to this qubit."
            ),
        ),
        "resonator_candidate_3_readout_amplitude": OutputParameterSpec(
            unit="a.u.",
            description=(
                "Readout amplitude from the optimal power of resonator candidate 3. "
                "Not assigned to this qubit."
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
        detection_only = self._detection_only()

        # Estimate resonator frequency and create marked figure
        estimated_frequency = 0.0
        optimal_power: float | None = None
        readout_amplitude: float | None = None
        minimum_usable_power: float | None = None
        local_boundaries: list[BareShiftBoundary] | None = None
        optimal_powers: list[float] | None = None
        candidates: list[tuple[float, float]] = []
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
            if detection_only:
                candidates = resonator_candidates(frequencies, optimal_powers)
                self._annotate_candidates(marked_fig, candidates)
            else:
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

        if detection_only:
            return self._detection_result(qid, execution_id, candidates, analysis_error, figures)

        # Create a deep copy of output_parameters to avoid sharing state
        # between multiple qids (output_parameters is a ClassVar)
        output_params_copy = {
            name: value
            for name, value in copy.deepcopy(self.output_parameters).items()
            if name not in CANDIDATE_OUTPUT_NAMES
        }
        output_params_copy["resonator_frequency"].value = estimated_frequency
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

    def _detection_result(
        self,
        qid: str,
        execution_id: str,
        candidates: list[tuple[float, float]],
        analysis_error: str | None,
        figures: list[go.Figure],
    ) -> PostProcessResult:
        """Return the candidate set of a detection-only run, or fail without outputs.

        The result depends only on the MUX measurement, so every qid of the MUX
        gets the same outputs or the same failure.
        """
        error_msg = analysis_error
        if error_msg is None and not candidates:
            error_msg = (
                f"Resonator detection for qid={qid} produced no usable candidate set: "
                f"expected 1 to {NUM_RESONATORS} peaks with finite, positive frequency "
                "and readout amplitude"
            )
        if error_msg is not None:
            print(f"[ERROR] {error_msg}")
            return PostProcessResult(
                output_parameters={}, figures=figures, validation_error=error_msg
            )

        outputs: dict[str, OutputParameterModel] = {}
        all_outputs = copy.deepcopy(self.output_parameters)
        outputs["resonator_candidate_count"] = all_outputs["resonator_candidate_count"]
        outputs["resonator_candidate_count"].value = len(candidates)
        for index, (frequency, amplitude) in enumerate(candidates):
            frequency_name = f"resonator_candidate_{index}_frequency"
            amplitude_name = f"resonator_candidate_{index}_readout_amplitude"
            outputs[frequency_name] = all_outputs[frequency_name]
            outputs[frequency_name].value = frequency
            outputs[amplitude_name] = all_outputs[amplitude_name]
            outputs[amplitude_name].value = amplitude
        for value in outputs.values():
            value.execution_id = execution_id
        print(
            f"Detected {len(candidates)} unassigned resonator candidates for qid={qid}: "
            f"{[f'{frequency:.6f}' for frequency, _ in candidates]} GHz"
        )
        return PostProcessResult(output_parameters=outputs, figures=figures)

    @staticmethod
    def _annotate_candidates(marked_fig: Any, candidates: list[tuple[float, float]]) -> None:
        """Label each candidate peak with its index instead of an assigned qubit."""
        if marked_fig is None:
            return
        for index, (frequency, _) in enumerate(candidates):
            marked_fig.add_annotation(
                x=frequency,
                y=1.02,
                yref="paper",
                text=f"c{index}",
                showarrow=False,
                font={"color": "red", "size": 11},
                align="center",
            )

    def _detection_only(self) -> bool:
        """Return whether the run publishes only the unassigned candidate set."""
        return bool(self.run_parameters["detection_only"].get_value())

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
        super().resolve_run_parameters(backend, qid)
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
            shot_interval=self.run_parameters["interval"].get_value(),
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
            shot_interval=self.run_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)
