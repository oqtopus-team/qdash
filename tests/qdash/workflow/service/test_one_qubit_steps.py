from types import SimpleNamespace

from qdash.workflow.service.steps.one_qubit import CustomOneQubit


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

    result = step._execute_direct(service, ["1", "2"])

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
