"""The result of a dispatched run, shared by calibrations and registered workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qdash.client.services.models import ExecutionResponseDetail


def run_status(detail: ExecutionResponseDetail) -> str:
    """The whole pipeline run's status, or the execution's own without pipeline progress."""
    return detail.pipeline.status if detail.pipeline is not None else detail.status


@dataclass(frozen=True)
class RunResult:
    """The state of a run when it was read.

    ``status`` is the whole run's: ``detail.pipeline.status``, which stays ``running`` until
    the last step ends even when the first step's execution has completed. A run without
    pipeline progress leaves ``detail.status``. ``detail`` is the execution detail as the API
    returned it.
    """

    execution_id: str
    detail: ExecutionResponseDetail

    @property
    def status(self) -> str:
        return run_status(self.detail)
