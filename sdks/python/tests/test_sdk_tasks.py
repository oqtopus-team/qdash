"""The task catalog and single-task runs: QDash.tasks list, get and run."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from test_sdk_session import CHIP, Server

from qdash.sdk import (
    QDashApiError,
    QDashConfigError,
    QDashNotFoundError,
    QDashTransportError,
    QDashValidationError,
    TaskRun,
)
from qdash.sdk.calibration import TaskCall, sweep
from qdash.sdk.pipeline import CustomOneQubit, Pipeline, Qubits

EXECUTE = ("POST", "/tasks/CheckT1/execute")


def task_info(name: str = "CheckT1", file_path: str = "qubex/one_qubit/t1.py") -> dict[str, Any]:
    return {
        "name": name,
        "class_name": name,
        "task_type": "qubit",
        "file_path": file_path,
        "enabled": True,
        "input_parameters": {"qubit_frequency": {"value_type": "float", "unit": "GHz"}},
        "run_parameters": {"time_range": {"value_type": "np.logspace"}, "shots": {}},
        "output_parameters": ["t1"],
    }


def execute_response(**extra: Any) -> dict[str, Any]:
    return {
        "execution_id": "exec-1",
        "flow_run_id": "run-1",
        "flow_run_url": "http://prefect/run-1",
        "qdash_ui_url": "http://qdash/executions/exec-1",
        "message": "started",
        "calibration_session_id": "auto-1",
        "calibration_run_id": "crun-1",
        **extra,
    }


def run_server(response: httpx.Response | None = None) -> Server:
    return Server({EXECUTE: [response or httpx.Response(200, json=execute_response())]})


def sent(server: Server) -> dict[str, Any]:
    (request,) = server.requests
    assert (request.method, request.url.path) == EXECUTE
    body: dict[str, Any] = json.loads(request.content)
    return body


def test_list_reads_the_catalog_of_a_backend() -> None:
    server = Server(
        {("GET", "/task-files/tasks"): [httpx.Response(200, json={"tasks": [task_info()]})]}
    )
    with server.session() as qdash:
        tasks = qdash.tasks.list(backend_name="qubex")
    assert [t.name for t in tasks] == ["CheckT1"]
    assert tasks[0].run_parameters is not None and "time_range" in tasks[0].run_parameters
    assert tasks[0].output_parameters == ["t1"]
    params = server.requests[0].url.params
    assert params["backend"] == "qubex" and "enabled_only" not in params


def test_list_without_backend_uses_the_configured_default() -> None:
    server = Server(
        {
            ("GET", "/task-files/settings"): [
                httpx.Response(200, json={"default_backend": "fake"})
            ],
            ("GET", "/task-files/tasks"): [httpx.Response(200, json={"tasks": []})],
        }
    )
    with server.session() as qdash:
        assert qdash.tasks.list(enabled_only=True) == []
    assert server.requests[1].url.params["backend"] == "fake"
    assert server.requests[1].url.params["enabled_only"] == "true"


def test_list_without_any_default_backend_asks_for_one() -> None:
    server = Server({("GET", "/task-files/settings"): [httpx.Response(200, json={})]})
    with server.session() as qdash, pytest.raises(QDashConfigError, match="backend_name"):
        qdash.tasks.list()


def test_get_selects_exactly_one_definition() -> None:
    catalog = {
        "tasks": [
            task_info(),
            task_info("CheckRabi"),
            task_info("Twin", "a.py"),
            task_info("Twin", "b.py"),
        ]
    }
    server = Server({("GET", "/task-files/tasks"): [httpx.Response(200, json=catalog)]})
    with server.session() as qdash:
        assert qdash.tasks.get("CheckRabi", backend_name="qubex").name == "CheckRabi"
        with pytest.raises(QDashNotFoundError, match="Missing"):
            qdash.tasks.get("Missing", backend_name="qubex")
        with pytest.raises(ValueError, match=r"more than once: a\.py, b\.py"):
            qdash.tasks.get("Twin", backend_name="qubex")
        with pytest.raises(ValueError):
            qdash.tasks.get("", backend_name="qubex")


def test_run_sends_a_task_call_as_the_workbench_does() -> None:
    call = TaskCall(
        name="CheckT1",
        run={"time_range": sweep.logspace(2, 5, 51), "shots": 1024},
        input={"qubit_frequency": 5.2},
    )
    before = call.model_dump()
    server = run_server()
    with server.session() as qdash:
        run = qdash.tasks.run(call, chip_id=CHIP, qid="0", backend_name="qubex")

    assert sent(server) == {
        "chip_id": CHIP,
        "qid": "0",
        "backend_name": "qubex",
        "input_parameter_overrides": {"qubit_frequency": 5.2},
        "run_parameter_overrides": {
            "time_range": {"value": [2, 5, 51], "value_type": "np.logspace"},
            "shots": 1024,
        },
        "reconfigure": False,
        "update_calibration_parameters": False,
        "update_params": False,
    }
    assert call.model_dump() == before
    assert isinstance(run, TaskRun)
    assert run.call == call
    assert run.call is not call
    assert (run.name, run.qid, run.chip_id, run.execution_id) == ("CheckT1", "0", CHIP, "exec-1")
    assert (run.calibration_session_id, run.calibration_run_id) == ("auto-1", "crun-1")
    assert server.requests[0].headers["X-Project-Id"] == "project-a"


def test_the_same_task_call_runs_in_a_calibration_pipeline() -> None:
    call = TaskCall(name="CheckT1", run={"shots": 1024}, update_calibration_parameters=False)
    spec = Pipeline(
        targets=Qubits(["0"]), steps=[CustomOneQubit(step_name="t1", tasks=[call])]
    ).to_spec()
    assert spec["steps"][0]["tasks"][0] == {
        "name": "CheckT1",
        "run": {"shots": 1024},
        "update_calibration_parameters": False,
    }


@pytest.mark.parametrize("update", [True, False])
def test_explicit_update_policy_is_preserved(update: bool) -> None:
    server = run_server()
    with server.session() as qdash:
        qdash.tasks.run(
            TaskCall(name="CheckT1", update_calibration_parameters=update),
            chip_id=CHIP,
            qid="0",
            reconfigure=True,
            update_params=True,
        )
    body = sent(server)
    assert body["update_calibration_parameters"] is update
    assert body["reconfigure"] is True and body["update_params"] is True
    assert body["input_parameter_overrides"] == {} and body["run_parameter_overrides"] == {}
    assert "backend_name" not in body


def test_a_task_name_is_short_for_a_task_call() -> None:
    server = run_server()
    with server.session() as qdash:
        run = qdash.tasks.run(
            "CheckT1",
            chip_id=CHIP,
            qid="0",
            run_parameters={"shots": 10},
            input_parameters={"qubit_frequency": 5.0},
            update_calibration_parameters=True,
            source_task_id="t-0",
        )
    body = sent(server)
    assert body["run_parameter_overrides"] == {"shots": 10}
    assert body["input_parameter_overrides"] == {"qubit_frequency": 5.0}
    assert body["update_calibration_parameters"] is True
    assert body["source_task_id"] == "t-0"
    assert run.call == TaskCall(
        name="CheckT1",
        run={"shots": 10},
        input={"qubit_frequency": 5.0},
        update_calibration_parameters=True,
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"run_parameters": {"shots": 1}},
        {"input_parameters": {}},
        {"update_calibration_parameters": False},
    ],
)
def test_settings_beside_a_task_call_are_rejected_locally(extra: dict[str, Any]) -> None:
    server = run_server()
    with server.session() as qdash, pytest.raises(TypeError, match="on the TaskCall"):
        qdash.tasks.run(TaskCall(name="CheckT1"), chip_id=CHIP, qid="0", **extra)
    assert server.requests == []


@pytest.mark.parametrize(
    ("fields", "named"),
    [
        ({"call_id": "first"}, "call_id"),
        ({"on_failure": "stop"}, "on_failure"),
        ({"call_id": "CheckT1", "on_failure": "continue"}, "call_id and on_failure"),
    ],
)
def test_pipeline_only_call_fields_are_rejected_locally(fields: dict[str, Any], named: str) -> None:
    server = run_server()
    with server.session() as qdash, pytest.raises(ValueError, match=f"{named} only apply"):
        qdash.tasks.run(TaskCall(name="CheckT1", **fields), chip_id=CHIP, qid="0")
    assert server.requests == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"chip_id": "", "qid": "0"},
        {"chip_id": CHIP, "qid": " "},
        {"chip_id": CHIP, "qid": "0", "backend_name": ""},
        {"chip_id": CHIP, "qid": "0", "source_task_id": ""},
        {"chip_id": CHIP, "qid": "0", "calibration_session_id": " "},
        {"chip_id": CHIP, "qid": "0", "idempotency_key": ""},
    ],
)
def test_empty_identifiers_are_rejected_locally(kwargs: dict[str, Any]) -> None:
    server = run_server()
    with server.session() as qdash, pytest.raises(ValueError):
        qdash.tasks.run(TaskCall(name="CheckT1"), **kwargs)
    assert server.requests == []


def test_invalid_task_and_flags_are_rejected_locally() -> None:
    server = run_server()
    with server.session() as qdash:
        with pytest.raises(ValueError):
            qdash.tasks.run("not a task", chip_id=CHIP, qid="0")
        with pytest.raises(TypeError):
            qdash.tasks.run({"name": "CheckT1"}, chip_id=CHIP, qid="0")
        with pytest.raises(TypeError):
            qdash.tasks.run("CheckT1", chip_id=CHIP, qid="0", reconfigure="yes")
    assert server.requests == []


def test_run_needs_a_project() -> None:
    server = run_server()
    with server.session(project_id=None) as qdash, pytest.raises(QDashConfigError, match="project"):
        qdash.tasks.run(TaskCall(name="CheckT1"), chip_id=CHIP, qid="0")
    assert server.requests == []


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(422, json={"detail": "run.shots must be int"}), QDashValidationError),
        (httpx.Response(503, json={"detail": "busy"}), QDashApiError),
    ],
)
def test_failures_are_sent_once_and_raised(response: httpx.Response, error: type) -> None:
    server = run_server(response)
    with server.session() as qdash, pytest.raises(error):
        qdash.tasks.run(TaskCall(name="CheckT1"), chip_id=CHIP, qid="0", idempotency_key="k-1")
    assert len(server.requests) == 1


def test_transport_failure_is_sent_once() -> None:
    attempts: list[httpx.Request] = []

    def fail(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        raise httpx.ReadTimeout("timed out", request=request)

    server = Server()
    server.handler = fail
    with server.session() as qdash, pytest.raises(QDashTransportError):
        qdash.tasks.run(TaskCall(name="CheckT1"), chip_id=CHIP, qid="0")
    assert len(attempts) == 1


def test_association_and_key_are_sent_and_checked() -> None:
    server = run_server(
        httpx.Response(200, json=execute_response(calibration_session_id="cs-1", replayed=True))
    )
    with server.session() as qdash:
        run = qdash.tasks.run(
            TaskCall(name="CheckT1"),
            chip_id=CHIP,
            qid="0",
            calibration_session_id="cs-1",
            idempotency_key="k-1",
        )
    body = sent(server)
    assert (body["calibration_session_id"], body["idempotency_key"]) == ("cs-1", "k-1")
    assert run.calibration_session_id == "cs-1"


@pytest.mark.parametrize(
    "response",
    [
        execute_response(calibration_session_id="other"),
        execute_response(calibration_run_id=None),
    ],
)
def test_unechoed_association_is_unknown_not_retried(response: dict[str, Any]) -> None:
    server = run_server(httpx.Response(200, json=response))
    with server.session() as qdash, pytest.raises(RuntimeError, match="Task result unknown"):
        qdash.tasks.run(
            TaskCall(name="CheckT1"),
            chip_id=CHIP,
            qid="0",
            calibration_session_id="cs-1",
            idempotency_key="k-1",
        )
    assert len(server.requests) == 1


def test_key_alone_needs_a_recorded_run() -> None:
    server = run_server(httpx.Response(200, json=execute_response(calibration_run_id=None)))
    with server.session() as qdash, pytest.raises(RuntimeError):
        qdash.tasks.run(TaskCall(name="CheckT1"), chip_id=CHIP, qid="0", idempotency_key="k")


def test_task_run_repr_sends_nothing_and_results_match_the_call() -> None:
    detail = {
        "name": "quick-run:CheckT1",
        "status": "completed",
        "note": {},
        "task": [
            {"task_id": "t-c", "name": "Configure", "qid": "0", "status": "completed"},
            {"task_id": "t-x", "name": "CheckT1", "qid": "1", "status": "completed"},
            {"task_id": "t-1", "name": "CheckT1", "qid": "0", "status": "failed"},
        ],
    }
    server = Server(
        {
            EXECUTE: [httpx.Response(200, json=execute_response())],
            ("GET", "/executions/exec-1"): [
                httpx.Response(200, json=detail),
            ],
        }
    )
    with server.session() as qdash:
        run = qdash.tasks.run(TaskCall(name="CheckT1"), chip_id=CHIP, qid="0")
        assert repr(run) == "TaskRun(name='CheckT1', qid='0', execution_id='exec-1')"
        assert len(server.requests) == 1
        assert run.wait(timeout_seconds=1, poll_interval_seconds=0).succeeded
        results = run.results()
    assert [(r.task_id, r.status) for r in results] == [("t-1", "failed")]


def test_task_run_keeps_launch_identity_when_call_is_edited() -> None:
    call = TaskCall(name="CheckT1", run={"time_range": sweep.values(100, 200)})
    detail = {
        "name": "quick-run:CheckT1",
        "status": "completed",
        "note": {},
        "task": [{"task_id": "t-1", "name": "CheckT1", "qid": "0", "status": "completed"}],
    }
    server = Server(
        {
            EXECUTE: [httpx.Response(200, json=execute_response())],
            ("GET", "/executions/exec-1"): [httpx.Response(200, json=detail)],
        }
    )
    with server.session() as qdash:
        run = qdash.tasks.run(call, chip_id=CHIP, qid="0")
        call.name = "CheckRabi"
        assert call.run is not None
        call.run["time_range"]["value"].append(300)
        exposed = run.call
        exposed.name = "Configure"
        assert exposed.run is not None
        exposed.run["time_range"]["value"].append(400)
        assert run.name == "CheckT1"
        assert run.call.run == {"time_range": sweep.values(100, 200)}
        assert [result.task_id for result in run.results()] == ["t-1"]
