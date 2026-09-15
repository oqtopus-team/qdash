"""Tests for the API proxy to the host updater."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException

from qdash.api.services.system_update_service import SystemUpdateService
from qdash.config import Settings


def settings(*, configured: bool = True) -> Settings:
    return Settings(
        env="test",
        prefect_api_url="http://prefect.test/api",
        postgres_data_path="",
        mongo_data_path="",
        calib_data_path="",
        updater_socket="/run/qdash-updater/updater.sock" if configured else "",
    )


@pytest.mark.asyncio
async def test_status_reports_disabled_when_updater_is_not_configured() -> None:
    result = await SystemUpdateService(settings(configured=False)).get_status()

    assert result.enabled is False
    assert result.can_update is False
    assert result.blocked_reason == "The host updater is not configured"


@pytest.mark.asyncio
async def test_status_uses_unix_socket_and_validates_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_at = datetime.now(timezone.utc).isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/status"
        return httpx.Response(
            200,
            json={
                "enabled": True,
                "current_version": "v1.0.0",
                "current_commit": "abc",
                "latest_version": "v1.1.0",
                "update_available": True,
                "can_update": True,
                "dirty": False,
                "operation_state": "idle",
                "checked_at": checked_at,
            },
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)

    result = await SystemUpdateService(settings()).get_status()

    assert result.current_version == "v1.0.0"
    assert result.latest_version == "v1.1.0"
    assert result.can_update is True


@pytest.mark.asyncio
async def test_start_update_refuses_active_calibration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "qdash.api.services.system_update_service.ExecutionLockDocument.try_reserve_maintenance",
        lambda operation_id: False,
    )

    with pytest.raises(HTTPException) as exc_info:
        await SystemUpdateService(settings()).start_update("v1.0.0")

    assert exc_info.value.status_code == 409
    assert "calibration is running" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_start_update_releases_reservation_when_updater_rejects_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SystemUpdateService(settings())
    request = AsyncMock(side_effect=HTTPException(status_code=409, detail="blocked"))
    release = MagicMock()
    monkeypatch.setattr(service, "_request", request)
    monkeypatch.setattr(
        "qdash.api.services.system_update_service.ExecutionLockDocument.try_reserve_maintenance",
        lambda operation_id: True,
    )
    monkeypatch.setattr(
        "qdash.api.services.system_update_service.ExecutionLockDocument.release_maintenance",
        release,
    )

    with pytest.raises(HTTPException, match="409"):
        await service.start_update("v1.0.0")

    assert request.await_args is not None
    operation_id = request.await_args.kwargs["json"]["operation_id"]
    release.assert_called_once_with(operation_id)
