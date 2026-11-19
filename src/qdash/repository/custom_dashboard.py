"""MongoDB repository for CustomDashboardDocument."""

from __future__ import annotations

from qdash.dbmodel.custom_dashboard import CustomDashboardDocument


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

    def save(self, doc: CustomDashboardDocument) -> CustomDashboardDocument:
        doc.system_info.update_time()
        doc.save()
        return doc

    def delete(self, doc: CustomDashboardDocument) -> None:
        doc.delete()
