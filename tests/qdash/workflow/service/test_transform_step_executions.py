"""Every pipeline step a run reaches is recorded in its own Execution, transforms included.

Transform steps (filters, CR schedules) open their Execution without a backend, tasks or
calibration publication; calibration steps keep their full lifecycle. The fixtures of
``test_calib_session`` record each Execution the pipeline opens, so the order, identity,
status and recorded outcome of every step can be checked without hardware or a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from qdash.datamodel.step_record import TransformStepRecord, step_keys
from qdash.datamodel.task_call import TaskCall
from qdash.workflow.service._internal.session import ExecutionRuntime
from qdash.workflow.service.results import OneQubitResult, QubitCalibData
from qdash.workflow.service.steps import (
    CustomOneQubit,
    FilterByMetric,
    FilterByStatus,
    GenerateCRSchedule,
    StepContext,
)
from qdash.workflow.service.steps.base import CandidateSnapshot, TransformStep
from qdash.workflow.service.targets import QubitTargets
from tests.qdash.workflow.service.test_calib_session import (  # noqa: F401 - fixtures
    CancelledRun,
    IncrementingExecutionCounterRepository,
    TerminationSignal,
    _session,
    chips_without_topology,
    clear_session_state,
    mock_flow_session_deps,
    pipeline_execution_env,
)


def _check_result(statuses: dict[str, str], metrics: dict[str, dict[str, float]] | None = None):
    """A CustomOneQubit execute that records the given per-qubit outcome as its result."""

    def execute(self: CustomOneQubit, session: Any, targets: Any, ctx: StepContext) -> Any:
        result = OneQubitResult(step_id=self.resolved_step_id)
        for qid in ctx.candidate_qids:
            status = statuses.get(qid)
            if status is None:
                continue
            result.add_qubit(
                qid,
                QubitCalibData(
                    status="success" if status == "success" else "failed",
                    metrics=dict((metrics or {}).get(qid, {})),
                    raw={
                        "calls": [
                            {
                                "call_id": "rabi",
                                "name": "CheckRabi",
                                "status": status,
                                "output": (metrics or {}).get(qid, {}),
                            }
                        ]
                    },
                ),
            )
        ctx.record_step_result(self.resolved_step_id, result)
        return ctx

    return execute


@dataclass
class ClearCandidates(TransformStep):
    """Empties the candidate list in place, as a careless custom step might."""

    @property
    def name(self) -> str:
        return "clear_candidates"

    def execute(self, session: Any, targets: Any, ctx: StepContext) -> StepContext:
        ctx.candidate_qids.clear()
        return ctx


@dataclass
class RaiseInTransform(TransformStep):
    exc: BaseException

    @property
    def name(self) -> str:
        return "raise_in_transform"

    def execute(self, session: Any, targets: Any, ctx: StepContext) -> StepContext:
        raise self.exc


def _owner(env: Any, **overrides: Any) -> ExecutionRuntime:
    return _session(
        username="alice",
        chip_id="chip-1",
        project_id="project-1",
        flow_name="nightly",
        lock_repo=env.lock,
        counter_repo=IncrementingExecutionCounterRepository(2),
        **overrides,
    )


@pytest.fixture
def cr_scheduler(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    scheduler = MagicMock()
    monkeypatch.setattr("qdash.workflow.engine.CRScheduler", lambda *a, **kw: scheduler)
    return scheduler


def _transform_result(record: Any) -> dict[str, Any]:
    return dict(record.persisted_note["transform_result"])


def test_calibration_filters_and_schedule_record_ordered_executions(
    pipeline_execution_env: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    cr_scheduler: MagicMock,
) -> None:
    env = pipeline_execution_env
    monkeypatch.setattr(
        CustomOneQubit,
        "execute",
        _check_result(
            {"0": "success", "1": "failed", "2": "success", "3": "success", "4": "success"},
            {"0": {"t1": 50.0}, "2": {"t1": 12.5}, "3": {}, "4": {"t1": 40.0}},
        ),
    )
    # The step derives t1 as a step-level metric, as OneQubitCheck derives its metrics.
    monkeypatch.setattr(CustomOneQubit, "step_metrics", ("t1",))
    cr_scheduler.generate.return_value = SimpleNamespace(parallel_groups=[[("0", "4")]])
    session = _owner(env)

    results = session.run_pipeline(
        QubitTargets(["0", "1", "2", "3", "4"]),
        steps=[
            CustomOneQubit(step_name="check", tasks=[TaskCall(name="CheckRabi", call_id="rabi")]),
            FilterByStatus(step="check"),
            FilterByMetric(step="check", metric="t1", threshold=30.0),
            FilterByStatus(step="check", call_id="rabi"),
            GenerateCRSchedule(max_parallel_ops=4),
        ],
    )

    records = env.records
    assert [r.config.note["step_index"] for r in records] == [1, 2, 3, 4, 5]
    assert [r.config.note["step_kind"] for r in records] == [
        "calibration",
        "transform",
        "transform",
        "transform",
        "transform",
    ]
    assert [r.config.note["step_key"] for r in records] == [
        "check",
        "filter_by_status_2",
        "filter_by_t1",
        "filter_by_status_4",
        "generate_cr_schedule",
    ]
    assert [r.config.note["step_type"] for r in records] == [
        "CustomOneQubit",
        "FilterByStatus",
        "FilterByMetric",
        "FilterByStatus",
        "GenerateCRSchedule",
    ]
    assert all(r.status == "completed" for r in records)
    # The calibration step adopted the reserved ID; every step has its own Execution.
    ids = [r.config.execution_id for r in records]
    assert ids[0] == "exec-reserved" and len(set(ids)) == 5
    assert session.run_execution_ids == ids
    # Every step names the run's session, run and flow run, like a calibration step.
    assert all(r.config.note["flow_run_id"] == "flow-1" for r in records)
    assert all("hardware_reservation" in r.config.note for r in records)
    assert "step_id" not in records[1].config.note
    assert [r.config.flow_name for r in records[1:3]] == [
        "nightly_filter_by_status",
        "nightly_filter_by_t1",
    ]

    by_status = _transform_result(records[1])
    assert by_status["input_qids"] == ["0", "1", "2", "3", "4"]
    assert by_status["output_qids"] == ["0", "2", "3", "4"]
    assert by_status["excluded"] == [{"target": "1", "reason": "step check failed"}]
    assert by_status["criteria"] == "step check: status == success"
    assert (by_status["kind"], by_status["source_step"], by_status["source_found"]) == (
        "filter",
        "check",
        True,
    )

    by_metric = _transform_result(records[2])
    assert by_metric["output_qids"] == ["0", "4"]
    assert by_metric["excluded"] == [
        {"target": "2", "reason": "t1 = 12.5 < 30"},
        {"target": "3", "reason": "metric t1 is missing"},
    ]
    assert (by_metric["metric"], by_metric["threshold"]) == ("t1", 30.0)

    by_call = _transform_result(records[3])
    assert (by_call["input_qids"], by_call["output_qids"], by_call["excluded"]) == (
        ["0", "4"],
        ["0", "4"],
        [],
    )

    schedule = _transform_result(records[4])
    assert schedule["kind"] == "cr_schedule"
    assert schedule["groups"] == [["0-4"]]
    assert schedule["output_couplings"] == ["0-4"]
    assert (schedule["max_parallel_ops"], schedule["direction"]) == (4, "forward")
    assert schedule["message"] is None
    cr_scheduler.generate.assert_called_once()
    assert cr_scheduler.generate.call_args.kwargs["candidate_qubits"] == ["0", "4"]

    assert list(results["transforms"]) == [
        "filter_by_status_2",
        "filter_by_t1",
        "filter_by_status_4",
        "generate_cr_schedule",
    ]
    assert results["transforms"]["filter_by_t1"] == by_metric
    assert results["candidate_couplings"] == ["0-4"]
    # The transforms ran no hardware: only the calibration step closed with publication.
    assert ExecutionRuntime._update_chip_history.call_count == 1  # type: ignore[attr-defined]
    assert ExecutionRuntime._push_to_github_if_configured.call_count == 1  # type: ignore[attr-defined]
    assert env.lock.try_lock_calls == ["exec-reserved"]
    assert env.lock.locked is False


def test_recorded_outcomes_are_snapshots(
    pipeline_execution_env: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = pipeline_execution_env
    monkeypatch.setattr(CustomOneQubit, "execute", _check_result({"0": "success", "1": "failed"}))
    session = _owner(env)

    results = session.run_pipeline(
        QubitTargets(["0", "1"]),
        steps=[
            CustomOneQubit(step_name="check", tasks=[TaskCall(name="CheckRabi")]),
            FilterByStatus(step="check"),
            ClearCandidates(),
        ],
    )

    # The later step emptied the very list the filter produced; the record kept its copy.
    assert _transform_result(env.records[1])["output_qids"] == ["0"]
    assert results["transforms"]["filter_by_status"]["output_qids"] == ["0"]
    cleared = _transform_result(env.records[2])
    assert (cleared["kind"], cleared["input_qids"], cleared["output_qids"]) == (
        "transform",
        ["0"],
        [],
    )
    assert results["candidate_qids"] == []


def test_a_transform_only_run_needs_no_backend_and_publishes_nothing(
    pipeline_execution_env: Any,  # noqa: F811
    cr_scheduler: MagicMock,
) -> None:
    env = pipeline_execution_env
    session = _owner(env)

    results = session.run_pipeline(QubitTargets(["0"]), steps=[GenerateCRSchedule()])

    [record] = env.records
    # The reserved execution is adopted by the first step, whatever its kind.
    assert record.config.execution_id == "exec-reserved"
    assert record.config.connect_backend is False
    assert record.status == "completed"
    assert session.backend is None and session._orchestrator is None
    cr_scheduler.generate.assert_not_called()
    outcome = _transform_result(record)
    assert outcome["groups"] == [] and outcome["output_couplings"] == []
    assert outcome["message"] == "Fewer than 2 candidate qubits (1)"
    assert results["candidate_couplings"] == []
    ExecutionRuntime._update_chip_history.assert_not_called()  # type: ignore[attr-defined]
    ExecutionRuntime._push_to_github_if_configured.assert_not_called()  # type: ignore[attr-defined]
    ExecutionRuntime.record_stage_result.assert_not_called()  # type: ignore[attr-defined]
    assert env.lock.try_lock_calls == ["exec-reserved"]
    assert env.lock.locked is False


def test_a_filter_without_a_source_records_that_it_kept_every_candidate(
    pipeline_execution_env: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero candidates in, nothing excluded, and no made-up reason."""
    env = pipeline_execution_env
    monkeypatch.setattr(CustomOneQubit, "execute", _check_result({}))
    session = _owner(env)

    session.run_pipeline(
        QubitTargets(["0", "1"]),
        steps=[
            CustomOneQubit(step_name="check", tasks=[TaskCall(name="CheckRabi")]),
            FilterByStatus(step="check"),
            FilterByStatus(step="check"),
        ],
    )

    first = _transform_result(env.records[1])
    assert first["output_qids"] == []
    assert first["excluded"] == [
        {"target": "0", "reason": "no result from step check"},
        {"target": "1", "reason": "no result from step check"},
    ]
    empty = _transform_result(env.records[2])
    assert (empty["input_qids"], empty["output_qids"], empty["excluded"]) == ([], [], [])


