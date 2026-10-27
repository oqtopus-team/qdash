"""HTTP client for the workflow deployment service."""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("uvicorn.app")

DEPLOYMENT_SERVICE_URL = os.getenv("DEPLOYMENT_SERVICE_URL", "http://deployment-service:8001")


class DeploymentRegistrationError(RuntimeError):
    """Raised when the deployment service cannot register a flow."""


class DeploymentServiceClient:
    """Register flow files as Prefect deployments through the workflow service."""

    def __init__(
        self,
        base_url: str = DEPLOYMENT_SERVICE_URL,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout

    async def register(
        self,
        *,
        file_path: str,
        flow_function_name: str,
        deployment_name: str,
        old_deployment_id: str | None = None,
    ) -> str:
        """Register one flow file and return its Prefect deployment ID."""
        logger.info(f"Registering deployment '{deployment_name}' at {self._base_url}")
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=self._timeout,
            ) as client:
                response = await client.post(
                    f"{self._base_url}/register-deployment",
                    json={
                        "file_path": file_path,
                        "flow_function_name": flow_function_name,
                        "deployment_name": deployment_name,
                        "old_deployment_id": old_deployment_id,
                    },
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                f"HTTP error during deployment registration: "
                f"{exc.response.status_code} - {exc.response.text}"
            )
            raise DeploymentRegistrationError(
                f"{exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            logger.error(f"Failed to register deployment: {type(exc).__name__}: {exc}")
            raise DeploymentRegistrationError(str(exc)) from exc

        deployment_id = str(data["deployment_id"])
        logger.info(f"Successfully registered deployment: {deployment_id}")
        return deployment_id
