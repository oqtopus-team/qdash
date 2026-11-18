"""Identify a qubit's coarse frequency and resonator from multiplexed readout candidates."""

import copy
import importlib
import inspect
import itertools
import logging
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

import numpy as np
from qubex.experiment.experiment_constants import DEFAULT_SHOTS

from qdash.common.mux_mapping import canonical_qid, resolve_chip_mux_mapping
from qdash.common.visualization.figure_metadata import set_figure_role
from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
    TaskStatusModel,
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
from qdash.workflow.calibtasks.qubex.cw.check_qubit_spectroscopy import (
    MIN_VALID_QUBIT_FREQUENCY,
    compute_coarse_control_amplitude,
)
from qdash.workflow.engine.backend.qubex import QubexBackend

if TYPE_CHECKING:
    import plotly.graph_objs as go

logger = logging.getLogger(__name__)

DEFAULT_QUBIT_FREQUENCY_MAPPING_INTERVAL = 1024.0
MAX_RESONATOR_CANDIDATES = 4
CANDIDATE_PRODUCER_TASK = "CheckResonatorSpectroscopy"
MULTIPLEXED_READOUT_HELPER = "multiplexed_readout_qubit_spectroscopy"
MULTIPLEXED_READOUT_PREREQUISITE = "https://github.com/amachino/qubex/pull/472"
# Provisional separation heuristic: the best candidate's f01 moment must be at least this
# many times the runner-up's. It is NOT empirically calibrated; see the task docstring.
DEFAULT_MIN_SCORE_RATIO = 2.0
MAPPING_EVIDENCE_META_KEY = "qubit_frequency_mapping"
MAPPING_EVIDENCE_SCHEMA = "qdash.qubit_frequency_mapping.v1"
# Names what a mapping figure shows: "selected" (the selected candidate's marked map) or
# "summary" (every candidate and the decision).
MAPPING_FIGURE_META_KEY = "qubit_frequency_mapping_figure"
_PAYLOAD_FREQUENCY_ABS_TOL = 1e-9
_PAYLOAD_AMPLITUDE_REL_TOL = 1e-9
_AXIS_ABS_TOL = 1e-9
# The readout candidates of one acquisition share one readout AWG channel, where their
# tones are summed; the sum of the per-tone amplitudes must stay within this full scale.
MULTIPLEXED_READOUT_AMPLITUDE_BUDGET = 1.0
# Every candidate is read at one shared amplitude: the minimum of the producer's
# requested amplitudes over the whole candidate set.
READOUT_AMPLITUDE_POLICY = "shared_minimum"
READOUT_AMPLITUDE_POLICY_RULE = (
    "every candidate is read at the minimum requested amplitude of all candidates, computed "
    "once over the whole candidate set before grouping and never reduced to fit the budget"
)
# ``readout_grouping`` modes: "frequency_pairs" reads adjacent candidates in frequency
# order together (the two lowest, then the next two, and so on); "multiplexed" reads every
# candidate together. Candidates are not yet assigned to qubits, so their readout slots
# carry no physical meaning and do not affect grouping. The budget applies to the tones
# that are actually read together.
READOUT_GROUPINGS: tuple[str, ...] = ("frequency_pairs", "multiplexed")
DEFAULT_READOUT_GROUPING = "frequency_pairs"
READOUT_GROUPING_RULES: dict[str, str] = {
    "frequency_pairs": (
        "candidates sorted by frequency (ties by index) are partitioned into adjacent pairs "
        "from the lowest frequency, with an odd last candidate alone; within each pair, "
        "candidates in index order join the current group while its shared-amplitude sum "
        "stays <= budget"
    ),
    "multiplexed": (
        "candidates in index order join the current group while its shared-amplitude sum "
        "stays <= budget"
    ),
}
# QDash forms every acquisition itself, so each helper call reads exactly its candidates
# as one group and the helper never re-partitions them.
HELPER_READOUT_GROUPING = "multiplexed"


def load_multiplexed_readout_qubit_spectroscopy() -> Callable[..., Any]:
    """Return the Qubex contrib helper, or raise an error naming the Qubex prerequisite.

    The import is deferred so that registering the task does not require a Qubex
    revision that provides the helper.
    """
    try:
        contrib = importlib.import_module("qubex.contrib")
    except ImportError as exc:
        raise RuntimeError(_missing_helper_message()) from exc
    helper: object = getattr(contrib, MULTIPLEXED_READOUT_HELPER, None)
    if not callable(helper):
        raise RuntimeError(_missing_helper_message())
    try:
        accepts_grouping = "readout_grouping" in inspect.signature(helper).parameters
    except (TypeError, ValueError):
        accepts_grouping = False
    if not accepts_grouping:
        raise RuntimeError(_missing_helper_message())
    return helper


def _missing_helper_message() -> str:
    return (
        "CheckQubitFrequencyMapping requires qubex.contrib."
        f"{MULTIPLEXED_READOUT_HELPER} with the readout_grouping argument, which the "
        "installed qubex does not provide. Install a qubex revision that includes "
        f"{MULTIPLEXED_READOUT_PREREQUISITE} and readout_grouping support, such as the "
        "revision pinned in the QDash uv.lock, in the workflow environment, or run "
        "CheckQubitSpectroscopy instead."
    )


class ProducerAttempt(Protocol):
    """The task result fields that identify one candidate producer attempt."""

    task_id: str
    execution_id: str
    qid: str
    status: str
    start_at: datetime | None


def candidate_source_error(
    attempts: Sequence[ProducerAttempt],
    *,
    qid: str,
    execution_id: str,
    task_id: str,
) -> str | None:
    """Describe why a candidate set is not from the latest complete producer attempt.

    ``attempts`` are the CheckResonatorSpectroscopy task results of every qid in
    the MUX of ``qid``; ``execution_id`` and ``task_id`` identify the result that
    published the candidate set. The set is accepted only when that result
    completed for ``qid``, every result of its execution in the MUX completed, and
    no other execution started a producer attempt in the MUX at or after it. A
    failed, partial, or running later attempt therefore invalidates an older
    successful candidate set instead of leaving it in use.
    """
    source = next((attempt for attempt in attempts if attempt.task_id == task_id), None)
    if source is None:
        return (
            f"no {CANDIDATE_PRODUCER_TASK} task result with task_id={task_id} is recorded "
            "for this MUX"
        )
    if source.execution_id != execution_id:
        return (
            f"{CANDIDATE_PRODUCER_TASK} task result {task_id} belongs to execution "
            f"{source.execution_id}, not {execution_id}"
        )
    if canonical_qid(source.qid) != canonical_qid(qid):
        return f"{CANDIDATE_PRODUCER_TASK} task result {task_id} is for qid={source.qid}"
    for attempt in attempts:
        status = str(getattr(attempt.status, "value", attempt.status))
        if attempt.execution_id == source.execution_id:
            if status != TaskStatusModel.COMPLETED.value:
                return (
                    f"{CANDIDATE_PRODUCER_TASK} in execution {source.execution_id} is "
                    f"{status} for qid={attempt.qid}; the candidate set of that attempt "
                    "is not usable"
                )
            if (
                attempt.task_id != source.task_id
                and canonical_qid(attempt.qid) == canonical_qid(source.qid)
                and _started_at_or_after(attempt, source)
            ):
                return (
                    f"{CANDIDATE_PRODUCER_TASK} ran again for qid={attempt.qid} in "
                    f"execution {source.execution_id} (task_id={attempt.task_id})"
                )
        elif _started_at_or_after(attempt, source):
            return (
                f"a newer {CANDIDATE_PRODUCER_TASK} attempt (execution "
                f"{attempt.execution_id}, qid={attempt.qid}, status={status}) started "
                f"after the candidate set from execution {source.execution_id}"
            )
    return None


def _started_at_or_after(attempt: ProducerAttempt, source: ProducerAttempt) -> bool:
    """Return whether ``attempt`` cannot be shown to start before ``source``."""
    if attempt.start_at is None or source.start_at is None:
        return True
    return attempt.start_at >= source.start_at


@dataclass(frozen=True)
class ResonatorCandidate:
    """One unassigned resonator peak from a CheckResonatorSpectroscopy run."""

    index: int
    frequency: float
    readout_amplitude: float


@dataclass(frozen=True)
class CandidateReadout:
    """A resonator candidate paired with its readout slot and its acquisition group.

    ``readout_label`` is the candidate's own slot whichever group reads it.
    ``readout_group`` numbers the helper call that acquires the candidate; every call
    reads its candidates in one simultaneous acquisition. ``readout_group_position``
    is the candidate's position in that call, which is the ``candidate_index`` the
    helper reports for it. ``frequency_pair`` is the index of the candidate's
    frequency pair (0 for the two lowest frequencies) when ``readout_grouping`` is
    ``"frequency_pairs"``, and None when it is ``"multiplexed"``. ``readout_amplitude`` is the amplitude applied in the
    measurement, shared by every candidate of the set; the producer's own amplitude
    is kept as ``requested_readout_amplitude`` for provenance only.
    """

    candidate: ResonatorCandidate
    readout_label: str
    readout_group: int
    readout_group_position: int
    readout_amplitude: float
    frequency_pair: int | None = None

    @property
    def requested_readout_amplitude(self) -> float:
        """The producer's readout amplitude for this candidate (single-tone optimum)."""
        return self.candidate.readout_amplitude


