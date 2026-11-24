"""Metric scripts and dashboards of a QDash session: save, read, pin.

These operations reach the server's ``/metric-scripts`` and ``/dashboards`` routes with
the session's project and the caller's permissions. Every create and update names its target
explicitly: nothing is matched by name, cached locally, retried or rolled back. A save based
on a stale revision or version raises :class:`~qdash.sdk.QDashConflictError` (409).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qdash.sdk._http import api_errors, body, read_options
from qdash.sdk.dashboard import Dashboard, MetricScriptError, Script, ScriptMetric, Visibility

if TYPE_CHECKING:
    from qdash.sdk._config import QDashConfig
    from qdash.sdk._generated.client import QDashApi
    from qdash.sdk._generated.types.dashboard_response import DashboardResponse
    from qdash.sdk._generated.types.metric_info import MetricInfo
    from qdash.sdk._generated.types.metric_script_response import MetricScriptResponse
    from qdash.sdk._generated.types.metric_script_revision import MetricScriptRevision
    from qdash.sdk._generated.types.metric_script_summary import MetricScriptSummary
    from qdash.sdk._generated.types.metric_script_validate_response import (
        MetricScriptValidateResponse,
    )


def _diagnostic_text(response: MetricScriptResponse) -> list[str]:
    lines = []
    for diagnostic in response.diagnostics:
        where = f"line {diagnostic.line}: " if diagnostic.line is not None else ""
        lines.append(f"{where}{diagnostic.message}")
    return lines


class SavedScript:
    """A metric script as the server stored it, bound to one revision.

    After :meth:`Scripts.create` or :meth:`Scripts.update` the bound revision is the one that
    save produced (or kept, when the source was unchanged), valid or not; after
    :meth:`Scripts.get` it is the active (last valid) revision unless another is asked for.
    :meth:`metric` refuses an invalid revision instead of falling back to an older one.
    ``response`` is the script as the API returned it.
    """

    def __init__(self, response: MetricScriptResponse, revision: int | None) -> None:
        self.response = response
        self.revision = revision

    @property
    def script_id(self) -> str:
        return self.response.script_id

    @property
    def name(self) -> str:
        return self.response.name

    @property
    def valid(self) -> bool:
        """Whether the bound revision validated, so its metrics can back panels."""
        entry = self._entry()
        return entry is not None and entry.status == "valid"

    @property
    def diagnostics(self) -> list[str]:
        """Problems the server reported for the latest saved source."""
        return _diagnostic_text(self.response) if self.revision == self.response.revision else []

    @property
    def metrics(self) -> list[MetricInfo]:
        """The catalog of the bound revision; empty when it is invalid."""
        entry = self._entry()
        return list(entry.metrics or []) if entry is not None else []

    def __repr__(self) -> str:
        return (
            f"SavedScript(script_id={self.script_id!r}, revision={self.revision!r}, "
            f"valid={self.valid})"
        )

    def _entry(self) -> MetricScriptRevision | None:
        return next((r for r in self.response.revisions if r.revision == self.revision), None)

    def metric(self, metric_id: str) -> ScriptMetric:
        """The metric ``metric_id`` of the bound revision, for a dashboard panel.

        Raises :class:`MetricScriptError` when the revision is invalid, missing or does not
        declare the metric; the error names the saved script and revision.
        """
        where = f"metric script {self.name!r} ({self.script_id})"
        if self.revision is None:
            raise MetricScriptError(
                f"{where} has no valid revision", script_id=self.script_id, revision=None
            )
        if self._entry() is None:
            raise MetricScriptError(
                f"revision {self.revision} of {where} is not in its history",
                script_id=self.script_id,
                revision=self.revision,
            )
        if not self.valid:
            diagnostics = self.diagnostics
            details = "".join(f"\n- {line}" for line in diagnostics)
            raise MetricScriptError(
                f"revision {self.revision} of {where} did not validate{details}",
                script_id=self.script_id,
                revision=self.revision,
                diagnostics=diagnostics,
            )
        catalog = self.metrics
        info = next((entry for entry in catalog if entry.id == metric_id), None)
        if info is None:
            known = ", ".join(entry.id for entry in catalog) or "none"
            raise MetricScriptError(
                f"revision {self.revision} of {where} has no metric {metric_id!r}; "
                f"it declares: {known}",
                script_id=self.script_id,
                revision=self.revision,
            )
        return ScriptMetric(script_id=self.script_id, revision=self.revision, info=info)


class Scripts:
    """The project's metric scripts, reached as ``QDash.scripts``."""

    def __init__(self, api: QDashApi, config: QDashConfig) -> None:
        self._api = api
        self._config = config

    def list(self) -> list[MetricScriptSummary]:
        """Scripts visible to the caller: shared with the project or their own."""
        with api_errors():
            response = self._api.metric_script.list_metric_scripts(
                request_options=read_options(self._config)
            )
        return list(response.scripts)

    def get(self, script_id: str, *, revision: int | None = None) -> SavedScript:
        """A saved script bound to ``revision``, by default its active (last valid) revision."""
        with api_errors():
            response = self._api.metric_script.get_metric_script(
                script_id, request_options=read_options(self._config)
            )
        return SavedScript(response, revision if revision is not None else response.active_revision)

    def template(
        self,
        template_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        visibility: Visibility | None = None,
    ) -> Script:
        """A local :class:`Script` holding a starter template's source; nothing is saved."""
        with api_errors():
            templates = self._api.metric_script.list_metric_script_templates(
                request_options=read_options(self._config)
            ).templates
        template = next((t for t in templates if t.template_id == template_id), None)
        if template is None:
            known = ", ".join(t.template_id for t in templates)
            raise ValueError(f"unknown metric script template {template_id!r}; known: {known}")
        return Script(
            name=name if name is not None else template.name,
            source=template.source,
            description=description if description is not None else template.description,
            visibility=visibility,
        )

    def validate(self, script: Script | str) -> MetricScriptValidateResponse:
        """Compile source on the server and return its catalog or diagnostics; saves nothing."""
        source = script.source if isinstance(script, Script) else script
        with api_errors():
            return self._api.metric_script.validate_metric_script(source=source)

    def create(self, script: Script) -> SavedScript:
        """Save a new script; the result is bound to its first revision, valid or not."""
        with api_errors():
            response = self._api.metric_script.create_metric_script(**body(script.create_request()))
        return SavedScript(response, response.revision)

    def update(
        self,
        target: str | SavedScript,
        script: Script,
        *,
        expected_revision: int | None = None,
    ) -> SavedScript:
        """Save ``script`` over the script ``target`` names.

        New source is validated and recorded as the next revision; source equal to the latest
        saved source adds none. The result is bound to that latest revision, so an invalid
        save is reported by :meth:`SavedScript.metric` instead of falling back to the old
        active revision. With a :class:`SavedScript` target the update is refused with
        :class:`~qdash.sdk.QDashConflictError` when the script was saved again since it was
        read; ``expected_revision`` sets that guard for an ID. Nothing is retried.
        """
        if isinstance(target, SavedScript):
            script_id = target.script_id
            if expected_revision is None:
                expected_revision = target.response.revision
        else:
            script_id = target
        request = script.update_request(expected_revision=expected_revision)
        with api_errors():
            response = self._api.metric_script.update_metric_script(script_id, **body(request))
        return SavedScript(response, response.revision)