def test_a_transform_first_hands_the_next_step_a_new_execution(
    pipeline_execution_env: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = pipeline_execution_env
    seen: list[str | None] = []

    def execute(self: CustomOneQubit, session: Any, targets: Any, ctx: StepContext) -> Any:
        seen.append(session.execution_id)
        assert session.backend is not None  # The calibration step has its backend.
        return ctx

    monkeypatch.setattr(CustomOneQubit, "execute", execute)
    session = _owner(env)
    session.run_pipeline(
        QubitTargets(["0", "1"]),
        steps=[ClearCandidates(), CustomOneQubit(tasks=[TaskCall(name="CheckRabi")])],
    )

    transform, calibration = env.records
    assert transform.config.execution_id == "exec-reserved"
    assert transform.config.note["step_kind"] == "transform"
    assert calibration.config.execution_id not in {None, "exec-reserved"}
    assert seen == [calibration.config.execution_id]
    assert [r.status for r in env.records] == ["completed", "completed"]


@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (RuntimeError("bad threshold"), "failed"),
        (CancelledRun("cancelled"), "cancelled"),
        (TerminationSignal("SIGTERM"), "running"),
    ],
)
def test_a_failing_transform_closes_its_execution_and_stops_the_run(
    pipeline_execution_env: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    exc: BaseException,
    status: str,
) -> None:
    env = pipeline_execution_env
    monkeypatch.setattr(CustomOneQubit, "execute", _check_result({"0": "success"}))
    session = _owner(env)

    with pytest.raises(type(exc)):
        session.run_pipeline(
            QubitTargets(["0"]),
            steps=[
                CustomOneQubit(step_name="check", tasks=[TaskCall(name="CheckRabi")]),
                RaiseInTransform(exc=exc),
                CustomOneQubit(step_name="later", tasks=[TaskCall(name="CheckRabi")]),
            ],
        )

    # A termination signal leaves the Execution open for the flow run hooks.
    assert [r.status for r in env.records] == ["completed", status]
    if status == "failed":
        assert env.records[1].message == "bad threshold"
    # No outcome is recorded for a step that did not finish; no later step was opened.
    assert "transform_result" not in getattr(env.records[1], "persisted_note", {})
    assert env.lock.locked is False
    assert session._transform_service is None


