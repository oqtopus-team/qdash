"""Tests for FlowScheduleService per-schedule cron resolution and mutation (#795)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from qdash.api.schemas.flow import UpdateScheduleRequest
from qdash.api.services import flow_schedule_service
from qdash.api.services.flow_schedule_service import FlowScheduleService


class _FakeFlowRepo:
    """Minimal stand-in for MongoFlowRepository."""

    def __init__(self, flows: list[object]) -> None:
        self._flows = flows

    def list_by_project(self, project_id: str) -> list[object]:
        return self._flows

    def find_one(self, query: dict[str, object]) -> object | None:
        for flow in self._flows:
            if all(getattr(flow, key, None) == value for key, value in query.items()):
                return flow
        return None


class _ClientCtx:
    """Async-context-manager stand-in for ``get_client()``."""

    def __init__(self, client: object) -> None:
        self._client = client

    async def __aenter__(self) -> object:
        return self._client

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def _fake_schedule(
    schedule_id: uuid.UUID,
    cron: str = "0 2 * * *",
    timezone: str = "Asia/Tokyo",
    active: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=schedule_id,
        schedule=SimpleNamespace(cron=cron, timezone=timezone),
        active=active,
        created=None,
    )


def _flow(
    name: str = "myflow", deployment_id: str | None = None, project_id: str = "proj-1"
) -> SimpleNamespace:
    return SimpleNamespace(name=name, deployment_id=deployment_id, project_id=project_id)


# --- _resolve_cron_schedule ---


@pytest.mark.asyncio
async def test_resolve_cron_schedule_found() -> None:
    schedule_id = uuid.uuid4()
    deployment_id = uuid.uuid4()
    schedule = _fake_schedule(schedule_id)
    flow = _flow(deployment_id=str(deployment_id))
    client = SimpleNamespace(read_deployment_schedules=AsyncMock(return_value=[schedule]))
    service = FlowScheduleService(flow_repository=_FakeFlowRepo([flow]))

    result = await service._resolve_cron_schedule(client, str(schedule_id), "proj-1")

    assert result is not None
    found_flow, found_deployment_uuid, found_schedule = result
    assert found_flow is flow
    assert found_deployment_uuid == deployment_id
    assert found_schedule is schedule


@pytest.mark.asyncio
async def test_resolve_cron_schedule_not_found() -> None:
    deployment_id = uuid.uuid4()
    flow = _flow(deployment_id=str(deployment_id))
    client = SimpleNamespace(read_deployment_schedules=AsyncMock(return_value=[]))
    service = FlowScheduleService(flow_repository=_FakeFlowRepo([flow]))

    result = await service._resolve_cron_schedule(client, str(uuid.uuid4()), "proj-1")

    assert result is None


@pytest.mark.asyncio
async def test_resolve_cron_schedule_invalid_uuid() -> None:
    client = SimpleNamespace(read_deployment_schedules=AsyncMock())
    service = FlowScheduleService(flow_repository=_FakeFlowRepo([]))

    result = await service._resolve_cron_schedule(client, "not-a-uuid", "proj-1")

    assert result is None
    client.read_deployment_schedules.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_cron_schedule_skips_flow_whose_read_fails() -> None:
    """A flow whose deployment schedules can't be read is skipped, not fatal."""
    schedule_id = uuid.uuid4()
    bad_deployment_id = uuid.uuid4()
    good_deployment_id = uuid.uuid4()
    schedule = _fake_schedule(schedule_id)
    bad_flow = _flow(name="bad", deployment_id=str(bad_deployment_id))
    good_flow = _flow(name="good", deployment_id=str(good_deployment_id))

    async def read_schedules(deployment_uuid: uuid.UUID) -> list[object]:
        if deployment_uuid == bad_deployment_id:
            raise RuntimeError("boom")
        return [schedule]

    client = SimpleNamespace(read_deployment_schedules=AsyncMock(side_effect=read_schedules))
    service = FlowScheduleService(flow_repository=_FakeFlowRepo([bad_flow, good_flow]))

    result = await service._resolve_cron_schedule(client, str(schedule_id), "proj-1")

    assert result is not None
    found_flow, found_deployment_uuid, _found_schedule = result
    assert found_flow is good_flow
    assert found_deployment_uuid == good_deployment_id


# --- update_schedule ---


