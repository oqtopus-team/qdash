"""MongoDB repository for MetricScriptDocument."""

from __future__ import annotations

from qdash.dbmodel.metric_script import MetricScriptDocument


class MongoMetricScriptRepository:
    """CRUD helpers for MetricScriptDocument."""

    def list_visible(self, *, project_id: str, user_id: str) -> list[MetricScriptDocument]:
        """Project-shared scripts plus the caller's own, newest update first."""
        docs = list(
            MetricScriptDocument.find(
                {
                    "project_id": project_id,
                    "$or": [{"visibility": "project"}, {"user_id": user_id}],
                }
            ).run()
        )
        docs.sort(key=lambda d: d.system_info.updated_at, reverse=True)
        return docs

    def get(self, *, project_id: str, script_id: str) -> MetricScriptDocument | None:
        return MetricScriptDocument.find_one(
            MetricScriptDocument.project_id == project_id,
            MetricScriptDocument.script_id == script_id,
        ).run()

    def find_by_template(self, *, project_id: str, template_id: str) -> list[MetricScriptDocument]:
        """Scripts of the project created from ``template_id``, oldest first."""
        docs = list(
            MetricScriptDocument.find({"project_id": project_id, "template_id": template_id}).run()
        )
        docs.sort(key=lambda d: d.system_info.created_at)
        return docs

    def insert(self, doc: MetricScriptDocument) -> MetricScriptDocument:
        doc.insert()
        return doc

    def save(self, doc: MetricScriptDocument) -> MetricScriptDocument:
        doc.system_info.update_time()
        doc.save()
        return doc

    def delete(self, doc: MetricScriptDocument) -> None:
        doc.delete()