def shared_readout_amplitude(candidates: Sequence[ResonatorCandidate]) -> float:
    """Return the readout amplitude applied to every candidate: the minimum request.

    Raises ValueError when there is no candidate or a requested amplitude is not
    finite, not positive, or above the readout full scale.
    """
    if not candidates:
        raise ValueError("no resonator candidate to read")
    for candidate in candidates:
        amplitude = candidate.readout_amplitude
        if not (
            math.isfinite(amplitude) and 0.0 < amplitude <= MULTIPLEXED_READOUT_AMPLITUDE_BUDGET
        ):
            raise ValueError(
                f"resonator_candidate_{candidate.index}_readout_amplitude {amplitude!r} must be "
                f"finite, positive, and at most the readout full scale "
                f"{MULTIPLEXED_READOUT_AMPLITUDE_BUDGET:g}"
            )
    return min(candidate.readout_amplitude for candidate in candidates)


def frequency_pairs(
    candidates: Sequence[ResonatorCandidate],
) -> tuple[tuple[ResonatorCandidate, ...], ...]:
    """Return adjacent candidate pairs in ascending frequency, an odd last one alone.

    Candidates are sorted by frequency, ties by candidate index, and paired from
    the lowest frequency, so each pair holds the closest neighbours of the sorted
    order rather than the extremes. Each pair lists its candidates by index.
    """
    ordered = sorted(candidates, key=lambda c: (c.frequency, c.index))
    return tuple(
        tuple(sorted(ordered[start : start + 2], key=lambda c: c.index))
        for start in range(0, len(ordered), 2)
    )


def plan_readout_groups(
    candidates: Sequence[ResonatorCandidate],
    slots: Sequence[str],
    grouping: str = DEFAULT_READOUT_GROUPING,
) -> tuple[CandidateReadout, ...]:
    """Pair each candidate with its slot and split them into budget-safe acquisition groups.

    Every candidate is read at ``shared_readout_amplitude(candidates)``, the minimum
    requested amplitude of the whole set, computed once before grouping. Candidate
    ``i`` in input order keeps slot ``slots[i]`` and its own candidate index.
    ``grouping`` ``"frequency_pairs"`` partitions the candidates with
    ``frequency_pairs``, from the lowest pair up; ``"multiplexed"`` keeps them in one
    partition. Within each partition, candidates in index order join the current
    group while its sum of shared amplitudes stays within
    ``MULTIPLEXED_READOUT_AMPLITUDE_BUDGET`` and otherwise open a new group. A
    partition is therefore one group unless its tones would exceed full scale, and
    the budget is never applied across partitions, which are separate acquisitions.
    The shared amplitude is never reduced to fit the budget. Groups are numbered in
    creation order and list their candidates by candidate index. Returns the
    readouts in candidate order. Raises ValueError when the counts differ, candidate
    indices repeat, ``grouping`` is unknown, or ``shared_readout_amplitude``
    rejects a requested amplitude.
    """
    if len(candidates) != len(slots):
        raise ValueError(f"{len(candidates)} candidates do not match {len(slots)} readout slots")
    if len({candidate.index for candidate in candidates}) != len(candidates):
        raise ValueError("resonator candidate indices are duplicated")
    if grouping not in READOUT_GROUPINGS:
        raise ValueError(
            f"readout_grouping must be one of {list(READOUT_GROUPINGS)}, got {grouping!r}"
        )
    amplitude = shared_readout_amplitude(candidates)
    partitions: list[tuple[int | None, Sequence[ResonatorCandidate]]]
    if grouping == "multiplexed":
        partitions = [(None, list(candidates))]
    else:
        partitions = list(enumerate(frequency_pairs(candidates)))
    bins: list[tuple[int | None, list[ResonatorCandidate]]] = []
    for partition, members_of_partition in partitions:
        partition_bins: list[list[ResonatorCandidate]] = []
        for candidate in sorted(members_of_partition, key=lambda c: c.index):
            if partition_bins and math.fsum([amplitude] * (len(partition_bins[-1]) + 1)) <= (
                MULTIPLEXED_READOUT_AMPLITUDE_BUDGET
            ):
                partition_bins[-1].append(candidate)
            else:
                partition_bins.append([candidate])
        bins.extend((partition, members) for members in partition_bins)
    slot_of = {candidate.index: slot for candidate, slot in zip(candidates, slots, strict=True)}
    readouts = [
        CandidateReadout(
            candidate=candidate,
            readout_label=slot_of[candidate.index],
            readout_group=group,
            readout_group_position=position,
            readout_amplitude=amplitude,
            frequency_pair=partition,
        )
        for group, (partition, members) in enumerate(bins)
        for position, candidate in enumerate(sorted(members, key=lambda c: c.index))
    ]
    return tuple(sorted(readouts, key=lambda r: r.candidate.index))


def readout_groups(
    readouts: Sequence[CandidateReadout],
) -> tuple[tuple[CandidateReadout, ...], ...]:
    """Return the readouts of each acquisition group, ordered by position in the group.

    Raises ValueError unless the groups are numbered from 0 without gaps, every group
    lists positions from 0 without gaps, candidate indices and readout slots are
    unique, every candidate is read at the shared amplitude of the set (the minimum
    requested amplitude), every group's candidates share one frequency pair, and
    every group's amplitude sum is within the readout budget.
    """
    indices = [r.candidate.index for r in readouts]
    labels = [r.readout_label for r in readouts]
    if len(set(indices)) != len(indices) or len(set(labels)) != len(labels):
        raise ValueError("readout candidates or slots are duplicated")
    if readouts:
        shared = shared_readout_amplitude([r.candidate for r in readouts])
        applied = sorted({r.readout_amplitude for r in readouts})
        if applied != [shared]:
            raise ValueError(
                f"applied readout amplitudes {applied} are not the shared minimum requested "
                f"amplitude {shared:.6g}"
            )
    count = 1 + max((r.readout_group for r in readouts), default=-1)
    groups: list[tuple[CandidateReadout, ...]] = []
    for group in range(count):
        members = tuple(
            sorted(
                (r for r in readouts if r.readout_group == group),
                key=lambda r: r.readout_group_position,
            )
        )
        if [r.readout_group_position for r in members] != list(range(len(members))) or (
            not members
        ):
            raise ValueError(f"readout group {group} has inconsistent positions")
        if len({r.frequency_pair for r in members}) != 1:
            raise ValueError(f"readout group {group} mixes frequency pairs")
        amplitude_sum = math.fsum(r.readout_amplitude for r in members)
        if amplitude_sum > MULTIPLEXED_READOUT_AMPLITUDE_BUDGET:
            raise ValueError(
                f"readout group {group} amplitude sum {amplitude_sum:.6g} exceeds "
                f"{MULTIPLEXED_READOUT_AMPLITUDE_BUDGET:g}"
            )
        groups.append(members)
    if sum(len(members) for members in groups) != len(readouts):
        raise ValueError("readout groups do not cover every candidate")
    return tuple(groups)


@dataclass(frozen=True)
class FrequencyMappingRunPayload:
    """The requested candidate readouts and sweep together with one Qubex result per group.

    ``readouts`` are in candidate order; ``results[g]`` is the helper result of
    readout group ``g``. ``readout_grouping`` is the task's grouping mode; every helper
    call uses ``HELPER_READOUT_GROUPING`` so that it reads its group as one acquisition.
    """

    target: str
    readouts: tuple[CandidateReadout, ...]
    results: tuple[Any, ...]
    frequency_range: Any = None
    power_range: Any = None
    readout_grouping: str = DEFAULT_READOUT_GROUPING


@dataclass(frozen=True)
class _CandidateMap:
    """One candidate's validated phase map on the validated sweep axes."""

    frequencies: Any
    powers: Any
    phases: Any


@dataclass(frozen=True)
class _CandidateEvaluation:
    """One candidate's analysis: the raw ``F01Result`` values, or why it has none."""

    readout: CandidateReadout
    frequency: float | None = None
    repr_db: float | None = None
    quality_level: int | None = None
    moment: float | None = None
    error: str | None = None
    marked_figure: Any = field(default=None, compare=False, repr=False)
    candidate_map: _CandidateMap | None = field(default=None, compare=False, repr=False)

    @property
    def has_f01(self) -> bool:
        """Whether the analysis detected an f01 peak, and so produced a moment score."""
        return self.error is None and self.moment is not None

    @property
    def has_response(self) -> bool:
        return self.quality_level is not None and self.quality_level > 0

    @property
    def describe(self) -> str:
        if self.error is not None:
            return f"analysis failed: {self.error}"
        if self.frequency is None or self.quality_level is None or self.moment is None:
            return "no f01 peak"
        return (
            f"f01={self.frequency:.6f} GHz, moment={_format_score(self.moment)}, "
            f"quality_level={self.quality_level}"
        )


@dataclass(frozen=True)
class MappingDecision:
    """The deterministic selection over every candidate, accepted or not.

    ``best`` is the candidate with the highest f01 moment and ``runner_up`` the next
    one among every candidate with an f01 peak, whatever its quality. ``score_ratio``
    is ``best.moment / runner_up.moment``; it is ``None`` when there is no runner-up
    or its moment is zero, or the ratio overflows. ``selected`` is ``best`` only
    when every gate passed.
    """

    reason: str
    selected: _CandidateEvaluation | None = None
    best: _CandidateEvaluation | None = None
    runner_up: _CandidateEvaluation | None = None
    score_ratio: float | None = None
    score_ratio_overflow: bool = False
    ranking: tuple[_CandidateEvaluation, ...] = ()

    @property
    def runner_up_status(self) -> str:
        """``present``, ``zero`` (runner-up moment is 0), or ``absent`` (no runner-up)."""
        if self.runner_up is None:
            return "absent"
        if self.runner_up.moment == 0.0:
            return "zero"
        return "present"


