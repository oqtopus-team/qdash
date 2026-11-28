"""Registered workflows: QDash.workflows list, get and run, and the run handle."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from test_sdk_session import Server, detail

from qdash.sdk import (
    QDash,
    QDashApiError,
    QDashAuthError,
    QDashConfigError,
    QDashConflictError,
    QDashNotFoundError,
    QDashTransportError,
    QDashValidationError,
    Run,
    RunResult,
    Workflow,
    WorkflowCancellation,
    WorkflowRun,
    WorkflowRunResult,
)
from qdash.sdk.types import FlowSummary

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


STATE_PATH = "/calibration-sessions/cs-auto/runs/cpr-1"


def execute_body(*, recorded: bool = True) -> dict[str, Any]:
    body: dict[str, Any] = {
        "execution_id": "exec-1",
        "flow_run_id": "run-1",
        "flow_run_url": "http://prefect/run-1",
        "qdash_ui_url": "http://qdash/executions/exec-1",
        "message": "started",
    }
    if recorded:
        body.update(calibration_session_id="cs-auto", calibration_run_id="cpr-1")
    return body


def state_body(
    flow_status: str,
    *,
    reason: str = "",
    executions: list[tuple[str, str]] | None = None,
    steps: list[tuple[str, int]] | None = None,
) -> dict[str, Any]:
    """A recorded run's state as GET /calibration-sessions/{id}/runs/{run_id} returns it."""
    body: dict[str, Any] = {
        "run_id": "cpr-1",
        "calibration_session_id": "cs-auto",
        "chip_id": FLOW_CHIP,
        "run_kind": "workflow",
        "idempotency_key": "k",
        "requested_by": "alice",
        "dispatch_status": "dispatched",
        "attempts": 1,
        "pipeline_name": NAME,
        "backend_name": "qubex",
        "flow_run_id": "run-1",
        "requested_at": "2026-11-01T00:00:00Z",
        "updated_at": "2026-11-01T00:00:00Z",
        "executions": [
            {"name": NAME, "execution_id": eid, "status": status, "tags": [], "note": {}}
            for eid, status in executions or []
        ],
        "flow_status": flow_status,
        "flow_status_reason": reason,
        "observed_at": "2026-11-01T00:01:00Z",
    }
    if steps:
        body["pipeline"] = {
            "name": NAME,
            "flow_run_id": "run-1",
            "root_execution_id": "exec-1",
            "status": "running",
            "steps": [
                {"index": index, "name": f"step{index}", "execution_id": eid, "status": "running"}
                for eid, index in steps
            ],
        }
    return body


def run_states(*responses: httpx.Response) -> dict[str, list[httpx.Response]]:
    return {STATE_PATH: list(responses)}


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
    with server.session(project_id="project-b") as qdash:
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
    workflow = server.session().workflows.get(NAME)

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
        server.session().workflows.get("missing")


@pytest.mark.parametrize("name", ["", "../flows", "a/b", "templates/x", "a b", "x\n", 3])
def test_names_a_saved_workflow_cannot_have_are_rejected_before_a_request(name: Any) -> None:
    server = Server(routes())
    workflows = server.session().workflows

    with pytest.raises(ValueError, match="workflow name"):
        workflows.get(name)
    with pytest.raises(ValueError, match="workflow name"):
        workflows.run(name)
    assert server.requests == []


