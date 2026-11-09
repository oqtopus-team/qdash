from types import SimpleNamespace
from typing import Any, cast

import pytest

from qdash.datamodel.task_call import StepCalls, TaskCall, normalize_calls
from qdash.workflow.service._internal.session import CalibSession
from qdash.workflow.service._internal.settings import SessionSettings, WorkerLease, WorkerSpec
from qdash.workflow.service.one_qubit_stage_runner import OneQubitStageRunner


def _plan(*calls: TaskCall) -> StepCalls:
    return StepCalls(step_id="spectroscopy", calls=normalize_calls(calls))


def _service() -> CalibSession:
    return cast(
        "CalibSession",
        SimpleNamespace(
            username="alice",
            chip_id="144Q-test",
            backend_name="qubex",
            project_id="project-1",
            default_run_parameters={"interval": {"value": 1024}},
            task_parameters={"CreateHPIPulse": {"run": {"hpi_duration": {"value": 52}}}},
            tags=["tag-1"],
            note={"kind": "test"},
        ),
    )


def _worker_spec() -> WorkerSpec:
    return WorkerSpec(
        settings=SessionSettings(
            username="alice",
            chip_id="144Q-test",
            project_id="project-1",
            backend_name="qubex",
            task_defaults={"CreateHPIPulse": {"run": {"hpi_duration": {"value": 52}}}},
        ).for_worker(),
        lease=WorkerLease(execution_id="exec-1"),
    )


def test_collect_qids_preserves_order_and_filters_duplicates() -> None:
    runner = OneQubitStageRunner(_service())
    schedule = SimpleNamespace(
        stages=[
            SimpleNamespace(parallel_groups=[["0", "4"], ["1"]]),
            SimpleNamespace(parallel_groups=[["4", "8"]]),
        ]
    )

    assert runner.collect_scheduled_qids(schedule, allowed_qids=["4", "8"]) == ["4", "8"]


def test_execute_scheduled_mux_schedule_hands_workers_the_owner_spec(
    monkeypatch: Any,
) -> None:
    runner = OneQubitStageRunner(_service())
    calls: list[dict[str, Any]] = []

    def run_mux_calibrations_parallel(
        *, mux_groups: list[list[str]], plan: StepCalls, worker: WorkerSpec
    ) -> dict[str, Any]:
        calls.append({"mux_groups": mux_groups, "plan": plan, "worker": worker})
        return {qid: {"calls": [], "status": "success"} for group in mux_groups for qid in group}

    monkeypatch.setattr(
        "qdash.workflow.service.one_qubit_stage_runner.run_mux_calibrations_parallel",
        run_mux_calibrations_parallel,
    )
    schedule = SimpleNamespace(
        stages=[
            SimpleNamespace(box_type="A", parallel_groups=[["0", "4"], ["1"]]),
            SimpleNamespace(box_type="B", parallel_groups=[["8"]]),
        ]
    )
    worker = _worker_spec()

    plan = _plan(TaskCall(name="CheckResonatorSpectroscopy"))
    result = runner.execute_scheduled_mux_schedule(
        schedule,
        plan=plan,
        worker=worker,
        allowed_qids=["0", "8"],
    )

    assert calls[0]["mux_groups"] == [["0"]]
    assert calls[0]["worker"].lease.execution_id == "exec-1"
    assert calls[0]["worker"].settings.task_defaults["CreateHPIPulse"]["run"] == {
        "hpi_duration": {"value": 52}
    }
    assert calls[1]["mux_groups"] == [["8"]]
    assert all(call["plan"] is plan for call in calls)
    assert result == {
        "Box_A": {"0": {"calls": [], "status": "success"}},
        "Box_B": {"8": {"calls": [], "status": "success"}},
    }


class FakeBatchSession:
    def __init__(self, failures: dict[str, set[str]] | None = None) -> None:
        self.calls: list[tuple[str, list[str], str]] = []
        self.failures = failures or {}

    def execute_task_batch(
        self, task_name: str, qids: list[str], *, parameters: Any = None, invocation: Any = None
    ) -> dict[str, dict[str, Any]]:
        self.calls.append((task_name, qids, invocation.call_id))
        failed = self.failures.get(invocation.call_id, set())
        return {
            qid: {
                "task_id": f"{invocation.call_id}-{qid}",
                "status": "failed" if qid in failed else "success",
                **({"error": "fit failed"} if qid in failed else {}),
            }
            for qid in qids
        }


def test_execute_simultaneous_spectroscopy_schedule_batches_current_session(
    monkeypatch: Any,
) -> None:
    runner = OneQubitStageRunner(_service())
    session = FakeBatchSession()
    monkeypatch.setattr(
        "qdash.workflow.service.one_qubit_stage_runner.get_session",
        lambda: session,
    )
    schedule = SimpleNamespace(
        steps=[
            SimpleNamespace(step_index=0, parallel_qids=["0", "4"]),
            SimpleNamespace(step_index=1, parallel_qids=["1", "5"]),
        ]
    )

    result = runner.execute_simultaneous_spectroscopy_schedule(
        schedule,
        plan=_plan(TaskCall(name="CheckSimultaneousQubitSpectroscopy")),
        allowed_qids=["0", "5"],
    )

    assert session.calls == [
        ("CheckSimultaneousQubitSpectroscopy", ["0"], "CheckSimultaneousQubitSpectroscopy"),
        ("CheckSimultaneousQubitSpectroscopy", ["5"], "CheckSimultaneousQubitSpectroscopy"),
    ]
    assert result["step_0"]["0"]["calls"][0]["task_id"] == "CheckSimultaneousQubitSpectroscopy-0"
    assert result["step_1"]["5"]["status"] == "success"


