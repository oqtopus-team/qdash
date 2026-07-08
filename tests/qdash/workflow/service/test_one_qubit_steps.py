from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from qdash.workflow.service.steps.one_qubit import CustomOneQubit

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService


def test_custom_one_qubit_direct_targets_create_visible_execution(monkeypatch) -> None:
    init_calls = []
    run_calls = []
    finish_calls = []
    recorded = []

    session = SimpleNamespace(
        execution_id="exec-visible",
        record_stage_result=lambda stage_name, result: recorded.append((stage_name, result)),
    )

    def fake_init_calibration(*args, **kwargs):
        init_calls.append((args, kwargs))
        return session

    def fake_run_qubit_calibrations_parallel(*, qids, tasks, session_config):
        run_calls.append(
            {
                "qids": qids,
                "tasks": tasks,
                "session_config": session_config,
            }
        )
        return {qid: {"status": "success"} for qid in qids}

    def fake_finish_calibration():
        finish_calls.append(True)

    monkeypatch.setattr(
        "qdash.workflow.service.calib_service.init_calibration",
        fake_init_calibration,
    )
    monkeypatch.setattr(
        "qdash.workflow.service.calib_service.finish_calibration",
        fake_finish_calibration,
    )
    monkeypatch.setattr(
        "qdash.workflow.service._internal.scheduling_tasks.run_qubit_calibrations_parallel",
        fake_run_qubit_calibrations_parallel,
    )

    service = SimpleNamespace(
        username="alice",
        chip_id="64Qv3",
        backend_name="qubex",
        project_id="project-1",
        default_run_parameters={"interval": {"value": 128, "value_type": "int"}},
        tags=["simple"],
        flow_name="simple_calibration",
        note={"source": "test"},
    )
    step = CustomOneQubit(step_name="simple_tasks", tasks=["CheckRabi"])

    result = step._execute_direct(cast("CalibService", service), ["1", "2"])

    assert result == {"direct": {"1": {"status": "success"}, "2": {"status": "success"}}}
    assert init_calls
    assert init_calls[0][0][:3] == ("alice", "64Qv3", ["1", "2"])
    assert init_calls[0][1]["flow_name"] == "simple_calibration_simple_tasks"
    assert init_calls[0][1]["project_id"] == "project-1"
    assert init_calls[0][1]["note"] == {
        "type": "1-qubit-direct",
        "stage": "simple_tasks",
        "total_qubits": 2,
    }
    assert run_calls == [
        {
            "qids": ["1", "2"],
            "tasks": ["CheckRabi"],
            "session_config": {
                "username": "alice",
                "chip_id": "64Qv3",
                "backend_name": "qubex",
                "execution_id": "exec-visible",
                "project_id": "project-1",
                "default_run_parameters": {"interval": {"value": 128, "value_type": "int"}},
                "tags": ["simple"],
                "flow_name": "simple_calibration",
                "note": {"source": "test"},
            },
        }
    ]
    assert recorded == [("simple_tasks", result)]
    assert finish_calls == [True]


def test_custom_one_qubit_qubit_targets_use_scheduled_strategy(monkeypatch) -> None:
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import QubitTargets

    calls = []

    class FakeStrategy:
        def execute(self, service, config):
            calls.append(config)
            return {"scheduled": {"1": {"status": "success"}, "4": {"status": "success"}}}

    monkeypatch.setattr(
        "qdash.workflow.service.strategy.get_one_qubit_strategy",
        lambda mode: FakeStrategy(),
    )

    service = SimpleNamespace(
        username="alice",
        chip_id="64Qv3",
        backend_name="qubex",
        project_id="project-1",
        default_run_parameters={},
        tags=[],
        flow_name="simple_calibration",
        note={},
    )
    step = CustomOneQubit(step_name="simple_tasks", tasks=["CheckRabi"], mode="scheduled")

    step.execute(cast("CalibService", service), QubitTargets(["1", "4"]), StepContext())

    assert len(calls) == 1
    assert calls[0].mux_ids == [0, 1]
    assert calls[0].qids == ["1", "4"]
    assert calls[0].tasks == ["CheckRabi"]
    assert calls[0].flow_name == "simple_calibration_simple_tasks"


def test_one_qubit_check_qubit_targets_use_scheduled_strategy(monkeypatch) -> None:
    from qdash.workflow.service.steps.one_qubit import OneQubitCheck
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import QubitTargets

    calls = []

    class FakeStrategy:
        def execute(self, service, config):
            calls.append(config)
            return {"scheduled": {"2": {"status": "success"}, "5": {"status": "success"}}}

    monkeypatch.setattr(
        "qdash.workflow.service.strategy.get_one_qubit_strategy",
        lambda mode: FakeStrategy(),
    )

    service = SimpleNamespace(
        username="alice",
        chip_id="64Qv3",
        backend_name="qubex",
        project_id="project-1",
        default_run_parameters={},
        tags=[],
        flow_name="one_qubit",
        note={},
    )
    step = OneQubitCheck(mode="synchronized", tasks=["CheckRabi"])

    step.execute(cast("CalibService", service), QubitTargets(["2", "5"]), StepContext())

    assert len(calls) == 1
    assert calls[0].mux_ids == [0, 1]
    assert calls[0].qids == ["2", "5"]
    assert calls[0].tasks == ["CheckRabi"]
    assert calls[0].flow_name == "one_qubit_one_qubit_check"


def test_custom_one_qubit_direct_targets_do_not_fallback_tags_to_flow_name(monkeypatch) -> None:
    init_calls = []
    session = SimpleNamespace(
        execution_id="exec-visible",
        record_stage_result=lambda stage_name, result: None,
    )

    def fake_init_calibration(*args, **kwargs):
        init_calls.append((args, kwargs))
        return session

    monkeypatch.setattr(
        "qdash.workflow.service.calib_service.init_calibration",
        fake_init_calibration,
    )
    monkeypatch.setattr(
        "qdash.workflow.service.calib_service.finish_calibration",
        lambda: None,
    )
    monkeypatch.setattr(
        "qdash.workflow.service._internal.scheduling_tasks.run_qubit_calibrations_parallel",
        lambda *, qids, tasks, session_config: {qid: {"status": "success"} for qid in qids},
    )

    service = SimpleNamespace(
        username="alice",
        chip_id="64Qv3",
        backend_name="qubex",
        project_id="project-1",
        default_run_parameters={},
        tags=[],
        flow_name="t1_simple_tasks",
        note={},
    )
    step = CustomOneQubit(step_name="simple_tasks", tasks=["CheckRabi"])

    step._execute_direct(cast("CalibService", service), ["1"])

    assert init_calls[0][1]["flow_name"] == "t1_simple_tasks_simple_tasks"
    assert init_calls[0][1]["tags"] == []