def test_run_of_a_read_workflow_forwards_the_parameters_and_follows_the_whole_run() -> None:
    server = Server(
        routes(
            **run_states(
                httpx.Response(404, json={"detail": "not found"}),
                # The first execution completed; the flow goes on and then fails.
                httpx.Response(
                    200, json=state_body("running", executions=[("exec-1", "completed")])
                ),
                httpx.Response(
                    200, json=state_body("failed", executions=[("exec-1", "completed")])
                ),
            ),
            **executions(httpx.Response(200, json=detail("completed", "completed"))),
        )
    )
    qdash = server.session()
    workflow = qdash.workflows.get(NAME)

    run = workflow.run(parameters={"qids": ["0", "1"]})

    assert isinstance(run, WorkflowRun)
    # The handle follows the recorded run, not an execution.
    assert not isinstance(run, Run)
    assert run.execution_id == "exec-1"
    assert run.response.flow_run_id == "run-1"
    assert repr(run) == f"WorkflowRun(name={NAME!r}, execution_id='exec-1')"
    execute = server.requests[1]
    assert (execute.method, execute.url.path) == ("POST", f"/flows/{NAME}/execute")
    assert json.loads(execute.content) == {"parameters": {"qids": ["0", "1"]}}
    assert execute.headers["X-Project-Id"] == "project-a"

    result = run.wait(timeout_seconds=60, poll_interval_seconds=2)

    assert isinstance(result, WorkflowRunResult)
    assert not isinstance(result, RunResult)
    assert (result.status, result.done, result.succeeded) == ("failed", True, False)
    # The first execution's own status never decides the whole run.
    assert result.detail is not None
    assert result.detail.status == "completed"
    assert result.run.run_id == "cpr-1"
    assert repr(result) == "WorkflowRunResult(execution_id='exec-1', status='failed')"
    assert result.execution_id == "exec-1"
    assert server.sleeps == [2, 2]
    assert [path for _, path in server.paths()].count(STATE_PATH) == 3


def test_a_completed_first_execution_does_not_end_a_running_flow() -> None:
    server = Server(
        routes(
            **run_states(
                httpx.Response(
                    200, json=state_body("running", executions=[("exec-1", "completed")])
                ),
                httpx.Response(
                    200,
                    json=state_body(
                        "completed", executions=[("exec-1", "completed"), ("exec-2", "completed")]
                    ),
                ),
            ),
            **executions(httpx.Response(200, json=detail("completed", None))),
        )
    )
    run = server.session().workflows.run(NAME)

    current = run.get()
    assert (current.status, current.done, current.succeeded) == ("running", False, False)
    assert server.sleeps == []
    result = run.wait(poll_interval_seconds=1)
    assert (result.status, result.succeeded) == ("completed", True)
    assert [e.execution_id for e in result.run.executions] == ["exec-1", "exec-2"]


@pytest.mark.parametrize("ended", ["failed", "cancelled", "crashed", "not_launched"])
def test_ended_flows_are_returned_not_raised(ended: str) -> None:
    server = Server(
        routes(
            **run_states(httpx.Response(200, json=state_body(ended))),
            **executions(httpx.Response(200, json=detail("completed", "completed"))),
        )
    )
    result = server.session().workflows.run(NAME).wait()
    assert (result.status, result.done, result.succeeded) == (ended, True, False)


@pytest.mark.parametrize("unsettled", ["dispatching", "running", "unknown", "unavailable"])
def test_unknown_and_unavailable_states_are_waited_on_not_ended(unsettled: str) -> None:
    server = Server(
        routes(
            **run_states(httpx.Response(200, json=state_body(unsettled, reason="Prefect said so"))),
            # A pipeline status the old execution-backed wait would have ended on.
            **executions(httpx.Response(200, json=detail("completed", "completed"))),
        )
    )
    run = server.session().workflows.run(NAME)

    assert run.get().done is False
    with pytest.raises(TimeoutError, match=f"last read: {unsettled}: Prefect said so"):
        run.wait(timeout_seconds=0)


def test_run_by_name_without_parameters_runs_the_saved_defaults() -> None:
    server = Server(
        routes(
            **run_states(httpx.Response(200, json=state_body("cancelled"))),
            **executions(httpx.Response(200, json=detail("cancelled", None))),
        )
    )
    run = server.session().workflows.run(NAME)

    assert server.paths() == [("POST", f"/flows/{NAME}/execute")]
    assert json.loads(server.requests[0].content) == {"parameters": {}}
    result = run.wait()
    assert result.status == "cancelled"
    assert result.detail is not None
    assert result.detail.pipeline is None


