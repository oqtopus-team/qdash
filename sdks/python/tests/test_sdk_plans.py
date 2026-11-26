"""Stored pipeline plans through the SDK: create, read, and execute with echo checks."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from test_sdk_session import CHIP, Server, execute_body, pipeline

from qdash.sdk import QDashConflictError, QDashTransportError

DIGEST = "sha256:v1:" + "a" * 64


def plan_body(**fields: Any) -> dict[str, Any]:
    return {
        "plan_id": "cpp-1",
        "chip_id": CHIP,
        "backend_name": "qubex",
        "created_by": "alice",
        "created_at": "2026-11-26T00:00:00Z",
        "expires_at": "2026-11-27T00:00:00Z",
        "expired": False,
        "review_version": 1,
        "review_digest": DIGEST,
        "spec": {"spec_version": 2},
        "target_qids": ["0", "1"],
        "steps": [],
        **fields,
    }


def plan_run_body(**fields: Any) -> dict[str, Any]:
    return {
        **execute_body(),
        "pipeline_run_id": "cpr-1",
        "calibration_session_id": "cs-auto",
        "plan_id": "cpp-1",
        "review_digest": DIGEST,
        **fields,
    }


def test_create_plan_sends_the_spec_and_key_once() -> None:
    server = Server(
        {("POST", "/calibration-pipelines/plans"): [httpx.Response(201, json=plan_body())]}
    )
    plan = server.session().pipelines.create_plan(pipeline(), chip_id=CHIP, idempotency_key="k1")

    assert plan.plan_id == "cpp-1"
    assert plan.review_digest == DIGEST
    body = json.loads(server.requests[0].content)
    assert body["idempotency_key"] == "k1"
    assert body["chip_id"] == CHIP
    assert body["spec"]["spec_version"] == 2


def test_create_plan_is_never_sent_again() -> None:
    server = Server(
        {
            ("POST", "/calibration-pipelines/plans"): [
                httpx.Response(409, json={"detail": "other request"}),
                httpx.Response(201, json=plan_body()),
            ]
        }
    )
    with pytest.raises(QDashConflictError):
        server.session().pipelines.create_plan(pipeline(), chip_id=CHIP, idempotency_key="k1")
    assert len(server.requests) == 1


def test_create_plan_needs_a_key() -> None:
    with pytest.raises(ValueError, match="idempotency_key"):
        Server().session().pipelines.create_plan(pipeline(), chip_id=CHIP, idempotency_key=" ")


def test_get_plan_reads_it_by_id() -> None:
    server = Server(
        {("GET", "/calibration-pipelines/plans/cpp-1"): [httpx.Response(200, json=plan_body())]}
    )
    assert server.session().pipelines.get_plan("cpp-1").target_qids == ["0", "1"]


def test_execute_plan_sends_the_approved_digest() -> None:
    server = Server(
        {
            ("POST", "/calibration-pipelines/plans/cpp-1/execute"): [
                httpx.Response(202, json=plan_run_body())
            ]
        }
    )
    run = server.session().pipelines.execute_plan(
        "cpp-1", chip_id=CHIP, expected_review_digest=DIGEST, idempotency_key="run-1"
    )
    assert run.execution_id == "exec-1"
    body = json.loads(server.requests[0].content)
    assert body == {
        "chip_id": CHIP,
        "expected_review_digest": DIGEST,
        "idempotency_key": "run-1",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"plan_id": None},
        {"plan_id": "cpp-2"},
        {"review_digest": None},
        {"review_digest": "sha256:v1:" + "b" * 64},
    ],
)
def test_execute_plan_without_its_echo_is_result_unknown(change: dict[str, Any]) -> None:
    server = Server(
        {
            ("POST", "/calibration-pipelines/plans/cpp-1/execute"): [
                httpx.Response(202, json=plan_run_body(**change)),
                httpx.Response(202, json=plan_run_body()),
            ]
        }
    )
    with pytest.raises(RuntimeError, match="Pipeline plan result unknown"):
        server.session().pipelines.execute_plan(
            "cpp-1", chip_id=CHIP, expected_review_digest=DIGEST, idempotency_key="run-1"
        )
    assert len(server.requests) == 1


def test_execute_plan_is_sent_once_after_a_timeout() -> None:
    requests: list[httpx.Request] = []

    def timeout(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ReadTimeout("timed out", request=request)

    from qdash.sdk import QDash, QDashConfig

    qdash = QDash(
        QDashConfig(base_url="http://qdash.local", api_token="t", project_id="p"),
        http_client=httpx.Client(transport=httpx.MockTransport(timeout)),
    )
    with pytest.raises(QDashTransportError):
        qdash.pipelines.execute_plan("cpp-1", chip_id=CHIP, expected_review_digest=DIGEST)
    assert len(requests) == 1
