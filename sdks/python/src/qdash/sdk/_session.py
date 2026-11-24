"""The QDash session: one configured connection, the generated resources and the helpers."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from qdash.sdk._calibration import Chip
from qdash.sdk._chips import Chips
from qdash.sdk._config import QDashConfig, _load_config
from qdash.sdk._dashboards import Dashboards, Scripts
from qdash.sdk._device_topology import DeviceTopologies
from qdash.sdk._history import ExecutionHistory, TaskResultHistory
from qdash.sdk._http import build_api, close_owned_http_client, owned_http_client
from qdash.sdk._pipelines import Pipelines
from qdash.sdk._qubex import Qubex
from qdash.sdk._results import Execution
from qdash.sdk._runs import Executions, Run
from qdash.sdk._tasks import Tasks
from qdash.sdk._workflows import Workflows

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from types import TracebackType

    import httpx

    from qdash.sdk._generated.client import QDashApi
    from qdash.sdk._results import TaskResult


class QDash:
    """Entry point of the QDash SDK.

    Create one session and reuse it for every request of a notebook or script.
    ``QDash(config)``, ``QDash.from_env()`` and ``QDash.from_profile()`` create an HTTP
    connection that the session owns. It stays usable while this session, a session from
    :meth:`with_project`, :attr:`api`, a helper or a handle that uses it is referenced, and is
    closed at normal interpreter exit if it is still open; no explicit close is needed.
    :meth:`close`, or leaving a ``with`` block, releases it earlier. If the interpreter is
    terminated abruptly (for example by ``SIGKILL`` or ``os._exit``), the operating system
    reclaims the connections instead.

    ``QDash(config, http_client=client)`` uses an ``httpx.Client`` the caller created and
    closes; the SDK never closes it, and the client's own TLS and proxy settings apply.

    ``project_id`` (else ``config.project_id``) is sent as ``X-Project-Id`` with every
    request of the session, including the generated resource calls on :attr:`api`.

    The helpers (:attr:`chips`, :attr:`pipelines`, :attr:`workflows`, :attr:`tasks`,
    :attr:`scripts`, :attr:`dashboards`, :attr:`executions`, :attr:`task_results`,
    :attr:`device_topology`, :attr:`qubex`, :meth:`chip`, :meth:`run`, :meth:`execution`,
    :meth:`task_result`) raise the SDK's errors and send every write, and every POST, once. :attr:`api`
    is the generated client of the whole API, for every route the helpers do not cover.
    """

    def __init__(
        self,
        config: QDashConfig,
        *,
        project_id: str | None = None,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if project_id is not None:
            if not project_id:
                raise ValueError("project_id must be a non-empty string")
            config = config.model_copy(update={"project_id": project_id})
        self._config = config.model_copy(deep=True)
        config = self._config
        self._owns_http_client = http_client is None
        self._http_client = http_client if http_client is not None else owned_http_client(config)
        self._sleep = sleep
        try:
            self._api = build_api(config, self._http_client, project_id=config.project_id)
            self._executions = Executions(self._api, config, sleep=sleep)
            self.pipelines = Pipelines(self._api, config, self._executions, config.project_id)
            self.workflows = Workflows(self._api, config, self._executions, config.project_id)
            self.tasks = Tasks(self._api, config, self._executions, config.project_id)
            self.chips = Chips(self._api, config)
            self.scripts = Scripts(self._api, config)
            self.dashboards = Dashboards(self._api, config)
            self.executions = ExecutionHistory(self._api, config)
            self.task_results = TaskResultHistory(self._api, config)
            self.device_topology = DeviceTopologies(self._api, config)
            self.qubex = Qubex(self._api, config)
        except BaseException:
            self.close()
            raise

    @classmethod
    def from_env(cls, *, project_id: str | None = None) -> QDash:
        """A session configured from ``QDASH_*`` environment variables."""
        return cls(QDashConfig.from_env(), project_id=project_id)

    @classmethod
    def from_profile(
        cls,
        profile: str | None = None,
        path: str | Path | None = None,
        *,
        project_id: str | None = None,
    ) -> QDash:
        """A session configured from a profile of the QDash config file.

        The file and profile resolve as in :meth:`QDashConfig.from_file`: ``config.toml``
        and its ``default_profile`` unless ``path`` or ``profile`` is given.
        """
        return cls(_load_config(profile, path, stacklevel=3), project_id=project_id)

    def with_project(self, project_id: str) -> QDash:
        """A session scoped to ``project_id`` on this session's connection.

        The returned session borrows the connection: its :meth:`close` leaves it open, and it
        keeps working after this session is no longer referenced, until this session is
        closed or the interpreter exits. This session and its configuration are unchanged.
        """
        return QDash(
            self._config, project_id=project_id, http_client=self._http_client, sleep=self._sleep
        )

    @property
    def api(self) -> QDashApi:
        """The generated client of the whole API, with this session's auth and project.

        Resources follow the API's tags, e.g. ``qdash.api.chip.list_chips()`` or
        ``qdash.api.execution.get_execution(execution_id)``. Calls send no automatic retry
        unless ``request_options={"max_retries": n}`` asks for one, and raise the generated
        ``ApiError`` types (of which the SDK's errors are subclasses).
        """
        return self._api

    @property
    def config(self) -> QDashConfig:
        """A copy of the session settings; use with_project() to change project scope."""
        return self._config.model_copy(deep=True)

    @property
    def project_id(self) -> str | None:
        """The project sent as ``X-Project-Id``, or None for the server's default."""
        return self._config.project_id

    def chip(self, chip_id: str) -> Chip:
        """Calibration on ``chip_id`` through this session; sends no request.

        To read the chip's metadata, use ``chips.get(chip_id)``.
        """
        return Chip(self.pipelines, self._executions, chip_id)

    def run(self, execution_id: str) -> Run:
        """A handle to follow an execution already dispatched; sends no request."""
        if not isinstance(execution_id, str) or not execution_id:
            raise ValueError("execution_id must be a non-empty string")
        return Run(self._executions, execution_id)

    def execution(self, execution_id: str) -> Execution:
        """A handle to read one execution by ID; sends no request.

        Unlike :meth:`run`, which follows a whole pipeline run, its ``get()`` reports only this
        execution's own status and tasks.
        """
        if not isinstance(execution_id, str) or not execution_id:
            raise ValueError("execution_id must be a non-empty string")
        return Execution(self._executions, execution_id)

    def task_result(self, task_id: str) -> TaskResult:
        """The full saved result of one task run, read by ``task_id``."""
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("task_id must be a non-empty string")
        return self._executions.task_result(task_id)

    def close(self) -> None:
        """Release the connection now when the session created it; a borrowed one stays open.

        Optional: an owned connection still open at normal interpreter exit is closed then.
        Closing sends no request, and closing again does nothing. Sessions from
        :meth:`with_project`, :attr:`api` and the helpers of this session cannot send requests
        afterwards.
        """
        if self._owns_http_client:
            close_owned_http_client(self._http_client)

    def __enter__(self) -> QDash:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
