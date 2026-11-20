"""Registered workflows: QDash.workflows list, get and run, and the run handle."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from test_sdk_session import Server, detail

from qdash.client.services.models import FlowSummary
from qdash.sdk import (
    QDash,
    QDashConfigError,
    QDashNotFoundError,
    QDashValidationError,
    RunResult,
    Workflow,
    WorkflowRun,
)

NAME = "coherence_check"
FLOW_CHIP = "64Qv3"


def summary_body(name: str = NAME) -> dict[str, Any]:
    return {
        "name": name,
        "created_by": "alice",
        "description": "T1 and T2 echo",
        "chip_id": FLOW_CHIP,
        "flow_function_name": name,
        "created_at": "2026-11-01T00:00:00Z",
        "updated_at": "2026-11-02T00:00:00Z",
        "tags": ["coherence"],
    }


def flow_body() -> dict[str, Any]:
    return {
        **summary_body(),
        "code": "from prefect import flow\n",
        "default_parameters": {"qids": ["0"], "shots": 1024},
        "default_run_parameters": {"interval": 262_144},
        "file_path": "user_flows/coherence_check.py",
    }


def execute_body() -> dict[str, Any]:
    return {
        "execution_id": "exec-1",
        "flow_run_id": "run-1",
        "flow_run_url": "http://prefect/run-1",
        "qdash_ui_url": "http://qdash/executions/exec-1",
        "message": "started",
    }


def routes(**extra: list[httpx.Response]) -> dict[tuple[str, str], list[httpx.Response]]:
    table = {
        ("GET", "/flows"): [
            httpx.Response(200, json={"flows": [summary_body(), summary_body("t1_scan")]})
        ],
        ("GET", f"/flows/{NAME}"): [httpx.Response(200, json=flow_body())],
        ("POST", f"/flows/{NAME}/execute"): [httpx.Response(200, json=execute_body())],
    }
    table.update({("GET", path): queue for path, queue in extra.items()})
    return table


def executions(*responses: httpx.Response) -> dict[str, list[httpx.Response]]:
    return {"/executions/exec-1": list(responses)}


def test_list_returns_summaries_scoped_to_the_project() -> None:
    server = Server(routes())
    with QDash(server.client(), project_id="project-b") as qdash:
        workflows = qdash.workflows.list()

    assert [type(w) for w in workflows] == [FlowSummary, FlowSummary]
    assert [(w.name, w.chip_id, w.description) for w in workflows] == [
        (NAME, FLOW_CHIP, "T1 and T2 echo"),
        ("t1_scan", FLOW_CHIP, "T1 and T2 echo"),
    ]
    assert server.paths() == [("GET", "/flows")]
    assert server.requests[0].headers["X-Project-Id"] == "project-b"


def test_get_maps_the_saved_workflow_and_dispatches_nothing() -> None:
    server = Server(routes())
    workflow = QDash(server.client()).workflows.get(NAME)

    assert isinstance(workflow, Workflow)
    assert (workflow.name, workflow.chip_id) == (NAME, FLOW_CHIP)
    assert workflow.description == "T1 and T2 echo"
    assert workflow.default_parameters == {"qids": ["0"], "shots": 1024}
    assert workflow.detail.code == "from prefect import flow\n"
    assert workflow.detail.default_run_parameters == {"interval": 262_144}
    assert repr(workflow) == f"Workflow(name={NAME!r}, chip_id={FLOW_CHIP!r})"
    # The copy keeps the read detail intact.
    workflow.default_parameters["shots"] = 1
    assert workflow.detail.default_parameters["shots"] == 1024
    assert server.paths() == [("GET", f"/flows/{NAME}")]


def test_get_of_a_missing_workflow_raises_not_found() -> None:
    server = Server(
        {("GET", "/flows/missing"): [httpx.Response(404, json={"detail": "Flow not found"})]}
    )
    with pytest.raises(QDashNotFoundError):
        QDash(server.client()).workflows.get("missing")


@pytest.mark.parametrize("name", ["", "../flows", "a/b", "templates/x", "a b", "x\n", 3])
def test_names_a_saved_workflow_cannot_have_are_rejected_before_a_request(name: Any) -> None:
    server = Server(routes())
    workflows = QDash(server.client()).workflows

    with pytest.raises(ValueError, match="workflow name"):
        workflows.get(name)
    with pytest.raises(ValueError, match="workflow name"):
        workflows.run(name)
    assert server.requests == []


def test_run_of_a_read_workflow_forwards_the_parameters_and_follows_the_whole_run() -> None:
    server = Server(
        routes(
            **executions(
                httpx.Response(404, json={"detail": "not found"}),
                # The first step's execution completes; the run goes on and then fails.
                httpx.Response(200, json=detail("completed", "running")),
                httpx.Response(200, json=detail("completed", "failed")),
            )
        )
    )
    qdash = QDash(server.client())
    workflow = qdash.workflows.get(NAME)

    run = workflow.run(parameters={"qids": ["0", "1"]})

    assert isinstance(run, WorkflowRun)
    assert run.execution_id == "exec-1"
    assert run.response.flow_run_id == "run-1"
    assert repr(run) == f"WorkflowRun(name={NAME!r}, execution_id='exec-1')"
    execute = server.requests[1]
    assert (execute.method, execute.url.path) == ("POST", f"/flows/{NAME}/execute")
    assert json.loads(execute.content) == {"parameters": {"qids": ["0", "1"]}}
    assert execute.headers["X-Project-Id"] == "project-a"

    result = run.wait(timeout_seconds=60, poll_interval_seconds=2)

    assert isinstance(result, RunResult)
    assert result.status == "failed"
    assert result.detail.status == "completed"
    assert result.execution_id == "exec-1"
    assert server.sleeps == [2, 2]


def test_run_by_name_without_parameters_runs_the_saved_defaults() -> None:
    server = Server(routes(**executions(httpx.Response(200, json=detail("cancelled", None)))))
    run = QDash(server.client()).workflows.run(NAME)

    assert server.paths() == [("POST", f"/flows/{NAME}/execute")]
    assert json.loads(server.requests[0].content) == {"parameters": {}}
    result = run.wait()
    assert result.status == "cancelled"
    assert result.detail.pipeline is None


def test_get_reads_the_current_state_without_waiting() -> None:
    server = Server(routes(**executions(httpx.Response(200, json=detail("completed", "running")))))
    run = QDash(server.client()).workflows.run(NAME)

    assert run.get().status == "running"
    assert server.sleeps == []


def test_wait_times_out_without_cancelling() -> None:
    server = Server(routes(**executions(httpx.Response(404, json={"detail": "not found"}))))
    run = QDash(server.client()).workflows.run(NAME)

    with pytest.raises(TimeoutError):
        run.wait(timeout_seconds=0)
    assert {path for _, path in server.paths()} == {f"/flows/{NAME}/execute", "/executions/exec-1"}


def test_run_needs_a_project_but_list_and_get_do_not() -> None:
    server = Server(routes())
    workflows = QDash(server.client(project_id=None)).workflows

    with pytest.raises(QDashConfigError):
        workflows.run(NAME)
    assert server.requests == []
    workflow = workflows.get(NAME)
    workflows.list()
    with pytest.raises(QDashConfigError):
        workflow.run()
    assert server.paths() == [("GET", f"/flows/{NAME}"), ("GET", "/flows")]


def test_a_rejected_run_raises_the_api_error() -> None:
    rejected = {"detail": [{"loc": ["body", "parameters"], "msg": "bad", "type": "dict_type"}]}
    server = Server({("POST", f"/flows/{NAME}/execute"): [httpx.Response(422, json=rejected)]})
    with pytest.raises(QDashValidationError):
        QDash(server.client()).workflows.run(NAME, parameters={"qids": ["0"]})
    assert len(server.requests) == 1


def test_workflows_share_the_session_client_and_its_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QDASH_BASE_URL", "http://qdash.local")
    monkeypatch.setenv("QDASH_API_TOKEN", "api-token")
    monkeypatch.setenv("QDASH_PROJECT_ID", "project-a")

    qdash = QDash.from_env()
    transport = qdash.client._rest_client._client
    assert qdash.workflows._client is qdash.client
    assert qdash.chip(FLOW_CHIP)._pipelines._client is qdash.client
    qdash.close()

    assert transport.is_closed
