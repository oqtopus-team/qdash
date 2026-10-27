"""Fold a System-named chip (``144Qv3-quel3``) into its physical chip (``144Qv3``).

While two QDash instances run one chip with two Systems, the second instance
stores its data under a chip whose name is the System id. Once a single
instance takes over, that data moves into the physical chip. The move is a
one-off operated by hand, so it is a command, not a registered migration::

    python -m qdash.dbmodel.merge_chip_systems \\
        --from-chip 144Qv3-quel3 --to-chip 144Qv3 \\
        --source-db qdash_quel3 --target-db qdash --project <project_id> [--apply]

Rules (design section 10.1, stage D):

* Qubit and coupling documents of the System's qids replace the target's
  documents for the same qids; the other qids of the chip are untouched.
  The qid set comes from ``--qids``, else from the configuration tree
  (``SystemCatalog.resources_of``), else every source document with data.
* History collections (task results, qubit/coupling/chip history, executions,
  calibration notes, notes, provenance, evaluations, forum posts, ...) are
  copied with ``chip_id`` rewritten; a document that already exists in the
  target is skipped. Task results without ``system_id`` get the source chip
  id, which is the System they were measured on.
* The chip document, cool-downs, locks and counters are never copied: the
  target chip exists already and the cryostat belongs to the target instance.

Without ``--apply`` nothing is written; the report lists what would move.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from typing import TYPE_CHECKING, Any

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pymongo.database import Database

logger = logging.getLogger(__name__)

CURRENT_STATE_COLLECTIONS: tuple[str, ...] = ("qubit", "coupling")
"""Documents keyed by (project, chip, qid) whose latest value wins per qid."""

NEVER_COPIED_COLLECTIONS: frozenset[str] = frozenset(
    {"chip", "cooldown", "execution_lock", "execution_counter", "migration_ledger"}
)
"""Collections that describe the instance rather than the chip's data."""

SKIPPED_FIELDS: frozenset[str] = frozenset({"_id"})


def _project_filter(project_id: str | None) -> dict[str, Any]:
    return {"project_id": project_id} if project_id else {}


def resolve_system_qids(to_chip: str, from_chip: str) -> set[str] | None:
    """Qids of System ``from_chip`` on chip ``to_chip`` from the configuration tree."""
    try:
        from qdash.common.config.qubex_layout import QubexLayout
        from qdash.common.config.system_catalog import SystemCatalog

        catalog = SystemCatalog(QubexLayout.detect(), to_chip)
        if from_chip not in catalog.system_ids():
            return None
        qids: set[str] = set()
        for mux in catalog.entry(from_chip).mux_ids:
            mux_size = catalog.mux_size()
            qids.update(str(mux * mux_size + offset) for offset in range(mux_size))
        return qids or None
    except Exception as exc:  # the tree is optional for this command
        logger.info("Configuration tree not used for the qid set: %s", exc)
        return None


def _chip_collections(database: Database[Any], from_chip: str) -> list[str]:
    names: list[str] = []
    for name in sorted(database.list_collection_names()):
        if name in NEVER_COPIED_COLLECTIONS or name.startswith("system."):
            continue
        if database[name].count_documents({"chip_id": from_chip}, limit=1):
            names.append(name)
    return names


def _rewritten(
    doc: dict[str, Any], from_chip: str, to_chip: str, collection: str
) -> dict[str, Any]:
    out = {key: value for key, value in doc.items() if key not in SKIPPED_FIELDS}
    out["chip_id"] = to_chip
    if collection == "task_result_history" and not out.get("system_id"):
        out["system_id"] = from_chip
    return out


def _merge_current_state(
    source: Database[Any],
    target: Database[Any],
    collection: str,
    *,
    from_chip: str,
    to_chip: str,
    project_id: str | None,
    qids: set[str] | None,
    apply: bool,
) -> dict[str, Any]:
    stats: dict[str, Any] = {"matched": 0, "replaced": 0, "inserted": 0, "skipped": 0}
    query = {"chip_id": from_chip, **_project_filter(project_id)}
    for doc in source[collection].find(query):
        stats["matched"] += 1
        qid = doc.get("qid")
        owned = qid in qids if qids is not None else bool(doc.get("data"))
        if not owned:
            stats["skipped"] += 1
            continue
        key = {"project_id": doc.get("project_id"), "chip_id": to_chip, "qid": qid}
        existing = target[collection].find_one(key, {"_id": 1})
        if existing is None:
            stats["inserted"] += 1
            if apply:
                target[collection].insert_one(_rewritten(doc, from_chip, to_chip, collection))
        else:
            stats["replaced"] += 1
            if apply:
                target[collection].replace_one(
                    {"_id": existing["_id"]}, _rewritten(doc, from_chip, to_chip, collection)
                )
    return stats


