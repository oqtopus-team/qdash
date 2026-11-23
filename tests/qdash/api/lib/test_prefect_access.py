"""Tests for the Prefect read-only request classifier."""

import pytest

from qdash.api.lib.prefect_access import is_prefect_read_request

DEPLOYMENT_ID = "123e4567-e89b-12d3-a456-426614174000"
API = "/prefect/api"


@pytest.mark.parametrize(
    ("method", "uri"),
    [
        ("GET", "/prefect/dashboard"),
        ("HEAD", f"{API}/health"),
        ("GET", f"{API}/flow_runs/{DEPLOYMENT_ID}?limit=5"),
        ("POST", f"{API}/flow_runs/filter"),
        ("POST", f"{API}/flow_runs/filter?offset=10"),
        ("POST", f"{API}/flow_runs/{DEPLOYMENT_ID}/input/filter"),
        ("POST", f"{API}/work_pools/default-pool/workers/filter"),
        ("POST", f"{API}/events/count-by/event"),
        ("POST", f"{API}/ui/task_runs/dashboard/counts"),
    ],
)
def test_read_requests_are_allowed(method: str, uri: str) -> None:
    """Reads and allowlisted POST queries are read-only."""
    assert is_prefect_read_request(method, uri)


@pytest.mark.parametrize(
    "uri",
    [
        f"{API}/deployments/{DEPLOYMENT_ID}/create_flow_run",
        f"{API}/deployments/{DEPLOYMENT_ID}/create_flow_run?x=/filter",
        f"{API}/flow_runs/filter/../../deployments/{DEPLOYMENT_ID}/create_flow_run",
        f"{API}/flow_runs%2Ffilter",
        f"{API}/flow_runs/%66ilter",
        f"{API}/flow_runs/filter/",
        f"{API}/Flow_Runs/filter",
        "/PREFECT/API/flow_runs/filter",
        "//prefect/api/flow_runs/filter",
        f"{API}/block_documents/filter",
        f"{API}/deployments/get_scheduled_flow_runs",
        f"{API}/work_pools/a%2Fb/queues/filter",
        f"{API}/work_pools/a/b/queues/filter",
        f"{API}/flow_runs/not-a-uuid/input/filter",
    ],
)
def test_post_outside_allowlist_is_denied(uri: str) -> None:
    """POST variants that are not exact allowlist matches fail closed."""
    assert not is_prefect_read_request("POST", uri)


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "", "post"])
def test_other_methods_are_denied(method: str) -> None:
    """Only GET, HEAD, and allowlisted POST are read-only."""
    assert not is_prefect_read_request(method, f"{API}/flow_runs/filter")


@pytest.mark.parametrize(
    "query",
    ["include_secrets=true", "include%5Fsecrets=true", "a=1&include_secrets", "include_secrets="],
)
def test_get_with_include_secrets_is_denied(query: str) -> None:
    """Secret-revealing block document reads need an administrator."""
    assert not is_prefect_read_request("GET", f"{API}/block_documents/{DEPLOYMENT_ID}?{query}")
    assert not is_prefect_read_request("HEAD", f"{API}/block_documents/?{query}")


def test_websocket_read_streams_only() -> None:
    """Only the outbound event and log streams are readable websockets."""
    assert is_prefect_read_request("GET", f"{API}/events/out", "websocket")
    assert is_prefect_read_request("GET", f"{API}/logs/out", "websocket")
    assert not is_prefect_read_request("GET", f"{API}/events/in", "websocket")
    assert not is_prefect_read_request(
        "GET", f"{API}/task_runs/subscriptions/scheduled", "websocket"
    )
    assert not is_prefect_read_request("GET", f"{API}/work_pools/p/workers/connect", "websocket")
    assert not is_prefect_read_request("GET", f"{API}/events/out/", "websocket")
    assert not is_prefect_read_request("POST", f"{API}/events/out", "websocket")
