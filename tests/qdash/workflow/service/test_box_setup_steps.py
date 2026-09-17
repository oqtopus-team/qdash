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
