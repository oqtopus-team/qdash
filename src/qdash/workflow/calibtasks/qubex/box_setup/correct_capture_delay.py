"""Correct the capture delay of a readout MUX on QuEL-1 or QuEL-3.

Ported from https://github.com/orangekame3/capture-delay-tools. The task sweeps
the capture delay with a fixed readout tone, picks the delay that centers the
readout pulse in the capture window with at least 32 ns before and after it,
verifies the candidate, and then remeasures the final value.

- QuEL-1 sweeps ``capture_delay`` (128 ns) with ``capture_delay_word`` fixed at 0,
  then sweeps the word (8 ns, 32 ns steps) at the chosen coarse delay.
- QuEL-3 sweeps ``capture_delay`` in ns once and selects on its 0.8 ns grid.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from qdash.analysis.capture_delay import (
    MARGIN_NS,
    QUEL1_RESOLUTION_NS,
    QUEL3_RESOLUTION_NS,
    WORD_STEP,
    EdgeResult,
    FinalReport,
    SelectionReport,
    Waveform,
    analyze_waveforms,
    finalize_delay,
    select_delay,
    split_total_delay,
    total_delay_ns,
)
from qdash.common.visualization.figure_metadata import set_figure_role
from qdash.datamodel.task import InputParameterSpec, OutputParameterSpec, RunParameterSpec
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import QubexTask, readout_duration_run_parameter

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend

# Place the default tone just above the resonator spectroscopy range so that
# resonators do not distort the captured pulse: 11.0 GHz (high band), 7.0 GHz (low band).
READOUT_FREQUENCY_OFFSET_GHZ = 0.25
RESOLUTION_NS = {"quel1": QUEL1_RESOLUTION_NS, "quel3": QUEL3_RESOLUTION_NS}

# A delay setting to capture with: total delay in ns and its label in figures.
Setting = tuple[float, str]


def _quel1_setting(delay: int, word: int) -> Setting:
    return total_delay_ns(delay, word), f"{delay}/{word}"


def _quel3_setting(total_ns: float) -> Setting:
    return total_ns, f"{total_ns:g}"


@dataclass
class CaptureDelayRun:
    """Measurements and decisions from one MUX calibration."""

    backend: str
    mux: int
    target: str
    center_ns: float
    coarse: list[EdgeResult] = field(default_factory=list)
    coarse_selection: SelectionReport | None = None
    fine: list[EdgeResult] = field(default_factory=list)
    fine_selection: SelectionReport | None = None
    verification: list[EdgeResult] = field(default_factory=list)
    final: FinalReport | None = None
    final_check: list[EdgeResult] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    accepted_targets: list[str] = field(default_factory=list)
    rejected_targets: dict[str, str] = field(default_factory=dict)
    error: str | None = None


class CorrectCaptureDelay(QubexTask):
    """Center the readout pulse in the capture window of each MUX.

    This MUX-level task measures each active qubit separately. Only qubits with
    supported pulse edges and successful verification contribute to the common
    delay. A shared delay must fit every accepted qubit with 32 ns margins;
    incompatible successful measurements fail the task without publishing values.
    The accepted delay applies to the MUX, including qubits rejected by the fit.
    """

    name: str = "CorrectCaptureDelay"
    task_type: str = "qubit"
    is_mux_level: bool = True
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {}
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_frequency": RunParameterSpec(
            unit="GHz",
            value_type="float",
            default=None,
            description=(
                "Fixed readout tone frequency used for every capture. Choose a frequency "
                "inside the readout band but away from the resonators; resonator "
                "calibration is not required. Leave blank to use 0.25 GHz above the "
                "connected readout box's default resonator spectroscopy range: "
                "11.0 GHz for the high band and 7.0 GHz for the low band."
            ),
        ),
        "delay_range": RunParameterSpec(
            unit="128 ns",
            value_type="range",
            default=(0, 19, 1),
            description=(
                "QuEL-1: coarse capture_delay sweep as [start, stop, step] in 128 ns "
                "units. The stop value is exclusive."
            ),
        ),
        "capture_delay_word_range": RunParameterSpec(
            unit="8 ns",
            value_type="range",
            default=(0, 16, WORD_STEP),
            description=(
                "QuEL-1: capture_delay_word sweep at the chosen coarse delay as "
                "[start, stop, step] in 8 ns words. Every value must be a multiple of "
                "4 words (32 ns)."
            ),
        ),
        "capture_delay_ns_range": RunParameterSpec(
            unit="ns",
            value_type="np.arange",
            default=(0, 2432, 128),
            description=(
                "QuEL-3: capture_delay sweep as [start, stop, step] in ns. Every value "
                "must be a multiple of 0.8 ns. The stop value is exclusive."
            ),
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=1024,
            description="Number of averaged shots per capture",
        ),
        "snr_threshold": RunParameterSpec(
            unit="a.u.",
            value_type="float",
            default=5.0,
            description="Minimum signal-to-noise ratio of a detected pulse edge",
        ),
        "smoothing": RunParameterSpec(
            unit="samples",
            value_type="int",
            default=5,
            description="Moving-average window used to locate the pulse plateau",
        ),
        "readout_duration": readout_duration_run_parameter(),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "capture_delay": OutputParameterSpec(
            unit="ndelay",
            value_type="float",
            description=("Capture delay of the MUX: 128 ns units (ndelay) on QuEL-1, ns on QuEL-3"),
        ),
        "capture_delay_word": OutputParameterSpec(
            unit="word",
            value_type="int",
            description="QuEL-1 capture delay word of the MUX in 8 ns units",
        ),
    }

    def _targets(self, exp: Any, label: str) -> tuple[int, list[str]]:
        """Resolve active session qubits in the MUX, even if its first qubit is inactive."""
        system = exp.system_manager.experiment_system
        mux = int(system.get_mux_by_qubit(label).index)
        targets = [
            target
            for target in exp.qubit_labels
            if int(system.get_mux_by_qubit(target).index) == mux
        ]
        if not targets:
            raise ValueError(
                f"MUX{mux}: no active qubits in the Qubex session. Set "
                "readout_frequency and control_frequency for the "
                "MUX qubits in the params files before correcting the capture delay."
            )
        return mux, targets

    def resolve_run_parameters(self, backend: QubexBackend, qid: str) -> None:
        """Record the effective readout tone frequency before the run."""
        super().resolve_run_parameters(backend, qid)
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        _, targets = self._targets(exp, label)
        label = targets[0]
        parameter = self.run_parameters["readout_frequency"]
        if parameter.value is not None:
            return
        box = exp.ctx.experiment_system.get_readout_box_for_qubit(label)
        _, stop, _ = box.traits.default_readout_frequency_range
        parameter.value = round(float(stop) + READOUT_FREQUENCY_OFFSET_GHZ, 6)

    def _sweep_values(self, name: str) -> list[float]:
        values = [float(value) for value in self.run_parameters[name].get_value()]
        if not values or any(value < 0 for value in values):
            raise ValueError(f"{name} must contain at least one nonnegative value")
        return list(dict.fromkeys(values))

    def _coarse_settings(self, backend_kind: str) -> list[Setting]:
        if backend_kind == "quel1":
            words = self._sweep_values("capture_delay_word_range")
            if any(word % WORD_STEP for word in words):
                raise ValueError(
                    f"capture_delay_word_range values must be multiples of {WORD_STEP} "
                    "words (32 ns)"
                )
            return [_quel1_setting(int(delay), 0) for delay in self._sweep_values("delay_range")]
        totals = [round(value, 6) for value in self._sweep_values("capture_delay_ns_range")]
        if any(
            not math.isclose(
                value / QUEL3_RESOLUTION_NS, round(value / QUEL3_RESOLUTION_NS), abs_tol=1e-6
            )
            for value in totals
        ):
            raise ValueError(
                f"capture_delay_ns_range values must be multiples of {QUEL3_RESOLUTION_NS} ns"
            )
        return [_quel3_setting(value) for value in totals]

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Sweep, verify, and remeasure the capture delay of the qubit's MUX."""
        exp = self.get_experiment(backend)
        backend_kind = exp.system_manager.backend_kind
        if backend_kind not in RESOLUTION_NS:
            raise ValueError(f"{self.name} supports QuEL-1 and QuEL-3 capture delays only")
        resolution = RESOLUTION_NS[backend_kind]
        target = self.get_qubit_label(backend, qid)
        mux, targets = self._targets(exp, target)

        coarse_settings = self._coarse_settings(backend_kind)
        frequency = float(self.run_parameters["readout_frequency"].get_value())
        if not math.isfinite(frequency) or frequency <= 0:
            raise ValueError("readout_frequency must be finite and positive")
        snr_threshold = float(self.run_parameters["snr_threshold"].get_value())
        smoothing = int(self.run_parameters["smoothing"].get_value())

        def measure_and_analyze(
            settings: list[Setting], measured_targets: list[str]
        ) -> list[EdgeResult]:
            waveforms = [
                waveform
                for measured_target in measured_targets
                for waveform in self._measure(
                    exp, backend_kind, mux, measured_target, frequency, settings
                )
            ]
            return analyze_waveforms(waveforms, snr_threshold=snr_threshold, smoothing=smoothing)

        def setting(total_ns: float) -> Setting:
            if backend_kind == "quel1":
                return _quel1_setting(*split_total_delay(total_ns))
            return _quel3_setting(total_ns)

        coarse = measure_and_analyze(coarse_settings, targets)
        center = float(np.median([result.waveform.window_center_ns for result in coarse]))
        result = CaptureDelayRun(
            backend=backend_kind,
            mux=mux,
            target=target,
            center_ns=center,
            coarse=coarse,
            targets=targets,
        )

        def supported_targets(
            edges: list[EdgeResult], candidates: list[str], stage: str
        ) -> list[str]:
            supported = []
            for candidate in candidates:
                report = select_delay(
                    [edge for edge in edges if edge.target == candidate],
                    mux=mux,
                    center=center,
                    resolution_ns=resolution,
                )
                if report.selected_total_ns is None:
                    result.rejected_targets[candidate] = f"{stage}: {report.reason}"
                else:
                    supported.append(candidate)
            return supported

        def common_selection(edges: list[EdgeResult], candidates: list[str]) -> SelectionReport:
            return select_delay(
                [edge for edge in edges if edge.target in candidates],
                mux=mux,
                center=center,
                resolution_ns=resolution,
            )

        candidates = supported_targets(coarse, targets, "coarse sweep")
        result.coarse_selection = common_selection(coarse, candidates)
        selection = result.coarse_selection
        selected_total = selection.selected_total_ns
        if selected_total is None:
            result.error = f"coarse sweep: {selection.reason}"
            return RunResult(raw_result=result)

        if backend_kind == "quel1":
            delay, _ = split_total_delay(selected_total)
            words = self._sweep_values("capture_delay_word_range")
            result.fine = measure_and_analyze(
                [_quel1_setting(delay, int(w)) for w in words], candidates
            )
            candidates = supported_targets(result.fine, candidates, "word sweep")
            result.fine_selection = common_selection(result.fine, candidates)
            selection = result.fine_selection
            selected_total = selection.selected_total_ns
            if selected_total is None:
                result.error = f"word sweep: {selection.reason}"
                return RunResult(raw_result=result)

        result.verification = measure_and_analyze([setting(selected_total)], candidates)
        verified = []
        for candidate in candidates:
            edges = [edge for edge in result.verification if edge.target == candidate]
            single_selection = replace(selection, supporting_targets=(candidate,))
            report = finalize_delay(
                edges, single_selection, center=center, resolution_ns=resolution
            )
            if report.final_total_ns is None:
                result.rejected_targets[candidate] = f"verification: {report.reason}"
            else:
                verified.append(candidate)
        selection = replace(selection, supporting_targets=tuple(verified))
        result.final = finalize_delay(
            [edge for edge in result.verification if edge.target in verified],
            selection,
            center=center,
            resolution_ns=resolution,
        )
        if result.final.final_total_ns is None:
            result.error = f"verification: {result.final.reason}"
            return RunResult(raw_result=result)

        result.final_check = measure_and_analyze([setting(result.final.final_total_ns)], verified)
        for candidate in verified:
            checks = [edge for edge in result.final_check if edge.target == candidate]
            if checks and all(
                check.success
                and check.rise_ns is not None
                and check.fall_ns is not None
                and check.rise_ns - check.time_start_ns >= MARGIN_NS - 1e-6
                and check.time_stop_ns - check.fall_ns >= MARGIN_NS - 1e-6
                for check in checks
            ):
                result.accepted_targets.append(candidate)
            else:
                result.rejected_targets[candidate] = (
                    "final check: missing edges or insufficient margins"
                )
        if not result.accepted_targets:
            result.error = "final check: no qubits passed verification"
        return RunResult(raw_result=result)

    def _measure(
        self,
        exp: Any,
        backend_kind: str,
        mux: int,
        target: str,
        frequency: float,
        settings: list[Setting],
    ) -> list[Waveform]:
        """Capture ``target`` once per delay setting."""
        from qubex import Blank

        system = exp.system_manager.experiment_system
        params = system.control_params

        def current() -> tuple[Any, ...]:
            # QuEL-3 has no word offset; reading it raises on that backend.
            if backend_kind == "quel1":
                return params.get_capture_delay(mux), params.get_capture_delay_word(mux)
            return (params.get_capture_delay(mux),)

        original = current()
        duration = float(self.run_parameters["readout_duration"].get_value())
        read_label = system.resolve_read_label(target)
        waveforms: list[Waveform] = []
        with exp.modified_frequencies({read_label: frequency}):
            for total_ns, label in settings:
                with exp.system_manager.modified_capture_delay({mux: total_ns}):
                    measured_result = exp.measure(
                        {target: Blank(0)},
                        readout_duration=duration,
                        time_integration=False,
                        add_pump_pulses=False,
                        n_shots=int(self.run_parameters["shots"].get_value()),
                        plot=False,
                    )
                measured = measured_result.data[target]
                iq = np.asarray(measured.raw, dtype=np.complex128)
                if iq.ndim == 2:
                    iq = iq.mean(axis=0)
                waveforms.append(
                    Waveform(
                        mux=mux,
                        target=target,
                        total_delay_ns=total_ns,
                        time_ns=np.arange(iq.size) * float(measured.sampling_period),
                        iq=iq,
                        pulse_duration_ns=duration,
                        setting=label,
                    )
                )
        if current() != original:
            raise RuntimeError(f"MUX{mux}: capture delay settings were not restored")
        return waveforms

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Publish the final delay of the MUX with the sweep and check figures."""
        result: CaptureDelayRun = run_result.raw_result
        target = self.get_qubit_label(backend, qid)
        # A MUX-wide failure stops distribution, so retain all individual
        # experiments on the representative task for diagnosis.
        figures = _figures(result, target=None if result.error else target)
        final_total = result.final.final_total_ns if result.final is not None else None
        if result.error is not None or final_total is None or not result.accepted_targets:
            return PostProcessResult(
                output_parameters={},
                figures=figures,
                validation_error=f"{self.name} MUX{result.mux}: {result.error}",
            )
        output_parameters = copy.deepcopy(self.output_parameters)
        if result.backend == "quel1":
            delay, word = split_total_delay(final_total)
            output_parameters["capture_delay"].value = delay
            output_parameters["capture_delay"].value_type = "int"
            output_parameters["capture_delay_word"].value = word
        else:
            output_parameters["capture_delay"].value = final_total
            output_parameters["capture_delay"].unit = "ns"
            del output_parameters["capture_delay_word"]
        for parameter in output_parameters.values():
            parameter.execution_id = execution_id
        return PostProcessResult(output_parameters=output_parameters, figures=figures)


_RISE_COLOR = "#d62728"
_FALL_COLOR = "#ff7f0e"
_CENTER_COLOR = "#7f7f7f"


def _figures(result: CaptureDelayRun, *, target: str | None = None) -> list[go.Figure]:
    """Return sweep heatmaps and the final capture, most decisive first."""
    figures: list[go.Figure] = []
    for measured_target in result.targets or [result.target]:
        if target is not None and measured_target != target:
            continue
        qubit = measured_target
        individual = replace(
            result,
            target=qubit,
            coarse=[edge for edge in result.coarse if edge.target == qubit],
            fine=[edge for edge in result.fine if edge.target == qubit],
            verification=[edge for edge in result.verification if edge.target == qubit],
            final_check=[edge for edge in result.final_check if edge.target == qubit],
        )
        status = (
            "accepted"
            if qubit in result.accepted_targets
            else result.rejected_targets.get(qubit, result.error or "not accepted")
        )
        captures: list[tuple[str, go.Figure]] = []
        if individual.final_check:
            captures.append(
                ("final", _capture_figure(individual, individual.final_check, "Final capture"))
            )
        elif individual.verification:
            captures.append(
                (
                    "verification",
                    _capture_figure(individual, individual.verification, "Verification"),
                )
            )
        if individual.fine:
            captures.append(
                ("word_sweep", _sweep_figure(individual, individual.fine, "capture_delay_word"))
            )
        if individual.coarse:
            captures.append(
                ("delay_sweep", _sweep_figure(individual, individual.coarse, "capture_delay"))
            )
        for role, figure in captures:
            figure.update_layout(title=f"{figure.layout.title.text} — {status}")
            set_figure_role(figure, role)
            figures.append(figure)
    return figures


def _sweep_figure(result: CaptureDelayRun, edges: list[EdgeResult], title: str) -> go.Figure:
    """Plot |IQ| for each delay/word pair with detected edges per target."""
    targets = list(dict.fromkeys(edge.target for edge in edges))
    figure = make_subplots(rows=len(targets), cols=1, subplot_titles=targets)
    for row, target in enumerate(targets, start=1):
        group = sorted(
            (edge for edge in edges if edge.target == target),
            key=lambda edge: edge.waveform.total_delay_ns,
        )
        columns = [edge.waveform.label for edge in group]
        figure.add_trace(
            go.Heatmap(
                x=columns,
                y=group[0].waveform.time_ns,
                z=np.array([np.abs(edge.waveform.iq) for edge in group]).T,
                colorscale="Blues",
                showscale=False,
                hovertemplate="delay %{x}<br>%{y} ns<br>|IQ| %{z:.3g}<extra></extra>",
            ),
            row=row,
            col=1,
        )
        for name, color, values in (
            ("Rise", _RISE_COLOR, [edge.rise_ns for edge in group]),
            ("Fall", _FALL_COLOR, [edge.fall_ns for edge in group]),
        ):
            points = [(x, y) for x, y in zip(columns, values, strict=True) if y is not None]
            figure.add_trace(
                go.Scatter(
                    x=[x for x, _ in points],
                    y=[y for _, y in points],
                    mode="markers",
                    marker={"color": color, "size": 7},
                    name=name,
                    legendgroup=name,
                    showlegend=row == 1,
                ),
                row=row,
                col=1,
            )
        figure.add_hline(
            y=result.center_ns, line_color=_CENTER_COLOR, line_dash="dash", row=row, col=1
        )
        figure.update_xaxes(
            title_text=(
                "capture_delay / word" if result.backend == "quel1" else "capture_delay (ns)"
            ),
            type="category",
            row=row,
            col=1,
        )
        figure.update_yaxes(title_text="Time in capture (ns)", row=row, col=1)
    figure.update_layout(
        title=f"MUX{result.mux} {result.target} {title} sweep |IQ|",
        height=260 * len(targets) + 120,
        width=700,
    )
    return figure


def _capture_figure(result: CaptureDelayRun, edges: list[EdgeResult], title: str) -> go.Figure:
    """Plot I and Q of one capture per target with detected edges."""
    figure = make_subplots(
        rows=len(edges),
        cols=1,
        subplot_titles=[f"{edge.target} / capture_delay={edge.waveform.label}" for edge in edges],
    )
    for row, edge in enumerate(edges, start=1):
        for name, values in (("I", edge.waveform.iq.real), ("Q", edge.waveform.iq.imag)):
            figure.add_trace(
                go.Scatter(
                    x=edge.waveform.time_ns,
                    y=values,
                    mode="lines",
                    name=name,
                    legendgroup=name,
                    showlegend=row == 1,
                ),
                row=row,
                col=1,
            )
        for value, color in ((edge.rise_ns, _RISE_COLOR), (edge.fall_ns, _FALL_COLOR)):
            if value is not None:
                figure.add_vline(x=value, line_color=color, line_dash="dot", row=row, col=1)
        figure.add_vline(
            x=result.center_ns, line_color=_CENTER_COLOR, line_dash="dash", row=row, col=1
        )
        figure.update_xaxes(title_text="Time (ns)", row=row, col=1)
        figure.update_yaxes(title_text="Signal (arb. units)", row=row, col=1)
    figure.update_layout(
        title=f"MUX{result.mux} {result.target} {title}",
        height=260 * len(edges) + 120,
        width=700,
    )
    return figure