class CheckQubitFrequencyMapping(QubexTask):
    """Task to identify a qubit's coarse frequency and its resonator.

    The task drives one qubit and reads every resonator candidate published by the
    latest CheckResonatorSpectroscopy run of its MUX with multiplexed qubit
    spectroscopy. It analyzes each candidate's map with the CheckQubitSpectroscopy
    analysis and ranks the candidates by the raw f01 ``moment`` of that analysis. It
    publishes the readout and coarse qubit values of the best candidate only when it
    shows a response (``quality_level`` above 0), its f01 is at least 2.5 GHz, and its
    moment is at least ``min_score_ratio`` times the runner-up's, where the runner-up is
    the next candidate with any f01 peak, low quality included. The ``quality_level``
    of each candidate is reported as a diagnostic and is not an acceptance threshold,
    so a low-quality best candidate is selected when it passes the other gates.
    Exact and near ties
    are rejected as ambiguous. The default ratio of 2.0 is a provisional heuristic, not
    an empirically calibrated threshold, and the moment is not normalized: it depends
    on each candidate's resonator response, noise, and readout group. It does not use
    the qubit's existing readout_frequency, so a wrong resonator assignment does not
    affect the result.

    So that the moments are compared under one readout condition, every candidate is
    read at one shared amplitude: the minimum of the producer's requested amplitudes
    over the whole candidate set, computed once before grouping. The requested
    amplitudes are kept as provenance only. A common amplitude does not remove the
    differences in resonator response or noise between candidates. The candidate
    tones of one acquisition share the MUX readout AWG channel, so their amplitudes
    must sum to at most full scale. The ``readout_grouping`` run parameter selects
    which candidates are read together: ``frequency_pairs`` (default) sorts them by
    frequency and reads adjacent pairs, the two lowest and then the two highest of
    four candidates, so the tones read together stay close; ``multiplexed`` reads
    them all together. The candidates are not yet assigned to qubits, so their
    readout slots carry no physical meaning, and grouping never uses qubit indices.
    Within each pair, or within all candidates, candidates in index order join the
    current acquisition group while its sum of shared amplitudes stays within full
    scale, so a group is split further only when its tones would exceed full scale;
    the shared amplitude is never reduced to fit. Each group is one helper call with
    the same drive sweep and readout amplitude and ``readout_grouping="multiplexed"``,
    so the helper reads exactly that group and must report it as one acquisition; a
    candidate keeps its readout slot and candidate index whichever group reads it. A requested amplitude that is not finite and
    positive or exceeds full scale is rejected before any measurement. A failed group
    or an inconsistent group result fails the task without outputs.

    When a candidate is selected, the first figure is that candidate's marked map
    with its f01 marker, titled with the qid, the candidate's readout identity and
    its score; the summary figure follows. Without a selection the summary figure
    comes first. The remaining figures are each candidate's marked and raw figures in
    candidate order, without repeating the selected marked figure. The summary lists
    every candidate's moment, quality level, f01, readout frequency and power, the
    ranking, runner-up margin, and the selection or rejection reason. The summary
    and the selected figure both carry that evidence as JSON under
    ``layout.meta["qubit_frequency_mapping"]``, so the AI evaluation of a task
    result, which reads the first figure, keeps every candidate's evidence.

    The candidate set must come from a CheckResonatorSpectroscopy run with
    ``detection_only`` set, and that run must be the latest complete producer
    attempt in the MUX: a newer, failed, or partial attempt rejects the task before
    any measurement. Each candidate's map is analyzed from its phase data on the
    measured sweep axes, never from a figure.

    Requires a Qubex revision that provides
    ``qubex.contrib.multiplexed_readout_qubit_spectroscopy`` with its
    ``readout_grouping`` argument.
    """

    name: str = "CheckQubitFrequencyMapping"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "resonator_candidate_count": InputParameterSpec.required_database(
            user_override="forbidden",
            unit="",
            value_type="int",
            description="Number of resonator candidates from CheckResonatorSpectroscopy.",
            ui_group="Resonator candidates",
            ui_group_collapsed=True,
        ),
        "resonator_candidate_0_frequency": InputParameterSpec.database_optional(
            user_override="forbidden",
            unit="GHz",
            description="Frequency of resonator candidate 0.",
            ui_group="Resonator candidates",
            ui_group_collapsed=True,
        ),
        "resonator_candidate_0_readout_amplitude": InputParameterSpec.database_optional(
            user_override="forbidden",
            unit="a.u.",
            description="Readout amplitude of resonator candidate 0.",
            ui_group="Resonator candidates",
            ui_group_collapsed=True,
        ),
        "resonator_candidate_1_frequency": InputParameterSpec.database_optional(
            user_override="forbidden",
            unit="GHz",
            description="Frequency of resonator candidate 1.",
            ui_group="Resonator candidates",
            ui_group_collapsed=True,
        ),
        "resonator_candidate_1_readout_amplitude": InputParameterSpec.database_optional(
            user_override="forbidden",
            unit="a.u.",
            description="Readout amplitude of resonator candidate 1.",
            ui_group="Resonator candidates",
            ui_group_collapsed=True,
        ),
        "resonator_candidate_2_frequency": InputParameterSpec.database_optional(
            user_override="forbidden",
            unit="GHz",
            description="Frequency of resonator candidate 2.",
            ui_group="Resonator candidates",
            ui_group_collapsed=True,
        ),
        "resonator_candidate_2_readout_amplitude": InputParameterSpec.database_optional(
            user_override="forbidden",
            unit="a.u.",
            description="Readout amplitude of resonator candidate 2.",
            ui_group="Resonator candidates",
            ui_group_collapsed=True,
        ),
        "resonator_candidate_3_frequency": InputParameterSpec.database_optional(
            user_override="forbidden",
            unit="GHz",
            description="Frequency of resonator candidate 3.",
            ui_group="Resonator candidates",
            ui_group_collapsed=True,
        ),
        "resonator_candidate_3_readout_amplitude": InputParameterSpec.database_optional(
            user_override="forbidden",
            unit="a.u.",
            description="Readout amplitude of resonator candidate 3.",
            ui_group="Resonator candidates",
            ui_group_collapsed=True,
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "simultaneous_drive": RunParameterSpec(
            unit="a.u.",
            value_type="bool",
            default=True,
            description=(
                "Whether control and readout pulses start together. "
                "False starts readout after the control pulse ends."
            ),
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=DEFAULT_SHOTS,
            description="Number of shots per sweep point",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=DEFAULT_QUBIT_FREQUENCY_MAPPING_INTERVAL,
            description="Time interval between shots",
        ),
        "frequency_range": RunParameterSpec(
            unit="GHz",
            value_type="np.arange",
            default=None,
            description=(
                "Drive frequency range as [start, stop, step] in GHz. Leave blank to use "
                "the connected control box's qubex default: low band "
                "[3.0, 5.75, 0.005], high band [6.5, 9.75, 0.005]."
            ),
        ),
        "power_range": RunParameterSpec(
            unit="dB",
            value_type="np.arange",
            default=(-60, 0, 5),
            description=(
                "Drive power range as [start, stop, step] in dB. The QDash default is "
                "[-60, 0, 5] dB. The stop value is exclusive."
            ),
        ),
        "min_score_ratio": RunParameterSpec(
            unit="",
            value_type="float",
            default=DEFAULT_MIN_SCORE_RATIO,
            description=(
                "Minimum ratio of the best candidate's f01 moment to the runner-up's "
                "(any candidate with an f01 peak) required to select it. Must be greater "
                "than 1. The default 2.0 is a provisional heuristic, not empirically "
                "calibrated."
            ),
        ),
        "readout_grouping": RunParameterSpec(
            unit="",
            value_type="str",
            default=DEFAULT_READOUT_GROUPING,
            description=(
                "How resonator candidates are read together: frequency_pairs (default) "
                "sorts them by frequency and reads adjacent pairs (the two lowest, then the "
                "next two) in separate acquisitions; multiplexed reads every candidate in "
                "one acquisition. Every candidate is read at the minimum "
                "requested readout amplitude of the candidate set, and an acquisition whose "
                "amplitude sum would exceed full scale is split further."
            ),
        ),
    }
    _analysis_config: ClassVar[EstimateQubitFrequencyConfig] = EstimateQubitFrequencyConfig()
    _retry_with_trim: ClassVar[bool] = True
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "resonator_frequency": OutputParameterSpec(
            unit="GHz",
            description=("Frequency of the resonator candidate that shows this qubit's response."),
            publish_targets=(
                "resonator_frequency",
                "readout_frequency",
            ),
        ),
        "readout_amplitude": OutputParameterSpec(
            unit="a.u.",
            description=(
                "Readout amplitude applied to the selected resonator candidate: the "
                "minimum requested amplitude of the candidate set, shared by every "
                "candidate."
            ),
        ),
        "resonator_candidate_index": OutputParameterSpec(
            unit="",
            value_type="int",
            description=(
                "Index of the selected candidate in the frequency-sorted candidate set "
                "of CheckResonatorSpectroscopy."
            ),
        ),
        "coarse_qubit_frequency": OutputParameterSpec(
            unit="GHz",
            description=(
                "Coarse f01 estimate from the selected candidate's spectroscopy. NOT a "
                "calibrated qubit_frequency; a seed for frequency-refinement tasks."
            ),
            publish_targets=(
                "coarse_qubit_frequency",
                "control_frequency",
            ),
        ),
        "f01_repr_db": OutputParameterSpec(
            unit="dB",
            description="Representative drive power of the selected f01 peak.",
        ),
        "f01_quality_level": OutputParameterSpec(
            unit="a.u.",
            description=(
                "Discrete quality score (0..len(f01_moment_thresholds)) of the selected "
                "f01 peak. Higher = more confident."
            ),
        ),
        "coarse_control_amplitude": OutputParameterSpec(
            unit="a.u.",
            description=(
                "Coarse drive-amplitude seed derived from f01_repr_db with the same "
                "headroom as CheckQubitSpectroscopy. NOT a calibrated control_amplitude."
            ),
        ),
    }

    def _candidate_set(self) -> list[ResonatorCandidate]:
        """Return the validated, frequency-sorted candidates from one producer result.

        Raises ValueError when the count is missing or out of range, when a candidate
        value is missing, non-finite, or not positive, when a readout amplitude exceeds
        the readout full scale, when frequencies are not strictly increasing, or when
        any value comes from a different producer result than the count.
        """
        count_param = self.input_parameters["resonator_candidate_count"]
        count_value = count_param.value
        if (
            count_value is None
            or isinstance(count_value, bool)
            or not float(count_value).is_integer()
            or not 1 <= int(count_value) <= MAX_RESONATOR_CANDIDATES
        ):
            raise ValueError(
                "resonator_candidate_count must be an integer from 1 to "
                f"{MAX_RESONATOR_CANDIDATES}, got {count_value!r}; run "
                "CheckResonatorSpectroscopy for this MUX until it detects resonator peaks"
            )
        source = (count_param.execution_id, count_param.task_id)
        if not all(source):
            raise ValueError(
                "resonator_candidate_count has no execution_id/task_id provenance; the "
                "candidate set must come from one CheckResonatorSpectroscopy result"
            )

        candidates: list[ResonatorCandidate] = []
        for index in range(int(count_value)):
            values: dict[str, float] = {}
            for kind in ("frequency", "readout_amplitude"):
                name = f"resonator_candidate_{index}_{kind}"
                parameter = self.input_parameters[name]
                value = parameter.value
                if (
                    value is None
                    or isinstance(value, bool)
                    or not math.isfinite(float(value))
                    or float(value) <= 0.0
                ):
                    raise ValueError(f"{name} must be finite and positive, got {value!r}")
                if kind == "readout_amplitude" and float(value) > (
                    MULTIPLEXED_READOUT_AMPLITUDE_BUDGET
                ):
                    raise ValueError(
                        f"{name} must not exceed the readout full scale "
                        f"{MULTIPLEXED_READOUT_AMPLITUDE_BUDGET:g}, got {value!r}"
                    )
                if (parameter.execution_id, parameter.task_id) != source:
                    raise ValueError(
                        f"{name} does not come from the same CheckResonatorSpectroscopy "
                        f"result as resonator_candidate_count (execution_id={source[0]}, "
                        f"task_id={source[1]})"
                    )
                values[kind] = float(value)
            candidates.append(
                ResonatorCandidate(
                    index=index,
                    frequency=values["frequency"],
                    readout_amplitude=values["readout_amplitude"],
                )
            )
        frequencies = [candidate.frequency for candidate in candidates]
        if any(high <= low for low, high in itertools.pairwise(frequencies)):
            raise ValueError(
                f"Resonator candidate frequencies must be strictly increasing, got {frequencies}"
            )
        return candidates

    def _candidate_source(self) -> tuple[str, str]:
        """Return the ``(execution_id, task_id)`` of the validated candidate set."""
        count_param = self.input_parameters["resonator_candidate_count"]
        return count_param.execution_id, count_param.task_id

    def _verify_candidate_source(self, backend: QubexBackend, qid: str) -> None:
        """Reject a candidate set that is not from the latest complete producer attempt.

        Reads the CheckResonatorSpectroscopy task results of every qid in the MUX of
        ``qid`` on this chip. Raises ValueError when the backend has no project or
        chip context, or when ``candidate_source_error`` reports a problem.
        """
        project_id = backend.config.get("project_id")
        chip_id = backend.config.get("chip_id")
        if not project_id or not chip_id:
            raise ValueError(
                "CheckQubitFrequencyMapping needs project_id and chip_id to verify that "
                "its resonator candidates come from the latest CheckResonatorSpectroscopy "
                "attempt"
            )
        from qdash.repository import MongoTaskResultHistoryRepository

        mapping = resolve_chip_mux_mapping(project_id, chip_id)
        mux_id = mapping.find_mux(qid)
        mux_qids = {canonical_qid(qid)} if mux_id is None else set(mapping.qids_of(mux_id))
        attempts = MongoTaskResultHistoryRepository().find(
            {
                "project_id": project_id,
                "chip_id": chip_id,
                "name": CANDIDATE_PRODUCER_TASK,
                "qid": {"$in": sorted(mux_qids | {qid})},
            }
        )
        execution_id, task_id = self._candidate_source()
        error = candidate_source_error(
            attempts, qid=qid, execution_id=execution_id, task_id=task_id
        )
        if error is not None:
            raise ValueError(
                f"Resonator candidates for qid={qid} are stale or incomplete: {error}. "
                "Run CheckResonatorSpectroscopy with detection_only for this MUX and "
                "rerun CheckQubitFrequencyMapping after it completes."
            )

    @staticmethod
    def _readout_slots(exp: Any, label: str, count: int) -> list[str]:
        """Return ``count`` readout labels of the target's MUX, sorted by label."""
        mux = exp.ctx.experiment_system.get_mux_by_qubit(label)
        slots = sorted(
            str(resonator.label)
            for resonator in mux.resonators
            if getattr(resonator, "is_valid", True)
        )
        if len(slots) < count:
            raise ValueError(
                f"The MUX of {label} has {len(slots)} configured readout slots {slots}, "
                f"fewer than the {count} resonator candidates"
            )
        return slots[:count]

    def _frequency_range(self) -> Any:
        """Return an explicit override, or let qubex select by control box type."""
        parameter = self.run_parameters["frequency_range"]
        return None if parameter.value is None else parameter.get_value()

    def resolve_run_parameters(self, backend: QubexBackend, qid: str) -> None:
        """Populate the effective device-specific sweep before it is recorded."""
        super().resolve_run_parameters(backend, qid)
        parameter = self.run_parameters["frequency_range"]
        if parameter.value is not None:
            return

        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        box = exp.ctx.experiment_system.get_control_box_for_qubit(label)
        parameter.value = tuple(box.traits.default_control_frequency_range)

    def _min_score_ratio(self) -> float:
        """Return the validated ``min_score_ratio`` run parameter.

        Raises ValueError unless it is a finite number greater than 1, because a ratio
        of 1 or less would accept an exact tie.
        """
        value = self.run_parameters["min_score_ratio"].value
        ratio = (
            float(value)
            if isinstance(value, int | float) and not isinstance(value, bool)
            else math.nan
        )
        if not math.isfinite(ratio) or ratio <= 1.0:
            raise ValueError(
                f"min_score_ratio must be a finite number greater than 1, got {value!r}"
            )
        return ratio

    def _readout_grouping(self) -> str:
        """Return the validated ``readout_grouping`` run parameter.

        Raises ValueError unless it is ``"frequency_pairs"`` or ``"multiplexed"``.
        """
        value = self.run_parameters["readout_grouping"].value
        if value not in READOUT_GROUPINGS:
            raise ValueError(
                f"readout_grouping must be one of {list(READOUT_GROUPINGS)}, got {value!r}"
            )
        return str(value)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Drive the qubit with the same sweep once per budget-safe acquisition group.

        Under ``readout_grouping="frequency_pairs"`` the candidates are first split
        into adjacent frequency pairs, so the amplitude budget applies to the tones
        that are read together. Every group calls the Qubex helper with the same drive
        target and settings and ``readout_grouping="multiplexed"``, so the helper reads
        exactly that group, at the shared readout amplitude of the candidate set. Raises RuntimeError naming the group when a
        helper call fails, so no group result is published.
        """
        self._min_score_ratio()
        grouping = self._readout_grouping()
        candidates = self._candidate_set()
        self._verify_candidate_source(backend, qid)
        helper = load_multiplexed_readout_qubit_spectroscopy()
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        slots = self._readout_slots(exp, label, len(candidates))
        readouts = plan_readout_groups(candidates, slots, grouping)
        groups = readout_groups(readouts)
        print(f"Qubit frequency mapping for qid={qid}: {_readout_groups_text(groups, grouping)}")
        frequency_range = self._frequency_range()
        power_range = self.run_parameters["power_range"].get_value()
        settings = {
            "frequency_range": frequency_range,
            "power_range": power_range,
            "simultaneous_drive": self.run_parameters["simultaneous_drive"].get_value(),
            "shots": self.run_parameters["shots"].get_value(),
            "interval": self.run_parameters["interval"].get_value(),
            "readout_grouping": HELPER_READOUT_GROUPING,
            "plot": False,
            "save_image": False,
        }
        results = tuple(
            _measure_readout_group(
                helper, exp, label, members, group=group, group_count=len(groups), settings=settings
            )
            for group, members in enumerate(groups)
        )
        return RunResult(
            raw_result=FrequencyMappingRunPayload(
                target=label,
                readouts=readouts,
                results=results,
                frequency_range=frequency_range,
                power_range=power_range,
                readout_grouping=grouping,
            )
        )

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Select the best-scoring candidate when it passes every gate, or fail without outputs.

        Every candidate is analyzed from its validated phase data on the validated
        sweep axes; the figures in the Qubex result are not used. On selection the
        selected candidate's marked figure comes first and the summary figure with
        the decision evidence second; on rejection the summary comes first. A marked
        and a raw figure, both built from that data, follow for every analyzable
        candidate in candidate order, except the selected marked figure already
        shown first. On rejection the validation error is one line that names the
        reason and every candidate's scores.
        """
        payload = run_result.raw_result
        if not isinstance(payload, FrequencyMappingRunPayload):
            return self._reject(f"Unexpected run result for qid={qid}: {type(payload)!r}", [])

        try:
            min_score_ratio = self._min_score_ratio()
        except ValueError as exc:
            return self._reject(f"{exc} for qid={qid}", [])

        common_error, axes, candidate_payloads = self._merged_group_results(payload)
        evaluations: list[_CandidateEvaluation] = []
        figures: list[go.Figure] = []
        if common_error is not None or axes is None:
            evaluations = [
                _CandidateEvaluation(readout=readout, error=f"not analyzed: {common_error}")
                for readout in payload.readouts
            ]
            decision = MappingDecision(reason=f"Malformed result: {common_error}")
        else:
            frequencies, powers = axes
            for readout in payload.readouts:
                evaluation, candidate_figures = self._evaluate_candidate(
                    readout,
                    candidate_payloads.get(readout.candidate.index),
                    frequencies,
                    powers,
                )
                evaluations.append(evaluation)
                figures.extend(candidate_figures)
            decision = self._select(evaluations, min_score_ratio)

        summary = _decision_summary(decision, evaluations, min_score_ratio)
        print(f"Qubit frequency mapping for qid={qid}: {summary}")
        selected = decision.selected
        proposal = _proposal(decision.selected or decision.best)
        evidence = mapping_evidence(
            qid=qid,
            payload=payload,
            axes=axes,
            evaluations=evaluations,
            decision=decision,
            min_score_ratio=min_score_ratio,
            proposal=proposal,
        )
        summary_figure = _summary_figure(qid, evaluations, decision, evidence)
        if selected is None:
            return self._reject(
                f"{decision.reason} for qid={qid}: {summary}", [summary_figure, *figures]
            )

        assert selected.frequency is not None
        assert selected.repr_db is not None
        assert selected.quality_level is not None
        assert proposal is not None
        coarse_control_amplitude = proposal["coarse_control_amplitude"]
        _, marker_db = compute_coarse_control_amplitude(selected.repr_db)
        selected.marked_figure.add_hline(
            y=marker_db,
            line_width=1,
            line_color="red",
            line_dash="dash",
            annotation_text=f"coarse A = {coarse_control_amplitude:.4f} a.u.",
            annotation_position="top left",
            annotation_font_color="red",
        )
        selected_figure = _mark_selected_figure(
            selected.marked_figure, qid, selected, decision, evidence
        )
        figures = [
            selected_figure,
            summary_figure,
            *(fig for fig in figures if fig is not selected_figure),
        ]

        candidate = selected.readout.candidate
        outputs = copy.deepcopy(self.output_parameters)
        outputs["resonator_frequency"].value = candidate.frequency
        outputs["readout_amplitude"].value = selected.readout.readout_amplitude
        outputs["resonator_candidate_index"].value = candidate.index
        outputs["coarse_qubit_frequency"].value = selected.frequency
        outputs["f01_repr_db"].value = selected.repr_db
        outputs["f01_quality_level"].value = selected.quality_level
        outputs["coarse_control_amplitude"].value = coarse_control_amplitude
        for value in outputs.values():
            value.execution_id = execution_id
        print(
            f"Selected resonator candidate {candidate.index} for qid={qid}: "
            f"readout_frequency={candidate.frequency:.6f} GHz, "
            f"readout_amplitude={selected.readout.readout_amplitude:.6f} a.u. "
            f"(shared minimum, requested "
            f"{selected.readout.requested_readout_amplitude:.6f} a.u., "
            f"readout group {selected.readout.readout_group}), "
            f"coarse_qubit_frequency={selected.frequency:.6f} GHz, "
            f"coarse_control_amplitude={coarse_control_amplitude:.6f} a.u. ({decision.reason})"
        )
        return PostProcessResult(output_parameters=outputs, figures=figures)

    @staticmethod
    def _reject(message: str, figures: list[Any]) -> PostProcessResult:
        # The task message must stay on one line: evaluation reads its first line only.
        message = " ".join(message.split())
        print(f"[ERROR] {message}")
        return PostProcessResult(output_parameters={}, figures=figures, validation_error=message)

    @classmethod
    def _merged_group_results(
        cls, payload: FrequencyMappingRunPayload
    ) -> tuple[str | None, Any, dict[int, Any]]:
        """Validate every group result and merge the candidate payloads by candidate index.

        Returns ``(error, axes, payloads)``: ``axes`` are the common validated
        ``(frequencies, powers)`` and ``payloads`` maps each global candidate index to
        its group's candidate payload, which still carries the helper-local
        ``candidate_index``. Any inconsistent group plan, missing or extra group result,
        malformed group result, or group whose axes differ from the first group's
        returns an error and no payloads, so no group is published alone.
        """
        try:
            groups = readout_groups(payload.readouts)
        except ValueError as exc:
            return f"inconsistent readout groups: {exc}", None, {}
        if len(payload.results) != len(groups):
            return (
                f"{len(payload.results)} group results do not match {len(groups)} readout groups",
                None,
                {},
            )
        axes: tuple[Any, Any] | None = None
        merged: dict[int, Any] = {}
        for group, (members, result) in enumerate(zip(groups, payload.results, strict=True)):
            data = getattr(result, "data", None)
            error, group_axes = cls._common_axes(payload, members, data)
            if error is not None or group_axes is None:
                return f"readout group {group}: {error}", None, {}
            if axes is None:
                axes = group_axes
            elif not all(
                _same_axis(mine, first) for mine, first in zip(group_axes, axes, strict=True)
            ):
                return (
                    f"readout group {group}: sweep axes differ from readout group 0",
                    None,
                    {},
                )
            assert isinstance(data, Mapping)
            for readout in members:
                merged[readout.candidate.index] = data["candidates"].get(readout.readout_label)
        return None, axes, merged

    @staticmethod
    def _common_axes(
        payload: FrequencyMappingRunPayload,
        members: Sequence[CandidateReadout],
        data: Any,
    ) -> tuple[str | None, Any]:
        """Return one group result's validated ``(frequencies, powers)`` axes, or the error.

        The result must name the drive target and exactly the group's readout slots in
        group order, report ``HELPER_READOUT_GROUPING``, and report the group
        as one acquisition in ``readout_groups``, so the helper did not split it. The axes must be finite, strictly increasing, and equal to the
        requested sweep when the run recorded one.
        """
        if not isinstance(data, Mapping):
            return "result has no data mapping", None
        if data.get("target") != payload.target:
            return f"target {data.get('target')!r} does not match {payload.target!r}", None
        requested_labels = [readout.readout_label for readout in members]
        labels = data.get("readout_labels")
        if labels is None or list(labels) != requested_labels:
            return f"readout_labels {labels!r} do not match {requested_labels}", None
        if data.get("readout_grouping") != HELPER_READOUT_GROUPING:
            return (
                f"readout_grouping {data.get('readout_grouping')!r} does not match "
                f"{HELPER_READOUT_GROUPING!r}"
            ), None
        acquisitions = data.get("readout_groups")
        if (
            not isinstance(acquisitions, Sequence)
            or isinstance(acquisitions, str)
            or [list(group) for group in acquisitions] != [requested_labels]
        ):
            return (
                f"readout_groups {acquisitions!r} are not one acquisition of {requested_labels}"
            ), None
        candidates = data.get("candidates")
        if not isinstance(candidates, Mapping):
            return "result has no candidates mapping", None
        if set(candidates) - set(requested_labels):
            extra = sorted(set(candidates) - set(requested_labels))
            return f"candidates {extra} were not requested in this group", None
        axes: list[Any] = []
        for name, requested in (
            ("frequency_range", payload.frequency_range),
            ("power_range", payload.power_range),
        ):
            values, error = _finite_axis(data.get(name), name)
            if error is not None:
                return error, None
            if requested is not None and not _same_axis(values, requested):
                return f"{name} does not match the requested sweep", None
            axes.append(values)
        return None, (axes[0], axes[1])

    def _evaluate_candidate(
        self,
        readout: CandidateReadout,
        candidate_data: Any,
        frequencies: Any,
        powers: Any,
    ) -> tuple[_CandidateEvaluation, list[Any]]:
        """Validate one candidate's payload and analyze its phase map."""
        label = readout.readout_label
        payload_error, candidate_map = self._candidate_map(
            readout, candidate_data, frequencies, powers
        )
        if payload_error is not None or candidate_map is None:
            return _CandidateEvaluation(readout=readout, error=f"{label}: {payload_error}"), []
        raw_fig = _candidate_figure(readout, candidate_map)
        set_figure_role(raw_fig, "raw")
        try:
            marked_fig, freq_result = estimate_and_mark_qubit_figure(
                raw_fig, self._analysis_config, retry_with_trim=self._retry_with_trim
            )
        except Exception as exc:
            logger.warning("Failed to analyze readout candidate %s", label, exc_info=True)
            return (
                _CandidateEvaluation(
                    readout=readout,
                    error=f"{label}: {type(exc).__name__}: {exc}",
                    candidate_map=candidate_map,
                ),
                [raw_fig],
            )

        f01 = freq_result.f01
        evaluation = (
            _CandidateEvaluation(readout=readout, candidate_map=candidate_map)
            if f01 is None
            else _CandidateEvaluation(
                readout=readout,
                frequency=float(f01.frequency),
                repr_db=float(f01.repr_db),
                quality_level=int(f01.quality_level),
                moment=float(f01.moment),
                candidate_map=candidate_map,
            )
        )
        set_figure_role(marked_fig, "marked")
        marked_fig.add_annotation(
            xref="paper",
            yref="paper",
            x=0.01,
            y=1.0,
            text=f"candidate {readout.candidate.index}: {evaluation.describe}",
            showarrow=False,
            font={"color": "red", "size": 11},
            align="left",
        )
        return replace(evaluation, marked_figure=marked_fig), [marked_fig, raw_fig]

    @staticmethod
    def _candidate_map(
        readout: CandidateReadout,
        candidate_data: Any,
        frequencies: Any,
        powers: Any,
    ) -> tuple[str | None, _CandidateMap | None]:
        """Return one candidate's validated phase map, or why its payload is rejected.

        The payload must name the requested readout slot, the candidate's position in
        its readout group (the helper numbers candidates per call), acquisition 0 of
        the call as ``readout_group_index``, the readout
        frequency, and the applied (shared) readout amplitude, carry the common sweep axes,
        and hold a finite real ``phases`` array of shape ``(powers, frequencies)``. A
        ``data`` array, which Qubex defines as the same array as ``phases``, must
        equal it. The caller keeps the global candidate index of ``readout``.
        """
        candidate = readout.candidate
        if not isinstance(candidate_data, Mapping):
            return "missing candidate payload", None
        if candidate_data.get("readout_label") != readout.readout_label:
            return (
                f"readout_label {candidate_data.get('readout_label')!r} "
                f"does not match {readout.readout_label!r}"
            ), None
        local_index = candidate_data.get("candidate_index")
        if (
            isinstance(local_index, bool)
            or not isinstance(local_index, int | np.integer)
            or local_index != readout.readout_group_position
        ):
            return (
                f"candidate_index {local_index!r} does not match position "
                f"{readout.readout_group_position} of candidate {candidate.index} in "
                f"readout group {readout.readout_group}"
            ), None
        acquisition = candidate_data.get("readout_group_index")
        if (
            isinstance(acquisition, bool)
            or not isinstance(acquisition, int | np.integer)
            or (acquisition != 0)
        ):
            return (
                f"readout_group_index {acquisition!r} is not the single acquisition 0 of "
                f"readout group {readout.readout_group}"
            ), None
        try:
            frequency = float(candidate_data["readout_frequency"])
            amplitude = float(candidate_data["readout_amplitude"])
        except (KeyError, TypeError, ValueError):
            return "missing readout_frequency or readout_amplitude", None
        if not math.isclose(frequency, candidate.frequency, abs_tol=_PAYLOAD_FREQUENCY_ABS_TOL):
            return f"readout_frequency {frequency} does not match {candidate.frequency}", None
        if not math.isclose(
            amplitude, readout.readout_amplitude, rel_tol=_PAYLOAD_AMPLITUDE_REL_TOL
        ):
            return (
                f"readout_amplitude {amplitude:.6g} does not match the applied "
                f"{readout.readout_amplitude:.6g}"
            ), None
        for name, common in (("frequency_range", frequencies), ("power_range", powers)):
            values, error = _finite_axis(candidate_data.get(name), name)
            if error is not None:
                return error, None
            if not _same_axis(values, common):
                return f"{name} does not match the result's {name}", None
        phases, error = _finite_map(candidate_data.get("phases"), (len(powers), len(frequencies)))
        if error is not None:
            return f"phases: {error}", None
        if "data" in candidate_data:
            data, error = _finite_map(candidate_data["data"], phases.shape)
            if error is not None or not np.array_equal(data, phases):
                return "data does not equal phases", None
        return None, _CandidateMap(frequencies=frequencies, powers=powers, phases=phases)

    def _select(
        self, evaluations: list[_CandidateEvaluation], min_score_ratio: float
    ) -> MappingDecision:
        """Rank the candidates by f01 moment and accept the best only if every gate passes.

        Any candidate analysis error or a non-finite or negative moment rejects the
        result. Candidates with an f01 peak are ranked by moment, ties broken by
        candidate index so that the decision does not depend on candidate order. The
        best candidate is selected only when it shows a response (``quality_level``
        above 0), its f01 is finite and at least ``MIN_VALID_QUBIT_FREQUENCY``, and its
        moment is at least ``min_score_ratio`` times the runner-up's. A low
        ``quality_level`` does not reject the best candidate; it stays a diagnostic. Without a runner-up, or with a
        runner-up moment of zero, the separation gate passes and the ratio is None.
        """
        failed = [e for e in evaluations if e.error is not None]
        if failed:
            indices = [e.readout.candidate.index for e in failed]
            return MappingDecision(reason=f"Readout candidate analysis failed on {indices}")
        invalid = [
            e
            for e in evaluations
            if e.moment is not None and not (math.isfinite(e.moment) and e.moment >= 0.0)
        ]
        if invalid:
            details = ", ".join(
                f"candidate {e.readout.candidate.index}={e.moment!r}" for e in invalid
            )
            return MappingDecision(reason=f"Invalid f01 moment score ({details})")

        ranking = tuple(
            sorted(
                (e for e in evaluations if e.has_f01),
                key=lambda e: (-(e.moment or 0.0), e.readout.candidate.index),
            )
        )
        best = ranking[0] if ranking else None
        runner_up = ranking[1] if len(ranking) > 1 else None
        score_ratio: float | None = None
        score_ratio_overflow = False
        if best is not None and runner_up is not None and runner_up.moment:
            assert best.moment is not None
            score_ratio = best.moment / runner_up.moment
            if not math.isfinite(score_ratio):
                score_ratio = None
                score_ratio_overflow = True
        decision = MappingDecision(
            reason="",
            best=best,
            runner_up=runner_up,
            score_ratio=score_ratio,
            score_ratio_overflow=score_ratio_overflow,
            ranking=ranking,
        )

        if best is None or not best.has_response:
            return replace(decision, reason="No readout candidate shows a qubit response")
        assert best.frequency is not None
        assert best.quality_level is not None
        index = best.readout.candidate.index
        if runner_up is not None and best.moment == runner_up.moment:
            return replace(decision, reason="Ambiguous qubit response: tied best moment scores")
        if best.moment is None or best.moment <= 0:
            return replace(decision, reason="Best candidate has no positive moment score")
        if not math.isfinite(best.frequency) or best.frequency < MIN_VALID_QUBIT_FREQUENCY:
            return replace(
                decision,
                reason=(
                    f"Qubit frequency of best candidate {index} is below "
                    f"{MIN_VALID_QUBIT_FREQUENCY} GHz"
                ),
            )
        # Dividing the best by the threshold avoids overflowing best / runner-up.
        if (
            runner_up is not None
            and runner_up.moment is not None
            and runner_up.moment > 0
            and best.moment / min_score_ratio < runner_up.moment
        ):
            assert runner_up is not None
            assert score_ratio is not None
            return replace(
                decision,
                reason=(
                    f"Ambiguous qubit response: best candidate {index} moment is "
                    f"{score_ratio:.3g}x runner-up candidate {runner_up.readout.candidate.index}, "
                    f"below min_score_ratio {min_score_ratio:g}"
                ),
            )
        if runner_up is None:
            separation = "it is the only candidate with an f01 peak"
        elif score_ratio_overflow:
            separation = (
                "its score ratio exceeds the finite floating-point range (overflow); "
                "the positive runner-up passes the overflow-safe separation comparison"
            )
        elif score_ratio is None:
            separation = (
                f"runner-up candidate {runner_up.readout.candidate.index} has a zero moment"
            )
        else:
            separation = (
                f"its moment is {score_ratio:.3g}x runner-up candidate "
                f"{runner_up.readout.candidate.index} (min_score_ratio {min_score_ratio:g})"
            )
        return replace(
            decision,
            selected=best,
            reason=f"Selected candidate {index}: {separation}",
        )


