"""User-written execution rounds and the checks shared by the worker and the API.

A step with ``execution_mode="manual"`` lists its rounds explicitly: one-qubit
rounds are lists of qubit IDs and two-qubit rounds are lists of directed
``(control, target)`` pairs. The worker runs the rounds exactly as written; it
never colors, reorders or splits them. This module holds every check that does
not need the worker runtime, so the execution-plan preview in the API and the
worker reject the same rounds with the same messages:

- :func:`parse_qubit_rounds` and :func:`parse_pair_rounds` check the shape
  (non-empty rounds, IDs, self pairs, repeats);
- :func:`qubit_round_issues` and :func:`pair_round_issues` check the rounds
  against the chip's wiring (and, for pairs, its directed coupling IDs) with
  the same resource model the automatic schedulers use;
- :func:`qubit_candidate_issues` and :func:`pair_candidate_issues` check the
  rounds against the qubits a step may run on.

MUX membership comes from the chip topology's :class:`~qdash.common.mux_mapping.MuxMapping`
(the same mapping the schedulers, execution locks and MUX fan-out use); the
wiring is joined to it by MUX ID. Without a mapping the legacy convention
(MUX ``N`` owns qubits ``4N`` to ``4N + 3``) applies, as for chips without a
topology. A standalone qubit (a qubit of the topology in no MUX) has no known
hardware resources, so it must run alone in its round, as the automatic
schedulers run it.

The resource model is the schedulers' model, not a hardware certificate: a
round that passes may still contend for resources the wiring file does not
describe.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import yaml

from qdash.common.mux_mapping import MuxMapping, canonical_qid
from qdash.common.wiring_resources import mux_module_resources

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Mapping, Sequence
    from pathlib import Path

QubitRounds = tuple[tuple[str, ...], ...]
PairRounds = tuple[tuple[tuple[str, str], ...], ...]

_QID = re.compile(r"^(?:0|[1-9]\d*)$")
_CHANNEL = re.compile(r"^([A-Za-z0-9]+)(?:-\d+)?$")

BOX_A = "A"
BOX_B = "B"
BOX_MIXED = "MIXED"

MANUAL_TARGET_OVERRIDE_REASON = (
    "This workflow runs manual rounds, which name their own targets. Target overrides "
    "are not accepted; edit the rounds in the workflow source instead."
)


@dataclass(frozen=True)
class RoundIssue:
    """One problem with manual rounds.

    ``round_number`` is 1-based and ``None`` for problems of the whole list.
    """

    reason: str
    round_number: int | None = None
    targets: tuple[str, ...] = ()

    def describe(self) -> str:
        """``round 2 (0, 8): reason`` or the bare reason."""
        if self.round_number is None:
            return self.reason
        where = f"round {self.round_number}"
        if self.targets:
            where += f" ({', '.join(self.targets)})"
        return f"{where}: {self.reason}"


class ManualRoundsError(ValueError):
    """Manual rounds that cannot run; ``issues`` lists every problem found."""

    def __init__(self, step: str, issues: Sequence[RoundIssue]) -> None:
        self.step = step
        self.issues = list(issues)
        super().__init__(format_issues(step, self.issues))

    def __reduce__(self) -> tuple[Any, ...]:
        # Keep step and issues when the error crosses a process boundary.
        return (type(self), (self.step, self.issues))


def format_issues(step: str, issues: Sequence[RoundIssue]) -> str:
    """One message naming the step and every issue."""
    details = "; ".join(issue.describe() for issue in issues)
    return f"Manual rounds of step {step!r} cannot run: {details}"


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def _sequence(value: object) -> bool:
    return isinstance(value, (list, tuple))


def _qid_issue(value: object) -> str | None:
    if not isinstance(value, str):
        return f"qubit ID {value!r} must be a string such as '0'"
    if not _QID.match(value):
        return (
            f"qubit ID {value!r} must be a non-negative integer string without leading "
            "zeros, such as '7'"
        )
    return None


def parse_qubit_rounds(value: object, *, step: str) -> QubitRounds:
    """Return one-qubit rounds as tuples, or raise :class:`ManualRoundsError`.

    Every round must be a non-empty list of qubit ID strings, and a qubit may
    appear only once in the whole step: its result is keyed by qubit, so a
    second run would overwrite the first.
    """
    issues: list[RoundIssue] = []
    if not _sequence(value) or not value:
        raise ManualRoundsError(
            step, [RoundIssue("rounds must be a non-empty list of rounds, e.g. [['0', '8']]")]
        )
    assert isinstance(value, (list, tuple))
    parsed: list[tuple[str, ...]] = []
    first_round: dict[str, int] = {}
    for number, raw_round in enumerate(value, start=1):
        if not _sequence(raw_round) or not raw_round:
            issues.append(RoundIssue("a round must be a non-empty list of qubit IDs", number))
            continue
        assert isinstance(raw_round, (list, tuple))
        qids: list[str] = []
        for qid in raw_round:
            problem = _qid_issue(qid)
            if problem is not None:
                issues.append(RoundIssue(problem, number))
                continue
            assert isinstance(qid, str)
            if qid in qids:
                issues.append(RoundIssue(f"qubit {qid} appears twice", number, (qid,)))
                continue
            if qid in first_round:
                issues.append(
                    RoundIssue(
                        f"qubit {qid} already runs in round {first_round[qid]}; a qubit may "
                        "appear in only one round of a step",
                        number,
                        (qid,),
                    )
                )
                continue
            first_round[qid] = number
            qids.append(qid)
        parsed.append(tuple(qids))
    if issues:
        raise ManualRoundsError(step, issues)
    return tuple(parsed)


def parse_pair_rounds(value: object, *, step: str) -> PairRounds:
    """Return two-qubit rounds as tuples of ``(control, target)``, or raise.

    Every round must be a non-empty list of directed pairs of two different
    qubit ID strings. Pairs of one round may not share a qubit, and a directed
    pair may appear only once in the step (results are keyed by pair).
    """
    issues: list[RoundIssue] = []
    if not _sequence(value) or not value:
        raise ManualRoundsError(
            step,
            [RoundIssue("rounds must be a non-empty list of rounds, e.g. [[('0', '1')]]")],
        )
    assert isinstance(value, (list, tuple))
    parsed: list[tuple[tuple[str, str], ...]] = []
    first_round: dict[tuple[str, str], int] = {}
    for number, raw_round in enumerate(value, start=1):
        if not _sequence(raw_round) or not raw_round:
            issues.append(RoundIssue("a round must be a non-empty list of pairs", number))
            continue
        assert isinstance(raw_round, (list, tuple))
        pairs: list[tuple[str, str]] = []
        for raw_pair in raw_round:
            if not _sequence(raw_pair) or len(raw_pair) != 2:
                issues.append(
                    RoundIssue(
                        f"{raw_pair!r} must be a (control, target) pair such as ('0', '1')",
                        number,
                    )
                )
                continue
            assert isinstance(raw_pair, (list, tuple))
            problems = [p for p in (_qid_issue(raw_pair[0]), _qid_issue(raw_pair[1])) if p]
            if problems:
                issues.extend(RoundIssue(problem, number) for problem in problems)
                continue
            pair = (str(raw_pair[0]), str(raw_pair[1]))
            label = f"{pair[0]}-{pair[1]}"
            if pair[0] == pair[1]:
                issues.append(RoundIssue("a pair needs two different qubits", number, (label,)))
                continue
            if pair in pairs:
                issues.append(RoundIssue(f"pair {label} appears twice", number, (label,)))
                continue
            if pair in first_round:
                issues.append(
                    RoundIssue(
                        f"pair {label} already runs in round {first_round[pair]}; a pair may "
                        "appear in only one round of a step",
                        number,
                        (label,),
                    )
                )
                continue
            shared = next((other for other in pairs if set(other) & set(pair)), None)
            if shared is not None:
                other = f"{shared[0]}-{shared[1]}"
                qubit = sorted(set(shared) & set(pair), key=int)[0]
                issues.append(
                    RoundIssue(
                        f"pairs {other} and {label} share qubit {qubit}",
                        number,
                        (other, label),
                    )
                )
                continue
            first_round[pair] = number
            pairs.append(pair)
        parsed.append(tuple(pairs))
    if issues:
        raise ManualRoundsError(step, issues)
    return tuple(parsed)


def qubit_rounds_for_mode(mode: str, rounds: object, *, step: str) -> QubitRounds | None:
    """Parsed rounds of a one-qubit step; ``rounds`` belongs to ``manual`` only."""
    if mode == "manual":
        if rounds is None:
            raise ManualRoundsError(
                step,
                [
                    RoundIssue(
                        "execution_mode='manual' requires rounds, e.g. [['0', '8'], ['1', '9']]"
                    )
                ],
            )
        return parse_qubit_rounds(rounds, step=step)
    if rounds is not None:
        raise ValueError(
            f"Step {step!r} sets rounds with execution_mode={mode!r}; rounds is only "
            "accepted with execution_mode='manual'"
        )
    return None


def pair_rounds_for_mode(
    mode: str, rounds: object, max_parallel_ops: int | None, *, step: str
) -> PairRounds | None:
    """Parsed rounds of a two-qubit step.

    ``rounds`` belongs to ``manual`` only, and ``max_parallel_ops`` to
    ``automatic`` only: manual rounds are never split, so a cap would either be
    ignored or change the rounds.
    """
    if mode == "manual":
        if max_parallel_ops is not None:
            raise ValueError(
                f"Step {step!r} sets max_parallel_ops with execution_mode='manual'; "
                "max_parallel_ops only caps automatic CR groups, and manual rounds run as "
                "written. Remove it, or split a round yourself"
            )
        if rounds is None:
            raise ManualRoundsError(
                step,
                [
                    RoundIssue(
                        "execution_mode='manual' requires rounds, "
                        "e.g. [[('0', '1'), ('4', '5')], [('8', '9')]]"
                    )
                ],
            )
        return parse_pair_rounds(rounds, step=step)
    if rounds is not None:
        raise ValueError(
            f"Step {step!r} sets rounds with execution_mode={mode!r}; rounds is only "
            "accepted with execution_mode='manual'"
        )
    return None


def round_qids(rounds: QubitRounds | PairRounds) -> list[str]:
    """Every qubit the rounds touch, in first-use order."""
    seen: dict[str, None] = {}
    for round_ in rounds:
        for target in round_:
            for qid in (target,) if isinstance(target, str) else target:
                seen.setdefault(qid, None)
    return list(seen)


# ---------------------------------------------------------------------------
# Wiring model
# ---------------------------------------------------------------------------


def load_wiring_entries(path: Path, chip_id: str) -> list[dict[str, Any]]:
    """The MUX entries of a ``wiring.yaml`` in the chip-keyed or group-keyed format.

    Raises:
        FileNotFoundError: the file does not exist.
        ValueError: the file is not a wiring mapping of MUX entries.
    """
    if not path.exists():
        raise FileNotFoundError(f"Wiring config not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Wiring config {path} is not a mapping")
    groups = [data[chip_id]] if chip_id in data else list(data.values())
    entries: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, list):
            raise ValueError(f"Wiring config {path} has a group that is not a list")
        for entry in group:
            if not isinstance(entry, dict) or type(entry.get("mux")) is not int:
                raise ValueError(f"Wiring config {path} has an entry without an integer mux")
            entries.append(entry)
    return entries


def channel_module_id(channel: str) -> str | None:
    """``R21B-5`` -> ``R21B``; ``None`` when the ID is not in that form."""
    match = _CHANNEL.match(channel)
    return match.group(1) if match else None


def channel_box_type(channel: str) -> str | None:
    """``A`` or ``B`` from the last character of the module ID, else ``None``."""
    module_id = channel_module_id(channel)
    if module_id is None:
        return None
    if module_id.endswith("A"):
        return BOX_A
    if module_id.endswith("B"):
        return BOX_B
    return None


def mux_box_types(entry: Mapping[str, Any]) -> set[str]:
    """Box types of every recognized ``ctrl``, ``read_out``, ``read_in`` and ``pump`` channel."""
    channels: list[Any] = list(entry.get("ctrl") or [])
    channels.extend(entry.get(key) for key in ("read_out", "read_in", "pump"))
    return {
        box
        for channel in channels
        if isinstance(channel, str) and (box := channel_box_type(channel)) is not None
    }


def mux_box_class(entry: Mapping[str, Any]) -> str:
    """``A`` or ``B`` for a MUX on one box type, ``MIXED`` for both or neither."""
    types = mux_box_types(entry)
    return next(iter(types)) if len(types) == 1 else BOX_MIXED


def box_b_ctrl_modules(entry: Mapping[str, Any]) -> set[str]:
    """Box B module IDs among the MUX's ``ctrl`` channels."""
    return {
        module_id
        for ctrl in entry.get("ctrl") or []
        if isinstance(ctrl, str)
        and (module_id := channel_module_id(ctrl)) is not None
        and module_id.endswith("B")
    }


