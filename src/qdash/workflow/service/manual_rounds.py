"""Run user-written execution rounds exactly as written.

``execution_mode="manual"`` steps hand their rounds here. Before any worker
starts, the rounds are checked with :mod:`qdash.common.manual_rounds` against
the chip's wiring, its directed coupling IDs and the step's current qubits;
the API preview runs the same checks. Then every round runs its targets in
parallel and the next round starts after every target of the round finished.
No round is colored, reordered, chunked or reversed, and no earlier CR schedule
or target override replaces it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from prefect import get_run_logger

from qdash.common.manual_rounds import (
    ManualRoundsError,
    PairRounds,
    QubitRounds,
    load_wiring_entries,
    pair_candidate_issues,
    pair_round_issues,
    qubit_candidate_issues,
    qubit_round_issues,
)
from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths

if TYPE_CHECKING:
    from collections.abc import Sequence

    from qdash.datamodel.task_call import StepCalls
    from qdash.workflow.service._internal.session import CalibSession

MANUAL_STAGE_RESULT = "1q_manual"


def chip_wiring(chip_id: str) -> list[dict[str, Any]]:
    """The MUX entries of the chip's wiring.yaml, as the schedulers read it."""
    return load_wiring_entries(get_qubex_paths().wiring_yaml(chip_id), chip_id)


def chip_coupling_ids(project_id: str | None, chip_id: str) -> set[str]:
    """Directed coupling IDs of the chip, as ``CRScheduler.schedule_pairs`` checks them."""
    from qdash.repository import MongoChipRepository

    if not project_id:
        raise ValueError(f"Cannot read the couplings of chip {chip_id!r} without a project")
    return set(MongoChipRepository().get_coupling_ids(project_id, chip_id))


def check_qubit_rounds(
    session: CalibSession,
    rounds: QubitRounds,
    *,
    step: str,
    candidates: Sequence[str] | None = None,
) -> None:
    """Raise :class:`ManualRoundsError` for rounds the model or the candidates reject."""
    issues = qubit_round_issues(rounds, chip_wiring(session.chip_id))
    if candidates is not None:
        issues.extend(qubit_candidate_issues(rounds, candidates))
    if issues:
        raise ManualRoundsError(step, issues)


def check_pair_rounds(
    session: CalibSession,
    rounds: PairRounds,
    *,
    step: str,
    candidates: Sequence[str] | None = None,
) -> None:
    """Raise :class:`ManualRoundsError` for pairs the model or the candidates reject."""
    issues = pair_round_issues(
        rounds,
        chip_wiring(session.chip_id),
        chip_coupling_ids(session.project_id, session.chip_id),
    )
    if candidates is not None:
        issues.extend(pair_candidate_issues(rounds, candidates))
    if issues:
        raise ManualRoundsError(step, issues)


def run_qubit_rounds(
    session: CalibSession,
    rounds: QubitRounds,
    *,
    plan: StepCalls,
    candidates: Sequence[str],
    step: str,
) -> dict[str, Any]:
    """Check, then run each round's qubits in parallel and the rounds in order.

    Returns ``{"round_1": {qid: result, ...}, ...}``.
    """
    from qdash.workflow.service._internal.scheduling_tasks import (
        run_qubit_calibrations_parallel,
    )

    check_qubit_rounds(session, rounds, step=step, candidates=candidates)
    logger = get_run_logger()
    worker = session.worker_spec()
    results: dict[str, Any] = {}
    for number, round_ in enumerate(rounds, start=1):
        logger.info(f"[{step}] manual round {number}/{len(rounds)}: {', '.join(round_)}")
        results[f"round_{number}"] = run_qubit_calibrations_parallel(
            qids=list(round_), plan=plan, worker=worker
        )
    session.record_stage_result(MANUAL_STAGE_RESULT, results)
    return results


def run_pair_rounds(
    session: CalibSession,
    rounds: PairRounds,
    *,
    plan: StepCalls,
    candidates: Sequence[str],
    step: str,
) -> dict[str, Any]:
    """Check, then run each round's pairs in parallel and the rounds in order.

    Returns ``{"control-target": result, ...}``.
    """
    from qdash.workflow.service._internal.scheduling_tasks import (
        run_coupling_calibrations_parallel,
    )

    check_pair_rounds(session, rounds, step=step, candidates=candidates)
    logger = get_run_logger()
    worker = session.worker_spec()
    results: dict[str, Any] = {}
    for number, round_ in enumerate(rounds, start=1):
        coupling_ids = [f"{control}-{target}" for control, target in round_]
        logger.info(f"[{step}] manual round {number}/{len(rounds)}: {', '.join(coupling_ids)}")
        results.update(
            run_coupling_calibrations_parallel(coupling_qids=coupling_ids, plan=plan, worker=worker)
        )
    return results