class SavedDashboard:
    """A dashboard as the server stored it; ``response`` is the API's answer.

    ``version`` is the dashboard's write counter at that time; :meth:`Dashboards.update`
    sends it so a save made by someone else since then is not overwritten.
    """

    def __init__(self, response: DashboardResponse) -> None:
        self.response = response

    @property
    def dashboard_id(self) -> str:
        return self.response.dashboard_id

    @property
    def name(self) -> str:
        return self.response.name

    @property
    def version(self) -> int:
        return self.response.version

    def __repr__(self) -> str:
        return (
            f"SavedDashboard(dashboard_id={self.dashboard_id!r}, version={self.version}, "
            f"panels={len(self.response.panels)})"
        )

    def edit(self) -> Dashboard:
        """A local copy of this dashboard's settings and panels to change and save back."""
        return Dashboard.from_response(self.response)


class Dashboards:
    """The project's dashboards, reached as ``QDash.dashboards``."""

    def __init__(self, api: QDashApi, config: QDashConfig) -> None:
        self._api = api
        self._config = config

    def list(self) -> list[DashboardResponse]:
        """Dashboards visible to the caller: shared with the project or their own."""
        with api_errors():
            response = self._api.dashboard.list_dashboards(
                request_options=read_options(self._config)
            )
        return list(response.dashboards)

    def get(self, dashboard_id: str) -> SavedDashboard:
        with api_errors():
            return SavedDashboard(
                self._api.dashboard.get_dashboard(
                    dashboard_id, request_options=read_options(self._config)
                )
            )

    def create(self, dashboard: Dashboard) -> SavedDashboard:
        """Save a new dashboard owned by the caller."""
        with api_errors():
            response = self._api.dashboard.create_dashboard(**body(dashboard.create_request()))
        return SavedDashboard(response)

    def update(
        self,
        target: str | SavedDashboard,
        dashboard: Dashboard,
        *,
        expected_version: int | None = None,
    ) -> SavedDashboard:
        """Replace the settings and panels of the dashboard ``target`` names.

        The update is refused with :class:`~qdash.sdk.QDashConflictError` (409) when the
        dashboard changed since the version it is based on: ``expected_version``, else the version of a :class:`SavedDashboard`
        target, else the version read from the server just before saving. Nothing is retried.
        """
        if isinstance(target, SavedDashboard):
            dashboard_id = target.dashboard_id
            if expected_version is None:
                expected_version = target.version
        else:
            dashboard_id = target
            if expected_version is None:
                expected_version = self.get(dashboard_id).version
        request = dashboard.update_request(expected_version=expected_version)
        with api_errors():
            response = self._api.dashboard.update_dashboard(dashboard_id, **body(request))
        return SavedDashboard(response)
