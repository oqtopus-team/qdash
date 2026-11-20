"""Metric scripts and custom dashboards of a QDash session: save, read, pin.

These operations reach the server's ``/metric-scripts`` and ``/custom-dashboards`` routes with
the session's project and the caller's permissions. Every create and update names its target
explicitly: nothing is matched by name, cached locally, retried or rolled back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qdash.sdk.dashboard import Dashboard, MetricScriptError, Script, ScriptMetric, Visibility

if TYPE_CHECKING:
    from qdash.client.services.client import QDashClient
    from qdash.client.services.models import (
        CustomDashboardResponse,
        MetricInfo,
        MetricScriptResponse,
        MetricScriptRevision,
        MetricScriptSummary,
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
        return entry is not None and entry.status.value == "valid"

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

    def __init__(self, client: QDashClient) -> None:
        self._client = client

    def list(self) -> list[MetricScriptSummary]:
        """Scripts visible to the caller: shared with the project or their own."""
        return list(self._client.list_metric_scripts().scripts)

    def get(self, script_id: str, *, revision: int | None = None) -> SavedScript:
        """A saved script bound to ``revision``, by default its active (last valid) revision."""
        response = self._client.get_metric_script(script_id)
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
        templates = self._client.list_metric_script_templates().templates
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
        return self._client.validate_metric_script(source)

    def create(self, script: Script) -> SavedScript:
        """Save a new script; the result is bound to its first revision, valid or not."""
        response = self._client.create_metric_script(script.create_request())
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
        active revision. With a :class:`SavedScript` target the update is refused (409) when
        the script was saved again since it was read; ``expected_revision`` sets that guard
        for an ID.
        """
        if isinstance(target, SavedScript):
            script_id = target.script_id
            if expected_revision is None:
                expected_revision = target.response.revision
        else:
            script_id = target
        response = self._client.update_metric_script(
            script_id, script.update_request(expected_revision=expected_revision)
        )
        return SavedScript(response, response.revision)


class SavedDashboard:
    """A custom dashboard as the server stored it; ``response`` is the API's answer.

    ``version`` is the dashboard's write counter at that time; :meth:`Dashboards.update`
    sends it so a save made by someone else since then is not overwritten.
    """

    def __init__(self, response: CustomDashboardResponse) -> None:
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
    """The project's custom dashboards, reached as ``QDash.dashboards``."""

    def __init__(self, client: QDashClient) -> None:
        self._client = client

    def list(self) -> list[CustomDashboardResponse]:
        """Dashboards visible to the caller: shared with the project or their own."""
        return list(self._client.list_custom_dashboards().dashboards)

    def get(self, dashboard_id: str) -> SavedDashboard:
        return SavedDashboard(self._client.get_custom_dashboard(dashboard_id))

    def create(self, dashboard: Dashboard) -> SavedDashboard:
        """Save a new dashboard owned by the caller."""
        return SavedDashboard(self._client.create_custom_dashboard(dashboard.create_request()))

    def update(
        self,
        target: str | SavedDashboard,
        dashboard: Dashboard,
        *,
        expected_version: int | None = None,
    ) -> SavedDashboard:
        """Replace the settings and panels of the dashboard ``target`` names.

        The update is refused with a 409 error when the dashboard changed since the version
        it is based on: ``expected_version``, else the version of a :class:`SavedDashboard`
        target, else the version read from the server just before saving. Nothing is retried.
        """
        if isinstance(target, SavedDashboard):
            dashboard_id = target.dashboard_id
            if expected_version is None:
                expected_version = target.version
        else:
            dashboard_id = target
            if expected_version is None:
                expected_version = self._client.get_custom_dashboard(dashboard_id).version
        response = self._client.update_custom_dashboard(
            dashboard_id, dashboard.update_request(expected_version=expected_version)
        )
        return SavedDashboard(response)
