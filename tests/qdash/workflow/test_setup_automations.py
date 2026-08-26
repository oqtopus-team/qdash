"""
Tests for the zombie-flow detection automation setup (#1351).
"""

from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock

import pytest

from qdash.workflow import setup_automations
from qdash.workflow.setup_automations import (
    AUTOMATION_NAME,
    _build_zombie_automation,
    _ensure_zombie_automation,
)

if TYPE_CHECKING:
    from prefect.client.orchestration import PrefectClient


class _Fake:
    """Records constructor kwargs as attributes for later assertion."""

    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


class FakeAutomationCore(_Fake):
    """Test stand-in for Prefect's AutomationCore model."""


class FakeEventTrigger(_Fake):
    """Test stand-in for Prefect's EventTrigger model."""


class FakeChangeFlowRunState(_Fake):
    """Test stand-in for Prefect's ChangeFlowRunState action."""

    state: Any


class FakeResourceSpecification:
    """Test stand-in for Prefect's ResourceSpecification root model."""

    def __init__(self, spec: Any) -> None:
        self.spec = spec


class FakePosture:
    """Test stand-in for Prefect's Posture enum."""

    Proactive = "Proactive"
    Reactive = "Reactive"


class FakeStateType:
    """Test stand-in for Prefect's StateType enum."""

    CRASHED = "CRASHED"


def _patch_automation_types(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap the prefect symbols on ``setup_automations`` for recording fakes."""
    monkeypatch.setattr(setup_automations, "AutomationCore", FakeAutomationCore)
    monkeypatch.setattr(setup_automations, "EventTrigger", FakeEventTrigger)
    monkeypatch.setattr(setup_automations, "ChangeFlowRunState", FakeChangeFlowRunState)
    monkeypatch.setattr(setup_automations, "ResourceSpecification", FakeResourceSpecification)
    monkeypatch.setattr(setup_automations, "Posture", FakePosture)
    monkeypatch.setattr(setup_automations, "StateType", FakeStateType)


def test_build_zombie_automation_uses_heartbeat_trigger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The trigger fires proactively when flow-run heartbeats stop arriving."""
    _patch_automation_types(monkeypatch)

    # Fakes are injected via monkeypatch, so treat the return as Any: the static
    # type is the real prefect union, which does not expose these attributes.
    automation: Any = _build_zombie_automation()
    trigger = automation.trigger

    assert automation.name == AUTOMATION_NAME
    assert trigger.posture == FakePosture.Proactive
    assert trigger.after == {"prefect.flow-run.heartbeat"}
    assert trigger.expect == {"prefect.flow-run.*"}
    assert trigger.for_each == {"prefect.resource.id"}
    assert trigger.match.spec == {"prefect.resource.id": ["prefect.flow-run.*"]}
    assert trigger.threshold == 1


def test_build_zombie_automation_waits_three_heartbeat_intervals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The window is 3x the 180s heartbeat interval, per the Prefect docs."""
    _patch_automation_types(monkeypatch)

    trigger: Any = _build_zombie_automation().trigger

    assert trigger.within == timedelta(seconds=3 * 180)


def test_build_zombie_automation_crashes_the_flow_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The single action flips the stalled run to CRASHED."""
    _patch_automation_types(monkeypatch)

    automation: Any = _build_zombie_automation()

    assert len(automation.actions) == 1
    action = automation.actions[0]
    assert isinstance(action, FakeChangeFlowRunState)
    assert action.state == FakeStateType.CRASHED


@pytest.mark.asyncio
async def test_ensure_zombie_automation_creates_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no matching automation, a new one is created."""
    _patch_automation_types(monkeypatch)
    client = SimpleNamespace(
        read_automations_by_name=AsyncMock(return_value=[]),
        create_automation=AsyncMock(return_value="automation-id"),
    )

    await _ensure_zombie_automation(cast("PrefectClient", client))

    client.read_automations_by_name.assert_awaited_once_with(AUTOMATION_NAME)
    client.create_automation.assert_awaited_once()
    created = client.create_automation.await_args.args[0]
    assert created.name == AUTOMATION_NAME


@pytest.mark.asyncio
async def test_ensure_zombie_automation_skips_when_present() -> None:
    """An existing automation with the same name is left untouched (idempotent)."""
    existing = SimpleNamespace(id="existing-id")
    client = SimpleNamespace(
        read_automations_by_name=AsyncMock(return_value=[existing]),
        create_automation=AsyncMock(),
    )

    await _ensure_zombie_automation(cast("PrefectClient", client))

    client.read_automations_by_name.assert_awaited_once_with(AUTOMATION_NAME)
    client.create_automation.assert_not_called()


class _FakeClientCtx:
    """Async-context-manager stand-in for ``get_client()``."""

    def __init__(self, client: object) -> None:
        self._client = client

    async def __aenter__(self) -> object:
        return self._client

    async def __aexit__(self, *_exc: object) -> bool:
        return False


@pytest.mark.asyncio
async def test_setup_automations_ensures_automation_via_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``setup_automations`` opens a client and registers the automation through it."""
    _patch_automation_types(monkeypatch)
    client = SimpleNamespace(
        read_automations_by_name=AsyncMock(return_value=[]),
        create_automation=AsyncMock(return_value="automation-id"),
    )
    monkeypatch.setattr(setup_automations, "get_client", lambda: _FakeClientCtx(client))

    await setup_automations.setup_automations()

    client.read_automations_by_name.assert_awaited_once_with(AUTOMATION_NAME)
    client.create_automation.assert_awaited_once()
