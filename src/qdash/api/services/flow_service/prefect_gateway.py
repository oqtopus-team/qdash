"""Thin wrapper around the Prefect client used for flow dispatch."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from prefect.client.orchestration import get_client

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

logger = logging.getLogger("uvicorn.app")


class SystemDeploymentUnavailable(LookupError):
    """Raised when a system deployment has not been registered yet."""

    def __init__(self, deployment_name: str) -> None:
        super().__init__(deployment_name)
        self.deployment_name = deployment_name


class PrefectGateway:
    """Create flow runs, look up deployments and drop them when a flow is deleted."""

    def __init__(self, client_factory: Callable[[], Any] | None = None) -> None:
        self._client_factory = client_factory or get_client

    async def create_flow_run(
        self, *, deployment_id: UUID | str, parameters: dict[str, Any]
    ) -> str:
        """Create a flow run from a deployment and return its Prefect run ID."""
        async with self._client_factory() as client:
            flow_run = await client.create_flow_run_from_deployment(
                deployment_id=cast("UUID", deployment_id),
                parameters=parameters,
            )
        return str(flow_run.id)

    async def read_deployment_id(self, deployment_name: str) -> UUID:
        """Return the deployment ID registered under a system deployment name."""
        try:
            async with self._client_factory() as client:
                deployment = await client.read_deployment_by_name(deployment_name)
        except Exception as exc:
            logger.error(f"System deployment '{deployment_name}' not found")
            raise SystemDeploymentUnavailable(deployment_name) from exc
        return cast("UUID", deployment.id)

    async def delete_deployment(self, deployment_id: str) -> None:
        """Delete a deployment, tolerating one that no longer exists."""
        try:
            async with self._client_factory() as client:
                await client.delete_deployment(cast("UUID", deployment_id))
        except Exception as exc:
            logger.warning(f"Failed to delete Prefect deployment (may not exist): {exc}")
            return
        logger.info(f"Deleted Prefect deployment: {deployment_id}")