def test_get_reads_the_current_state_without_waiting() -> None:
    server = Server(
        routes(
            **run_states(httpx.Response(200, json=state_body("running"))),
            **executions(httpx.Response(200, json=detail("completed", "completed"))),
        )
    )
    run = server.session().workflows.run(NAME)

    assert run.get().status == "running"
    assert server.sleeps == []


def test_wait_times_out_without_cancelling_while_the_run_is_not_found() -> None:
    server = Server(
        routes(
            **run_states(httpx.Response(404, json={"detail": "not found"})),
            **executions(httpx.Response(200, json=detail("completed", "completed"))),
        )
    )
    run = server.session().workflows.run(NAME)

    with pytest.raises(TimeoutError, match="the run was not found"):
        run.wait(timeout_seconds=0)
    # A missing run never falls back to the execution's status.
    assert {path for _, path in server.paths()} == {f"/flows/{NAME}/execute", STATE_PATH}
    with pytest.raises(QDashNotFoundError):
        run.get()


def not_found() -> httpx.Response:
    return httpx.Response(404, json={"detail": "not found"})


@pytest.mark.parametrize("ended", ["completed", "failed", "crashed", "not_launched"])
def test_an_ended_run_without_an_execution_is_returned_without_detail(ended: str) -> None:
    server = Server(
        routes(
            **run_states(httpx.Response(200, json=state_body(ended, reason="flow said so"))),
            **executions(not_found()),
        )
    )
    run = server.session().workflows.run(NAME)

    current = run.get()
    assert (current.status, current.done, current.detail) == (ended, True, None)
    assert current.succeeded is (ended == "completed")
    result = run.wait(poll_interval_seconds=3)
    assert (result.status, result.done, result.detail) == (ended, True, None)
    assert result.run.flow_status_reason == "flow said so"
    # The known whole-run state is returned at once, not after waiting for an execution.
    assert server.sleeps == []
    assert [path for _, path in server.paths()].count("/executions/exec-1") == 2


def test_a_running_run_without_an_execution_reads_without_detail() -> None:
    server = Server(
        routes(
            **run_states(
                httpx.Response(200, json=state_body("dispatching")),
                httpx.Response(200, json=state_body("running")),
            ),
            **executions(not_found()),
        )
    )
    run = server.session().workflows.run(NAME)

    current = run.get()
    assert (current.status, current.done, current.detail) == ("dispatching", False, None)
    with pytest.raises(TimeoutError, match="last read: running"):
        run.wait(timeout_seconds=0)
    # A run that has not ended does not read its execution while waiting.
    assert [path for _, path in server.paths()].count("/executions/exec-1") == 1


def test_an_execution_read_error_other_than_not_found_is_raised() -> None:
    server = Server(
        routes(
            **run_states(httpx.Response(200, json=state_body("completed"))),
            **executions(httpx.Response(403, json={"detail": "forbidden"})),
        )
    )
    run = server.session().workflows.run(NAME)

    with pytest.raises(QDashAuthError):
        run.get()
    with pytest.raises(QDashAuthError):
        run.wait()


def test_executions_lists_every_recorded_execution_of_the_run() -> None:
    later = {**detail("running", None), "name": "coherence_step2"}
    server = Server(
        routes(
            **run_states(
                httpx.Response(
                    200,
                    json=state_body(
                        "running",
                        executions=[("exec-1", "completed"), ("exec-2", "running")],
                        steps=[("exec-2", 2)],
                    ),
                )
            ),
            **executions(httpx.Response(200, json=detail("completed", None))),
            **{"/executions/exec-2": [httpx.Response(200, json=later)]},
        )
    )
    found = server.session().workflows.run(NAME).executions()

    assert [(e.execution_id, e.status) for e in found] == [
        ("exec-1", "completed"),
        ("exec-2", "running"),
    ]
    assert found[0].step is None
    assert found[1].step is not None
    assert found[1].step.index == 2


