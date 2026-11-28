"""Associated writes fail closed against APIs that predate calibration sessions."""

from __future__ import annotations

from contextlib import closing
from typing import Any

import httpx
import pytest

from qdash.client import QDashClient, QDashConfig, QDashNotFoundError

PARENT = {"calibration_session_id": "cs-1", "chip_id": "chip-1", "status": "open"}
PIPELINE = {
    "execution_id": "e1",
    "flow_run_id": "f1",
    "flow_run_url": "http://prefect/f1",
    "qdash_ui_url": "http://qdash/e1",
    "message": "started",
    "calibration_session_id": "cs-1",
    "pipeline_run_id": "r1",
}
AGENT: dict[str, Any] = {
    "session_id": "a1",
    "project_id": "p1",
    "chip_id": "chip-1",
    "created_by": "tester",
    "policy": {
        "qids": ["0"],
        "allowed_tasks": ["CheckT1"],
        "allowed_actions": ["run_task"],
        "allowed_overrides": {},
        "max_actions": 4,
    },
    "skill_name": "",
    "skill_version": "",
    "skill_hash": "",
    "status": "active",
    "state_version": 0,
    "action_count": 0,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
    "expires_at": "2026-01-01T01:00:00Z",
    "calibration_session_id": "cs-1",
    "calibration_admission": "admitted",
}


def make_client(
    parent: Any = PARENT, result: Any = None, status: int = 200
) -> tuple[QDashClient, list[str]]:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(
            status if request.method == "GET" else 200,
            json=parent if request.method == "GET" else result,
        )

    config = QDashConfig.model_validate({"base_url": "http://qdash.local", "api_token": "token"})
    transport = httpx.Client(base_url=config.base_url, transport=httpx.MockTransport(handler))
    return QDashClient(config, http_client=transport), methods


def run(client: QDashClient, kind: str, associated: bool = True) -> Any:
    session_id = "cs-1" if associated else None
    if kind == "pipeline":
        return client.execute_calibration_pipeline(
            chip_id="chip-1",
            spec={},
            idempotency_key="key-1" if associated else None,
            calibration_session_id=session_id,
        )
    return client.create_agent_session(
        chip_id="chip-1", policy=AGENT["policy"], calibration_session_id=session_id
    )


@pytest.mark.parametrize("kind", ["pipeline", "agent"])
def test_old_api_missing_parent_route_never_dispatches(kind: str) -> None:
    client, methods = make_client({}, {}, 404)
    with closing(client), pytest.raises(QDashNotFoundError):
        run(client, kind)
    assert methods == ["GET"]


@pytest.mark.parametrize("kind", ["pipeline", "agent"])
@pytest.mark.parametrize(
    "parent", [{}, {**PARENT, "chip_id": "wrong"}, {**PARENT, "calibration_session_id": "wrong"}]
)
def test_malformed_parent_never_dispatches(kind: str, parent: dict[str, Any]) -> None:
    client, methods = make_client(parent)
    with closing(client), pytest.raises(ValueError, match="nothing dispatched"):
        run(client, kind)
    assert methods == ["GET"]


@pytest.mark.parametrize("kind", ["pipeline", "agent"])
@pytest.mark.parametrize(
    "result",
    [
        {},
        {
            "calibration_session_id": "other",
            "pipeline_run_id": "r1",
            "calibration_admission": "admitted",
        },
        {
            "calibration_session_id": "cs-1",
            "pipeline_run_id": "",
            "calibration_admission": "pending",
        },
    ],
)
def test_lost_association_is_unknown_and_not_retried(kind: str, result: dict[str, Any]) -> None:
    client, methods = make_client(result=result)
    with (
        closing(client),
        pytest.raises(RuntimeError, match=r"result unknown.*Do not retry automatically"),
    ):
        run(client, kind)
    assert methods == ["GET", "POST"]


def test_closed_parent_still_allows_server_idempotent_replay() -> None:
    client, methods = make_client({**PARENT, "status": "closed"}, {**PIPELINE, "replayed": True})
    with closing(client):
        assert run(client, "pipeline").replayed
    assert methods == ["GET", "POST"]