def test_step_keys_keep_repeated_transforms_apart() -> None:
    assert step_keys(
        [
            ("check", "check"),
            ("filter_by_status", None),
            ("filter_by_t1", None),
            ("filter_by_status", None),
            ("generate_cr_schedule", None),
        ]
    ) == [
        "check",
        "filter_by_status_2",
        "filter_by_t1",
        "filter_by_status_4",
        "generate_cr_schedule",
    ]
    # A transform never takes a calibration step's ID.
    assert step_keys([("filter_by_status", "filter_by_status"), ("filter_by_status", None)]) == [
        "filter_by_status",
        "filter_by_status_2",
    ]


def test_filter_reasons_follow_the_selected_call() -> None:
    result = OneQubitResult(step_id="check")
    for qid, status, output in (
        ("0", "success", {"t2": 40.0}),
        ("1", "failed", {"t2": 90.0}),
        ("2", "skipped", {}),
        ("3", "success", {}),
    ):
        result.add_qubit(
            qid,
            QubitCalibData(
                status="success",
                raw={
                    "calls": [
                        {
                            "call_id": "ramsey",
                            "name": "CheckRamsey",
                            "status": status,
                            "output": output,
                        }
                    ]
                },
            ),
        )
    result.add_qubit("4", QubitCalibData(status="success", raw={"calls": []}))
    ctx = StepContext(candidate_qids=["0", "1", "2", "3", "4", "5"])
    ctx.record_step_result("check", result)
    step = FilterByMetric(step="check", call_id="ramsey", metric="t2", threshold=50.0)
    before = CandidateSnapshot.of(ctx)

    after = step.execute(MagicMock(), MagicMock(), ctx)
    record = step.result_record(before, after)

    assert isinstance(record, TransformStepRecord)
    assert record.output_qids == []
    assert {e.target: e.reason for e in record.excluded} == {
        "0": "t2 = 40 < 50",
        "1": "call ramsey failed",
        "2": "call ramsey skipped",
        "3": "output t2 of call ramsey is missing",
        "4": "call ramsey has no result",
        "5": "no result from check.ramsey",
    }
