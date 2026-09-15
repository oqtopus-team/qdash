"""QDash API proxy for the privileged host-side updater."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx
from fastapi import HTTPException, status

from qdash.api.schemas.system_update import (
    SystemUpdateOperationResponse,
    SystemUpdateState,
    SystemUpdateStatusResponse,
)
from qdash.dbmodel.execution_lock import ExecutionLockDocument

if TYPE_CHECKING:
    from qdash.config import Settings


class SystemUpdateService:
    """Enforce QDash preconditions and forward fixed updater operations."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._background_tasks: set[asyncio.Task[None]] = set()

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
        response = SystemUpdateStatusResponse.model_validate(payload)
        self._release_terminal_reservation(response.operation_id, response.operation_state)
        return response

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
        operation_id = str(uuid4())
        if not ExecutionLockDocument.try_reserve_maintenance(operation_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A calibration is running; wait for it to finish before updating QDash",
            )
        try:
            payload = await self._request(
                "POST",
                "/updates",
                json={
                    "expected_current_version": expected_current_version,
                    "operation_id": operation_id,
                },
            )
            response = SystemUpdateOperationResponse.model_validate(payload)
            if response.operation_id != operation_id:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="The host updater returned an unexpected operation ID",
                )
        except Exception:
            ExecutionLockDocument.release_maintenance(operation_id)
            raise

        task = asyncio.create_task(self._watch_operation(operation_id))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return response

    async def get_operation(self, operation_id: str) -> SystemUpdateOperationResponse:
        """Return updater-owned progress across QDash API restarts."""
        if not self._is_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The host updater is not configured",
            )
        payload = await self._request("GET", f"/updates/{operation_id}")
        response = SystemUpdateOperationResponse.model_validate(payload)
        self._release_terminal_reservation(response.operation_id, response.state)
        return response

    async def reconcile_maintenance(self) -> None:
        """Resume watching a reservation left across an API container restart."""
        operation_id = ExecutionLockDocument.maintenance_operation_id()
        if operation_id is None or not self._is_configured:
            return
        await self._watch_operation(operation_id)

    async def _watch_operation(self, operation_id: str) -> None:
        """Release maintenance once the host updater reaches a terminal state."""
        while True:
            try:
                payload = await self._request("GET", f"/updates/{operation_id}")
                response = SystemUpdateOperationResponse.model_validate(payload)
            except HTTPException as exc:
                if exc.status_code == status.HTTP_404_NOT_FOUND:
                    ExecutionLockDocument.release_maintenance(operation_id)
                    return
                await asyncio.sleep(2)
                continue
            if response.state not in {
                SystemUpdateState.QUEUED,
                SystemUpdateState.RUNNING,
                SystemUpdateState.ROLLING_BACK,
            }:
                ExecutionLockDocument.release_maintenance(operation_id)
                return
            await asyncio.sleep(2)

    @staticmethod
    def _release_terminal_reservation(
        operation_id: str | None,
        state: SystemUpdateState,
    ) -> None:
        """Release a matching reservation reported in a terminal response."""
        if operation_id and state not in {
            SystemUpdateState.QUEUED,
            SystemUpdateState.RUNNING,
            SystemUpdateState.ROLLING_BACK,
        }:
            ExecutionLockDocument.release_maintenance(operation_id)

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