def _measure_readout_group(
    helper: Callable[..., Any],
    exp: Any,
    target: str,
    members: Sequence[CandidateReadout],
    *,
    group: int,
    group_count: int,
    settings: Mapping[str, Any],
) -> Any:
    """Acquire one readout group with the helper, or raise RuntimeError naming the group.

    The helper reads the group's slots in group order at the shared applied amplitude.
    """
    try:
        return helper(
            exp,
            target,
            readout_frequencies={r.readout_label: r.candidate.frequency for r in members},
            readout_amplitudes={r.readout_label: r.readout_amplitude for r in members},
            **settings,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Readout group {group} of {group_count} "
            f"(candidates {[r.candidate.index for r in members]}) failed: "
            f"{type(exc).__name__}: {exc}; no candidate result is published"
        ) from exc


def _format_score(value: float | None) -> str:
    return "none" if value is None else f"{value:.6g}"


def _readout_power_db(amplitude: float) -> float:
    """Return the readout power in dB of a positive readout amplitude, ``20*log10(a)``."""
    return float(20 * math.log10(amplitude))


def _runner_up_text(decision: MappingDecision) -> str:
    if decision.runner_up is None:
        return "runner-up absent (no other candidate with an f01 peak)"
    runner_index = decision.runner_up.readout.candidate.index
    if decision.score_ratio_overflow:
        return f"runner-up candidate {runner_index} has positive moment (ratio overflow)"
    if decision.score_ratio is None:
        return f"runner-up candidate {runner_index} has moment 0 (ratio undefined)"
    return f"runner-up candidate {runner_index}, ratio {decision.score_ratio:.6g}"


