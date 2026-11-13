"""Check manual execution rounds against a chip without touching hardware.

The API reuses the checks the worker runs before any target measures
(:mod:`qdash.common.manual_rounds`) with the same inputs: the chip's
``wiring.yaml`` and its directed coupling IDs. Everything here only reads
configuration files and the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import yaml

from qdash.common.config.path_resolver import resolve_config_base_path
from qdash.common.manual_rounds import (
    PairRounds,
    QubitRounds,
    RoundIssue,
    load_wiring_entries,
    pair_candidate_issues,
    pair_round_issues,
    qubit_candidate_issues,
    qubit_round_issues,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

RoundScope = Literal["qubit", "coupling"]


@dataclass(frozen=True)
class ChipRoundModel:
    """The chip data the round checks read; ``None`` fields could not be loaded."""

    wiring: list[dict[str, Any]] | None
    wiring_error: str | None = None
    coupling_ids: frozenset[str] | None = None


def load_chip_round_model(
    project_id: str,
    chip_id: str,
    coupling_ids: Callable[[str, str], Sequence[str]] | None,
) -> ChipRoundModel:
    """Read the chip's wiring and, when a loader is given, its coupling IDs."""
    path = resolve_config_base_path() / chip_id / "config" / "wiring.yaml"
    try:
        wiring: list[dict[str, Any]] | None = load_wiring_entries(path, chip_id)
        error = None
    except (OSError, ValueError, yaml.YAMLError) as exc:
        wiring, error = None, f"the wiring of chip {chip_id!r} could not be read: {exc}"
    couplings = frozenset(coupling_ids(project_id, chip_id)) if coupling_ids is not None else None
    return ChipRoundModel(wiring=wiring, wiring_error=error, coupling_ids=couplings)


@dataclass(frozen=True)
class RoundCheck:
    """The outcome of checking one step's rounds.

    ``unchecked`` names what could not be checked (for example missing wiring);
    the worker checks it again before the step runs.
    """

    issues: tuple[RoundIssue, ...] = ()
    unchecked: tuple[str, ...] = ()


def check_rounds(
    scope: RoundScope,
    rounds: QubitRounds | PairRounds,
    model: ChipRoundModel,
    candidates: Sequence[str] | None,
) -> RoundCheck:
    """Run the hardware-model and, when candidates are known, the candidate checks."""
    issues: list[RoundIssue] = []
    unchecked: list[str] = []
    if model.wiring is None:
        unchecked.append(model.wiring_error or "the chip's wiring is unavailable")
    if scope == "qubit":
        qubit_rounds: QubitRounds = rounds  # type: ignore[assignment]
        if model.wiring is not None:
            issues.extend(qubit_round_issues(qubit_rounds, model.wiring))
        if candidates is not None:
            issues.extend(qubit_candidate_issues(qubit_rounds, candidates))
    else:
        pair_rounds: PairRounds = rounds  # type: ignore[assignment]
        if model.wiring is not None:
            if model.coupling_ids is None:
                unchecked.append("the chip's coupling IDs are unavailable")
            else:
                issues.extend(pair_round_issues(pair_rounds, model.wiring, model.coupling_ids))
        if candidates is not None:
            issues.extend(pair_candidate_issues(pair_rounds, candidates))
    if candidates is None:
        unchecked.append(
            "the step's current qubits depend on earlier steps and are checked when it starts"
        )
    return RoundCheck(issues=tuple(issues), unchecked=tuple(unchecked))
