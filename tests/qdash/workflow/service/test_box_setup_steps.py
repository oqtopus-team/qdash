from __future__ import annotations

from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock

import pytest

from qdash.workflow.service.steps.box_setup import ConfigureAll
from qdash.workflow.service.steps.pipeline import StepContext
from qdash.workflow.service.targets import MuxTargets

if TYPE_CHECKING:
    from qdash.workflow.service._internal.session import CalibSession


class CancelledRun(Exception):
    """Stand-in for prefect.exceptions.CancelledRun, which is matched by class name."""


@pytest.mark.parametrize("exc", [RuntimeError("boom"), CancelledRun("cancelled")])
def test_configure_all_leaves_closing_the_execution_to_the_pipeline(monkeypatch, exc) -> None:
    """The pipeline's owned Execution records the abort; the step only propagates it."""
    monkeypatch.setattr("qdash.workflow.service.steps.box_setup.get_run_logger", MagicMock)
    service = MagicMock()
    service.execute_task.side_effect = exc

    with pytest.raises(type(exc)) as raised:
        ConfigureAll(mux_ids=[1]).execute(
            cast("CalibSession", service), MuxTargets([1]), StepContext()
        )

    assert raised.value is exc
    for name in (
        "_initialize",
        "finish_calibration",
        "fail_calibration",
        "cancel_calibration",
        "abandon_calibration",
    ):
        getattr(service, name).assert_not_called()


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
    step.execute(cast("CalibSession", service), MuxTargets([2, 3]), StepContext())

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
