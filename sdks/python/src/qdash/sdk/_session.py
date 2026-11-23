"""The QDash session: one configured client and the SDK operations on it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qdash.client.services.client import QDashClient
from qdash.client.services.config import QDashConfig
from qdash.sdk._calibration import Chip
from qdash.sdk._dashboards import Dashboards, Scripts
from qdash.sdk._pipelines import Pipelines
from qdash.sdk._workflows import Workflows

if TYPE_CHECKING:
    from pathlib import Path
    from types import TracebackType


class QDash:
    """Entry point of the QDash SDK.

    ``QDash.from_env()`` and ``QDash.from_profile()`` create a ``QDashClient`` that the session
    owns; :meth:`close` closes it. ``QDash(client)`` uses a client the caller created; the
    session never closes it. A session is reusable: every call shares its one connection
    until it is closed, so a script or notebook keeps one session and calls :meth:`close` when
    done, or uses ``with``, which calls it on exit. ``project_id`` scopes every request of the
    session to that project without changing the given client or its configuration.
    """

    def __init__(self, client: QDashClient, *, project_id: str | None = None) -> None:
        self._client = client.with_project(project_id) if project_id is not None else client
        self._owns_client = False
        self.pipelines = Pipelines(self._client)
        self.workflows = Workflows(self._client)
        self.scripts = Scripts(self._client)
        self.dashboards = Dashboards(self._client)

    @classmethod
    def from_env(cls, *, project_id: str | None = None) -> QDash:
        """A session configured from ``QDASH_*`` environment variables."""
        return cls._owning(QDashConfig.from_env(), project_id)

    @classmethod
    def from_profile(
        cls,
        profile: str = "default",
        path: str | Path | None = None,
        *,
        project_id: str | None = None,
    ) -> QDash:
        """A session configured from a profile of the client's config file."""
        config = (
            QDashConfig.from_file(profile=profile)
            if path is None
            else QDashConfig.from_file(profile=profile, path=path)
        )
        return cls._owning(config, project_id)

    @classmethod
    def _owning(cls, config: QDashConfig, project_id: str | None) -> QDash:
        if project_id is not None:
            config = config.model_copy(update={"project_id": project_id})
        session = cls(QDashClient(config))
        session._owns_client = True
        return session

    def chip(self, chip_id: str) -> Chip:
        """Calibration on ``chip_id`` through this session; sends no request."""
        return Chip(self.pipelines, chip_id)

    @property
    def client(self) -> QDashClient:
        """The underlying client, for routes the SDK does not wrap."""
        return self._client

    @property
    def project_id(self) -> str | None:
        """The project sent as ``X-Project-Id``, or None for the server's default."""
        return self._client.config.project_id

    def close(self) -> None:
        """Close the client when the session created it; a caller's client stays open."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> QDash:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
