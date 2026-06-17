import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

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

    # conftest mocks out prefect, so DeploymentScheduleCreate is not a real class here.
    # Stand in a recording factory to assert the schedule + active flag are carried over.
    # Assert on the recorded calls rather than the typed return value: the declared
    # return type's `schedule` is a prefect schedule union with no `.cron` attribute,
    # which mypy would reject (the SimpleNamespace records type as `Any`).
    recorded: list[SimpleNamespace] = []

    def fake_schedule_create(schedule: object, active: bool) -> SimpleNamespace:
        created = SimpleNamespace(schedule=schedule, active=active)
        recorded.append(created)
        return created

    monkeypatch.setattr(deployment_service, "DeploymentScheduleCreate", fake_schedule_create)

    cron = SimpleNamespace(cron="0 2 * * *", timezone="Asia/Tokyo")
    deployment = SimpleNamespace(
        parameters={"chip_id": "X", "username": "u"},
        schedules=[SimpleNamespace(schedule=cron, active=True)],
    )
    _patch_get_client(monkeypatch, deployment)

    schedules, parameters = await _capture_deployment_state(
        uuid.UUID("00000000-0000-0000-0000-000000000000")
    )

    assert parameters == {"chip_id": "X", "username": "u"}
    assert len(schedules) == 1
    assert len(recorded) == 1
    assert recorded[0].active is True
    # The original schedule object is passed through to DeploymentScheduleCreate unchanged.
    assert recorded[0].schedule is cron
    assert recorded[0].schedule.cron == "0 2 * * *"


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


class _FullFakeClient:
    """Fake Prefect client recording the calls ``register_deployment`` makes."""

    def __init__(self, deployment: object, new_deployment_id: uuid.UUID) -> None:
        self._new_deployment_id = new_deployment_id
        self.deleted: list[object] = []
        self.create_deployment_kwargs: dict[str, object] | None = None
        self.read_work_pool = AsyncMock(return_value=SimpleNamespace(id="pool-id"))
        self.create_flow = AsyncMock(return_value="flow-id")
        self.read_deployment = AsyncMock(return_value=deployment)

    async def delete_deployment(self, deployment_id: object) -> None:
        self.deleted.append(deployment_id)

    async def create_deployment(self, **kwargs: object) -> uuid.UUID:
        self.create_deployment_kwargs = kwargs
        return self._new_deployment_id


class _SharedClientCtx:
    """Async-context-manager yielding the same client on every ``get_client()`` call."""

    def __init__(self, client: object) -> None:
        self._client = client

    async def __aenter__(self) -> object:
        return self._client

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def _make_flow_file(tmp_path: Path) -> Path:
    flow_file = tmp_path / "myflow.py"
    flow_file.write_text("def my_flow():\n    return None\n")
    return flow_file


def _patch_register_deps(
    monkeypatch: pytest.MonkeyPatch, client: object, workflow_dir: Path
) -> None:
    monkeypatch.setattr(deployment_service, "get_client", lambda: _SharedClientCtx(client))
    monkeypatch.setattr(
        deployment_service,
        "get_path_resolver",
        lambda: SimpleNamespace(workflow_dir=workflow_dir),
    )
    monkeypatch.setattr(
        deployment_service,
        "DeploymentScheduleCreate",
        lambda schedule, active: SimpleNamespace(schedule=schedule, active=active),
    )


@pytest.mark.asyncio
async def test_register_deployment_preserves_schedules_from_old_deployment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Re-saving a flow carries the old deployment's schedule + parameters over (#793)."""
    cron = SimpleNamespace(cron="0 2 * * *", timezone="Asia/Tokyo")
    old_deployment = SimpleNamespace(
        parameters={"chip_id": "X", "username": "u"},
        schedules=[SimpleNamespace(schedule=cron, active=True)],
    )
    new_deployment_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    client = _FullFakeClient(old_deployment, new_deployment_id)

    flow_file = _make_flow_file(tmp_path)
    _patch_register_deps(monkeypatch, client, tmp_path)

    old_deployment_id = "00000000-0000-0000-0000-000000000000"
    request = deployment_service.RegisterDeploymentRequest(
        file_path=str(flow_file),
        flow_function_name="my_flow",
        old_deployment_id=old_deployment_id,
    )

    response = await deployment_service.register_deployment(request)

    assert response.deployment_id == str(new_deployment_id)
    assert response.deployment_name == "my_flow"
    # Old deployment was deleted using the parsed UUID (not the raw string).
    assert client.deleted == [uuid.UUID(old_deployment_id)]
    # Preserved schedule + parameters were forwarded to the new deployment.
    assert client.create_deployment_kwargs is not None
    kwargs = client.create_deployment_kwargs
    assert kwargs["parameters"] == {"chip_id": "X", "username": "u"}
    assert len(kwargs["schedules"]) == 1  # type: ignore[arg-type]
    assert kwargs["schedules"][0].schedule is cron  # type: ignore[index]


@pytest.mark.asyncio
async def test_register_deployment_without_old_deployment_passes_no_schedules(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A fresh deployment (no old id) is created with no preserved schedule/parameters."""
    new_deployment_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    client = _FullFakeClient(deployment=None, new_deployment_id=new_deployment_id)

    flow_file = _make_flow_file(tmp_path)
    _patch_register_deps(monkeypatch, client, tmp_path)

    request = deployment_service.RegisterDeploymentRequest(
        file_path=str(flow_file),
        flow_function_name="my_flow",
    )

    response = await deployment_service.register_deployment(request)

    assert response.deployment_id == str(new_deployment_id)
    assert client.deleted == []
    client.read_deployment.assert_not_awaited()
    assert client.create_deployment_kwargs is not None
    assert client.create_deployment_kwargs["schedules"] is None
    assert client.create_deployment_kwargs["parameters"] is None


@pytest.mark.asyncio
async def test_register_deployment_continues_when_reading_old_deployment_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If capturing the old deployment fails, registration still proceeds without it."""
    new_deployment_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    client = _FullFakeClient(deployment=None, new_deployment_id=new_deployment_id)
    client.read_deployment = AsyncMock(side_effect=lambda *_a, **_k: _raise(RuntimeError("boom")))

    flow_file = _make_flow_file(tmp_path)
    _patch_register_deps(monkeypatch, client, tmp_path)

    old_deployment_id = "00000000-0000-0000-0000-000000000000"
    request = deployment_service.RegisterDeploymentRequest(
        file_path=str(flow_file),
        flow_function_name="my_flow",
        old_deployment_id=old_deployment_id,
    )

    response = await deployment_service.register_deployment(request)

    # Read failure is swallowed: old deployment is still deleted and the new one is created.
    assert response.deployment_id == str(new_deployment_id)
    assert client.deleted == [uuid.UUID(old_deployment_id)]
    assert client.create_deployment_kwargs is not None
    assert client.create_deployment_kwargs["schedules"] is None
    assert client.create_deployment_kwargs["parameters"] is None