def _amplitude_text(readout: CandidateReadout) -> str:
    """Return the applied amplitude, the candidate's request, and its acquisition group."""
    return (
        f"{readout.readout_amplitude:.6g} (shared minimum; requested "
        f"{readout.requested_readout_amplitude:.6g}; group {readout.readout_group})"
    )


def _readout_groups_text(groups: Sequence[Sequence[CandidateReadout]], grouping: str) -> str:
    """Return one line naming the shared amplitude, mode, budget, and each group."""
    parts = []
    for group, members in enumerate(groups):
        tones = ", ".join(
            f"candidate {r.candidate.index} ({r.readout_label}, "
            f"{r.candidate.frequency:.6g} GHz) requested "
            f"{r.requested_readout_amplitude:.6g}"
            for r in members
        )
        amplitude_sum = math.fsum(r.readout_amplitude for r in members)
        pair = members[0].frequency_pair if members else None
        origin = "" if pair is None else f" (frequency pair {pair})"
        parts.append(f"group {group}{origin} [{tones}] sum {amplitude_sum:.6g}")
    shared = groups[0][0].readout_amplitude if groups and groups[0] else math.nan
    return (
        f"shared readout amplitude {shared:.6g} (minimum requested) applied to every "
        f"candidate; readout_grouping={grouping}: {len(groups)} readout group(s), one "
        f"simultaneous acquisition each, with amplitude sum <= "
        f"{MULTIPLEXED_READOUT_AMPLITUDE_BUDGET:g} each; {'; '.join(parts)}"
    )


