"""MongoDB repository for MetricScriptDocument."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from bunnet.exceptions import DocumentNotFound

from qdash.dbmodel.custom_dashboard import CustomDashboardDocument
from qdash.dbmodel.metric_script import MetricScriptDocument


def _bson_millis(value: datetime) -> datetime:
    """``value`` as BSON stores it: UTC, truncated to whole milliseconds."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    value = value.astimezone(UTC)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


def version_filter(version: int) -> Any:
    """Match ``version``; documents written before the field existed count as version 0."""
    return version if version else {"$in": [0, None]}


def _pin_path(dashboard_id: str) -> str:
    # Dashboard IDs are server-generated ("dash_<hex>"); refuse anything that would be
    # read as a nested path or an operator.
    if not dashboard_id or "." in dashboard_id or dashboard_id.startswith("$"):
        raise ValueError(f"Invalid dashboard ID for a pin key: {dashboard_id!r}")
    return f"pins.{dashboard_id}"


class MongoMetricScriptRepository:
    """CRUD helpers for MetricScriptDocument."""

    def ensure_pins_initialized(self, *, project_id: str, script_id: str) -> None:
        """Backfill legacy references before any pin or destructive script write.

        Never trust a model's default empty pins. The persisted marker distinguishes a
        complete registry from an old or partially populated one. Every dashboard writer
        widens pins before saving; its version increment invalidates our snapshot. Script
        replacement/deletion require the marker, so cannot cross an unfinished backfill.
        A crash or ambiguous acknowledgement leaves either the old protected document or
        the complete registry. Retry from a fresh snapshot after any competing write.
        """
        collection = MetricScriptDocument.get_motor_collection()
        identity = {"project_id": project_id, "script_id": script_id}
        while True:
            raw = collection.find_one(identity)
            if raw is None or (raw.get("pins_initialized") is True and "pins" in raw):
                return
            pins = deepcopy(raw.get("pins", {}))
            for dashboard in CustomDashboardDocument.get_motor_collection().find(
                {"project_id": project_id, "panels.config.script_id": script_id}
            ):
                revisions = {
                    panel["config"]["script_revision"]
                    for panel in dashboard.get("panels", [])
                    if panel.get("type") == "metric_script"
                    and panel.get("config", {}).get("script_id") == script_id
                    and isinstance(panel["config"].get("script_revision"), int)
                }
                if not revisions:
                    continue
                dashboard_id = dashboard["dashboard_id"]
                _pin_path(dashboard_id)
                pin = pins.setdefault(
                    dashboard_id, {"revisions": [], "shared": False, "writer": uuid4().hex}
                )
                pin["revisions"] = sorted(set(pin["revisions"]) | revisions)
                pin["shared"] = pin.get("shared", False) or dashboard.get("visibility") == "project"
            result = collection.update_one(
                {"_id": raw["_id"], "version": version_filter(raw.get("version", 0))},
                {"$set": {"pins": pins, "pins_initialized": True}, "$inc": {"version": 1}},
            )
            if result.matched_count:
                return

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
        self.ensure_pins_initialized(project_id=project_id, script_id=script_id)
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
        doc.pins_initialized = True
        doc.insert()
        return doc

    def save_if_unchanged(
        self, doc: MetricScriptDocument, *, revision: int, updated_at: datetime, version: int
    ) -> bool:
        """Replace the stored script only if it is still in the state ``doc`` was read in.

        ``revision``, ``updated_at`` and ``version`` are the values read before ``doc`` was
        modified. ``version`` is incremented by every write to the document, including the
        pin operations below, so a save also fails when a dashboard pinned or unpinned a
        revision after the read. The
        match and the replace are one atomic operation, so of two writes that started from
        the same stored state exactly one succeeds. Returns False, writing nothing, when
        another write landed first; ``doc`` then keeps its incremented ``version``.
        """
        doc.system_info.update_time()
        # BSON keeps milliseconds only: make sure a save within the same millisecond as the
        # previous one still changes the stored value that later saves compare against.
        if _bson_millis(doc.system_info.updated_at) <= _bson_millis(updated_at):
            doc.system_info.updated_at = _bson_millis(updated_at) + timedelta(milliseconds=1)
        doc.version = version + 1
        try:
            MetricScriptDocument.find_one(
                {
                    "_id": doc.id,
                    "pins_initialized": True,
                    "pins": {"$exists": True},
                    "revision": revision,
                    "system_info.updated_at": updated_at,
                    "version": version_filter(version),
                }
            ).replace_one(doc)
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
        self.ensure_pins_initialized(project_id=project_id, script_id=script_id)
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
            {
                "_id": doc.id,
                "version": version_filter(version),
                "pins_initialized": True,
                "pins": {"$exists": True},
            }
        )
        return bool(result.deleted_count)
