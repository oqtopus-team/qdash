"""MongoDB repository for MetricScriptDocument."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bunnet.exceptions import DocumentNotFound

from qdash.dbmodel.metric_script import MetricScriptDocument


def _bson_millis(value: datetime) -> datetime:
    """``value`` as BSON stores it: UTC, truncated to whole milliseconds."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    value = value.astimezone(UTC)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


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

    def save_if_unchanged(
        self, doc: MetricScriptDocument, *, revision: int, updated_at: datetime
    ) -> bool:
        """Replace the stored script only if it still has ``revision`` and ``updated_at``.

        ``revision`` and ``updated_at`` are the values read before ``doc`` was modified. The
        match and the replace are one atomic operation, so of two saves that started from
        the same stored state exactly one succeeds. Returns False, writing nothing, when
        another save landed first.
        """
        doc.system_info.update_time()
        # BSON keeps milliseconds only: make sure a save within the same millisecond as the
        # previous one still changes the stored value that later saves compare against.
        if _bson_millis(doc.system_info.updated_at) <= _bson_millis(updated_at):
            doc.system_info.updated_at = _bson_millis(updated_at) + timedelta(milliseconds=1)
        try:
            MetricScriptDocument.find_one(
                {"_id": doc.id, "revision": revision, "system_info.updated_at": updated_at}
            ).replace_one(doc)
        except DocumentNotFound:
            return False
        return True

    def delete(self, doc: MetricScriptDocument) -> None:
        doc.delete()
