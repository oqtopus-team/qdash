"""Reading and waiting for dispatched runs, shared by calibrations, pipelines and workflows."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from qdash.sdk._http import api_errors, read_options
from qdash.sdk.errors import QDashNotFoundError, QDashTransportError

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx

    from qdash.sdk._config import QDashConfig
    from qdash.sdk._generated.client import QDashApi
    from qdash.sdk._generated.core.request_options import RequestOptions
    from qdash.sdk._generated.types.execution_response_detail import ExecutionResponseDetail
    from qdash.sdk._results import ExecutionResult, TaskResult

# Execution and pipeline statuses after which nothing more runs.
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "canceled", "crashed"})


def run_status(detail: ExecutionResponseDetail) -> str:
    """The whole pipeline run's status, or the execution's own without pipeline progress."""
    return detail.pipeline.status if detail.pipeline is not None else detail.status


def _file_content(response: httpx.Response) -> bytes:
    """A served file's bytes; an HTML page in its place (such as a sign-in page) is an error."""
    if response.headers.get("content-type", "").lower().startswith("text/html"):
        raise QDashTransportError(
            f"{response.status_code}: expected a file but received an HTML page; check the "
            "base URL and any access proxy settings",
            status_code=response.status_code,
            headers=dict(response.headers),
        )
    return response.content


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

    def task_result(self, task_id: str) -> TaskResult:
        """The full saved result of ``task_id``; raises ``QDashNotFoundError`` when absent."""
        from qdash.sdk._results import TaskResult

        with api_errors():
            detail = self._api.task.get_task_result(
                task_id, request_options=read_options(self._config)
            )
        return TaskResult(self, detail)

    def figure_bytes(self, path: str) -> bytes:
        """The PNG the server keeps at ``path``, read through the session's connection."""
        with api_errors():
            raw = self._api.execution.with_raw_response.get_figure_by_path(
                path=path, request_options=self._binary_options("image/png, */*")
            )
        return _file_content(raw.response)

    def artifact_bytes(self, path: str) -> bytes:
        """The artifact file the server keeps at ``path``, such as figure JSON or raw data."""
        with api_errors():
            raw = self._api.execution.with_raw_response.download_artifact_by_path(
                path=path, request_options=self._binary_options("*/*")
            )
        return _file_content(raw.response)

    def _binary_options(self, accept: str) -> RequestOptions:
        # The session asks for JSON by default; a file read accepts the file's own type.
        options = read_options(self._config)
        options["additional_headers"] = {"Accept": accept}
        return options

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

    @property
    def succeeded(self) -> bool:
        """Whether the whole run completed; any case of ``completed`` counts."""
        return self.status.lower() == "completed"

    @property
    def done(self) -> bool:
        """Whether the whole run ended: completed, failed, cancelled, canceled or crashed."""
        return self.status.lower() in TERMINAL_STATUSES


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

    def executions(self) -> list[ExecutionResult]:
        """Each execution of the run as it is now, in pipeline step order.

        Reads the run's first execution, then the execution of every pipeline step that has
        started; pending steps and transforms are skipped, and an execution shared by steps
        appears once. A run without pipeline progress returns its one execution. Each result's
        ``status`` is that execution's own; :meth:`get` reports the whole run's. Waits for
        nothing: call :meth:`wait` first to inspect a finished run.
        """
        from qdash.sdk._results import collect_executions

        return collect_executions(self._executions, self.execution_id)

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
