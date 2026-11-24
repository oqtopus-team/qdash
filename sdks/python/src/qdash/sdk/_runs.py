"""Reading and waiting for dispatched runs, shared by calibrations, pipelines and workflows."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from qdash.sdk._http import api_errors, read_options
from qdash.sdk.errors import QDashNotFoundError

if TYPE_CHECKING:
    from collections.abc import Callable

    from qdash.sdk._config import QDashConfig
    from qdash.sdk._generated.client import QDashApi
    from qdash.sdk._generated.types.execution_response_detail import ExecutionResponseDetail

# Execution and pipeline statuses after which nothing more runs.
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "canceled", "crashed"})


def run_status(detail: ExecutionResponseDetail) -> str:
    """The whole pipeline run's status, or the execution's own without pipeline progress."""
    return detail.pipeline.status if detail.pipeline is not None else detail.status


class Executions:
    """Execution reads of one session; the run handles share it."""

    def __init__(
        self,
        api: QDashApi,
        config: QDashConfig,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._api = api
        self._config = config
        self._sleep = sleep
        self._clock = clock

    def get(self, execution_id: str) -> ExecutionResponseDetail:
        """The execution's detail; raises ``QDashNotFoundError`` before it exists."""
        with api_errors():
            return self._api.execution.get_execution(
                execution_id, request_options=read_options(self._config)
            )

    def wait(
        self, execution_id: str, *, timeout_seconds: float, poll_interval_seconds: float
    ) -> ExecutionResponseDetail:
        """Poll until the whole run reaches a terminal status and return its detail.

        An execution the server does not list yet (404) is polled again. A failed or
        cancelled run is returned, not raised. ``TimeoutError`` leaves the run going.
        """
        if timeout_seconds < 0 or poll_interval_seconds < 0:
            raise ValueError("Polling timeout and interval must be non-negative")
        deadline = self._clock() + timeout_seconds
        while True:
            try:
                detail: ExecutionResponseDetail | None = self.get(execution_id)
            except QDashNotFoundError:
                detail = None
            if detail is not None and run_status(detail).lower() in TERMINAL_STATUSES:
                return detail
            if self._clock() >= deadline:
                raise TimeoutError(
                    f"Execution '{execution_id}' did not reach a terminal state "
                    f"within {timeout_seconds} seconds"
                )
            self._sleep(poll_interval_seconds)


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


class Run:
    """A dispatched run, followed by its execution ID; ``QDash.run(id)`` reattaches to one."""

    def __init__(self, executions: Executions, execution_id: str) -> None:
        self._executions = executions
        self._execution_id = execution_id

    @property
    def execution_id(self) -> str:
        return self._execution_id

    def __repr__(self) -> str:
        return f"{type(self).__name__}(execution_id={self.execution_id!r})"

    def get(self) -> RunResult:
        """The run's current state; raises ``QDashNotFoundError`` before it exists."""
        return RunResult(self.execution_id, self._executions.get(self.execution_id))

    def wait(
        self,
        *,
        timeout_seconds: float = 3600.0,
        poll_interval_seconds: float = 5.0,
    ) -> RunResult:
        """Poll until the whole run ends and return its result.

        A failed or cancelled run is returned, not raised; check ``result.status``. An
        execution the server does not list yet is polled again. Raises ``TimeoutError`` when
        the run has not ended within ``timeout_seconds``; the run itself keeps going and is
        not cancelled.
        """
        detail = self._executions.wait(
            self.execution_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        return RunResult(self.execution_id, detail)
