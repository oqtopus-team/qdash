"""MongoDB repository for DashboardDocument."""

from __future__ import annotations

from bunnet.exceptions import DocumentNotFound

from qdash.dbmodel.dashboard import DashboardDocument


class MongoDashboardRepository:
    """CRUD helpers for DashboardDocument."""

    def list_visible(self, *, project_id: str, user_id: str) -> list[DashboardDocument]:
        """Project-shared dashboards plus the caller's own, newest update first."""
        docs = list(
            DashboardDocument.find(
                {
                    "project_id": project_id,
                    "$or": [{"visibility": "project"}, {"user_id": user_id}],
                }
            ).run()
        )
        docs.sort(key=lambda d: d.system_info.updated_at, reverse=True)
        return docs

    def get(self, *, project_id: str, dashboard_id: str) -> DashboardDocument | None:
        return DashboardDocument.find_one(
            DashboardDocument.project_id == project_id,
            DashboardDocument.dashboard_id == dashboard_id,
        ).run()

    def insert(self, doc: DashboardDocument) -> DashboardDocument:
        doc.insert()
        return doc

    def save_if_unchanged(self, doc: DashboardDocument, *, version: int) -> bool:
        """Replace the stored dashboard only if it still has ``version``.

        ``version`` is the value read before ``doc`` was modified. Returns False, writing
        nothing, when another save landed first or the dashboard was deleted.
        """
        doc.system_info.update_time()
        doc.version = version + 1
        try:
            DashboardDocument.find_one({"_id": doc.id, "version": version}).replace_one(doc)
        except DocumentNotFound:
            return False
        return True

    def delete(self, doc: DashboardDocument) -> None:
        result = doc.delete()
        if result is None or not result.acknowledged:
            raise RuntimeError("Dashboard deletion was not acknowledged; retaining script pins")

    def find_referencing_script(
        self, *, project_id: str, script_id: str
    ) -> list[DashboardDocument]:
        """Dashboards of the project with a metric_script panel reading ``script_id``."""
        return list(
            DashboardDocument.find(
                {"project_id": project_id, "panels.config.script_id": script_id}
            ).run()
        )
