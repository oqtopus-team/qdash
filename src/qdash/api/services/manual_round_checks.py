"""Check manual execution rounds against a chip without touching hardware.

The API reuses the checks the worker runs before any target measures
(:mod:`qdash.common.manual_rounds`) with the same inputs: the chip topology's
MUX mapping (resolved as the worker session resolves it), the chip's
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
    needs_wiring,
    pair_candidate_issues,
    pair_round_issues,
    qubit_candidate_issues,
    qubit_round_issues,
)
from qdash.common.mux_mapping import MuxMapping, MuxMappingError, resolve_chip_mux_mapping

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

RoundScope = Literal["qubit", "coupling"]


@dataclass(frozen=True)
class ChipRoundModel:
    """The chip data the round checks read; ``None`` fields could not be loaded.

    ``mux_mapping`` is the chip topology's MUX membership. ``None`` with no
    ``mapping_error`` means the legacy convention of a chip without a topology;
    with ``mapping_error`` the topology is unusable and every round is refused,
    as the worker refuses to run.
    """

    wiring: list[dict[str, Any]] | None
    wiring_error: str | None = None
    coupling_ids: frozenset[str] | None = None
    mux_mapping: MuxMapping | None = None
    mapping_error: str | None = None


def load_chip_round_model(
    project_id: str,
    chip_id: str,
    coupling_ids: Callable[[str, str], Sequence[str]] | None,
    mux_mapping: Callable[[], MuxMapping] | None = None,
) -> ChipRoundModel:
    """Read the chip's MUX mapping, its wiring and, when a loader is given, its coupling IDs.

    The mapping is resolved from the chip's ``topology_id`` exactly as a
    worker session resolves it (``mux_mapping`` may supply that resolution
    from a chip the caller already read), so the preview and the run agree on
    MUX membership. A topology without any MUX needs no wiring.
    """
    mapping: MuxMapping | None
    try:
        mapping = (
            mux_mapping()
            if mux_mapping is not None
            else resolve_chip_mux_mapping(project_id, chip_id)
        )
        mapping_error = None
    except MuxMappingError as exc:
        mapping, mapping_error = None, f"the MUX mapping of chip {chip_id!r} is unusable: {exc}"
    wiring: list[dict[str, Any]] | None
    error: str | None = None
    if mapping is not None and not needs_wiring(mapping):
        wiring = []
    else:
        path = resolve_config_base_path() / chip_id / "config" / "wiring.yaml"
        try:
            wiring = load_wiring_entries(path, chip_id)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            wiring, error = None, f"the wiring of chip {chip_id!r} could not be read: {exc}"
    couplings = frozenset(coupling_ids(project_id, chip_id)) if coupling_ids is not None else None
    return ChipRoundModel(
        wiring=wiring,
        wiring_error=error,
        coupling_ids=couplings,
        mux_mapping=mapping,
        mapping_error=mapping_error,
    )


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
    if model.mapping_error is not None:
        # The worker resolves the same topology and refuses to start the step.
        return RoundCheck(issues=(RoundIssue(model.mapping_error),))
    mapping = model.mux_mapping
    if model.wiring is None:
        unchecked.append(model.wiring_error or "the chip's wiring is unavailable")
    if scope == "qubit":
        qubit_rounds: QubitRounds = rounds  # type: ignore[assignment]
        if model.wiring is not None:
            issues.extend(qubit_round_issues(qubit_rounds, model.wiring, mapping))
        if candidates is not None:
            issues.extend(qubit_candidate_issues(qubit_rounds, candidates))
    else:
        pair_rounds: PairRounds = rounds  # type: ignore[assignment]
        if model.wiring is not None:
            if model.coupling_ids is None:
                unchecked.append("the chip's coupling IDs are unavailable")
            else:
                issues.extend(
                    pair_round_issues(pair_rounds, model.wiring, model.coupling_ids, mapping)
                )
        if candidates is not None:
            issues.extend(pair_candidate_issues(pair_rounds, candidates))
    if candidates is None:
        unchecked.append(
            "the step's current qubits depend on earlier steps and are checked when it starts"
        )
    return RoundCheck(issues=tuple(issues), unchecked=tuple(unchecked))
