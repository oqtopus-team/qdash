from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from qdash.workflow import deployment_service
from qdash.workflow.deployment_service import WORK_POOL_NAME, _ensure_work_pool


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
