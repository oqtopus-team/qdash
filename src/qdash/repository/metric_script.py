"""MongoDB repository for MetricScriptDocument."""

from __future__ import annotations

from typing import Any

from bunnet.exceptions import DocumentNotFound

from qdash.dbmodel.metric_script import MetricScriptDocument


def _pin_path(dashboard_id: str) -> str:
    # Dashboard IDs are server-generated ("dash_<hex>"); refuse anything that would be
    # read as a nested path or an operator.
    if not dashboard_id or "." in dashboard_id or dashboard_id.startswith("$"):
        raise ValueError(f"Invalid dashboard ID for a pin key: {dashboard_id!r}")
    return f"pins.{dashboard_id}"


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

    def save_if_unchanged(self, doc: MetricScriptDocument, *, version: int) -> bool:
        """Replace the stored script only if it still has ``version``.

        ``version`` is the value read before ``doc`` was modified. Every write to the
        document increments it, including the pin operations below, so a save also fails
        when a dashboard pinned or unpinned a revision after the read. The match and the
        replace are one atomic operation, so of two writes that started from the same
        stored state exactly one succeeds. Returns False, writing nothing, when another
        write landed first; ``doc`` then keeps its incremented ``version``.
        """
        doc.system_info.update_time()
        doc.version = version + 1
        try:
            MetricScriptDocument.find_one({"_id": doc.id, "version": version}).replace_one(doc)
        except DocumentNotFound:
            return False
        return True

    def add_pin(
        self,
        *,
        project_id: str,
        script_id: str,
        dashboard_id: str,
        revisions: list[int],
        shared: bool,
        writer: str,
    ) -> bool:
        """Atomically widen the pin of ``dashboard_id`` and claim it for ``writer``.

        Adds ``revisions`` to the pin (never removes any), sets ``shared`` when it is True
        and records ``writer`` as the last writer. With no ``revisions`` it only claims an
        existing pin. The filter requires every revision in
        ``revisions`` to still be stored and, for a shared pin, the script to be shared, so
        a revision is never pinned after a script save evicted it. Returns False, writing
        nothing, when the script is gone or the filter does not match.
        """
        path = _pin_path(dashboard_id)
        query: dict[str, Any] = {"project_id": project_id, "script_id": script_id}
        conditions: list[dict[str, Any]] = [{"revisions.revision": r} for r in revisions]
        if conditions:
            query["$and"] = conditions
        else:
            # Claiming an existing pin only; do not create an empty one.
            query[path] = {"$exists": True}
        if shared:
            query["visibility"] = "project"
        fields: dict[str, Any] = {f"{path}.writer": writer}
        if shared:
            fields[f"{path}.shared"] = True
        update: dict[str, Any] = {
            "$set": fields,
            "$addToSet": {f"{path}.revisions": {"$each": sorted(set(revisions))}},
            "$inc": {"version": 1},
        }
        result = MetricScriptDocument.get_motor_collection().update_one(query, update)
        return bool(result.matched_count)

    def narrow_pin(
        self,
        *,
        project_id: str,
        script_id: str,
        dashboard_id: str,
        revisions: list[int],
        shared: bool,
        writer: str,
    ) -> bool:
        """Set the pin of ``dashboard_id`` to exactly ``revisions`` if ``writer`` still owns it.

        An empty ``revisions`` removes the pin. Nothing is written when another dashboard
        write claimed the pin after ``writer`` did; that write narrows the pin itself.
        """
        path = _pin_path(dashboard_id)
        query = {"project_id": project_id, "script_id": script_id, f"{path}.writer": writer}
        update: dict[str, Any] = {"$inc": {"version": 1}}
        if revisions:
            pin = {"revisions": sorted(set(revisions)), "shared": shared, "writer": writer}
            update["$set"] = {path: pin}
        else:
            update["$unset"] = {path: ""}
        result = MetricScriptDocument.get_motor_collection().update_one(query, update)
        return bool(result.matched_count)

    def clear_dashboard_pins(self, *, project_id: str, dashboard_id: str) -> None:
        """Remove the pins of ``dashboard_id`` from every script of the project.

        Only for a dashboard that no longer exists and never will (IDs are not reused).
        """
        path = _pin_path(dashboard_id)
        MetricScriptDocument.get_motor_collection().update_many(
            {"project_id": project_id, path: {"$exists": True}},
            {"$unset": {path: ""}, "$inc": {"version": 1}},
        )

    def delete_if_unchanged(self, doc: MetricScriptDocument, *, version: int) -> bool:
        """Delete the script only if it still has ``version``; False when it changed."""
        result = MetricScriptDocument.get_motor_collection().delete_one(
            {"_id": doc.id, "version": version}
        )
        return bool(result.deleted_count)