@pytest.mark.parametrize(("kind", "reply"), [("pipeline", PIPELINE), ("agent", AGENT)])
def test_valid_association_and_unassociated_legacy_path(kind: str, reply: dict[str, Any]) -> None:
    client, methods = make_client(result=reply)
    with closing(client):
        assert run(client, kind).calibration_session_id == "cs-1"
        run(client, kind, associated=False)
    assert methods == ["GET", "POST", "POST"]


@pytest.mark.parametrize(("session_id", "key"), [("", "key"), ("cs-1", ""), (None, " ")])
def test_invalid_pipeline_recording_fails_without_requests(
    session_id: str, key: str | None
) -> None:
    client, methods = make_client()
    with closing(client), pytest.raises(ValueError):
        client.execute_calibration_pipeline(
            chip_id="chip-1", spec={}, calibration_session_id=session_id, idempotency_key=key
        )
    assert methods == []


FLOW_RUN = {
    "execution_id": "e1",
    "flow_run_id": "f1",
    "flow_run_url": "http://prefect/f1",
    "qdash_ui_url": "http://qdash/e1",
    "message": "started",
    "calibration_session_id": "cs-auto-1",
    "calibration_run_id": "cpr-1",
}
LEGACY_FLOW_RUN = {key: FLOW_RUN[key] for key in ("execution_id", "flow_run_id", "flow_run_url")}


def _sent_bodies(reply: Any) -> tuple[QDashClient, list[dict[str, Any]]]:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=reply)

    config = QDashConfig.model_validate({"base_url": "http://qdash.local", "api_token": "token"})
    transport = httpx.Client(base_url=config.base_url, transport=httpx.MockTransport(handler))
    return QDashClient(config, http_client=transport), bodies


def test_a_keyed_workflow_run_returns_its_session_and_run() -> None:
    client, bodies = _sent_bodies(FLOW_RUN)
    with closing(client):
        response = client.execute_flow("demo", idempotency_key="click-1")
    assert bodies == [{"parameters": {}, "idempotency_key": "click-1"}]
    assert (response.calibration_session_id, response.calibration_run_id) == (
        "cs-auto-1",
        "cpr-1",
    )


@pytest.mark.parametrize(("session_id", "key"), [(None, "click-1"), ("cs-1", None)])
def test_a_server_that_ignores_run_recording_is_reported_not_retried(
    session_id: str | None, key: str | None
) -> None:
    client, bodies = _sent_bodies({**LEGACY_FLOW_RUN, "qdash_ui_url": "u", "message": "m"})
    with closing(client), pytest.raises(RuntimeError, match="Do not retry automatically"):
        client.execute_flow("demo", calibration_session_id=session_id, idempotency_key=key)
    assert len(bodies) == 1


@pytest.mark.parametrize(("session_id", "key"), [(None, "click-1"), ("cs-1", None)])
def test_a_chipless_flow_refused_before_launch_is_reported_once(
    session_id: str | None, key: str | None
) -> None:
    from qdash.client import QDashApiError

    detail = (
        "chipless names no chip (no chip_id parameter and no chip saved with the flow), so "
        "QDash cannot record it in a calibration session or replay it by idempotency key. "
        "Nothing was started."
    )
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        bodies.append(json.loads(request.content))
        return httpx.Response(400, json={"detail": detail})

    config = QDashConfig.model_validate({"base_url": "http://qdash.local", "api_token": "token"})
    transport = httpx.Client(base_url=config.base_url, transport=httpx.MockTransport(handler))
    with (
        closing(QDashClient(config, http_client=transport)) as client,
        pytest.raises(QDashApiError, match="Nothing was started"),
    ):
        client.execute_flow("chipless", calibration_session_id=session_id, idempotency_key=key)
    # One request, carrying the caller's options: never retried without them.
    assert len(bodies) == 1
    assert bodies[0].get("idempotency_key") == key
    assert bodies[0].get("calibration_session_id") == session_id