def _mapping(mux_mapping: MuxMapping | None) -> MuxMapping:
    return mux_mapping if mux_mapping is not None else MuxMapping.legacy()


def needs_wiring(mux_mapping: MuxMapping | None) -> bool:
    """Whether checks against ``mux_mapping`` need ``wiring.yaml``.

    The wiring maps only MUXes to hardware, so a topology without any MUX
    (every qubit standalone) is checked without it, as the CR scheduler does.
    """
    mapping = _mapping(mux_mapping)
    return mapping.unbounded or bool(mapping.mux_ids)


def qubit_mux_map(
    entries: Iterable[Mapping[str, Any]], mux_mapping: MuxMapping | None = None
) -> dict[str, int]:
    """Qubit -> MUX for the wired MUXes the mapping defines.

    Members come from ``mux_mapping`` (legacy: MUX ``N`` owns ``4N`` to
    ``4N + 3``). A wired MUX the mapping does not define has no qubits.
    """
    mapping = _mapping(mux_mapping)
    return mapping.qid_to_mux(entry["mux"] for entry in entries if mapping.has_mux(entry["mux"]))


def _wiring_issues(
    mapping: MuxMapping, wiring: Sequence[Mapping[str, Any]], touched: Collection[int]
) -> list[RoundIssue]:
    """Slots of the rounds' MUXes that have no control port in the wiring."""
    rows = [entry for entry in wiring if entry.get("mux") in touched]
    return [RoundIssue(error) for error in mapping.wiring_errors(rows)]


