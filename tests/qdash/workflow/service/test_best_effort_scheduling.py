from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from qdash.workflow.service._internal.scheduling_tasks import (
    _execute_coupling_pair_with_session,
    _execute_mux_qubits_with_session,
    _execute_single_qubit_with_session,
)
from qdash.workflow.service.steps import CustomTwoQubit, StepContext
from qdash.workflow.service.targets import QubitTargets

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService


class FakeLogger:
    def error(self, message: str) -> None:
        _ = message

    def info(self, message: str) -> None:
        _ = message


class FakeSession:
    backend_name = "qubex"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def execute_task(self, task_name: str, qid: str) -> dict[str, Any]:
        self.calls.append((task_name, qid))
        if task_name == "fails":
            raise ValueError("fit failed")
        return {"task_id": f"{task_name}-{qid}"}


def test_single_qubit_best_effort_continues_after_task_failure() -> None:
    session = FakeSession()

    result = _execute_single_qubit_with_session(
        cast("CalibService", session),
        "0",
        ["first", "fails", "last"],
        FakeLogger(),
        continue_on_failure=True,
    )

    assert session.calls == [("first", "0"), ("fails", "0"), ("last", "0")]
    assert result["first"]["task_id"] == "first-0"
    assert result["fails"]["status"] == "failed"
    assert result["last"]["task_id"] == "last-0"
    assert result["status"] == "failed"


def test_single_qubit_remains_fail_fast_by_default() -> None:
    session = FakeSession()

    result = _execute_single_qubit_with_session(
        cast("CalibService", session),
        "0",
        ["first", "fails", "last"],
        FakeLogger(),
    )

    assert session.calls == [("first", "0"), ("fails", "0")]
    assert "first" not in result
    assert "fails" not in result
    assert "last" not in result
    assert result["status"] == "failed"


def test_single_qubit_best_effort_stops_on_explicit_prerequisite_failure() -> None:
    session = FakeSession()

    result = _execute_single_qubit_with_session(
        cast("CalibService", session),
        "0",
        ["first", "fails", "last"],
        FakeLogger(),
        continue_on_failure=True,
        stop_on_failure_tasks=("fails",),
    )

    assert session.calls == [("first", "0"), ("fails", "0")]
    assert "last" not in result
    assert result["status"] == "failed"


def test_mux_best_effort_continues_each_qubit_independently() -> None:
    session = FakeSession()

    result = _execute_mux_qubits_with_session(
        cast("CalibService", session),
        ["0", "1"],
        ["fails", "last"],
        FakeLogger(),
        continue_on_failure=True,
    )

    assert result["0"]["last"]["task_id"] == "last-0"
    assert result["1"]["last"]["task_id"] == "last-1"
    assert result["0"]["status"] == "failed"
    assert result["1"]["status"] == "failed"


def test_coupling_best_effort_continues_after_task_failure() -> None:
    session = FakeSession()

    result = _execute_coupling_pair_with_session(
        cast("CalibService", session),
        "0-1",
        ["fails", "last"],
        FakeLogger(),
        continue_on_failure=True,
    )

    assert session.calls == [("fails", "0-1"), ("last", "0-1")]
    assert result["fails"]["status"] == "failed"
    assert result["last"]["task_id"] == "last-0-1"
    assert result["status"] == "failed"


def test_custom_two_qubit_uses_saved_schedule_after_candidate_filtering(monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    def run_coupling_calibrations_parallel(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {qid: {"status": "success"} for qid in kwargs["coupling_qids"]}

    monkeypatch.setattr(
        "qdash.workflow.service._internal.scheduling_tasks.run_coupling_calibrations_parallel",
        run_coupling_calibrations_parallel,
    )
    service = SimpleNamespace(
        username="alice",
        chip_id="64Q",
        backend_name="qubex",
        execution_id="execution-1",
        project_id="project-1",
        default_run_parameters={},
        task_parameters={},
        tags=[],
        flow_name="characterization_jazz",
        note={},
        record_stage_result=lambda *args: None,
    )
    ctx = StepContext(candidate_qids=[], metadata={"cr_schedule": [[("0", "1")]]})
    step = CustomTwoQubit(
        step_name="jazz_characterization",
        tasks=["CheckJAZZ"],
        continue_on_failure=True,
    )

    result = step.execute(cast("CalibService", service), QubitTargets([]), ctx)

    assert calls[0]["coupling_qids"] == ["0-1"]
    assert calls[0]["continue_on_failure"] is True
    assert result.metadata["jazz_characterization"].successful_couplings() == ["0-1"]
