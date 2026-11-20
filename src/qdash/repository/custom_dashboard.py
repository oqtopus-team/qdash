"""MongoDB repository for CustomDashboardDocument."""

from __future__ import annotations

from bunnet.exceptions import DocumentNotFound

from qdash.dbmodel.custom_dashboard import CustomDashboardDocument
from qdash.repository.metric_script import version_filter


class MongoCustomDashboardRepository:
    """CRUD helpers for CustomDashboardDocument."""

    def list_visible(self, *, project_id: str, user_id: str) -> list[CustomDashboardDocument]:
        """Project-shared dashboards plus the caller's own, newest update first."""
        docs = list(
            CustomDashboardDocument.find(
                {
                    "project_id": project_id,
                    "$or": [{"visibility": "project"}, {"user_id": user_id}],
                }
            ).run()
        )
        docs.sort(key=lambda d: d.system_info.updated_at, reverse=True)
        return docs

    def get(self, *, project_id: str, dashboard_id: str) -> CustomDashboardDocument | None:
        return CustomDashboardDocument.find_one(
            CustomDashboardDocument.project_id == project_id,
            CustomDashboardDocument.dashboard_id == dashboard_id,
        ).run()

    def insert(self, doc: CustomDashboardDocument) -> CustomDashboardDocument:
        doc.insert()
        return doc

    def save_if_unchanged(self, doc: CustomDashboardDocument, *, version: int) -> bool:
        """Replace the stored dashboard only if it still has ``version``.

        ``version`` is the value read before ``doc`` was modified. Returns False, writing
        nothing, when another save landed first or the dashboard was deleted.
        """
        doc.system_info.update_time()
        doc.version = version + 1
        try:
            CustomDashboardDocument.find_one(
                {"_id": doc.id, "version": version_filter(version)}
            ).replace_one(doc)
        except DocumentNotFound:
            return False
        return True

    def delete(self, doc: CustomDashboardDocument) -> None:
        doc.delete()

    def find_referencing_script(
        self, *, project_id: str, script_id: str
    ) -> list[CustomDashboardDocument]:
        """Dashboards of the project with a metric_script panel reading ``script_id``."""
        return list(
            CustomDashboardDocument.find(
                {"project_id": project_id, "panels.config.script_id": script_id}
            ).run()
        )
