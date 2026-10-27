"""Tests for the deployment service HTTP client."""

import json
from collections.abc import Callable

import httpx
import pytest

from qdash.api.services.flow_service.deployment_client import (
    DeploymentRegistrationError,
    DeploymentServiceClient,
)

BASE_URL = "http://deployment.test"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> DeploymentServiceClient:
    """Build a client whose HTTP calls are served by the handler."""
    return DeploymentServiceClient(BASE_URL, transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_register_posts_the_flow_and_returns_the_deployment_id() -> None:
    """A successful registration returns the deployment ID from the response."""
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/register-deployment"
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"deployment_id": "deployment-9"})

    deployment_id = await _client(handler).register(
        file_path="/app/qdash/workflow/user_flows/project-1/my_flow.py",
        flow_function_name="my_flow",
        deployment_name="project-1-my_flow",
        old_deployment_id="deployment-1",
    )

    assert deployment_id == "deployment-9"
    assert seen == [
        {
            "file_path": "/app/qdash/workflow/user_flows/project-1/my_flow.py",
            "flow_function_name": "my_flow",
            "deployment_name": "project-1-my_flow",
            "old_deployment_id": "deployment-1",
        }
    ]


@pytest.mark.asyncio
async def test_register_reports_the_deployment_service_status() -> None:
    """A rejected registration carries the status code and response body."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="worker is down")

    with pytest.raises(DeploymentRegistrationError) as exc_info:
        await _client(handler).register(
            file_path="/tmp/my_flow.py",
            flow_function_name="my_flow",
            deployment_name="project-1-my_flow",
        )

    assert str(exc_info.value) == "500: worker is down"


@pytest.mark.asyncio
async def test_register_reports_a_transport_failure() -> None:
    """A connection failure is reported with the underlying message."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(DeploymentRegistrationError) as exc_info:
        await _client(handler).register(
            file_path="/tmp/my_flow.py",
            flow_function_name="my_flow",
            deployment_name="project-1-my_flow",
        )

    assert str(exc_info.value) == "connection refused"


@pytest.mark.asyncio
async def test_register_normalizes_a_trailing_slash_in_the_base_url() -> None:
    """A base URL with a trailing slash still targets the registration path."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json={"deployment_id": "deployment-1"})

    client = DeploymentServiceClient(
        f"{BASE_URL}/",
        transport=httpx.MockTransport(handler),
    )

    await client.register(
        file_path="/tmp/my_flow.py",
        flow_function_name="my_flow",
        deployment_name="project-1-my_flow",
    )

    assert paths == ["/register-deployment"]
