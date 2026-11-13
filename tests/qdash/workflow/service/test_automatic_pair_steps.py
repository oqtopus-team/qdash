"""Automatic two-qubit steps group exactly the directed pairs of CouplingTargets."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from qdash.common.mux_mapping import MuxMapping
from qdash.datamodel.task_call import TaskCall
from qdash.workflow.service._internal import scheduling_tasks
from qdash.workflow.service.steps import CustomTwoQubit, GenerateCRSchedule, TwoQubitCalibration
from qdash.workflow.service.steps.pipeline import StepContext
from qdash.workflow.service.targets import CouplingTargets, QubitTargets

if TYPE_CHECKING:
    from qdash.workflow.service._internal.session import CalibSession

CR = [TaskCall(name="CheckCrossResonance")]
PAIRS = [("0", "1"), ("1", "0"), ("4", "5")]
QUBITS = ["0", "1", "4", "5"]


class Scheduler:
    """Records the CRScheduler calls; each pair gets its own group."""

    calls: list[tuple[str, Any, int, bool]] = []

    def __init__(self, *args: Any, mux_mapping: Any = None, **kwargs: Any) -> None:
        self.mux_mapping = mux_mapping

    def schedule_pairs(self, pairs: list[tuple[str, str]], max_parallel_ops: int = 10) -> Any:
        Scheduler.calls.append(("schedule_pairs", list(pairs), max_parallel_ops, False))
        return SimpleNamespace(parallel_groups=[[pair] for pair in pairs])

    def generate(
        self, candidate_qubits: list[str], max_parallel_ops: int = 10, inverse: bool = False
    ) -> Any:
        Scheduler.calls.append(("generate", list(candidate_qubits), max_parallel_ops, inverse))
        return SimpleNamespace(parallel_groups=[[("0", "1")]])


@pytest.fixture
def groups(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Groups handed to the worker processes, in order."""
    ran: list[list[str]] = []

    def run(coupling_qids: list[str], plan: Any, worker: Any) -> dict[str, Any]:
        ran.append(list(coupling_qids))
        return {pair: {"status": "success"} for pair in coupling_qids}

    Scheduler.calls = []
    monkeypatch.setattr(scheduling_tasks, "run_coupling_calibrations_parallel", run)
    monkeypatch.setattr("qdash.workflow.engine.CRScheduler", Scheduler)
    monkeypatch.setattr(
        "qdash.workflow.service.steps.two_qubit.get_qubex_paths",
        lambda: SimpleNamespace(wiring_yaml=lambda chip: "wiring.yaml"),
    )
    logger = SimpleNamespace(info=lambda *_: None, warning=lambda *_: None)
    monkeypatch.setattr("qdash.workflow.service.steps.two_qubit.get_run_logger", lambda: logger)
    return ran


def _session() -> CalibSession:
    session = SimpleNamespace(
        chip_id="chip",
        username="alice",
        project_id="project",
        plan_digest=None,
        worker_spec=lambda: "worker",
        mux_mapping=MuxMapping.legacy(),
    )
    session.record_stage_result = lambda name, result: None
    return cast("CalibSession", session)


BUILDERS = {
    "CustomTwoQubit": lambda **kw: CustomTwoQubit(tasks=CR, **kw),
    "TwoQubitCalibration": lambda **kw: TwoQubitCalibration(tasks=CR, **kw),
}


@pytest.mark.parametrize("build", BUILDERS.values(), ids=BUILDERS)
def test_target_pairs_run_in_their_direction_without_extra_pairs(
    groups: list[list[str]], build: Any
) -> None:
    step = build(max_parallel_ops=3)
    ctx = step.execute(_session(), CouplingTargets(PAIRS), StepContext(candidate_qids=QUBITS))

    # The scheduler groups exactly the listed pairs; nothing is generated from qubits.
    assert Scheduler.calls == [("schedule_pairs", PAIRS, 3, False)]
    assert groups == [["0-1"], ["1-0"], ["4-5"]]
    assert sorted(ctx.get_step_result(step.resolved_step_id).couplings) == ["0-1", "1-0", "4-5"]


@pytest.mark.parametrize("build", BUILDERS.values(), ids=BUILDERS)
def test_pairs_of_filtered_qubits_are_left_out(groups: list[list[str]], build: Any) -> None:
    step = build()
    ctx = StepContext(candidate_qids=["0", "1", "4"])  # A filter removed qubit 5.

    step.execute(_session(), CouplingTargets(PAIRS), ctx)

    assert Scheduler.calls == [("schedule_pairs", [("0", "1"), ("1", "0")], 10, False)]
    assert groups == [["0-1"], ["1-0"]]


@pytest.mark.parametrize("build", BUILDERS.values(), ids=BUILDERS)
def test_no_remaining_pair_runs_nothing(groups: list[list[str]], build: Any) -> None:
    step = build()
    ctx = step.execute(_session(), CouplingTargets(PAIRS), StepContext(candidate_qids=["0", "4"]))

    assert Scheduler.calls == []
    assert groups == []
    assert ctx.get_step_result(step.resolved_step_id).couplings == {}


def test_generated_groups_are_reused_and_never_resurrect_filtered_qubits(
    groups: list[list[str]],
) -> None:
    session = _session()
    targets = CouplingTargets(PAIRS)
    ctx = GenerateCRSchedule(max_parallel_ops=4).execute(
        session, targets, StepContext(candidate_qids=QUBITS)
    )
    assert Scheduler.calls == [("schedule_pairs", PAIRS, 4, False)]
    assert ctx.candidate_couplings == ["0-1", "1-0", "4-5"]
    assert ctx.metadata["cr_schedule"] == [[("0", "1")], [("1", "0")], [("4", "5")]]

    ctx.candidate_qids = ["0", "1", "4"]  # A later filter removed qubit 5.
    TwoQubitCalibration(tasks=CR).execute(session, targets, ctx)

    # The groups are reused, not regrouped: the scheduler runs only once.
    assert len(Scheduler.calls) == 1
    assert groups == [["0-1"], ["1-0"]]


def test_inverse_is_rejected_for_coupling_targets(groups: list[list[str]]) -> None:
    with pytest.raises(ValueError, match="inverse does not apply to CouplingTargets"):
        GenerateCRSchedule(inverse=True).execute(
            _session(), CouplingTargets(PAIRS), StepContext(candidate_qids=QUBITS)
        )
    assert Scheduler.calls == []


def test_qubit_targets_still_generate_pairs_from_candidates(groups: list[list[str]]) -> None:
    ctx = GenerateCRSchedule(inverse=True).execute(
        _session(), QubitTargets(QUBITS), StepContext(candidate_qids=QUBITS)
    )
    TwoQubitCalibration(tasks=CR).execute(_session(), QubitTargets(QUBITS), ctx)

    assert Scheduler.calls == [("generate", QUBITS, 10, True)]
    assert groups == [["0-1"]]


def test_empty_generation_replaces_an_older_schedule(groups: list[list[str]]) -> None:
    session = _session()
    targets = CouplingTargets(PAIRS)
    ctx = StepContext(candidate_qids=["0", "4"])
    ctx.metadata["cr_schedule"] = [[("0", "1")]]
    GenerateCRSchedule().execute(session, targets, ctx)
    assert ctx.metadata["cr_schedule"] == []
    assert ctx.candidate_couplings == []
    TwoQubitCalibration(tasks=CR).execute(session, targets, ctx)
    assert groups == []
    assert Scheduler.calls == []