def _membership_issue(mapping: MuxMapping, qid: str) -> str | None:
    """Why ``qid`` cannot run on the chip at all, or ``None``."""
    if not mapping.is_known(qid):
        where = f"topology {mapping.topology_id}" if mapping.topology_id else "the chip topology"
        return f"qubit {qid} is not defined by {where}"
    return None


def mux_conflicts(entries: Iterable[Mapping[str, Any]]) -> dict[int, set[int]]:
    """MUXes that share a readout or control module, as the CR scheduler models them."""
    by_module: dict[str, set[int]] = {}
    for entry in entries:
        for resource in mux_module_resources(dict(entry)):
            by_module.setdefault(resource, set()).add(entry["mux"])
    conflicts: dict[int, set[int]] = {}
    for muxes in by_module.values():
        for left, right in itertools.combinations(sorted(muxes), 2):
            conflicts.setdefault(left, set()).add(right)
            conflicts.setdefault(right, set()).add(left)
    return conflicts


def qubit_round_issues(
    rounds: QubitRounds,
    wiring: Sequence[Mapping[str, Any]],
    mux_mapping: MuxMapping | None = None,
) -> list[RoundIssue]:
    """Problems of one-qubit rounds under the one-qubit scheduler's model.

    The model is that of ``parallel_by_round``: each qubit must be defined by
    the chip topology and, when it is in a MUX, wired; the qubits of a round
    use different MUXes, a round stays within one box stage (A, B or MIXED),
    and MIXED MUXes of a round do not share a Box B ``ctrl`` module. A
    standalone qubit runs alone in its round.
    """
    mapping = _mapping(mux_mapping)
    by_mux = {entry["mux"]: entry for entry in wiring}
    qid_to_mux = qubit_mux_map(wiring, mapping)
    issues: list[RoundIssue] = []
    touched: set[int] = set()
    for number, round_ in enumerate(rounds, start=1):
        wired: list[str] = []
        for qid in round_:
            problem = _membership_issue(mapping, qid)
            if problem is not None:
                issues.append(RoundIssue(problem, number, (qid,)))
            elif mapping.is_standalone(qid):
                if len(round_) > 1:
                    issues.append(
                        RoundIssue(
                            f"qubit {qid} is standalone (in no MUX), so the hardware it shares "
                            "is unknown; it must run alone in its round",
                            number,
                            (qid,),
                        )
                    )
            elif qid not in qid_to_mux:
                issues.append(
                    RoundIssue(
                        f"qubit {qid} has no MUX entry in the chip's wiring "
                        f"(MUX {mapping.mux_of(qid)})",
                        number,
                        (qid,),
                    )
                )
            else:
                wired.append(qid)
                touched.add(qid_to_mux[qid])
        seen_mux: dict[int, str] = {}
        for qid in wired:
            mux = qid_to_mux[qid]
            if mux in seen_mux:
                issues.append(
                    RoundIssue(
                        f"qubits {seen_mux[mux]} and {qid} share MUX {mux}; qubits of one "
                        "MUX must run in different rounds",
                        number,
                        (seen_mux[mux], qid),
                    )
                )
            else:
                seen_mux[mux] = qid
        classes: dict[str, list[str]] = {}
        for mux, qid in seen_mux.items():
            classes.setdefault(mux_box_class(by_mux[mux]), []).append(qid)
        if len(classes) > 1:
            parts = ", ".join(f"{box} ({', '.join(qids)})" for box, qids in sorted(classes.items()))
            issues.append(
                RoundIssue(
                    f"the round mixes box stages {parts}; the scheduler runs Box A, Box B and "
                    "MIXED MUXes in separate stages",
                    number,
                    tuple(qid for qids in classes.values() for qid in qids),
                )
            )
        module_owner: dict[str, str] = {}
        for mux, qid in seen_mux.items():
            entry = by_mux[mux]
            if mux_box_class(entry) != BOX_MIXED:
                continue
            for module_id in sorted(box_b_ctrl_modules(entry)):
                if module_id in module_owner:
                    issues.append(
                        RoundIssue(
                            f"qubits {module_owner[module_id]} and {qid} use MUXes that share "
                            f"Box B ctrl module {module_id}",
                            number,
                            (module_owner[module_id], qid),
                        )
                    )
                else:
                    module_owner[module_id] = qid
    return _wiring_issues(mapping, wiring, touched) + issues


