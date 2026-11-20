"""The QDash session: requests, run handles, client ownership and project scope."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from qdash.client import QDashClient, QDashConfig
from qdash.sdk import (
    QDash,
    QDashApiError,
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

    def http_client(self, base_url: str) -> httpx.Client:
        return httpx.Client(base_url=base_url, transport=httpx.MockTransport(self.handler))

    def client(self, *, project_id: str | None = "project-a") -> QDashClient:
        config = QDashConfig(
            base_url="http://qdash.local",
            api_token="api-token",
            project_id=project_id,
        )
        return QDashClient(
            config, http_client=self.http_client(config.base_url), sleep_fn=self.sleeps.append
        )

    def paths(self) -> list[tuple[str, str]]:
        return [(request.method, request.url.path) for request in self.requests]


def test_defining_a_pipeline_and_opening_a_session_send_nothing() -> None:
    server = Server()
    with QDash(server.client()):
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
    with QDash(server.client()) as qdash:
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
    with QDash(server.client()) as qdash:
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
    with QDash(server.client()) as qdash:
        run = qdash.pipelines.execute(pipeline(), chip_id=CHIP)
        assert server.paths() == [("POST", "/calibration-pipelines/execute")]

        finished = run.wait(timeout_seconds=60, poll_interval_seconds=2)

    assert run.execution_id == "exec-1"
    assert finished.pipeline is not None
    assert finished.pipeline.status == "completed"
    assert server.paths().count(("GET", "/executions/exec-1")) == 4
    assert server.sleeps == [2, 2, 2]
    assert ("POST", "/calibration-pipelines/validate") not in server.paths()


def test_wait_times_out_without_cancelling_the_run() -> None:
    server = Server(
        {
            ("POST", "/calibration-pipelines/execute"): [httpx.Response(202, json=execute_body())],
            ("GET", "/executions/exec-1"): [httpx.Response(200, json=detail("running", "running"))],
        }
    )
    with QDash(server.client()) as qdash:
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
    with QDash(server.client()) as qdash, pytest.raises(QDashValidationError) as raised:
        qdash.pipelines.execute(pipeline(), chip_id=CHIP)

    assert raised.value.payload == rejected
    assert len(server.requests) == 1


def test_permission_errors_propagate_without_retry() -> None:
    forbidden = {"detail": "Editor role required"}
    server = Server(
        {("POST", "/calibration-pipelines/execute"): [httpx.Response(403, json=forbidden)]}
    )
    with QDash(server.client()) as qdash, pytest.raises(QDashApiError) as raised:
        qdash.pipelines.execute(pipeline(), chip_id=CHIP)

    assert raised.value.status_code == 403
    assert len(server.requests) == 1


def test_execute_needs_a_project() -> None:
    server = Server()
    with QDash(server.client(project_id=None)) as qdash, pytest.raises(QDashConfigError):
        qdash.pipelines.execute(pipeline(), chip_id=CHIP)

    assert server.requests == []


def test_a_callers_client_is_not_closed() -> None:
    server = Server(
        {("POST", "/calibration-pipelines/validate"): [httpx.Response(200, json=validate_body())]}
    )
    client = server.client()
    with QDash(client) as qdash:
        qdash.pipelines.validate(pipeline(), chip_id=CHIP)

    client.validate_calibration_pipeline(chip_id=CHIP, spec=pipeline().to_spec())
    assert len(server.requests) == 2
    client.close()


def test_project_override_leaves_the_callers_client_unchanged() -> None:
    server = Server(
        {("POST", "/calibration-pipelines/validate"): [httpx.Response(200, json=validate_body())]}
    )
    client = server.client(project_id="project-a")

    with QDash(client, project_id="project-b") as qdash:
        assert qdash.project_id == "project-b"
        qdash.pipelines.validate(pipeline(), chip_id=CHIP)
    client.validate_calibration_pipeline(chip_id=CHIP, spec=pipeline().to_spec())

    assert client.config.project_id == "project-a"
    assert [request.headers["X-Project-Id"] for request in server.requests] == [
        "project-b",
        "project-a",
    ]
    client.close()


def test_with_project_replaces_a_default_project_header() -> None:
    server = Server({("GET", "/calibration-pipelines/catalog"): [httpx.Response(500)]})
    client = QDashClient(
        QDashConfig(base_url="http://qdash.local", api_token="api-token"),
        http_client=server.http_client("http://qdash.local"),
        default_headers={"x-project-id": "from-headers"},
    )
    scoped = client.with_project("project-b")

    with pytest.raises(QDashApiError):
        scoped.get_calibration_pipeline_catalog()

    assert server.requests[0].headers.get_list("X-Project-Id") == ["project-b"]
    assert client._default_headers == {"x-project-id": "from-headers"}
    with pytest.raises(ValueError, match="project_id"):
        client.with_project("")
    client.close()


def test_owned_session_closes_its_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDASH_BASE_URL", "http://qdash.local")
    monkeypatch.setenv("QDASH_API_TOKEN", "api-token")
    monkeypatch.setenv("QDASH_PROJECT_ID", "project-a")

    with QDash.from_env(project_id="project-b") as qdash:
        transport = qdash.client._rest_client._client
        assert qdash.project_id == "project-b"
        assert not transport.is_closed

    assert transport.is_closed
