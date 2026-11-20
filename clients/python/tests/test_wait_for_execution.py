"""When QDashClient.wait_for_execution stops polling, for standalone and pipeline executions."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from qdash.client import QDashClient, QDashConfig

_MISSING = object()


def _detail(status: str, pipeline: object = _MISSING) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": "exec-1", "status": status, "task": [], "note": {}}
    if pipeline is not _MISSING:
        payload["pipeline"] = pipeline
    return payload


def _pipeline(status: str) -> dict[str, Any]:
    return {
        "name": "coarse",
        "flow_run_id": "run-1",
        "root_execution_id": "exec-1",
        "status": status,
        "steps": [
            {"index": 1, "name": "CheckRabi", "execution_id": "exec-1", "status": "completed"},
            {"index": 2, "name": "CheckT1", "execution_id": None, "status": "pending"},
        ],
    }


class _Server:
    """Serve execution details in order, repeating the last one."""

    def __init__(self, *details: dict[str, Any] | None) -> None:
        self.details = details
        self.calls = 0
        self.sleeps: list[float] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/executions/exec-1"
        detail = self.details[min(self.calls, len(self.details) - 1)]
        self.calls += 1
        if detail is None:
            return httpx.Response(404, json={"detail": "not found"})
        return httpx.Response(200, json=detail)

    def client(self) -> QDashClient:
        config = QDashConfig.model_validate(
            {"base_url": "http://qdash.local", "api_token": "api-token"}
        )
        http_client = httpx.Client(
            base_url=config.base_url, transport=httpx.MockTransport(self.handler)
        )
        return QDashClient(config, http_client=http_client, sleep_fn=self.sleeps.append)


def _wait(server: _Server, **kwargs: Any) -> Any:
    client = server.client()
    try:
        return client.wait_for_execution(
            "exec-1", timeout_seconds=60, poll_interval_seconds=0.5, **kwargs
        )
    finally:
        client.close()


def test_pipeline_wait_continues_past_a_completed_intermediate_step() -> None:
    server = _Server(
        _detail("completed", _pipeline("running")),
        _detail("completed", _pipeline("running")),
        _detail("completed", _pipeline("completed")),
    )

    execution = _wait(server)

    assert execution.pipeline is not None
    assert execution.pipeline.status == "completed"
    assert server.calls == 3
    assert server.sleeps == [0.5, 0.5]


@pytest.mark.parametrize("outcome", ["failed", "cancelled", "canceled", "crashed"])
def test_pipeline_wait_returns_a_run_that_ended_without_completing(outcome: str) -> None:
    server = _Server(
        _detail("completed", _pipeline("running")), _detail("failed", _pipeline(outcome))
    )

    execution = _wait(server)

    assert execution.pipeline is not None
    assert execution.pipeline.status == outcome
    assert execution.status == "failed"
    assert server.calls == 2


def test_pipeline_wait_follows_the_run_even_when_the_first_step_failed() -> None:
    # The run's status decides; the server reports the run running until it settles.
    server = _Server(
        _detail("failed", _pipeline("running")), _detail("failed", _pipeline("failed"))
    )

    assert _wait(server).pipeline.status == "failed"
    assert server.calls == 2


def test_whole_pipeline_false_returns_when_the_step_itself_finishes() -> None:
    server = _Server(_detail("completed", _pipeline("running")))

    execution = _wait(server, whole_pipeline=False)

    assert execution.status == "completed"
    assert execution.pipeline.status == "running"
    assert server.calls == 1


@pytest.mark.parametrize("pipeline", [_MISSING, None], ids=["older-server", "standalone"])
def test_execution_without_pipeline_metadata_uses_its_own_status(pipeline: object) -> None:
    server = _Server(_detail("running", pipeline), _detail("completed", pipeline))

    execution = _wait(server)

    assert execution.status == "completed"
    assert execution.pipeline is None
    assert server.calls == 2


def test_wait_tolerates_an_execution_that_is_not_visible_yet() -> None:
    server = _Server(None, _detail("completed", _pipeline("completed")))

    assert _wait(server).pipeline.status == "completed"
    assert server.calls == 2


def test_custom_terminal_statuses_apply_to_the_pipeline_status() -> None:
    server = _Server(_detail("completed", _pipeline("paused")))

    assert _wait(server, terminal_statuses={"Paused"}).pipeline.status == "paused"


def test_wait_times_out_while_the_pipeline_is_still_running() -> None:
    server = _Server(_detail("completed", _pipeline("running")))
    client = server.client()
    try:
        with pytest.raises(TimeoutError, match="exec-1"):
            client.wait_for_execution("exec-1", timeout_seconds=0, poll_interval_seconds=0)
    finally:
        client.close()
    assert server.calls == 1


def test_wait_rejects_negative_timings() -> None:
    client = _Server(_detail("completed")).client()
    try:
        with pytest.raises(ValueError, match="non-negative"):
            client.wait_for_execution("exec-1", timeout_seconds=-1)
    finally:
        client.close()
