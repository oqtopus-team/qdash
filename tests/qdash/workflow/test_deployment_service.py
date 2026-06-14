import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from prefect.client.schemas.actions import DeploymentScheduleCreate
from prefect.client.schemas.schedules import CronSchedule

from qdash.workflow import deployment_service
from qdash.workflow.deployment_service import (
    WORK_POOL_NAME,
    _capture_deployment_state,
    _ensure_work_pool,
)


class ObjectNotFound(Exception):
    """Test stand-in for Prefect's not-found exception."""


class ObjectAlreadyExists(Exception):
    """Test stand-in for Prefect's already-exists exception."""


class FakeWorkPoolCreate:
    """Test stand-in for Prefect's WorkPoolCreate model."""

    def __init__(self, name: str, type: str, description: str) -> None:
        self.name = name
        self.type = type
        self.description = description


def _raise(exc: Exception) -> None:
    raise exc


@pytest.mark.asyncio
async def test_ensure_work_pool_skips_existing_pool() -> None:
    client = SimpleNamespace(
        read_work_pool=AsyncMock(return_value=SimpleNamespace(id="pool-id")),
        create_work_pool=AsyncMock(),
    )

    await _ensure_work_pool(client)

    client.read_work_pool.assert_awaited_once_with(WORK_POOL_NAME)
    client.create_work_pool.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_work_pool_creates_missing_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deployment_service, "WorkPoolCreate", FakeWorkPoolCreate)
    client = SimpleNamespace(
        read_work_pool=AsyncMock(side_effect=lambda *_args, **_kwargs: _raise(ObjectNotFound())),
        create_work_pool=AsyncMock(return_value=SimpleNamespace(id="pool-id")),
    )

    await _ensure_work_pool(client)

    client.read_work_pool.assert_awaited_once_with(WORK_POOL_NAME)
    client.create_work_pool.assert_awaited_once()
    request = client.create_work_pool.await_args.args[0]
    assert request.name == WORK_POOL_NAME
    assert request.type == "process"


@pytest.mark.asyncio
async def test_ensure_work_pool_ignores_race_when_pool_already_created() -> None:
    client = SimpleNamespace(
        read_work_pool=AsyncMock(side_effect=lambda *_args, **_kwargs: _raise(ObjectNotFound())),
        create_work_pool=AsyncMock(
            side_effect=lambda *_args, **_kwargs: _raise(ObjectAlreadyExists())
        ),
    )

    await _ensure_work_pool(client)

    client.create_work_pool.assert_awaited_once()


class _FakeClientCtx:
    """Async-context-manager stand-in for ``get_client()`` yielding a fake client."""

    def __init__(self, deployment: object) -> None:
        self._client = SimpleNamespace(read_deployment=AsyncMock(return_value=deployment))

    async def __aenter__(self) -> object:
        return self._client

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def _patch_get_client(monkeypatch: pytest.MonkeyPatch, deployment: object) -> None:
    monkeypatch.setattr(deployment_service, "get_client", lambda: _FakeClientCtx(deployment))


@pytest.mark.asyncio
async def test_capture_deployment_state_preserves_cron_and_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Old deployment's cron schedule and parameters are captured for re-use (#793)."""
    deployment = SimpleNamespace(
        parameters={"chip_id": "X", "username": "u"},
        schedules=[
            SimpleNamespace(
                schedule=CronSchedule(cron="0 2 * * *", timezone="Asia/Tokyo"),
                active=True,
            )
        ],
    )
    _patch_get_client(monkeypatch, deployment)

    schedules, parameters = await _capture_deployment_state(
        uuid.UUID("00000000-0000-0000-0000-000000000000")
    )

    assert parameters == {"chip_id": "X", "username": "u"}
    assert len(schedules) == 1
    assert isinstance(schedules[0], DeploymentScheduleCreate)
    assert schedules[0].active is True
    captured_schedule = schedules[0].schedule
    assert isinstance(captured_schedule, CronSchedule)
    assert captured_schedule.cron == "0 2 * * *"


@pytest.mark.asyncio
async def test_capture_deployment_state_handles_no_schedules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deployment with no schedules and empty parameters yields ([], None)."""
    deployment = SimpleNamespace(parameters={}, schedules=[])
    _patch_get_client(monkeypatch, deployment)

    schedules, parameters = await _capture_deployment_state(
        uuid.UUID("00000000-0000-0000-0000-000000000000")
    )

    assert schedules == []
    assert parameters is None