@pytest.mark.asyncio
async def test_update_schedule_updates_cron_in_place(monkeypatch: pytest.MonkeyPatch) -> None:
    """Updating cron patches the matched schedule; nothing is deleted or recreated."""
    import sys

    # conftest stubs this module in sys.modules; ``import ... as`` would walk
    # attributes from the (unrelated) mocked `prefect` root instead of hitting
    # the cached module, so patch the cached module object directly.
    prefect_schedules_module = sys.modules["prefect.client.schemas.schedules"]
    monkeypatch.setattr(
        prefect_schedules_module,
        "CronSchedule",
        lambda cron, timezone: SimpleNamespace(cron=cron, timezone=timezone),
    )

    schedule_id = uuid.uuid4()
    deployment_id = uuid.uuid4()
    schedule = _fake_schedule(schedule_id, cron="0 2 * * *", timezone="Asia/Tokyo")
    flow = _flow(deployment_id=str(deployment_id))

    client = SimpleNamespace(
        read_deployment_schedules=AsyncMock(return_value=[schedule]),
        update_deployment_schedule=AsyncMock(),
        delete_deployment_schedule=AsyncMock(),
        create_deployment_schedules=AsyncMock(),
    )
    monkeypatch.setattr(flow_schedule_service, "get_client", lambda: _ClientCtx(client))

    service = FlowScheduleService(flow_repository=_FakeFlowRepo([flow]))
    request = UpdateScheduleRequest(active=False, cron="0 3 * * *", timezone="Asia/Tokyo")

    response = await service.update_schedule(str(schedule_id), request, "user", "proj-1")

    client.delete_deployment_schedule.assert_not_called()
    client.create_deployment_schedules.assert_not_called()
    client.update_deployment_schedule.assert_awaited_once()
    args, kwargs = client.update_deployment_schedule.await_args
    assert args == (deployment_id, schedule_id)
    assert kwargs["active"] is False
    assert kwargs["schedule"].cron == "0 3 * * *"
    assert response.schedule_id == str(schedule_id)


@pytest.mark.asyncio
async def test_update_schedule_active_only_leaves_cron_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule_id = uuid.uuid4()
    deployment_id = uuid.uuid4()
    schedule = _fake_schedule(schedule_id)
    flow = _flow(deployment_id=str(deployment_id))

    client = SimpleNamespace(
        read_deployment_schedules=AsyncMock(return_value=[schedule]),
        update_deployment_schedule=AsyncMock(),
    )
    monkeypatch.setattr(flow_schedule_service, "get_client", lambda: _ClientCtx(client))

    service = FlowScheduleService(flow_repository=_FakeFlowRepo([flow]))
    request = UpdateScheduleRequest(active=False)

    await service.update_schedule(str(schedule_id), request, "user", "proj-1")

    client.update_deployment_schedule.assert_awaited_once_with(
        deployment_id, schedule_id, active=False
    )


@pytest.mark.asyncio
async def test_update_schedule_not_found_raises_404(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SimpleNamespace(read_deployment_schedules=AsyncMock(return_value=[]))
    monkeypatch.setattr(flow_schedule_service, "get_client", lambda: _ClientCtx(client))

    service = FlowScheduleService(flow_repository=_FakeFlowRepo([]))
    request = UpdateScheduleRequest(active=True)

    with pytest.raises(HTTPException) as exc_info:
        await service.update_schedule(str(uuid.uuid4()), request, "user", "proj-1")

    assert exc_info.value.status_code == 404


# --- delete_schedule ---


@pytest.mark.asyncio
async def test_delete_schedule_deletes_only_matched_cron_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule_id = uuid.uuid4()
    deployment_id = uuid.uuid4()
    other_schedule_id = uuid.uuid4()
    target = _fake_schedule(schedule_id)
    other = _fake_schedule(other_schedule_id, cron="0 5 * * *")
    flow = _flow(deployment_id=str(deployment_id))

    client = SimpleNamespace(
        read_deployment_schedules=AsyncMock(return_value=[target, other]),
        delete_deployment_schedule=AsyncMock(),
    )
    monkeypatch.setattr(flow_schedule_service, "get_client", lambda: _ClientCtx(client))

    service = FlowScheduleService(flow_repository=_FakeFlowRepo([flow]))

    response = await service.delete_schedule(str(schedule_id), "user", "proj-1")

    client.delete_deployment_schedule.assert_awaited_once_with(deployment_id, schedule_id)
    assert response.schedule_type == "cron"
    assert response.schedule_id == str(schedule_id)


@pytest.mark.asyncio
async def test_delete_schedule_falls_back_to_one_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """A schedule_id that doesn't match any cron schedule is tried as a flow_run_id."""
    flow_run_id = uuid.uuid4()
    deployment_id = uuid.uuid4()
    flow = _flow(deployment_id=str(deployment_id))
    flow_run = SimpleNamespace(deployment_id=deployment_id)

    client = SimpleNamespace(
        read_deployment_schedules=AsyncMock(return_value=[]),
        read_flow_run=AsyncMock(return_value=flow_run),
        delete_flow_run=AsyncMock(),
    )
    monkeypatch.setattr(flow_schedule_service, "get_client", lambda: _ClientCtx(client))

    service = FlowScheduleService(flow_repository=_FakeFlowRepo([flow]))

    response = await service.delete_schedule(str(flow_run_id), "user", "proj-1")

    client.delete_flow_run.assert_awaited_once_with(flow_run_id)
    assert response.schedule_type == "one-time"
    assert response.schedule_id == str(flow_run_id)


@pytest.mark.asyncio
async def test_delete_schedule_not_found_raises_404(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SimpleNamespace(
        read_deployment_schedules=AsyncMock(return_value=[]),
        read_flow_run=AsyncMock(side_effect=Exception("not found")),
    )
    monkeypatch.setattr(flow_schedule_service, "get_client", lambda: _ClientCtx(client))

    service = FlowScheduleService(flow_repository=_FakeFlowRepo([]))

    with pytest.raises(HTTPException) as exc_info:
        await service.delete_schedule(str(uuid.uuid4()), "user", "proj-1")

    assert exc_info.value.status_code == 404