def _copy_history(
    source: Database[Any],
    target: Database[Any],
    collection: str,
    *,
    from_chip: str,
    to_chip: str,
    project_id: str | None,
    apply: bool,
) -> dict[str, Any]:
    stats: dict[str, Any] = {"matched": 0, "inserted": 0, "duplicates": 0}
    query = {"chip_id": from_chip, **_project_filter(project_id)}
    same_database = source is target or (
        source.name == target.name and source.client.address == target.client.address
    )
    if same_database:
        stats["matched"] = source[collection].count_documents(query)
        if apply:
            update: dict[str, Any] = {"chip_id": to_chip}
            result = target[collection].update_many(query, {"$set": update})
            stats["inserted"] = result.modified_count
            if collection == "task_result_history":
                target[collection].update_many(
                    {
                        "chip_id": to_chip,
                        "$or": [{"system_id": {"$exists": False}}, {"system_id": None}],
                    },
                    {"$set": {"system_id": from_chip}},
                )
        else:
            stats["inserted"] = stats["matched"]
        return stats
    for doc in source[collection].find(query):
        stats["matched"] += 1
        if not apply:
            stats["inserted"] += 1
            continue
        try:
            target[collection].insert_one(_rewritten(doc, from_chip, to_chip, collection))
            stats["inserted"] += 1
        except DuplicateKeyError:
            stats["duplicates"] += 1
    return stats


def merge_chip_systems(
    source: Database[Any],
    target: Database[Any],
    *,
    from_chip: str,
    to_chip: str,
    project_id: str | None = None,
    qids: Iterable[str] | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Move every chip-scoped document of ``from_chip`` into ``to_chip``."""
    if from_chip == to_chip:
        raise ValueError("--from-chip and --to-chip must differ")
    if target["chip"].find_one({"chip_id": to_chip, **_project_filter(project_id)}) is None:
        raise ValueError(f"Target chip {to_chip!r} does not exist in the target database")
    qid_set = set(qids) if qids is not None else resolve_system_qids(to_chip, from_chip)
    report: dict[str, Any] = {
        "from_chip": from_chip,
        "to_chip": to_chip,
        "project_id": project_id,
        "qids": sorted(qid_set, key=lambda q: (len(q), q)) if qid_set else None,
        "apply": apply,
        "collections": {},
    }
    for collection in _chip_collections(source, from_chip):
        if collection in CURRENT_STATE_COLLECTIONS:
            report["collections"][collection] = _merge_current_state(
                source,
                target,
                collection,
                from_chip=from_chip,
                to_chip=to_chip,
                project_id=project_id,
                qids=qid_set,
                apply=apply,
            )
        else:
            report["collections"][collection] = _copy_history(
                source,
                target,
                collection,
                from_chip=from_chip,
                to_chip=to_chip,
                project_id=project_id,
                apply=apply,
            )
    source_chip = source["chip"].find_one({"chip_id": from_chip, **_project_filter(project_id)})
    report["source_chip_document"] = (
        "left in place; delete it after verifying the merge" if source_chip else "absent"
    )
    return report


def _client(uri: str | None) -> MongoClient[Any]:
    if uri:
        return MongoClient(uri)
    host = os.getenv("MONGO_HOST", "mongo")
    port = 27017 if host == "mongo" else int(os.getenv("MONGO_PORT", "27017"))
    return MongoClient(
        host,
        port=port,
        username=os.getenv("MONGO_INITDB_ROOT_USERNAME"),
        password=os.getenv("MONGO_INITDB_ROOT_PASSWORD"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--from-chip", required=True, help="System-named chip to fold in")
    parser.add_argument("--to-chip", required=True, help="Physical chip that receives the data")
    parser.add_argument("--project", default=None, help="Restrict to one project id")
    parser.add_argument("--source-uri", default=None, help="MongoDB URI of the source instance")
    parser.add_argument("--target-uri", default=None, help="MongoDB URI of the target instance")
    parser.add_argument("--source-db", default=os.getenv("MONGO_DB_NAME", "qdash"))
    parser.add_argument("--target-db", default=os.getenv("MONGO_DB_NAME", "qdash"))
    parser.add_argument(
        "--qids", default=None, help="Comma-separated qids owned by the System (overrides config)"
    )
    parser.add_argument("--apply", action="store_true", help="Write; default is a dry run")
    args = parser.parse_args(argv)

    source_client = _client(args.source_uri)
    target_client = (
        source_client if args.target_uri in (None, args.source_uri) else _client(args.target_uri)
    )
    try:
        report = merge_chip_systems(
            source_client[args.source_db],
            target_client[args.target_db],
            from_chip=args.from_chip,
            to_chip=args.to_chip,
            project_id=args.project,
            qids=args.qids.split(",") if args.qids else None,
            apply=args.apply,
        )
    finally:
        source_client.close()
        if target_client is not source_client:
            target_client.close()
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
