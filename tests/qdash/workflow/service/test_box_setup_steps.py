from __future__ import annotations

from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock

import pytest

from qdash.workflow.service.steps.box_setup import ConfigureAll
from qdash.workflow.service.steps.pipeline import StepContext
from qdash.workflow.service.targets import MuxTargets

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService


class CancelledRun(Exception):
    """Stand-in for prefect.exceptions.CancelledRun, which is matched by class name."""


class ExternalSignal(BaseException):
    """Stand-in for prefect.exceptions.ExternalSignal."""


class TerminationSignal(ExternalSignal):
    """Stand-in for prefect.exceptions.TerminationSignal."""


@pytest.mark.parametrize(
    ("exc", "handler"),
    [
        (RuntimeError("boom"), "fail_calibration"),
        (CancelledRun("cancelled"), "cancel_calibration"),
        (TerminationSignal("SIGTERM"), "abandon_calibration"),
    ],
)
def test_configure_all_routes_aborts_to_one_handler(monkeypatch, exc, handler) -> None:
    """A ConfigureAll that owns its session routes each abort to exactly one handler."""
    monkeypatch.setattr("qdash.workflow.service.steps.box_setup.get_run_logger", MagicMock)
    service = MagicMock()
    service._initialized = False
    service.execute_task.side_effect = exc

    step = ConfigureAll(mux_ids=[1])
    with pytest.raises(type(exc)):
        step.execute(cast("CalibService", service), MuxTargets([1]), StepContext())

    for name in ("fail_calibration", "cancel_calibration", "abandon_calibration"):
        if name == handler:
            getattr(service, name).assert_called_once()
        else:
            getattr(service, name).assert_not_called()


@pytest.mark.parametrize(
    ("exc", "handler"),
    [
        (RuntimeError("boom"), "fail_calibration"),
        (CancelledRun("cancelled"), "cancel_calibration"),
        (TerminationSignal("SIGTERM"), "abandon_calibration"),
    ],
)
def test_configure_all_keeps_the_abort_when_cleanup_fails(monkeypatch, exc, handler) -> None:
    """A handler that raises must not replace the abort that triggered it."""
    monkeypatch.setattr("qdash.workflow.service.steps.box_setup.get_run_logger", MagicMock)
    service = MagicMock()
    service._initialized = False
    service.execute_task.side_effect = exc
    getattr(service, handler).side_effect = RuntimeError("releasing the lock failed")

    step = ConfigureAll(mux_ids=[1])
    with pytest.raises(type(exc)) as raised:
        step.execute(cast("CalibService", service), MuxTargets([1]), StepContext())

    assert raised.value is exc


def test_configure_all_call_settings_reach_the_task_with_resolved_mux_ids(monkeypatch) -> None:
    """A ConfigureAll call's own run settings travel with the step's mux_ids."""
    from qdash.datamodel.task_call import TaskCall

    monkeypatch.setattr("qdash.workflow.service.steps.box_setup.get_run_logger", MagicMock)
    service = MagicMock()
    service._initialized = True
    service.plan_digest = None

    step = ConfigureAll(
        call=TaskCall(name="ConfigureAll", run={"configuration_mode": "ge-ef-cr"}),
    )
    assert [call.resolved_call_id for call in step.calls()] == ["ConfigureAll"]
    step.execute(cast("CalibService", service), MuxTargets([2, 3]), StepContext())

    _, kwargs = service.execute_task.call_args
    assert kwargs["parameters"] == {
        "run": {
            "configuration_mode": {"value": "ge-ef-cr"},
            "mux_ids": {"value": [2, 3]},
        },
        "input": {},
    }
    assert kwargs["invocation"].call_id == "ConfigureAll"


def test_configure_all_without_call_keeps_the_default_call() -> None:
    from qdash.datamodel.task_call import TaskCall

    assert ConfigureAll().calls() == (TaskCall(name="ConfigureAll", call_id="ConfigureAll"),)


def test_configure_all_call_must_name_configure_all() -> None:
    from qdash.datamodel.task_call import TaskCall

    with pytest.raises(ValueError, match="must name ConfigureAll"):
        ConfigureAll(call=TaskCall(name="Configure"))
