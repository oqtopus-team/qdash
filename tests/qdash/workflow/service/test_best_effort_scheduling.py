"""Per-target call execution: ordered results, failure policy, and its scope."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from qdash.datamodel.task_call import StepCalls, TaskCall, normalize_calls
from qdash.workflow.service._internal.scheduling_tasks import (
    _execute_coupling_pair_with_session,
    _execute_mux_qubits_with_session,
    _execute_single_qubit_with_session,
)
from qdash.workflow.service.steps import CustomTwoQubit, StepContext
from qdash.workflow.service.targets import QubitTargets

if TYPE_CHECKING:
    from qdash.workflow.service._internal.session import CalibSession


class FakeLogger:
    def error(self, message: str) -> None:
        _ = message

    def info(self, message: str) -> None:
        _ = message


class FakeSession:
    backend_name = "qubex"

    def __init__(self, fail_on: set[tuple[str, str]] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.invocations: list[Any] = []
        self.fail_on = fail_on

    def execute_task(
        self,
        task_name: str,
        qid: str,
        *,
        parameters: dict[str, Any] | None = None,
        invocation: Any = None,
    ) -> dict[str, Any]:
        self.calls.append((task_name, qid))
        self.invocations.append(invocation)
        fails = (
            (task_name, qid) in self.fail_on if self.fail_on is not None else task_name == "fails"
        )
        if fails:
            error = ValueError("fit failed")
            error.qdash_task_ids = {qid: f"{invocation.call_id}-{qid}"}  # type: ignore[attr-defined]
            raise error
        return {"task_id": f"{invocation.call_id}-{qid}", "value": 1.0}


def plan(*names: str, continue_on_failure: bool = False, **on_failure: str) -> StepCalls:
    calls = normalize_calls(TaskCall(name=name, on_failure=on_failure.get(name)) for name in names)  # type: ignore[arg-type]
    return StepCalls(step_id="step", calls=calls, continue_on_failure=continue_on_failure)


def statuses(result: dict[str, Any]) -> list[tuple[str, str]]:
    return [(call["call_id"], call["status"]) for call in result["calls"]]


def test_single_qubit_best_effort_continues_after_task_failure() -> None:
    session = FakeSession()

    result = _execute_single_qubit_with_session(
        cast("CalibSession", session),
        "0",
        plan("first", "fails", "last", continue_on_failure=True),
        FakeLogger(),
    )

    assert session.calls == [("first", "0"), ("fails", "0"), ("last", "0")]
    assert statuses(result) == [("first", "success"), ("fails", "failed"), ("last", "success")]
    assert result["calls"][0]["task_id"] == "first-0"
    # A failed call keeps the task id of its failed run.
    assert result["calls"][1]["task_id"] == "fails-0"
    assert result["calls"][2]["output"] == {"value": 1.0}
    assert result["status"] == "failed"
    assert "fails (fails): fit failed" in result["error"]


def test_single_qubit_remains_fail_fast_by_default_and_keeps_earlier_calls() -> None:
    session = FakeSession()

    result = _execute_single_qubit_with_session(
        cast("CalibSession", session),
        "0",
        plan("first", "fails", "last"),
        FakeLogger(),
    )

    assert session.calls == [("first", "0"), ("fails", "0")]
    assert statuses(result) == [("first", "success"), ("fails", "failed"), ("last", "skipped")]
    assert result["calls"][2]["reason"] == "stopped_after_failure"
    assert result["calls"][2]["after_call_id"] == "fails"
    assert result["status"] == "failed"


def test_call_stop_policy_overrides_best_effort_step() -> None:
    session = FakeSession()

    result = _execute_single_qubit_with_session(
        cast("CalibSession", session),
        "0",
        plan("first", "fails", "last", continue_on_failure=True, fails="stop"),
        FakeLogger(),
    )

    assert session.calls == [("first", "0"), ("fails", "0")]
    assert statuses(result)[-1] == ("last", "skipped")
    assert result["status"] == "failed"


def test_call_continue_policy_overrides_fail_fast_step() -> None:
    session = FakeSession()

    result = _execute_single_qubit_with_session(
        cast("CalibSession", session),
        "0",
        plan("first", "fails", "last", fails="continue"),
        FakeLogger(),
    )

    assert session.calls == [("first", "0"), ("fails", "0"), ("last", "0")]
    assert statuses(result)[-1] == ("last", "success")


def test_mux_failure_policy_is_scoped_to_one_target() -> None:
    session = FakeSession(fail_on={("first", "0")})

    result = _execute_mux_qubits_with_session(
        cast("CalibSession", session),
        ["0", "1"],
        plan("first", "last"),
        FakeLogger(),
    )

    assert statuses(result["0"]) == [("first", "failed"), ("last", "skipped")]
    assert statuses(result["1"]) == [("first", "success"), ("last", "success")]
    assert result["0"]["status"] == "failed"
    assert result["1"]["status"] == "success"
    assert session.calls == [("first", "0"), ("first", "1"), ("last", "1")]


def test_mux_best_effort_continues_each_qubit_independently() -> None:
    session = FakeSession()

    result = _execute_mux_qubits_with_session(
        cast("CalibSession", session),
        ["0", "1"],
        plan("fails", "last", continue_on_failure=True),
        FakeLogger(),
    )

    assert result["0"]["calls"][1]["task_id"] == "last-0"
    assert result["1"]["calls"][1]["task_id"] == "last-1"
    assert result["0"]["status"] == "failed"
    assert result["1"]["status"] == "failed"


def test_repeated_task_keeps_one_result_per_call_with_its_own_invocation() -> None:
    session = FakeSession()
    calls = normalize_calls(
        [
            TaskCall(name="CheckRamsey", call_id="ramsey_coarse", run={"detuning": 0.001}),
            TaskCall(name="CheckRamsey", call_id="ramsey_fine", run={"detuning": 0.0002}),
        ]
    )

    result = _execute_single_qubit_with_session(
        cast("CalibSession", session),
        "0",
        StepCalls(step_id="coherence", calls=calls, plan_digest="abc"),
        FakeLogger(),
    )

    assert [(call["call_id"], call["name"]) for call in result["calls"]] == [
        ("ramsey_coarse", "CheckRamsey"),
        ("ramsey_fine", "CheckRamsey"),
    ]
    assert [call["task_id"] for call in result["calls"]] == ["ramsey_coarse-0", "ramsey_fine-0"]
    assert [(inv.step_id, inv.call_id, inv.plan_digest) for inv in session.invocations] == [
        ("coherence", "ramsey_coarse", "abc"),
        ("coherence", "ramsey_fine", "abc"),
    ]


def test_coupling_best_effort_continues_after_task_failure() -> None:
    session = FakeSession()

    result = _execute_coupling_pair_with_session(
        cast("CalibSession", session),
        "0-1",
        plan("fails", "last", continue_on_failure=True),
        FakeLogger(),
    )

    assert session.calls == [("fails", "0-1"), ("last", "0-1")]
    assert statuses(result) == [("fails", "failed"), ("last", "success")]
    assert result["calls"][1]["task_id"] == "last-0-1"
    assert result["status"] == "failed"


def test_custom_two_qubit_uses_saved_schedule_after_candidate_filtering(monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    def run_coupling_calibrations_parallel(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {qid: {"status": "success", "calls": []} for qid in kwargs["coupling_qids"]}

    monkeypatch.setattr(
        "qdash.workflow.service._internal.scheduling_tasks.run_coupling_calibrations_parallel",
        run_coupling_calibrations_parallel,
    )
    spec = object()
    session = SimpleNamespace(
        username="alice",
        chip_id="64Q",
        project_id="project-1",
        worker_spec=lambda: spec,
        record_stage_result=lambda *args: None,
    )
    ctx = StepContext(
        candidate_qids=["0", "1"], metadata={"cr_schedule": [[("0", "1"), ("4", "5")]]}
    )
    step = CustomTwoQubit(
        step_name="jazz_characterization",
        tasks=[TaskCall(name="CheckJAZZ")],
        continue_on_failure=True,
    )

    result = step.execute(cast("CalibSession", session), QubitTargets([]), ctx)

    assert calls[0]["coupling_qids"] == ["0-1"]
    assert calls[0]["plan"].continue_on_failure is True
    assert calls[0]["plan"].step_id == "jazz_characterization"
    assert calls[0]["worker"] is spec
    assert result.metadata["jazz_characterization"].successful_couplings() == ["0-1"]
    assert (
        result.get_step_result("jazz_characterization") is result.metadata["jazz_characterization"]
    )