def test_batch_repeats_a_call_per_batch_and_stops_only_the_failed_qubit(
    monkeypatch: Any,
) -> None:
    runner = OneQubitStageRunner(_service())
    session = FakeBatchSession(failures={"coarse": {"0"}})
    monkeypatch.setattr(
        "qdash.workflow.service.one_qubit_stage_runner.get_session", lambda: session
    )
    schedule = SimpleNamespace(steps=[SimpleNamespace(step_index=0, parallel_qids=["0", "4"])])

    result = runner.execute_simultaneous_spectroscopy_schedule(
        schedule,
        plan=_plan(
            TaskCall(name="CheckQubitSpectroscopy", call_id="coarse"),
            TaskCall(name="CheckQubitSpectroscopy", call_id="fine", run={"shots": 2048}),
        ),
    )

    # Each call is one batch over the qubits still running; qubit 0 stopped after coarse.
    assert session.calls == [
        ("CheckQubitSpectroscopy", ["0", "4"], "coarse"),
        ("CheckQubitSpectroscopy", ["4"], "fine"),
    ]
    qubit0 = result["step_0"]["0"]
    qubit4 = result["step_0"]["4"]
    assert [(c["call_id"], c["status"]) for c in qubit0["calls"]] == [
        ("coarse", "failed"),
        ("fine", "skipped"),
    ]
    assert qubit0["calls"][0]["task_id"] == "coarse-0"
    assert [c["task_id"] for c in qubit4["calls"]] == ["coarse-4", "fine-4"]
    assert (qubit0["status"], qubit4["status"]) == ("failed", "success")


def test_batch_preflight_rejects_input_overrides_and_non_batch_tasks(monkeypatch: Any) -> None:
    runner = OneQubitStageRunner(_service())
    monkeypatch.setattr(
        "qdash.workflow.service.one_qubit_stage_runner.batch_capable_tasks",
        lambda backend: {"CheckQubitSpectroscopy": True, "CheckRabi": False},
    )

    with pytest.raises(ValueError) as error:
        runner.preflight_batch(
            _plan(
                TaskCall(name="CheckQubitSpectroscopy", input={"qubit_frequency": 5.0}),
                TaskCall(name="CheckRabi"),
            )
        )

    message = str(error.value)
    assert "spectroscopy.CheckQubitSpectroscopy" in message
    assert "calibration input overrides (qubit_frequency)" in message
    assert "spectroscopy.CheckRabi (CheckRabi): task does not support batch execution" in message
    runner.preflight_batch(_plan(TaskCall(name="CheckQubitSpectroscopy", run={"shots": 1})))


def test_batch_capable_tasks_reads_the_task_registry() -> None:
    import qdash.workflow.calibtasks.qubex  # noqa: F401
    from qdash.workflow.service.one_qubit_stage_runner import batch_capable_tasks

    capable = batch_capable_tasks("qubex")
    assert capable["CheckQubitSpectroscopy"] is True
    assert capable["CheckRabi"] is False


def test_fake_batch_preflight_rejects_inherited_stub() -> None:
    import qdash.workflow.calibtasks.fake  # noqa: F401 - registers actual fake tasks
    from qdash.workflow.calibtasks.base import BaseTask
    from qdash.workflow.calibtasks.fake.base import FakeTask
    from qdash.workflow.service.one_qubit_stage_runner import batch_capable_tasks

    assert BaseTask.registry["fake"]["FakeBringUp"].batch_run is FakeTask.batch_run
    assert batch_capable_tasks("fake")["FakeBringUp"] is False
    service = _service()
    service.backend_name = "fake"
    runner = OneQubitStageRunner(service)
    with pytest.raises(ValueError, match=r"FakeBringUp.*does not support batch execution"):
        runner.preflight_batch(_plan(TaskCall(name="FakeBringUp")))


def test_execute_simultaneous_spectroscopy_schedule_uses_isolated_batch(
    monkeypatch: Any,
) -> None:
    runner = OneQubitStageRunner(_service())
    calls: list[dict[str, Any]] = []

    def run_qubit_batch_calibration_isolated(
        *, qids: list[str], plan: StepCalls, worker: WorkerSpec
    ) -> dict[str, Any]:
        calls.append({"qids": qids, "plan": plan, "worker": worker})
        return {qid: {"calls": [], "status": "success"} for qid in qids}

    monkeypatch.setattr(
        "qdash.workflow.service.one_qubit_stage_runner.run_qubit_batch_calibration_isolated",
        run_qubit_batch_calibration_isolated,
    )
    schedule = SimpleNamespace(
        steps=[
            SimpleNamespace(step_index=0, parallel_qids=["0", "4"]),
            SimpleNamespace(step_index=1, parallel_qids=["1", "5"]),
        ]
    )
    worker = _worker_spec()
    plan = _plan(TaskCall(name="CheckSimultaneousQubitSpectroscopy"))

    result = runner.execute_simultaneous_spectroscopy_schedule(
        schedule,
        plan=plan,
        allowed_qids=["0", "5"],
        worker=worker,
    )

    assert calls == [
        {"qids": ["0"], "plan": plan, "worker": worker},
        {"qids": ["5"], "plan": plan, "worker": worker},
    ]
    assert result == {
        "step_0": {"0": {"calls": [], "status": "success"}},
        "step_1": {"5": {"calls": [], "status": "success"}},
    }