def test_a_run_without_a_recorded_run_refuses_to_report_the_workflow() -> None:
    server = Server(
        {
            **routes(**executions(httpx.Response(200, json=detail("completed", None)))),
            ("POST", f"/flows/{NAME}/execute"): [
                httpx.Response(200, json=execute_body(recorded=False))
            ],
        }
    )
    run = server.session().workflows.run(NAME)

    with pytest.raises(RuntimeError, match="predates run recording"):
        run.get()
    with pytest.raises(RuntimeError, match="predates run recording"):
        run.wait()
    # Listing executions still works from the first execution, without a status claim.
    assert [e.execution_id for e in run.executions()] == ["exec-1"]
    assert STATE_PATH not in {path for _, path in server.paths()}


def test_run_needs_a_project_but_list_and_get_do_not() -> None:
    server = Server(routes())
    workflows = server.session(project_id=None).workflows

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
        server.session().workflows.run(NAME, parameters={"qids": ["0"]})
    assert len(server.requests) == 1


def test_workflows_share_the_session_client_and_its_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QDASH_BASE_URL", "http://qdash.local")
    monkeypatch.setenv("QDASH_API_TOKEN", "api-token")
    monkeypatch.setenv("QDASH_PROJECT_ID", "project-a")

    qdash = QDash.from_env()
    http_client = qdash._http_client
    assert qdash.workflows._api is qdash.api
    assert qdash.chip(FLOW_CHIP)._pipelines._api is qdash.api
    qdash.close()

    assert http_client.is_closed


def test_a_run_names_its_calibration_session_and_run() -> None:
    recorded = {
        **execute_body(),
        "calibration_session_id": "cs-1",
        "calibration_run_id": "cpr-1",
    }
    server = Server(
        {
            **routes(),
            ("POST", f"/flows/{NAME}/execute"): [httpx.Response(200, json=recorded)],
        }
    )
    run = server.session().workflows.run(
        NAME, calibration_session_id="cs-1", idempotency_key="trial-1"
    )

    assert json.loads(server.requests[0].content) == {
        "parameters": {},
        "calibration_session_id": "cs-1",
        "idempotency_key": "trial-1",
    }
    assert (run.calibration_session_id, run.calibration_run_id) == ("cs-1", "cpr-1")


def test_a_run_result_repr_names_the_status_not_the_whole_detail() -> None:
    from qdash.sdk.types import ExecutionResponseDetail

    result = RunResult("exec-1", ExecutionResponseDetail(**detail("completed", "running")))
    assert repr(result) == "RunResult(execution_id='exec-1', status='running')"


FLOW_RUN = "0b6f6c2e-4c1f-4d3e-9a51-7f2d8e9c1a10"
CANCEL_PATH = f"/executions/{FLOW_RUN}/cancel"


def cancellable(flow_run_id: Any = FLOW_RUN) -> dict[tuple[str, str], list[httpx.Response]]:
    """Routes whose launch names ``flow_run_id``, distinct from the first execution's ID."""
    return {
        **routes(**executions(httpx.Response(200, json=detail("running", None)))),
        ("POST", f"/flows/{NAME}/execute"): [
            httpx.Response(200, json={**execute_body(), "flow_run_id": flow_run_id})
        ],
    }


def cancelled_body() -> dict[str, Any]:
    return {
        "execution_id": FLOW_RUN,
        "status": "cancelling",
        "message": f"Cancellation requested for flow run {FLOW_RUN}",
    }


