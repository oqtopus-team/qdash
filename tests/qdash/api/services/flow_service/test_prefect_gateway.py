"""Tests for the Prefect gateway wrapper."""

from typing import Any

import pytest

from qdash.api.services.flow_service.prefect_gateway import (
    PrefectGateway,
    SystemDeploymentUnavailable,
)


class _FakeClient:
    """Prefect client stub returning fixed identifiers."""

    def __init__(
        self,
        *,
        flow_run_id: str = "flow-run-1",
        deployment_id: str = "deployment-1",
        read_failure: Exception | None = None,
        delete_failure: Exception | None = None,
    ) -> None:
        self.flow_run_id = flow_run_id
        self.deployment_id = deployment_id
        self.read_failure = read_failure
        self.delete_failure = delete_failure
        self.created: list[dict[str, Any]] = []
        self.deleted: list[Any] = []

    async def create_flow_run_from_deployment(
        self,
        *,
        deployment_id: Any,
        parameters: dict[str, Any],
    ) -> Any:
        """Record the dispatch and return a stub flow run."""
        self.created.append({"deployment_id": deployment_id, "parameters": parameters})
        return type("FlowRun", (), {"id": self.flow_run_id})()

    async def read_deployment_by_name(self, deployment_name: str) -> Any:
        """Return a stub deployment or raise the configured failure."""
        if self.read_failure is not None:
            raise self.read_failure
        return type("Deployment", (), {"id": self.deployment_id})()

    async def delete_deployment(self, deployment_id: Any) -> None:
        """Record the deletion or raise the configured failure."""
        if self.delete_failure is not None:
            raise self.delete_failure
        self.deleted.append(deployment_id)


class _ClientContext:
    """Async context manager yielding the configured client."""

    def __init__(self, client: _FakeClient) -> None:
        self._client = client

    async def __aenter__(self) -> _FakeClient:
        """Return the configured client."""
        return self._client

    async def __aexit__(self, *_args: object) -> None:
        """Do nothing on context exit."""


def _gateway(client: _FakeClient) -> PrefectGateway:
    """Build a gateway whose client factory yields the stub."""
    return PrefectGateway(client_factory=lambda: _ClientContext(client))


@pytest.mark.asyncio
async def test_create_flow_run_returns_the_prefect_run_id() -> None:
    """Creating a run returns its Prefect ID and forwards the parameters."""
    client = _FakeClient(flow_run_id="flow-run-9")

    flow_run_id = await _gateway(client).create_flow_run(
        deployment_id="deployment-1",
        parameters={"chip_id": "chip-1"},
    )

    assert flow_run_id == "flow-run-9"
    assert client.created == [
        {"deployment_id": "deployment-1", "parameters": {"chip_id": "chip-1"}}
    ]


@pytest.mark.asyncio
async def test_read_deployment_id_returns_the_registered_deployment() -> None:
    """A registered system deployment resolves to its ID."""
    client = _FakeClient(deployment_id="deployment-7")

    deployment_id = await _gateway(client).read_deployment_id(
        "calibration-pipeline/system-calibration-pipeline"
    )

    assert str(deployment_id) == "deployment-7"


@pytest.mark.asyncio
async def test_read_deployment_id_reports_an_unregistered_deployment() -> None:
    """A missing system deployment raises the unavailable marker."""
    client = _FakeClient(read_failure=RuntimeError("deployment not found"))

    with pytest.raises(SystemDeploymentUnavailable) as exc_info:
        await _gateway(client).read_deployment_id("single-task-executor/system-single-task")

    assert exc_info.value.deployment_name == "single-task-executor/system-single-task"


@pytest.mark.asyncio
async def test_delete_deployment_removes_the_registered_deployment() -> None:
    """Deleting a flow deployment forwards its ID to Prefect."""
    client = _FakeClient()

    await _gateway(client).delete_deployment("deployment-3")

    assert client.deleted == ["deployment-3"]


@pytest.mark.asyncio
async def test_delete_deployment_tolerates_a_missing_deployment() -> None:
    """A deployment that is already gone does not fail the deletion."""
    client = _FakeClient(delete_failure=RuntimeError("not found"))

    await _gateway(client).delete_deployment("deployment-3")

    assert client.deleted == []
