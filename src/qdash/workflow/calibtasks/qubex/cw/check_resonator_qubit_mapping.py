"""MUX-level resonator-to-qubit mapping by 1D high-power qubit spectroscopy."""

from __future__ import annotations

import copy
import logging
import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np

from qdash.analysis.spectroscopy import (
    ResonatorCandidate,
    ResonatorQubitMappingResult,
    create_mapping_grid_figure,
    score_1d_spectroscopy_trace,
    solve_resonator_qubit_mapping,
)
from qdash.common.mux_mapping import MuxMapping, canonical_qid
from qdash.common.visualization.figure_metadata import set_figure_role
from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
    TaskDocumentation,
)
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.progress import ProgressPlan

if TYPE_CHECKING:
    import plotly.graph_objs as go

    from qdash.workflow.engine.backend.qubex import QubexBackend

logger = logging.getLogger(__name__)

DEFAULT_MAPPING_FREQUENCY_STEP = 0.020
DEFAULT_MAPPING_DRIVE_POWER = 0.0
DEFAULT_MAPPING_SHOTS = 512
DEFAULT_MAPPING_INTERVAL = 1024.0
DEFAULT_MAPPING_MIN_RESPONSE_SCORE = 5.0
DEFAULT_MAPPING_MIN_MARGIN_RATIO = 2.0
MIN_RESONATOR_CANDIDATES = 2
DUPLICATE_CANDIDATE_TOLERANCE = 0.0005
"""Candidates closer than this (GHz) are the same resonator stored on two qubits."""