def test_cancel_posts_once_for_the_whole_flow_run_and_wait_follows_it_to_cancelled() -> None:
    server = Server(
        {
            **cancellable(),
            ("POST", CANCEL_PATH): [httpx.Response(200, json=cancelled_body())],
            ("GET", STATE_PATH): [
                httpx.Response(200, json=state_body("running")),
                httpx.Response(200, json=state_body("cancelled")),
            ],
        }
    )
    run = server.session(project_id="project-b").workflows.run(NAME)
    assert run.flow_run_id == FLOW_RUN

    cancellation = run.cancel()

    assert cancellation == WorkflowCancellation(
        flow_run_id=FLOW_RUN,
        status="cancelling",
        message=f"Cancellation requested for flow run {FLOW_RUN}",
    )
    # One POST, named by the flow run (never the execution), in the session's project.
    assert server.paths() == [("POST", f"/flows/{NAME}/execute"), ("POST", CANCEL_PATH)]
    cancel = server.requests[1]
    assert cancel.headers["X-Project-Id"] == "project-b"
    assert cancel.headers["Authorization"] == "Bearer api-token"
    assert "exec-1" not in str(cancel.url)
    # Cancelling waits for nothing: no state was read and nothing slept.
    assert server.sleeps == []

    result = run.wait(poll_interval_seconds=1)
    assert (result.status, result.done, result.succeeded) == ("cancelled", True, False)
    assert server.sleeps == [1]
    assert server.paths().count(("POST", CANCEL_PATH)) == 1


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (403, QDashAuthError),
        (404, QDashNotFoundError),
        (409, QDashConflictError),
        (500, QDashApiError),
        (503, QDashApiError),
    ],
)
def test_a_refused_cancel_is_raised_and_never_retried(
    status: int, error: type[QDashApiError]
) -> None:
    server = Server(
        {
            **cancellable(),
            ("POST", CANCEL_PATH): [
                httpx.Response(status, headers={"retry-after-ms": "1"}, json={"detail": "refused"}),
                httpx.Response(200, json=cancelled_body()),
            ],
        }
    )
    run = server.session().workflows.run(NAME)

    with pytest.raises(error, match="refused") as raised:
        run.cancel()
    assert raised.value.status_code == status
    assert server.paths().count(("POST", CANCEL_PATH)) == 1
    assert server.sleeps == []


class _ResetOnCancel(Server):
    """A fake server whose connection drops on every cancellation request."""

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == CANCEL_PATH:
            self.requests.append(request)
            raise httpx.ConnectError("connection reset", request=request)
        response: httpx.Response = super().handler(request)
        return response


def test_a_cancel_transport_error_is_raised_and_never_retried() -> None:
    server = _ResetOnCancel(cancellable())
    run = server.session().workflows.run(NAME)

    with pytest.raises(QDashTransportError):
        run.cancel()
    assert server.paths().count(("POST", CANCEL_PATH)) == 1


@pytest.mark.parametrize("flow_run_id", ["", "   ", "run-1", "../flows/x", "exec-1"])
def test_cancel_without_a_valid_flow_run_sends_nothing(flow_run_id: str) -> None:
    server = Server(cancellable(flow_run_id))
    run = server.session().workflows.run(NAME)
    sent = len(server.requests)

    with pytest.raises(RuntimeError, match="no valid flow run"):
        run.cancel()
    assert len(server.requests) == sent


def test_cancel_needs_a_project_and_never_looks_up_an_execution() -> None:
    server = Server(cancellable())
    qdash = server.session()
    launched = qdash.workflows.run(NAME)
    sent = len(server.requests)
    detached = WorkflowRun(qdash._executions, NAME, launched.response)

    with pytest.raises(QDashConfigError, match="needs a project"):
        detached.cancel()
    assert len(server.requests) == sent


def test_a_run_state_for_another_run_is_never_reported() -> None:
    other = {**state_body("completed"), "run_id": "cpr-other"}
    elsewhere = {**state_body("completed"), "calibration_session_id": "cs-other"}
    for body in (other, elsewhere):
        server = Server(
            routes(
                **run_states(httpx.Response(200, json=body)),
                **executions(httpx.Response(200, json=detail("completed", None))),
            )
        )
        run = server.session().workflows.run(NAME)

        with pytest.raises(QDashTransportError, match="response describes run"):
            run.get()
        with pytest.raises(QDashTransportError, match="response describes run"):
            run.wait(timeout_seconds=60)
        with pytest.raises(QDashTransportError, match="response describes run"):
            run.executions()
        # The first execution is never read for a state that is not this run's.
        assert "/executions/exec-1" not in {path for _, path in server.paths()}