def pair_round_issues(
    rounds: PairRounds,
    wiring: Sequence[Mapping[str, Any]],
    coupling_ids: Collection[str],
    mux_mapping: MuxMapping | None = None,
) -> list[RoundIssue]:
    """Problems of two-qubit rounds under the CR scheduler's model.

    Every pair must be a chip coupling with exactly that ``control-target`` ID
    (a pair is never reversed), and both qubits must be defined by the chip
    topology and, when in a MUX, wired. Pairs of a round may not use the same
    MUX or MUXes that share a readout or control module. A pair with a
    standalone qubit runs alone in its round, as the CR scheduler never groups
    it with another pair.
    """
    mapping = _mapping(mux_mapping)
    qid_to_mux = qubit_mux_map(wiring, mapping)
    conflicts = mux_conflicts(wiring)
    known = set(coupling_ids)
    issues: list[RoundIssue] = []
    touched: set[int] = set()
    for number, round_ in enumerate(rounds, start=1):
        usable: list[tuple[str, tuple[int, int]]] = []
        for control, target in round_:
            label = f"{control}-{target}"
            if label not in known:
                hint = (
                    f"; {target}-{control} is, so swap control and target to run that direction"
                    if f"{target}-{control}" in known
                    else ""
                )
                issues.append(
                    RoundIssue(f"{label} is not a coupling of the chip{hint}", number, (label,))
                )
                continue
            undefined = [
                problem
                for qid in (control, target)
                if (problem := _membership_issue(mapping, qid)) is not None
            ]
            if undefined:
                issues.append(RoundIssue(f"{label}: {'; '.join(undefined)}", number, (label,)))
                continue
            standalone = [qid for qid in (control, target) if mapping.is_standalone(qid)]
            unwired = [
                qid for qid in (control, target) if qid not in qid_to_mux and qid not in standalone
            ]
            if unwired:
                issues.append(
                    RoundIssue(
                        f"qubit {', '.join(unwired)} of {label} has no MUX entry in the wiring",
                        number,
                        (label,),
                    )
                )
                continue
            if standalone:
                if len(round_) > 1:
                    issues.append(
                        RoundIssue(
                            f"{label} uses standalone qubit {', '.join(standalone)} (in no MUX), "
                            "so the hardware it shares is unknown; it must run alone in its round",
                            number,
                            (label,),
                        )
                    )
                touched.update(qid_to_mux[qid] for qid in (control, target) if qid in qid_to_mux)
                continue
            touched.update((qid_to_mux[control], qid_to_mux[target]))
            usable.append((label, (qid_to_mux[control], qid_to_mux[target])))
        for (left, left_muxes), (right, right_muxes) in itertools.combinations(usable, 2):
            shared = sorted(set(left_muxes) & set(right_muxes))
            if shared:
                issues.append(
                    RoundIssue(
                        f"pairs {left} and {right} both use MUX {shared[0]}",
                        number,
                        (left, right),
                    )
                )
                continue
            neighbors = conflicts.get(left_muxes[0], set()) | conflicts.get(left_muxes[1], set())
            clash = sorted(set(right_muxes) & neighbors)
            if clash:
                issues.append(
                    RoundIssue(
                        f"pairs {left} and {right} use MUXes that share a readout or control "
                        f"module (MUX {clash[0]})",
                        number,
                        (left, right),
                    )
                )
    return _wiring_issues(mapping, wiring, touched) + issues


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