def _decision_summary(
    decision: MappingDecision,
    evaluations: Sequence[_CandidateEvaluation],
    min_score_ratio: float,
) -> str:
    """Return one line with the rule, ranking, runner-up margin, and every candidate."""
    rule = (
        f"rule: rank by f01 moment, select the best if it shows a response, "
        f"f01>={MIN_VALID_QUBIT_FREQUENCY} GHz and best/runner-up moment>={min_score_ratio:g} "
        f"(quality_level is diagnostic only)"
    )
    best = (
        "best none"
        if decision.best is None
        else f"best candidate {decision.best.readout.candidate.index}"
    )
    candidates = "; ".join(
        f"candidate {e.readout.candidate.index} ({e.readout.readout_label}, "
        f"{e.readout.candidate.frequency:.6f} GHz, "
        f"amplitude {_amplitude_text(e.readout)}): {e.describe}"
        for e in evaluations
    )
    return " ".join(f"{rule}; {best}, {_runner_up_text(decision)} | {candidates}".split())


def _proposal(evaluation: _CandidateEvaluation | None) -> dict[str, Any] | None:
    """Return the values the candidate would publish, or None without a usable f01."""
    if (
        evaluation is None
        or evaluation.frequency is None
        or evaluation.repr_db is None
        or evaluation.quality_level is None
        or not math.isfinite(evaluation.repr_db)
    ):
        return None
    candidate = evaluation.readout.candidate
    coarse_control_amplitude, _ = compute_coarse_control_amplitude(evaluation.repr_db)
    return {
        "resonator_candidate_index": candidate.index,
        "readout_label": evaluation.readout.readout_label,
        "resonator_frequency": candidate.frequency,
        "readout_amplitude": evaluation.readout.readout_amplitude,
        "requested_readout_amplitude": evaluation.readout.requested_readout_amplitude,
        "readout_group": evaluation.readout.readout_group,
        "coarse_qubit_frequency": _json_number(evaluation.frequency),
        "f01_repr_db": evaluation.repr_db,
        "f01_quality_level": evaluation.quality_level,
        "coarse_control_amplitude": coarse_control_amplitude,
    }


