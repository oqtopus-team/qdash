"""The QDash session: requests, run handles, client ownership and project scope."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from qdash.sdk import (
    QDash,
    QDashApiError,
    QDashConfig,
    QDashConfigError,
    QDashValidationError,
)
from qdash.sdk.pipeline import CustomOneQubit, Pipeline, Qubits, TaskCall

CHIP = "64Qv3"


def pipeline() -> Pipeline:
    return Pipeline(
        name="coherence",
        targets=Qubits(["0", "1"]),
        steps=[CustomOneQubit(step_name="coherence", tasks=[TaskCall(name="CheckT1")])],
    )


def validate_body(*, valid: bool = True) -> dict[str, Any]:
    problems = [] if valid else [{"path": "targets.qids[0]", "message": "unknown qubit"}]
    return {"valid": valid, "problems": problems, "backend_name": "qubex", "steps": []}


def execute_body() -> dict[str, Any]:
    return {
        "execution_id": "exec-1",
        "flow_run_id": "run-1",
        "flow_run_url": "http://prefect/run-1",
        "qdash_ui_url": "http://qdash/executions/exec-1",
        "message": "started",
        "steps": [],
    }


def detail(status: str, pipeline_status: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": "coherence", "status": status, "task": [], "note": {}}
    if pipeline_status is not None:
        payload["pipeline"] = {
            "name": "coherence",
            "flow_run_id": "run-1",
            "root_execution_id": "exec-1",
            "status": pipeline_status,
            "steps": [],
        }
    return payload


class Server:
    """A fake QDash API that records requests and answers from per-route queues."""

    def __init__(self, routes: dict[tuple[str, str], list[httpx.Response]] | None = None) -> None:
        self.routes = routes or {}
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        queue = self.routes.get((request.method, request.url.path))
        if not queue:
            return httpx.Response(500, json={"detail": f"unexpected {request.url.path}"})
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def http_client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))

    def config(self, *, project_id: str | None = "project-a") -> QDashConfig:
        return QDashConfig(
            base_url="http://qdash.local", api_token="api-token", project_id=project_id
        )

    def session(self, *, project_id: str | None = "project-a") -> QDash:
        """A session on a borrowed client whose requests reach this fake server."""
        return QDash(
            self.config(project_id=project_id),
            http_client=self.http_client(),
            sleep=self.sleeps.append,
        )

    def paths(self) -> list[tuple[str, str]]:
        return [(request.method, request.url.path) for request in self.requests]


def test_defining_a_pipeline_and_opening_a_session_send_nothing() -> None:
    server = Server()
    with server.session():
        pipeline()

    assert server.requests == []


def test_validate_posts_the_spec_and_returns_problems_as_data() -> None:
    server = Server(
        {
            ("POST", "/calibration-pipelines/validate"): [
                httpx.Response(200, json=validate_body(valid=False))
            ]
        }
    )
    with server.session() as qdash:
        result = qdash.pipelines.validate(pipeline(), chip_id=CHIP, backend_name="qubex")

    assert result.valid is False
    assert result.problems is not None
    assert result.problems[0].path == "targets.qids[0]"
    assert server.paths() == [("POST", "/calibration-pipelines/validate")]
    request = server.requests[0]
    assert json.loads(request.content) == {
        "chip_id": CHIP,
        "spec": pipeline().to_spec(),
        "backend_name": "qubex",
    }
    assert request.headers["Authorization"] == "Bearer api-token"
    assert request.headers["X-Project-Id"] == "project-a"


def test_catalog_passes_the_backend() -> None:
    catalog = {
        "backend_name": "fake",
        "step_types": [],
        "one_qubit_execution_modes": ["parallel_by_round"],
        "two_qubit_execution_modes": ["automatic"],
        "tasks": {"qubit": ["CheckT1"]},
        "spec_version": 2,
        "spec_schema": {},
    }
    server = Server(
        {("GET", "/calibration-pipelines/catalog"): [httpx.Response(200, json=catalog)]}
    )
    with server.session() as qdash:
        result = qdash.pipelines.catalog(backend_name="fake")

    assert result.tasks == {"qubit": ["CheckT1"]}
    assert server.requests[0].url.params["backend_name"] == "fake"


def test_execute_then_wait_follows_the_whole_pipeline() -> None:
    server = Server(
        {
            ("POST", "/calibration-pipelines/execute"): [httpx.Response(202, json=execute_body())],
            ("GET", "/executions/exec-1"): [
                # Not listed yet, then step 1 done while the run continues, then the run ends.
                httpx.Response(404, json={"detail": "not found"}),
                httpx.Response(200, json=detail("running", None)),
                httpx.Response(200, json=detail("completed", "running")),
                httpx.Response(200, json=detail("completed", "completed")),
            ],
        }
    )
    with server.session() as qdash:
        run = qdash.pipelines.execute(pipeline(), chip_id=CHIP)
        assert server.paths() == [("POST", "/calibration-pipelines/execute")]

        finished = run.wait(timeout_seconds=60, poll_interval_seconds=2)

    assert run.execution_id == "exec-1"
    assert finished.pipeline is not None
    assert finished.pipeline.status == "completed"
    assert server.paths().count(("GET", "/executions/exec-1")) == 4
    assert server.sleeps == [2, 2, 2]
    assert ("POST", "/calibration-pipelines/validate") not in server.paths()


def calibration_session_body(session_id: str = "cs-1", chip_id: str = CHIP) -> dict[str, Any]:
    return {
        "calibration_session_id": session_id,
        "project_id": "project-a",
        "chip_id": chip_id,
        "objective": "coherence",
        "created_by": "alice",
        "status": "open",
        "created_at": "2026-11-24T00:00:00Z",
        "updated_at": "2026-11-24T00:00:00Z",
    }


def _recorded_server(execute: dict[str, Any]) -> Server:
    return Server(
        {
            ("GET", "/calibration-sessions/cs-1"): [
                httpx.Response(200, json=calibration_session_body())
            ],
            ("POST", "/calibration-pipelines/execute"): [httpx.Response(202, json=execute)],
        }
    )


def test_execute_forwards_the_decision_a_recorded_run_carries_out() -> None:
    linked = {
        **execute_body(),
        "calibration_session_id": "cs-1",
        "pipeline_run_id": "cpr-1",
        "decision_id": "cd-1",
    }
    server = _recorded_server(linked)
    with server.session() as qdash:
        run = qdash.pipelines.execute(
            pipeline(),
            chip_id=CHIP,
            calibration_session_id="cs-1",
            idempotency_key="key-1",
            decision_id="cd-1",
        )
    body = json.loads(server.requests[-1].content)
    assert body["decision_id"] == "cd-1"
    assert body["calibration_session_id"] == "cs-1"
    assert body["idempotency_key"] == "key-1"
    assert run.response.decision_id == "cd-1"


def test_execute_without_a_decision_sends_none() -> None:
    server = _recorded_server(
        {**execute_body(), "calibration_session_id": "cs-1", "pipeline_run_id": "cpr-1"}
    )
    with server.session() as qdash:
        qdash.pipelines.execute(
            pipeline(), chip_id=CHIP, calibration_session_id="cs-1", idempotency_key="key-1"
        )
    assert "decision_id" not in json.loads(server.requests[-1].content)


def test_a_dropped_decision_link_is_unknown_and_not_retried() -> None:
    # A server that ignores decision_id records the run without its intent.
    server = _recorded_server(
        {**execute_body(), "calibration_session_id": "cs-1", "pipeline_run_id": "cpr-1"}
    )
    with (
        server.session() as qdash,
        pytest.raises(RuntimeError, match=r"without its decision 'cd-1'.*Do not retry"),
    ):
        qdash.pipelines.execute(
            pipeline(),
            chip_id=CHIP,
            calibration_session_id="cs-1",
            idempotency_key="key-1",
            decision_id="cd-1",
        )
    assert server.paths().count(("POST", "/calibration-pipelines/execute")) == 1


def test_a_decision_needs_a_calibration_session() -> None:
    server = Server()
    with (
        server.session() as qdash,
        pytest.raises(ValueError, match="decision_id needs calibration_session_id"),
    ):
        qdash.pipelines.execute(pipeline(), chip_id=CHIP, decision_id="cd-1")
    assert server.requests == []


def test_wait_times_out_without_cancelling_the_run() -> None:
    server = Server(
        {
            ("POST", "/calibration-pipelines/execute"): [httpx.Response(202, json=execute_body())],
            ("GET", "/executions/exec-1"): [httpx.Response(200, json=detail("running", "running"))],
        }
    )
    with server.session() as qdash:
        run = qdash.pipelines.execute(pipeline(), chip_id=CHIP)
        with pytest.raises(TimeoutError):
            run.wait(timeout_seconds=0, poll_interval_seconds=1)

    assert {path for _, path in server.paths()} == {
        "/calibration-pipelines/execute",
        "/executions/exec-1",
    }


def test_execute_rejection_raises_with_the_problems() -> None:
    rejected = {"detail": {"message": "calibration pipeline spec is not valid", "problems": []}}
    server = Server(
        {("POST", "/calibration-pipelines/execute"): [httpx.Response(422, json=rejected)]}
    )
    with server.session() as qdash, pytest.raises(QDashValidationError) as raised:
        qdash.pipelines.execute(pipeline(), chip_id=CHIP)

    assert raised.value.payload == rejected
    assert len(server.requests) == 1


def test_permission_errors_propagate_without_retry() -> None:
    forbidden = {"detail": "Editor role required"}
    server = Server(
        {("POST", "/calibration-pipelines/execute"): [httpx.Response(403, json=forbidden)]}
    )
    with server.session() as qdash, pytest.raises(QDashApiError) as raised:
        qdash.pipelines.execute(pipeline(), chip_id=CHIP)

    assert raised.value.status_code == 403
    assert len(server.requests) == 1


def test_execute_needs_a_project() -> None:
    server = Server()
    with server.session(project_id=None) as qdash, pytest.raises(QDashConfigError):
        qdash.pipelines.execute(pipeline(), chip_id=CHIP)

    assert server.requests == []


def test_a_borrowed_http_client_is_not_closed() -> None:
    server = Server(
        {("POST", "/calibration-pipelines/validate"): [httpx.Response(200, json=validate_body())]}
    )
    http_client = server.http_client()
    with QDash(server.config(), http_client=http_client) as qdash:
        qdash.pipelines.validate(pipeline(), chip_id=CHIP)

    assert not http_client.is_closed
    http_client.close()


def test_project_override_leaves_the_config_unchanged() -> None:
    server = Server(
        {("POST", "/calibration-pipelines/validate"): [httpx.Response(200, json=validate_body())]}
    )
    config = server.config(project_id="project-a")
    http_client = server.http_client()

    with QDash(config, project_id="project-b", http_client=http_client) as qdash:
        assert qdash.project_id == "project-b"
        qdash.pipelines.validate(pipeline(), chip_id=CHIP)
    with QDash(config, http_client=http_client) as qdash:
        qdash.pipelines.validate(pipeline(), chip_id=CHIP)

    assert config.project_id == "project-a"
    assert [request.headers["X-Project-Id"] for request in server.requests] == [
        "project-b",
        "project-a",
    ]


def test_with_project_shares_the_connection_and_scopes_every_resource() -> None:
    server = Server(
        {
            ("GET", "/chips"): [httpx.Response(200, json={"chips": [], "total": 0})],
            ("POST", "/calibration-pipelines/validate"): [
                httpx.Response(200, json=validate_body())
            ],
        }
    )
    owner = server.session(project_id="project-a")
    scoped = owner.with_project("project-b")

    scoped.api.chip.list_chips()
    scoped.pipelines.validate(pipeline(), chip_id=CHIP)
    owner.api.chip.list_chips()
    scoped.close()

    assert owner.project_id == "project-a"
    assert [r.headers.get_list("X-Project-Id") for r in server.requests] == [
        ["project-b"],
        ["project-b"],
        ["project-a"],
    ]
    assert scoped._http_client is owner._http_client
    assert not owner._http_client.is_closed
    with pytest.raises(ValueError, match="project_id"):
        owner.with_project("")


def test_owned_session_closes_its_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDASH_BASE_URL", "http://qdash.local")
    monkeypatch.setenv("QDASH_API_TOKEN", "api-token")
    monkeypatch.setenv("QDASH_PROJECT_ID", "project-a")

    with QDash.from_env(project_id="project-b") as qdash:
        http_client = qdash._http_client
        assert qdash.project_id == "project-b"
        assert not http_client.is_closed
        scoped = qdash.with_project("project-c")
        scoped.close()
        assert not http_client.is_closed

    assert http_client.is_closed
