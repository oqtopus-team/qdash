"""Steps with execution_mode="manual" run their rounds exactly as written."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from qdash.common.manual_rounds import ManualRoundsError
from qdash.datamodel.calibration_pipeline import CalibrationPipelineSpec
from qdash.datamodel.flow_targets import FlowTargetOverride
from qdash.datamodel.task_call import TaskCall
from qdash.workflow.service import manual_rounds as manual_module
from qdash.workflow.service._internal import scheduling_tasks
from qdash.workflow.service.flow_targets import override_pipeline
from qdash.workflow.service.pipeline_flow import build_steps
from qdash.workflow.service.pipeline_resources import plan_pipeline_resources
from qdash.workflow.service.steps import (
    CustomOneQubit,
    CustomTwoQubit,
    FilterByStatus,
    OneQubitCheck,
    OneQubitFineTune,
    TwoQubitCalibration,
)
from qdash.workflow.service.steps.pipeline import StepContext
from qdash.workflow.service.targets import MuxTargets, QubitTargets

if TYPE_CHECKING:
    from qdash.workflow.service._internal.session import CalibSession

RABI = [TaskCall(name="CheckRabi")]
CR = [TaskCall(name="CheckCrossResonance")]
WIRING = [
    {"mux": mux, "ctrl": [f"Q{mux}A-2"], "read_out": f"Q{mux}A-1", "read_in": f"Q{mux}A-0"}
    for mux in range(8)
]
COUPLINGS = {"0-1", "1-0", "4-5", "8-9", "12-13", "16-17", "20-21", "24-25", "28-29"}
ONE_QUBIT_ROUNDS = [["0", "8"], ["1", "9"]]
PAIR_ROUNDS = [[("0", "1"), ("4", "5")], [("8", "9")]]


class Recorder:
    """Stands in for the worker processes; records every round handed to them."""

    def __init__(self) -> None:
        self.qubit_rounds: list[list[str]] = []
        self.pair_rounds: list[list[str]] = []

    def qubits(self, qids: list[str], plan: Any, worker: Any) -> dict[str, Any]:
        self.qubit_rounds.append(list(qids))
        return {qid: {"status": "success"} for qid in qids}

    def pairs(self, coupling_qids: list[str], plan: Any, worker: Any) -> dict[str, Any]:
        self.pair_rounds.append(list(coupling_qids))
        return {pair: {"status": "success"} for pair in coupling_qids}


def _forbid(*_: Any, **__: Any) -> Any:
    raise AssertionError("manual rounds must not be scheduled automatically")


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    record = Recorder()
    monkeypatch.setattr(scheduling_tasks, "run_qubit_calibrations_parallel", record.qubits)
    monkeypatch.setattr(scheduling_tasks, "run_coupling_calibrations_parallel", record.pairs)
    monkeypatch.setattr(manual_module, "chip_wiring", lambda chip_id: WIRING)
    monkeypatch.setattr(manual_module, "chip_coupling_ids", lambda project, chip: COUPLINGS)
    logger = SimpleNamespace(info=lambda *_: None, warning=lambda *_: None)
    for module in ("manual_rounds", "steps.one_qubit", "steps.two_qubit"):
        monkeypatch.setattr(f"qdash.workflow.service.{module}.get_run_logger", lambda: logger)
    # Neither scheduler nor any automatic strategy may touch manual rounds.
    monkeypatch.setattr("qdash.workflow.engine.OneQubitScheduler", _forbid)
    monkeypatch.setattr("qdash.workflow.engine.CRScheduler", _forbid)
    monkeypatch.setattr("qdash.workflow.service.strategy.get_one_qubit_strategy", _forbid)
    return record


def _session() -> CalibSession:
    session = SimpleNamespace(
        chip_id="chip",
        project_id="project",
        plan_digest=None,
        stages=[],
        worker_spec=lambda: "worker",
    )
    session.record_stage_result = lambda name, result: session.stages.append(name)
    return cast("CalibSession", session)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

ONE_QUBIT_BUILDERS = {
    "CustomOneQubit": lambda **kw: CustomOneQubit(tasks=RABI, **kw),
    "OneQubitCheck": lambda **kw: OneQubitCheck(tasks=RABI, **kw),
    "OneQubitFineTune": lambda **kw: OneQubitFineTune(tasks=RABI, **kw),
}
TWO_QUBIT_BUILDERS = {
    "CustomTwoQubit": lambda **kw: CustomTwoQubit(tasks=CR, **kw),
    "TwoQubitCalibration": lambda **kw: TwoQubitCalibration(tasks=CR, **kw),
}


@pytest.mark.parametrize("build", ONE_QUBIT_BUILDERS.values(), ids=ONE_QUBIT_BUILDERS)
def test_one_qubit_steps_take_manual_rounds(build: Any) -> None:
    step = build(execution_mode="manual", rounds=(("0", "8"), ["1", "9"]))
    assert step.rounds == ONE_QUBIT_ROUNDS
    with pytest.raises(ManualRoundsError, match="requires rounds"):
        build(execution_mode="manual")
    with pytest.raises(ValueError, match="rounds is only accepted"):
        build(rounds=ONE_QUBIT_ROUNDS)
    with pytest.raises(ValueError, match="Unknown execution_mode 'manaul'"):
        build(execution_mode="manaul", rounds=ONE_QUBIT_ROUNDS)
    with pytest.raises(ManualRoundsError, match="qubit 8 already runs in round 1"):
        build(execution_mode="manual", rounds=[["0", "8"], ["8"]])


@pytest.mark.parametrize("build", TWO_QUBIT_BUILDERS.values(), ids=TWO_QUBIT_BUILDERS)
def test_two_qubit_steps_take_manual_rounds(build: Any) -> None:
    assert build().execution_mode == "automatic"
    step = build(execution_mode="manual", rounds=[[["0", "1"], ("4", "5")], [("8", "9")]])
    assert step.rounds == PAIR_ROUNDS
    with pytest.raises(ValueError, match="max_parallel_ops only caps automatic CR groups"):
        build(execution_mode="manual", rounds=PAIR_ROUNDS, max_parallel_ops=10)
    with pytest.raises(ValueError, match="rounds is only accepted"):
        build(rounds=PAIR_ROUNDS)
    with pytest.raises(ValueError, match="Unknown execution_mode 'scheduled'"):
        build(execution_mode="scheduled")
    with pytest.raises(ManualRoundsError, match="a pair needs two different qubits"):
        build(execution_mode="manual", rounds=[[("3", "3")]])


def test_manual_one_qubit_steps_connect_in_isolated_workers() -> None:
    step = CustomOneQubit(tasks=RABI, execution_mode="manual", rounds=ONE_QUBIT_ROUNDS)
    assert step.connect_parent_backend is False


# ---------------------------------------------------------------------------
# One-qubit execution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("build", ONE_QUBIT_BUILDERS.values(), ids=ONE_QUBIT_BUILDERS)
def test_one_qubit_rounds_run_in_written_order(recorder: Recorder, build: Any) -> None:
    rounds = [["9", "0"], ["8", "1"]]
    step = build(execution_mode="manual", rounds=rounds)
    session = _session()

    ctx = step.execute(session, QubitTargets(["0", "1", "8", "9"]), StepContext())

    assert recorder.qubit_rounds == rounds
    result = ctx.get_step_result(step.resolved_step_id)
    assert sorted(result.qubits) == ["0", "1", "8", "9"]
    assert cast("Any", session).stages == ["1q_manual"]


def test_mux_targets_must_match_the_rounds_exactly(
    recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(MuxTargets, "to_qids", lambda self, chip: ["0", "1", "2", "3", "8", "9"])
    step = CustomOneQubit(tasks=RABI, execution_mode="manual", rounds=ONE_QUBIT_ROUNDS)

    with pytest.raises(ManualRoundsError, match="current qubits 2, 3 are in no round"):
        step.execute(_session(), MuxTargets([0, 2]), StepContext())
    assert recorder.qubit_rounds == []


def test_filtered_out_qubits_fail_instead_of_being_dropped(recorder: Recorder) -> None:
    step = CustomOneQubit(tasks=RABI, execution_mode="manual", rounds=ONE_QUBIT_ROUNDS)
    ctx = StepContext(candidate_qids=["0", "1", "8"])
    ctx.filters.append(cast("Any", object()))

    with pytest.raises(ManualRoundsError, match=r"round 2 \(9\): qubit 9 is not among"):
        step.execute(_session(), QubitTargets(["0", "1", "8", "9"]), ctx)
    assert recorder.qubit_rounds == []


def test_hardware_conflicts_fail_before_any_worker(recorder: Recorder) -> None:
    step = CustomOneQubit(tasks=RABI, execution_mode="manual", rounds=[["0", "1"]])

    with pytest.raises(ManualRoundsError, match="qubits 0 and 1 share MUX 0"):
        step.execute(_session(), QubitTargets(["0", "1"]), StepContext())
    with pytest.raises(ManualRoundsError, match="qubits 0 and 1 share MUX 0"):
        step.preflight(_session())
    assert recorder.qubit_rounds == []


# ---------------------------------------------------------------------------
# Two-qubit execution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("build", TWO_QUBIT_BUILDERS.values(), ids=TWO_QUBIT_BUILDERS)
def test_pair_rounds_run_as_written_and_ignore_an_earlier_schedule(
    recorder: Recorder, build: Any
) -> None:
    step = build(execution_mode="manual", rounds=PAIR_ROUNDS)
    ctx = StepContext(candidate_qids=["0", "1", "4", "5", "8", "9", "12"])
    ctx.metadata["cr_schedule"] = [[("12", "13")]]

    ctx = step.execute(_session(), QubitTargets(["0"]), ctx)

    assert recorder.pair_rounds == [["0-1", "4-5"], ["8-9"]]
    assert sorted(ctx.get_step_result(step.resolved_step_id).couplings) == ["0-1", "4-5", "8-9"]


def test_large_manual_rounds_are_not_chunked(recorder: Recorder) -> None:
    pairs = [(str(4 * mux), str(4 * mux + 1)) for mux in range(8)]
    step = CustomTwoQubit(tasks=CR, execution_mode="manual", rounds=[pairs])
    candidates = [qid for pair in pairs for qid in pair]

    step.execute(_session(), QubitTargets(candidates), StepContext(candidate_qids=candidates))

    assert recorder.pair_rounds == [[f"{c}-{t}" for c, t in pairs]]


def test_reversed_or_unknown_pairs_fail_before_any_worker(recorder: Recorder) -> None:
    step = CustomTwoQubit(tasks=CR, execution_mode="manual", rounds=[[("5", "4")]])
    with pytest.raises(ManualRoundsError, match=r"5-4 is not a coupling.*4-5 is"):
        step.execute(_session(), QubitTargets(["4", "5"]), StepContext(candidate_qids=["4", "5"]))
    assert recorder.pair_rounds == []


def test_pair_qubits_outside_the_candidates_fail(recorder: Recorder) -> None:
    step = TwoQubitCalibration(tasks=CR, execution_mode="manual", rounds=PAIR_ROUNDS)
    # Fewer than two candidates no longer skips the step silently.
    with pytest.raises(ManualRoundsError, match="qubit 1 of 0-1"):
        step.execute(_session(), QubitTargets(["0"]), StepContext(candidate_qids=["0"]))
    assert recorder.pair_rounds == []


def test_automatic_steps_keep_the_default_group_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[int] = []

    class Scheduler:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def generate(self, candidate_qubits: list[str], max_parallel_ops: int) -> Any:
            requested.append(max_parallel_ops)
            return SimpleNamespace(parallel_groups=[])

    monkeypatch.setattr("qdash.workflow.engine.CRScheduler", Scheduler)
    monkeypatch.setattr(
        "qdash.workflow.service.steps.two_qubit.get_qubex_paths",
        lambda: SimpleNamespace(wiring_yaml=lambda chip: "w"),
    )
    logger = SimpleNamespace(info=lambda *_: None, warning=lambda *_: None)
    monkeypatch.setattr("qdash.workflow.service.steps.two_qubit.get_run_logger", lambda: logger)
    session = cast(
        "CalibSession", SimpleNamespace(chip_id="c", username="u", project_id="p", plan_digest=None)
    )
    ctx = StepContext(candidate_qids=["0", "1"])

    CustomTwoQubit(tasks=CR).execute(session, QubitTargets(["0", "1"]), ctx)
    TwoQubitCalibration(tasks=CR, max_parallel_ops=3).execute(
        session, QubitTargets(["0", "1"]), ctx
    )

    assert requested == [10, 3]


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


def test_target_overrides_never_replace_manual_rounds() -> None:
    steps = [CustomTwoQubit(tasks=CR, execution_mode="manual", rounds=PAIR_ROUNDS)]
    for override in (
        FlowTargetOverride(qids=["0", "1"]),
        FlowTargetOverride(coupling_pairs=[["0", "1"]]),
    ):
        with pytest.raises(
            ValueError, match=r"Target overrides are not accepted.*custom_two_qubit"
        ):
            override_pipeline(QubitTargets(["0"]), steps, override, _forbid)
    # Without an override the steps pass through untouched.
    assert override_pipeline(QubitTargets(["0"]), steps, None, _forbid)[1] == steps


def test_pipeline_specs_build_manual_steps() -> None:
    spec = CalibrationPipelineSpec.model_validate(
        {
            "spec_version": 2,
            "targets": {"qids": ["0", "1", "8", "9"]},
            "steps": [
                {
                    "type": "CustomOneQubit",
                    "tasks": [{"name": "CheckRabi"}],
                    "execution_mode": "manual",
                    "rounds": ONE_QUBIT_ROUNDS,
                },
                {"type": "OneQubitCheck", "execution_mode": "manual", "rounds": [["8"]]},
                {
                    "type": "CustomTwoQubit",
                    "tasks": [{"name": "CheckCrossResonance"}],
                    "execution_mode": "manual",
                    "rounds": [[["0", "1"]], [["8", "9"]]],
                },
                {"type": "TwoQubitCalibration", "max_parallel_ops": 4},
            ],
        }
    )
    custom, check, pairs, full = build_steps(spec)
    assert isinstance(custom, CustomOneQubit) and custom.rounds == ONE_QUBIT_ROUNDS
    assert isinstance(check, OneQubitCheck) and check.rounds == [["8"]]
    assert isinstance(pairs, CustomTwoQubit)
    assert pairs.rounds == [[("0", "1")], [("8", "9")]] and pairs.max_parallel_ops is None
    assert isinstance(full, TwoQubitCalibration)
    assert full.execution_mode == "automatic" and full.max_parallel_ops == 4


def test_manual_rounds_are_part_of_the_hardware_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[list[str]] = []

    def scope(chip_id: str, parameters: dict[str, Any]) -> Any:
        from qdash.common.execution_resources import ExecutionResourceScope

        requested.append(list(parameters.get("qids", [])))
        return ExecutionResourceScope(chip_id, tuple(f"q{q}" for q in parameters["qids"]))

    monkeypatch.setattr(
        "qdash.workflow.service.pipeline_resources.resolve_execution_resource_scope", scope
    )
    steps = [
        FilterByStatus(),
        CustomTwoQubit(tasks=CR, execution_mode="manual", rounds=PAIR_ROUNDS),
    ]
    result = plan_pipeline_resources("chip", QubitTargets(["0"]), steps)
    assert requested == [["0"], ["0", "1", "4", "5", "8", "9"]]
    assert not result.exclusive