def _json_number(value: float | None) -> float | None:
    """Return a JSON-safe number: non-finite values become None."""
    if value is None or not math.isfinite(value):
        return None
    return float(value)


def _sweep(axis: Any) -> dict[str, Any] | None:
    if axis is None:
        return None
    return {"start": float(axis[0]), "stop": float(axis[-1]), "points": len(axis)}


def mapping_evidence(
    *,
    qid: str,
    payload: FrequencyMappingRunPayload,
    axes: tuple[Any, Any] | None,
    evaluations: Sequence[_CandidateEvaluation],
    decision: MappingDecision,
    min_score_ratio: float,
    proposal: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return the JSON-safe evidence of one mapping decision for later review.

    It records the rule, the measured sweep, every candidate's raw analysis
    values (moment, quality level, f01) or its error, the moment ranking, the
    runner-up and ratio, the reason, the readout grouping mode and readout groups with
    the shared readout amplitude and amplitude budget, and each candidate's group,
    position, frequency pair, applied amplitude (``readout_amplitude``, shared by every
    candidate), and producer request (``requested_readout_amplitude``), and the
    proposal of the selected candidate, or of the best candidate with
    ``published`` false when nothing is selected.
    A non-finite moment is kept as text in ``moment_raw`` and None in ``moment``.
    """
    rank = {id(e): position for position, e in enumerate(decision.ranking, start=1)}
    candidates = []
    for e in evaluations:
        candidate = e.readout.candidate
        if e.error is not None:
            status = "error"
        elif e.has_f01:
            status = "f01_detected"
        else:
            status = "no_f01_peak"
        candidates.append(
            {
                "candidate_index": candidate.index,
                "readout_label": e.readout.readout_label,
                "readout_frequency": candidate.frequency,
                "readout_amplitude": e.readout.readout_amplitude,
                "requested_readout_amplitude": e.readout.requested_readout_amplitude,
                "readout_group": e.readout.readout_group,
                "readout_group_position": e.readout.readout_group_position,
                "frequency_pair": e.readout.frequency_pair,
                "readout_power_db": _readout_power_db(e.readout.readout_amplitude),
                "status": status,
                "error": e.error,
                "f01_frequency": _json_number(e.frequency),
                "f01_repr_db": _json_number(e.repr_db),
                "quality_level": e.quality_level,
                "moment": _json_number(e.moment),
                "moment_raw": None if e.moment is None else repr(e.moment),
                "rank": rank.get(id(e)),
                "selected": decision.selected is e,
            }
        )
    frequencies, powers = axes if axes is not None else (None, None)
    best, runner_up = decision.best, decision.runner_up
    return {
        "schema": MAPPING_EVIDENCE_SCHEMA,
        "qid": qid,
        "target": payload.target,
        "outcome": "selected" if decision.selected is not None else "rejected",
        "reason": decision.reason,
        "rule": {
            "score": "F01Result.moment of the CheckQubitSpectroscopy analysis (not normalized)",
            "quality_level": "diagnostic only; a best candidate needs quality_level > 0",
            "min_qubit_frequency": MIN_VALID_QUBIT_FREQUENCY,
            "min_score_ratio": min_score_ratio,
            "runner_up": "next-highest moment among every candidate with an f01 peak",
            "calibrated": False,
            "note": (
                "min_score_ratio is a provisional heuristic, not empirically calibrated; "
                "every candidate is read at the same shared readout amplitude, but moments "
                "still depend on each candidate's resonator response and noise and are "
                "compared across readout groups without normalization"
            ),
        },
        "readout_groups": _readout_groups_evidence(payload.readouts, payload.readout_grouping),
        "sweep": {
            "drive_frequency_ghz": _sweep(frequencies),
            "drive_power_db": _sweep(powers),
        },
        "ranking": [e.readout.candidate.index for e in decision.ranking],
        "best": None
        if best is None
        else {"candidate_index": best.readout.candidate.index, "moment": _json_number(best.moment)},
        "runner_up": None
        if runner_up is None
        else {
            "candidate_index": runner_up.readout.candidate.index,
            "moment": _json_number(runner_up.moment),
            "quality_level": runner_up.quality_level,
        },
        "runner_up_status": decision.runner_up_status,
        "score_ratio": _json_number(decision.score_ratio),
        "score_ratio_status": (
            "overflow"
            if decision.score_ratio_overflow
            else "finite"
            if decision.score_ratio is not None
            else "undefined"
        ),
        "proposal": None
        if proposal is None
        else {**proposal, "published": decision.selected is not None},
        "candidates": candidates,
    }


def _readout_groups_evidence(readouts: Sequence[CandidateReadout], grouping: str) -> dict[str, Any]:
    """Return the JSON-safe description of the readout groups that were acquired.

    Each group is one helper call that the helper reported as one acquisition, so
    the groups are the acquisitions whose tones were read together.
    """
    members_of: dict[int, list[CandidateReadout]] = {}
    for readout in readouts:
        members_of.setdefault(readout.readout_group, []).append(readout)
    groups = []
    for group in sorted(members_of):
        members = sorted(members_of[group], key=lambda r: r.readout_group_position)
        groups.append(
            {
                "group": group,
                "frequency_pair": members[0].frequency_pair,
                "candidate_indices": [r.candidate.index for r in members],
                "readout_labels": [r.readout_label for r in members],
                "readout_frequencies": [r.candidate.frequency for r in members],
                "readout_amplitudes": [r.readout_amplitude for r in members],
                "requested_readout_amplitudes": [r.requested_readout_amplitude for r in members],
                "amplitude_sum": math.fsum(r.readout_amplitude for r in members),
            }
        )
    applied = sorted({r.readout_amplitude for r in readouts})
    return {
        "readout_grouping": grouping,
        "readout_amplitude": applied[0] if len(applied) == 1 else None,
        "readout_amplitude_policy": READOUT_AMPLITUDE_POLICY,
        "readout_amplitude_rule": READOUT_AMPLITUDE_POLICY_RULE,
        "budget": MULTIPLEXED_READOUT_AMPLITUDE_BUDGET,
        "count": len(groups),
        "rule": READOUT_GROUPING_RULES.get(grouping, grouping),
        "groups": groups,
        "note": (
            "requested amplitudes are the single-tone optima of CheckResonatorSpectroscopy and "
            "are recorded as provenance only; every candidate is read at their minimum so that "
            "the moments share one readout amplitude, which does not remove differences in "
            "resonator response or noise. Tones of one group are read together on one readout "
            "AWG channel, so each group's amplitude sum stays within full scale. Each group is "
            "one helper call that the helper reports as one acquisition, with the same drive "
            "sweep; groups are separate acquisitions."
        ),
    }


def _mark_selected_figure(
    fig: Any,
    qid: str,
    selected: _CandidateEvaluation,
    decision: MappingDecision,
    evidence: dict[str, Any],
) -> Any:
    """Title the selected candidate's marked figure and attach the decision evidence.

    The title names the qid, the selected candidate's readout slot and frequency,
    its f01 and moment score, and the runner-up margin. The figure keeps its own
    metadata and gains the same evidence the summary figure stores, so a consumer
    that reads only the first figure still has every candidate's scores.
    """
    candidate = selected.readout.candidate
    meta = dict(fig.layout.meta) if isinstance(fig.layout.meta, dict) else {}
    meta[MAPPING_EVIDENCE_META_KEY] = evidence
    meta[MAPPING_FIGURE_META_KEY] = "selected"
    fig.update_layout(
        title={
            "text": (
                f"Qubit frequency mapping for qid={qid}: SELECTED candidate "
                f"{candidate.index} ({selected.readout.readout_label})<br>"
                f"<sup>readout_frequency={candidate.frequency:.6f} GHz, "
                f"readout_amplitude={_amplitude_text(selected.readout)}; "
                f"f01={_format_score(selected.frequency)} GHz, "
                f"moment={_format_score(selected.moment)}, "
                f"quality_level={selected.quality_level}<br>"
                f"{_runner_up_text(decision)}</sup>"
            )
        },
        margin={"t": 120},
        meta=meta,
    )
    return fig


def _summary_figure(
    qid: str,
    evaluations: Sequence[_CandidateEvaluation],
    decision: MappingDecision,
    evidence: dict[str, Any],
) -> Any:
    """Return the figure that shows every candidate and the decision in one image.

    The table lists every candidate's evidence; the heatmaps below show each
    candidate's validated phase map with its f01 peak. The evidence dictionary is
    stored under ``layout.meta[MAPPING_EVIDENCE_META_KEY]``.
    """
    import plotly.graph_objects as pgo
    from plotly.subplots import make_subplots

    count = max(len(evaluations), 1)
    titles = []
    for e in evaluations:
        mark = " SELECTED" if decision.selected is e else ""
        titles.append(
            f"cand {e.readout.candidate.index} ({e.readout.readout_label}){mark}<br>"
            f"moment={_format_score(e.moment)}, "
            f"q={'-' if e.quality_level is None else e.quality_level}"
        )
    fig = make_subplots(
        rows=2,
        cols=count,
        specs=[
            [{"type": "table", "colspan": count}] + [None] * (count - 1),
            [{"type": "xy"}] * count,
        ],
        row_heights=[0.3, 0.7],
        vertical_spacing=0.12,
        subplot_titles=["", *titles],
    )
    rows = evidence["candidates"]

    def cell(value: Any, fmt: str = "{:.6g}") -> str:
        if value is None:
            return "-"
        if isinstance(value, bool):
            return "yes" if value else ""
        if isinstance(value, float):
            return fmt.format(value)
        return str(value)

    fig.add_trace(
        pgo.Table(
            header={
                "values": [
                    "cand",
                    "slot",
                    "group",
                    "readout f (GHz)",
                    "readout amp applied",
                    "readout amp requested",
                    "readout P (dB)",
                    "status",
                    "f01 (GHz)",
                    "moment",
                    "quality",
                    "rank",
                    "selected",
                ]
            },
            cells={
                "values": [
                    [cell(r["candidate_index"]) for r in rows],
                    [cell(r["readout_label"]) for r in rows],
                    [cell(r["readout_group"]) for r in rows],
                    [cell(r["readout_frequency"], "{:.6f}") for r in rows],
                    [cell(r["readout_amplitude"]) for r in rows],
                    [cell(r["requested_readout_amplitude"]) for r in rows],
                    [cell(r["readout_power_db"], "{:.2f}") for r in rows],
                    [cell(r["status"] if r["error"] is None else r["error"]) for r in rows],
                    [cell(r["f01_frequency"], "{:.6f}") for r in rows],
                    [
                        cell(r["moment"]) if r["moment"] is not None else cell(r["moment_raw"])
                        for r in rows
                    ],
                    [cell(r["quality_level"]) for r in rows],
                    [cell(r["rank"]) for r in rows],
                    [cell(r["selected"]) for r in rows],
                ]
            },
        ),
        row=1,
        col=1,
    )
    for column, e in enumerate(evaluations, start=1):
        candidate_map = e.candidate_map
        if candidate_map is None:
            continue
        fig.add_trace(
            pgo.Heatmap(
                x=candidate_map.frequencies,
                y=candidate_map.powers,
                z=candidate_map.phases,
                colorscale="Viridis",
                showscale=False,
            ),
            row=2,
            col=column,
        )
        if e.frequency is not None and e.repr_db is not None:
            fig.add_trace(
                pgo.Scatter(
                    x=[e.frequency],
                    y=[e.repr_db],
                    mode="markers",
                    marker={"color": "red", "size": 10, "symbol": "x"},
                    showlegend=False,
                ),
                row=2,
                col=column,
            )
        fig.update_xaxes(title_text="Drive frequency (GHz)", row=2, col=column)
    fig.update_yaxes(title_text="Drive power (dB)", row=2, col=1)
    ratio = evidence["score_ratio"]
    rule = evidence["rule"]
    grouping = evidence["readout_groups"]
    groups_text = "; ".join(
        f"group {g['group']}: candidates {g['candidate_indices']}, "
        f"amplitude sum {g['amplitude_sum']:.4g}"
        for g in grouping["groups"]
    )
    fig.update_layout(
        title={
            "text": (
                f"Qubit frequency mapping for qid={qid}: {evidence['outcome'].upper()}<br>"
                f"<sup>{decision.reason}<br>Runner-up: {evidence['runner_up_status']}, "
                f"ratio={'-' if ratio is None else f'{ratio:.4g}'}<br>Rule: best moment / "
                f"runner-up >= {rule['min_score_ratio']:g} (provisional, uncalibrated), "
                f"quality_level diagnostic only, "
                f"f01 >= {rule['min_qubit_frequency']} GHz<br>Readout groups "
                f"(readout_grouping={grouping['readout_grouping']}, one acquisition each, "
                f"amplitude sum <= {grouping['budget']:g}, shared readout amplitude "
                f"{_format_score(grouping['readout_amplitude'])} = minimum requested): "
                f"{groups_text}</sup>"
            )
        },
        width=max(1000, 380 * count),
        height=900,
        margin={"t": 160},
        meta={MAPPING_EVIDENCE_META_KEY: evidence, MAPPING_FIGURE_META_KEY: "summary"},
        showlegend=False,
    )
    return fig


def _finite_axis(values: Any, name: str) -> tuple[Any, str | None]:
    """Return a finite, strictly increasing one-dimensional axis, or why it is not."""
    try:
        array = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        return None, f"{name} must be a finite one-dimensional axis"
    if values is None or array.ndim != 1 or array.size < 2 or not np.all(np.isfinite(array)):
        return None, f"{name} must be a finite one-dimensional axis"
    if not np.all(np.diff(array) > 0):
        return None, f"{name} must be strictly increasing"
    return array, None


def _same_axis(values: Any, expected: Any) -> bool:
    """Return whether two axes hold the same points."""
    try:
        expected_array = np.asarray(expected, dtype=float)
    except (TypeError, ValueError):
        return False
    return expected_array.shape == values.shape and bool(
        np.allclose(values, expected_array, rtol=0.0, atol=_AXIS_ABS_TOL)
    )


def _finite_map(values: Any, shape: tuple[int, ...]) -> tuple[Any, str | None]:
    """Return a finite real two-dimensional array of ``shape``, or why it is not."""
    if values is None:
        return None, "missing"
    array = np.asarray(values)
    if np.iscomplexobj(array):
        return None, "must be real"
    try:
        array = array.astype(float)
    except (TypeError, ValueError):
        return None, "must be numeric"
    if array.shape != shape:
        return None, f"shape {array.shape} does not match axes {shape}"
    if not np.all(np.isfinite(array)):
        return None, "must be finite"
    return array, None


def _candidate_figure(readout: CandidateReadout, candidate_map: _CandidateMap) -> Any:
    """Return the phase heatmap of one candidate built from its validated data."""
    import plotly.graph_objects as pgo

    candidate = readout.candidate
    fig = pgo.Figure(
        pgo.Heatmap(
            x=candidate_map.frequencies,
            y=candidate_map.powers,
            z=candidate_map.phases,
            colorscale="Viridis",
            colorbar={"title": {"text": "Phase (rad)", "side": "right"}},
        )
    )
    fig.update_layout(
        title={
            "text": (
                f"Candidate {candidate.index} via {readout.readout_label}: "
                f"readout_frequency={candidate.frequency:.6g} GHz, "
                f"readout_amplitude={_amplitude_text(readout)}"
            )
        },
        xaxis_title="Drive frequency (GHz)",
        yaxis_title="Drive power (dB)",
        meta={
            "readout_label": readout.readout_label,
            "candidate_index": candidate.index,
            "readout_group": readout.readout_group,
        },
    )
    return fig