def _sorted_qids(qids: Iterable[str]) -> list[str]:
    return sorted(set(qids), key=lambda qid: (len(qid), qid))


def qubit_candidate_issues(rounds: QubitRounds, candidates: Sequence[str]) -> list[RoundIssue]:
    """Rounds and the step's current qubits must name the same qubits.

    A qubit in a round that is not a candidate (excluded, filtered out or not a
    target) and a candidate that no round names are both problems; neither is
    dropped or added silently.
    """
    named = set(round_qids(rounds))
    allowed = set(candidates)
    issues: list[RoundIssue] = []
    for number, round_ in enumerate(rounds, start=1):
        missing = [qid for qid in round_ if qid not in allowed]
        if missing:
            issues.append(
                RoundIssue(
                    f"qubit {', '.join(missing)} is not among the step's current qubits "
                    "(a target, not excluded, and kept by earlier filters)",
                    number,
                    tuple(missing),
                )
            )
    extra = _sorted_qids(allowed - named)
    if extra:
        issues.append(
            RoundIssue(
                f"current qubits {', '.join(extra)} are in no round; add them to a round or "
                "remove them from the targets"
            )
        )
    return issues


def pair_candidate_issues(rounds: PairRounds, candidates: Sequence[str]) -> list[RoundIssue]:
    """Both qubits of every pair must be among the step's current qubits."""
    allowed = set(candidates)
    issues: list[RoundIssue] = []
    for number, round_ in enumerate(rounds, start=1):
        for control, target in round_:
            missing = [qid for qid in (control, target) if qid not in allowed]
            if missing:
                issues.append(
                    RoundIssue(
                        f"qubit {', '.join(missing)} of {control}-{target} is not among the "
                        "step's current qubits (a target, not excluded, and kept by earlier "
                        "filters)",
                        number,
                        (f"{control}-{target}",),
                    )
                )
    return issues


def mux_target_qids(
    mux_ids: Iterable[int],
    exclude_qids: Iterable[str],
    wiring: Sequence[Mapping[str, Any]],
    mux_mapping: MuxMapping | None = None,
) -> list[str]:
    """Qubits of ``MuxTargets`` as the scheduler resolves them, in MUX-then-slot order.

    Members come from ``mux_mapping``; exclusions match by qubit number. A
    chip without a topology skips MUXes the wiring does not list, as the
    scheduler does. With a topology, an unwired MUX keeps its members (the
    worker refuses it, and the round checks report the missing wiring). MUX
    IDs the mapping does not define are left to the target checks.
    """
    mapping = _mapping(mux_mapping)
    wired = {entry["mux"] for entry in wiring}
    excluded = {canonical_qid(qid) for qid in exclude_qids}
    return [
        qid
        for mux in dict.fromkeys(mux_ids)
        if mapping.has_mux(mux) and (not mapping.unbounded or mux in wired)
        for qid in mapping.qids_of(mux)
        if qid not in excluded
    ]
