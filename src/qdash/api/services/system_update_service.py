"""QDash API proxy for the privileged host-side updater."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import HTTPException, status

from qdash.api.schemas.system_update import (
    SystemUpdateOperationResponse,
    SystemUpdateStatusResponse,
)
from qdash.dbmodel.execution_lock import ExecutionLockDocument

if TYPE_CHECKING:
    from qdash.config import Settings


class SystemUpdateService:
    """Enforce QDash preconditions and forward fixed updater operations."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def get_status(self) -> SystemUpdateStatusResponse:
        """Return updater status or an explicit disabled response."""
        if not self._is_configured:
            return SystemUpdateStatusResponse(
                enabled=False,
                current_version="unknown",
                current_commit="unknown",
                blocked_reason="The host updater is not configured",
                checked_at=datetime.now(timezone.utc),
            )
        payload = await self._request("GET", "/status")
        return SystemUpdateStatusResponse.model_validate(payload)

    async def start_update(
        self,
        expected_current_version: str | None,
    ) -> SystemUpdateOperationResponse:
        """Refuse active calibrations before asking the updater to deploy."""
        if not self._is_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The host updater is not configured",
            )
        if ExecutionLockDocument.find({"locked": True}).count() > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A calibration is running; wait for it to finish before updating QDash",
            )
        payload = await self._request(
            "POST",
            "/updates",
            json={"expected_current_version": expected_current_version},
        )
        return SystemUpdateOperationResponse.model_validate(payload)

    async def get_operation(self, operation_id: str) -> SystemUpdateOperationResponse:
        """Return updater-owned progress across QDash API restarts."""
        if not self._is_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The host updater is not configured",
            )
        payload = await self._request("GET", f"/updates/{operation_id}")
        return SystemUpdateOperationResponse.model_validate(payload)

    @property
    def _is_configured(self) -> bool:
        return bool(self._settings.updater_socket)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            transport = httpx.AsyncHTTPTransport(uds=self._settings.updater_socket)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://qdash-updater",
                timeout=30,
            ) as client:
                response = await client.request(
                    method,
                    path,
                    json=json,
                )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The host updater is unavailable",
            ) from exc

        if response.is_success:
            payload: dict[str, Any] = response.json()
            return payload

        detail = "The host updater rejected the request"
        try:
            body = response.json()
            if isinstance(body, dict) and isinstance(body.get("detail"), str):
                detail = body["detail"]
        except ValueError:
            pass
        mapped_status = (
            response.status_code
            if response.status_code in {400, 401, 404, 409, 422, 503}
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(status_code=mapped_status, detail=detail)