class CheckResonatorQubitMapping(QubexTask):
    """Map the resonators of a MUX to its qubits.

    CheckResonatorSpectroscopy writes one resonator frequency, readout amplitude
    and optimal power to each qubit of a MUX from an assumed frequency order.
    This MUX-level task verifies that order: it drives each qubit at high power
    with a coarse 1D frequency sweep while reading out at each resonator
    candidate, one pair at a time, and assigns each qubit the candidate whose
    readout shows its response. Only verified mappings are written.

    Note: task_type remains "qubit" for frontend compatibility, but
    is_mux_level=True indicates this task runs once per MUX.
    """

    name: str = "CheckResonatorQubitMapping"
    task_type: str = "qubit"
    documentation: ClassVar[TaskDocumentation] = TaskDocumentation(
        description=(
            "MUX-level check of which resonator reads which qubit. It takes the readout "
            "settings stored on the MUX's qubits as resonator candidates, runs a coarse 1D "
            "high-power qubit spectroscopy for every qubit and candidate pair one at a time, "
            "and solves the one-to-one assignment with the strongest responses. Each qubit "
            "whose mapping is unambiguous gets its candidate's resonator_frequency (also "
            "published as readout_frequency), readout_amplitude and optimal_power. It does "
            "not estimate qubit frequencies."
        ),
        when_to_use=(
            "Run it after CheckResonatorSpectroscopy and before CheckQubitSpectroscopy when "
            "the MUX's resonator frequency order is unknown or suspected to be wrong. A qubit "
            "with no response or an ambiguous response fails and keeps its stored values."
        ),
        prerequisites=(
            "readout_frequency (or resonator_frequency) and readout_amplitude are stored on "
            "at least two qubits of the MUX, normally by CheckResonatorSpectroscopy.",
        ),
    )
    is_mux_level: bool = True
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "readout_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("resonator_frequency",)
        ),
        "readout_amplitude": InputParameterSpec.required_database(),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "frequency_range": RunParameterSpec(
            unit="GHz",
            value_type="np.arange",
            default=None,
            description=(
                "Drive frequency range as [start, stop, step] in GHz. Leave blank to use the "
                "connected control box's qubex default band with frequency_step as the step."
            ),
        ),
        "frequency_step": RunParameterSpec(
            unit="GHz",
            value_type="float",
            default=DEFAULT_MAPPING_FREQUENCY_STEP,
            description=(
                "Drive frequency step in GHz used when frequency_range is blank. The default "
                "0.020 GHz is coarse because the high-power response is broad."
            ),
        ),
        "drive_power": RunParameterSpec(
            unit="dB",
            value_type="float",
            default=DEFAULT_MAPPING_DRIVE_POWER,
            description=(
                "Drive power in dB, at most 0 dB. The default 0 dB is control amplitude 1.0."
            ),
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=DEFAULT_MAPPING_SHOTS,
            description="Number of shots per drive frequency",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=DEFAULT_MAPPING_INTERVAL,
            description="Time interval between shots",
        ),
        "simultaneous_drive": RunParameterSpec(
            unit="a.u.",
            value_type="bool",
            default=True,
            description=(
                "Whether control and readout pulses start together. "
                "False starts readout after the control pulse ends."
            ),
        ),
        "min_response_score": RunParameterSpec(
            unit="a.u.",
            value_type="float",
            default=DEFAULT_MAPPING_MIN_RESPONSE_SCORE,
            description=(
                "Minimum trace score of a significant response. The score is the area of the "
                "robust phase z-score above 3 sigma, so pure noise scores near 0."
            ),
        ),
        "min_margin_ratio": RunParameterSpec(
            unit="a.u.",
            value_type="float",
            default=DEFAULT_MAPPING_MIN_MARGIN_RATIO,
            description=(
                "Minimum ratio by which a qubit's selected assignment must beat every "
                "alternative that moves the qubit. Lower margins are reported as ambiguous."
            ),
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "resonator_frequency": OutputParameterSpec(
            unit="GHz",
            description="Resonator frequency of the candidate mapped to this qubit",
            publish_targets=(
                "resonator_frequency",
                "readout_frequency",
            ),
        ),
        "readout_amplitude": OutputParameterSpec(
            unit="a.u.",
            description="Readout amplitude stored with the candidate mapped to this qubit",
        ),
        "optimal_power": OutputParameterSpec(
            unit="dB",
            description=(
                "Optimal readout power stored with the candidate mapped to this qubit; "
                "omitted when the candidate has none."
            ),
        ),
    }

    def get_progress_plan(self) -> ProgressPlan:
        """One qubit spectroscopy per measured pair: 2x2 up to 4x4 in a MUX."""
        return ProgressPlan(4, 16)

    # ------------------------------------------------------------------ settings

    def _run_value(self, name: str) -> Any:
        return self.run_parameters[name].get_value()

    def _frequency_range(self) -> Any:
        """Return the drive sweep, or None to let qubex choose its default band."""
        parameter = self.run_parameters["frequency_range"]
        return None if parameter.value is None else parameter.get_value()

    def _validated_settings(self) -> tuple[float, float, float]:
        """Return ``(drive_power, min_response_score, min_margin_ratio)`` after checks."""
        drive_power = float(self._run_value("drive_power"))
        if not math.isfinite(drive_power) or drive_power > 0.0:
            raise ValueError(
                f"drive_power must be finite and at most 0 dB (amplitude 1.0), got {drive_power}"
            )
        min_response_score = float(self._run_value("min_response_score"))
        if not math.isfinite(min_response_score) or min_response_score <= 0.0:
            raise ValueError(
                f"min_response_score must be finite and positive, got {min_response_score}"
            )
        min_margin_ratio = float(self._run_value("min_margin_ratio"))
        if not math.isfinite(min_margin_ratio) or min_margin_ratio < 1.0:
            raise ValueError(
                f"min_margin_ratio must be finite and at least 1.0, got {min_margin_ratio}"
            )
        return drive_power, min_response_score, min_margin_ratio

    def resolve_run_parameters(self, backend: QubexBackend, qid: str) -> None:
        """Record the effective coarse drive sweep before the task runs."""
        super().resolve_run_parameters(backend, qid)
        parameter = self.run_parameters["frequency_range"]
        if parameter.value is not None:
            return
        step = float(self._run_value("frequency_step"))
        if not math.isfinite(step) or step <= 0.0:
            raise ValueError(f"frequency_step must be finite and positive, got {step}")

        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        box = exp.ctx.experiment_system.get_control_box_for_qubit(label)
        start, stop, _default_step = box.traits.default_control_frequency_range
        parameter.value = (float(start), float(stop), step)

    # ------------------------------------------------------------------ candidates

    def _mux_qids(self, backend: QubexBackend, qid: str) -> list[str]:
        """Members of ``qid``'s MUX in local slot order, from the pinned MUX mapping."""
        resolve = getattr(backend, "ensure_mux_mapping_compatible", None)
        mapping = resolve() if callable(resolve) else None
        if not isinstance(mapping, MuxMapping):
            mapping = MuxMapping.legacy()
        return list(mapping.qids_of(mapping.mux_of(qid)))

    def _stored_calibration(self, backend: QubexBackend, qid: str) -> Mapping[str, Any]:
        """Return the qubit's stored calibration values, or an empty mapping."""
        project_id = backend.config.get("project_id")
        chip_id = backend.config.get("chip_id")
        if not project_id or not chip_id:
            return {}
        from qdash.repository.qubit import MongoQubitCalibrationRepository

        return MongoQubitCalibrationRepository().get_calibration_data(
            project_id=project_id, chip_id=chip_id, qid=qid
        )

    @staticmethod
    def _stored_value(data: Mapping[str, Any], *names: str) -> float | None:
        for name in names:
            entry = data.get(name)
            value = entry.get("value") if isinstance(entry, Mapping) else entry
            if value is None:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                return number
        return None

    def _collect_candidates(
        self, backend: QubexBackend, qid: str, mux_qids: list[str]
    ) -> list[ResonatorCandidate]:
        """Collect the provisional readout settings of the MUX as candidates.

        The representative qubit uses its resolved inputs, so explicit input
        overrides apply; the other members use their stored calibration. Entries
        without a positive frequency and amplitude are skipped, and entries at the
        same frequency are kept once. Candidates are sorted by frequency.
        """
        representative = canonical_qid(qid)
        entries: list[tuple[str, float, float, float | None]] = []
        for member in mux_qids:
            data = self._stored_calibration(backend, member)
            frequency = self._stored_value(data, "readout_frequency", "resonator_frequency")
            amplitude = self._stored_value(data, "readout_amplitude")
            if member == representative:
                frequency = self._input_value("readout_frequency", frequency)
                amplitude = self._input_value("readout_amplitude", amplitude)
            optimal_power = self._stored_value(data, "optimal_power")
            if frequency is None or frequency <= 0.0 or amplitude is None or amplitude <= 0.0:
                print(
                    f"[WARNING] qid={member} has no usable readout_frequency/readout_amplitude; "
                    "it contributes no resonator candidate"
                )
                continue
            entries.append((member, frequency, amplitude, optimal_power))

        entries.sort(key=lambda entry: entry[1])
        unique: list[tuple[str, float, float, float | None]] = []
        for entry in entries:
            if unique and abs(entry[1] - unique[-1][1]) < DUPLICATE_CANDIDATE_TOLERANCE:
                print(
                    f"[WARNING] qid={entry[0]} stores the same resonator as qid={unique[-1][0]} "
                    f"({entry[1]:.6f} GHz); keeping one candidate"
                )
                continue
            unique.append(entry)
        return [
            ResonatorCandidate(
                candidate_index=index,
                source_qid=member,
                frequency=frequency,
                readout_amplitude=amplitude,
                optimal_power=optimal_power,
            )
            for index, (member, frequency, amplitude, optimal_power) in enumerate(unique)
        ]

    def _input_value(self, name: str, fallback: float | None) -> float | None:
        parameter = self.input_parameters.get(name)
        if parameter is None or parameter.value is None:
            return fallback
        try:
            value = float(parameter.value)
        except (TypeError, ValueError):
            return fallback
        return value if math.isfinite(value) else fallback

    @staticmethod
    def _loaded_qubit_labels(exp: Any) -> set[str] | None:
        labels = getattr(exp, "qubit_labels", None)
        if isinstance(labels, (list, tuple, set, frozenset)):
            return {str(label) for label in labels}
        return None

    # ------------------------------------------------------------------ measurement

    @staticmethod
    def _as_phase(values: Any) -> np.ndarray:
        """Return phases in rad; complex IQ signals are converted with ``np.angle``."""
        array = np.asarray(values)
        if np.iscomplexobj(array):
            return np.asarray(np.angle(array), dtype=float)
        return np.asarray(array, dtype=float)

    @classmethod
    def _extract_1d_trace(cls, result: Any) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(frequencies, phases)`` of a single-power qubit spectroscopy.

        ``qubit_spectroscopy`` returns ``data`` with shape ``(n_powers, n_freqs)``;
        with one power the trace is its only row. A complex trace is read as IQ
        signals and converted to phase rather than dropping its imaginary part.
        """
        data = getattr(result, "data", result)
        if not isinstance(data, Mapping):
            raise ValueError("qubit_spectroscopy returned no data mapping")
        frequencies = np.asarray(data["frequency_range"], dtype=float).ravel()
        if "data" in data:
            phases = np.atleast_2d(cls._as_phase(data["data"]))[0]
        elif "phases" in data:
            phases = cls._as_phase(data["phases"]).ravel()
        else:
            raise ValueError("qubit_spectroscopy result has no phase data")
        if phases.size != frequencies.size:
            raise ValueError(
                f"qubit_spectroscopy returned {phases.size} phases for "
                f"{frequencies.size} frequencies"
            )
        return frequencies, phases

    def _measure_pair(
        self,
        exp: Any,
        label: str,
        candidate: ResonatorCandidate,
        frequency_range: Any,
        drive_power: float,
    ) -> Any:
        """Drive one qubit while reading out at one candidate, without multiplexing."""
        with self._modified_qubit_readout_frequencies(
            exp,
            qubit_label=label,
            frequency_overrides={"R" + label: candidate.frequency},
        ):
            return exp.qubit_spectroscopy(
                label,
                frequency_range=frequency_range,
                power_range=np.array([drive_power]),
                readout_amplitude=candidate.readout_amplitude,
                readout_frequency=candidate.frequency,
                n_shots=self._run_value("shots"),
                shot_interval=self._run_value("interval"),
                plot=False,
                save_image=False,
                simultaneous_drive=self._run_value("simultaneous_drive"),
            )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Measure every (qubit, candidate) pair of the MUX and solve the mapping."""
        drive_power, min_response_score, min_margin_ratio = self._validated_settings()
        exp = self.get_experiment(backend)
        mux_qids = self._mux_qids(backend, qid)
        candidates = self._collect_candidates(backend, qid, mux_qids)
        if len(candidates) < MIN_RESONATOR_CANDIDATES:
            raise ValueError(
                f"{self.name} needs at least {MIN_RESONATOR_CANDIDATES} resonator candidates "
                f"stored on MUX qubits {mux_qids}, found {len(candidates)}; run "
                "CheckResonatorSpectroscopy first"
            )

        loaded = self._loaded_qubit_labels(exp)
        labels: dict[str, str] = {}
        for member in mux_qids:
            label = self.get_qubit_label(backend, member)
            if loaded is not None and label not in loaded:
                print(f"[WARNING] {label} (qid={member}) is not loaded; it is not measured")
                continue
            labels[member] = label
        if not labels:
            raise ValueError(f"No qubit of MUX {mux_qids} is loaded in the experiment")
        measured_qids = list(labels)

        print(
            f"[{self.name}] MUX qubits={measured_qids} candidates="
            + ", ".join(
                f"C{c.candidate_index}={c.frequency:.6f} GHz (from qid={c.source_qid})"
                for c in candidates
            )
        )

        frequency_range = self._frequency_range()
        frequencies: np.ndarray | None = None
        traces: list[list[np.ndarray | None]] = []
        spectroscopy: dict[str, Any] = {}
        scores = np.zeros((len(measured_qids), len(candidates)))
        for row, member in enumerate(measured_qids):
            label = labels[member]
            row_traces: list[np.ndarray | None] = []
            for column, candidate in enumerate(candidates):
                result = self._measure_pair(exp, label, candidate, frequency_range, drive_power)
                spectroscopy[f"{label}@C{candidate.candidate_index}"] = result
                pair_frequencies, phases = self._extract_1d_trace(result)
                if frequencies is None:
                    frequencies = pair_frequencies
                elif pair_frequencies.shape != frequencies.shape or not np.allclose(
                    pair_frequencies, frequencies
                ):
                    raise ValueError(
                        f"{label}@C{candidate.candidate_index} swept different frequencies "
                        "from the first pair"
                    )
                scores[row, column] = score_1d_spectroscopy_trace(pair_frequencies, phases)
                row_traces.append(phases)
            traces.append(row_traces)

        mapping = solve_resonator_qubit_mapping(
            scores,
            measured_qids,
            candidates,
            min_response_score=min_response_score,
            min_margin_ratio=min_margin_ratio,
        )
        figure = create_mapping_grid_figure(
            frequencies if frequencies is not None else np.array([]),
            traces,
            mapping,
            [labels[member] for member in measured_qids],
            candidates,
        )
        set_figure_role(figure, "marked")
        for member in measured_qids:
            outcome = mapping.outcomes[member]
            print(f"[{self.name}] qid={member} {outcome.status}: {outcome.reason}")

        self.save_calibration(backend)
        return RunResult(
            raw_result={
                "mapping": mapping,
                "summary": mapping.summary(),
                "fig": figure,
                "frequency_range": frequencies,
                "qubit_labels": labels,
                "spectroscopy": spectroscopy,
            }
        )

    def batch_run(self, backend: QubexBackend, qids: list[str]) -> RunResult:
        """Not supported: the task measures its whole MUX from one representative."""
        raise NotImplementedError(f"{self.name} runs once per MUX; use run instead")

    # ------------------------------------------------------------------ results

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Publish the mapped candidate of ``qid`` or fail without outputs.

        This is called for every qubit of the MUX. Only a ``"mapped"`` qubit gets
        output parameters; a qubit with no response, an ambiguous response or no
        measurement returns the grid figure and a validation error, so stored
        values that the mapping did not verify are never overwritten.
        """
        raw = run_result.raw_result
        mapping: ResonatorQubitMappingResult = raw["mapping"]
        figure: go.Figure = raw["fig"]
        figures = [figure]
        member = canonical_qid(qid)

        outcome = mapping.outcome(member)
        error: str | None = None
        candidate = mapping.mapped_candidate(member)
        if outcome is None:
            error = f"Resonator mapping did not measure qid={qid}"
        elif candidate is None:
            error = f"Resonator mapping is {outcome.status} for qid={qid}: {outcome.reason}"
        elif not math.isfinite(candidate.frequency) or candidate.frequency <= 0.0:
            error = f"Invalid mapped resonator frequency for qid={qid}: {candidate.frequency}"
        elif not math.isfinite(candidate.readout_amplitude) or candidate.readout_amplitude <= 0.0:
            error = f"Invalid mapped readout amplitude for qid={qid}: {candidate.readout_amplitude}"
        if error is not None or candidate is None:
            message = error or f"Resonator mapping failed for qid={qid}"
            print(f"[ERROR] {message}")
            return PostProcessResult(
                output_parameters={}, figures=figures, validation_error=message
            )

        output_parameters = copy.deepcopy(self.output_parameters)
        output_parameters["resonator_frequency"].value = candidate.frequency
        output_parameters["readout_amplitude"].value = candidate.readout_amplitude
        if candidate.optimal_power is not None and math.isfinite(candidate.optimal_power):
            output_parameters["optimal_power"].value = candidate.optimal_power
        else:
            del output_parameters["optimal_power"]
        for parameter in output_parameters.values():
            parameter.execution_id = execution_id

        moved = (
            "" if candidate.source_qid == member else f" (moved from qid={candidate.source_qid})"
        )
        print(
            f"Mapped qid={qid} to resonator C{candidate.candidate_index} "
            f"{candidate.frequency:.6f} GHz{moved}, readout_amplitude="
            f"{candidate.readout_amplitude:.6f} a.u."
        )
        return PostProcessResult(output_parameters=output_parameters, figures=figures)
