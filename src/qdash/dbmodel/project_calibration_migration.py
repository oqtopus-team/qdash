"""Pre-start migration from user-owned to project-shared calibration state."""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pymongo.database import Database

MIGRATION_ID = "project-scoped-calibration-v1"
SCOPE_BACKFILL_MIGRATION_ID = "project-scoped-calibration-scope-backfill-v1"
ARTIFACT_MIGRATION_ID = "project-scoped-calibration-artifacts-date-layout-v2"
MIGRATION_LOCK_LEASE = timedelta(minutes=30)

_SHARED_COLLECTIONS: dict[str, tuple[str, ...]] = {
    "chip": ("project_id", "chip_id"),
    "qubit": ("project_id", "chip_id", "qid"),
    "coupling": ("project_id", "chip_id", "qid"),
    "chip_history": ("project_id", "chip_id", "recorded_date"),
    "qubit_history": ("project_id", "chip_id", "qid", "recorded_date"),
    "coupling_history": ("project_id", "chip_id", "qid", "recorded_date"),
    "calibration_note": ("project_id", "execution_id", "task_id", "chip_id"),
}


def _ensure_migration_archive_index(database: Database[Any]) -> None:
    """Install the lookup index used by idempotent migration archive writes."""
    database["migration_archive"].create_index(
        [
            ("migration_id", ASCENDING),
            ("source_collection", ASCENDING),
            ("source_id", ASCENDING),
            ("migration_kind", ASCENDING),
        ],
        name="migration_archive_lookup_idx",
    )


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _updated_at(document: dict[str, Any]) -> datetime:
    return _as_datetime(document.get("system_info", {}).get("updated_at")) or datetime.min.replace(
        tzinfo=timezone.utc
    )


def _winner(documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Choose a deterministic current value while preserving losers in the archive."""
    return max(documents, key=lambda doc: (_updated_at(doc), str(doc["_id"])))


def _deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Merge nested calibration mappings without dropping disjoint values."""
    result = dict(base)
    for key, value in update.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _merged_shared_fields(collection_name: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge current state without dropping disjoint or newer parameter values."""
    if collection_name not in {
        "qubit",
        "coupling",
        "qubit_history",
        "coupling_history",
        "calibration_note",
    }:
        return {}
    if collection_name != "calibration_note":
        selected: dict[str, tuple[datetime, str, Any]] = {}
        for document in documents:
            data = document.get("data")
            if not isinstance(data, dict):
                continue
            for name, parameter in data.items():
                calibrated_at = (
                    _as_datetime(parameter.get("calibrated_at"))
                    if isinstance(parameter, dict)
                    else None
                )
                key = (calibrated_at or _updated_at(document), str(document["_id"]))
                current = selected.get(name)
                if current is None or key > current[:2]:
                    selected[name] = (*key, parameter)
        return {"data": {name: selected_value[2] for name, selected_value in selected.items()}}

    merged: dict[str, Any] = {}
    for document in sorted(documents, key=lambda doc: (_updated_at(doc), str(doc["_id"]))):
        value = document.get("note")
        if isinstance(value, dict):
            merged = _deep_merge(merged, value)
    return {"note": merged}


def _is_missing_scope_value(value: Any) -> bool:
    return value is None or value == ""


def _resolve_legacy_project_id(database: Database[Any], document: dict[str, Any]) -> str | None:
    """Resolve a legacy user's project only when the stored ownership is unambiguous."""
    user_query: dict[str, Any] | None = None
    if document.get("user_id"):
        user_query = {"user_id": document["user_id"]}
    elif document.get("username"):
        user_query = {"username": document["username"]}

    if user_query is not None:
        user = database["user"].find_one(user_query, {"default_project_id": 1})
        if user and not _is_missing_scope_value(user.get("default_project_id")):
            return str(user["default_project_id"])

    membership_query: dict[str, Any] | None = None
    if document.get("user_id"):
        membership_query = {"user_id": document["user_id"], "status": "active"}
    elif document.get("username"):
        membership_query = {"username": document["username"], "status": "active"}
    if membership_query is None:
        return None

    project_ids = database["project_membership"].distinct("project_id", membership_query)
    valid_project_ids = [project_id for project_id in project_ids if project_id]
    return str(valid_project_ids[0]) if len(valid_project_ids) == 1 else None


def _resolve_calibration_note_chip_id(
    database: Database[Any], document: dict[str, Any]
) -> str | None:
    """Resolve a legacy note's chip from its uniquely scoped execution."""
    project_id = document.get("project_id")
    execution_id = document.get("execution_id")
    if not project_id or not execution_id:
        return None
    chip_ids = database["execution_history"].distinct(
        "chip_id",
        {"project_id": project_id, "execution_id": execution_id},
    )
    valid_chip_ids = [chip_id for chip_id in chip_ids if chip_id]
    return str(valid_chip_ids[0]) if len(valid_chip_ids) == 1 else None


def _scope_backfill_plan(
    database: Database[Any], collection_name: str, keys: tuple[str, ...]
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], int]:
    """Plan safe project scope repairs and count documents that remain invalid."""
    invalid_fields = [{"$or": [{key: {"$exists": False}}, {key: None}, {key: ""}]} for key in keys]
    documents = database[collection_name].find({"$or": invalid_fields})
    plan: list[tuple[dict[str, Any], dict[str, Any]]] = []
    unresolved = 0
    for document in documents:
        updates: dict[str, Any] = {}
        if "project_id" in keys and _is_missing_scope_value(document.get("project_id")):
            project_id = _resolve_legacy_project_id(database, document)
            if project_id is not None:
                updates["project_id"] = project_id
        projected = {**document, **updates}
        if collection_name == "calibration_note" and _is_missing_scope_value(
            projected.get("chip_id")
        ):
            chip_id = _resolve_calibration_note_chip_id(database, projected)
            if chip_id is not None:
                updates["chip_id"] = chip_id
                projected["chip_id"] = chip_id
        if any(_is_missing_scope_value(projected.get(key)) for key in keys):
            unresolved += 1
        elif updates:
            plan.append((document, updates))
    return plan, unresolved


def _apply_scope_backfill(
    database: Database[Any],
    plans: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]],
    *,
    migrated_at: datetime,
) -> None:
    archive = database["migration_archive"]
    for collection_name, collection_plan in plans.items():
        collection = database[collection_name]
        for document, updates in collection_plan:
            archive.update_one(
                {
                    "migration_id": SCOPE_BACKFILL_MIGRATION_ID,
                    "source_collection": collection_name,
                    "source_id": document["_id"],
                },
                {
                    "$setOnInsert": {
                        "migrated_at": migrated_at,
                        "document": document,
                        "backfilled_fields": updates,
                    }
                },
                upsert=True,
            )
            collection.update_one({"_id": document["_id"]}, {"$set": updates})


def _duplicates(
    database: Database[Any], collection_name: str, keys: tuple[str, ...]
) -> list[dict[str, Any]]:
    group_id = {key: f"${key}" for key in keys}
    return list(
        database[collection_name].aggregate(
            [
                {"$group": {"_id": group_id, "ids": {"$push": "$_id"}, "count": {"$sum": 1}}},
                {"$match": {"count": {"$gt": 1}}},
            ]
        )
    )


def _replace_unique_index(
    database: Database[Any], collection_name: str, keys: tuple[str, ...]
) -> None:
    collection = database[collection_name]
    desired_keys = [(key, ASCENDING) for key in keys]
    desired_name = "_".join(f"{key}_1" for key in keys)
    desired_exists = False
    for name, info in collection.index_information().items():
        if name == "_id_":
            continue
        raw_keys = info.get("key", [])
        existing_keys = list(raw_keys.items()) if isinstance(raw_keys, dict) else list(raw_keys)
        if name == desired_name:
            if existing_keys == desired_keys and info.get("unique") is True:
                desired_exists = True
            else:
                collection.drop_index(name)
            continue
        if existing_keys == desired_keys and info.get("unique") is True:
            collection.drop_index(name)
        if info.get("unique") and any(key == "username" for key, _ in existing_keys):
            collection.drop_index(name)
    if desired_exists:
        return
    collection.create_index(desired_keys, unique=True)


def migrate_project_scoped_calibration(
    database: Database[Any], *, dry_run: bool = True
) -> dict[str, Any]:
    """Consolidate calibration state by project and install project-scoped indexes.

    Losing documents are copied verbatim to ``migration_archive`` before deletion.
    Re-running the migration is safe; completed migrations return immediately.
    """
    _ensure_migration_archive_index(database)
    ledger = database["migration_ledger"]
    if ledger.find_one({"migration_id": MIGRATION_ID, "status": "completed"}):
        if not dry_run:
            for collection_name, keys in _SHARED_COLLECTIONS.items():
                _replace_unique_index(database, collection_name, keys)
            _replace_unique_index(database, "execution_counter", ("project_id", "date", "chip_id"))
        return {"migration_id": MIGRATION_ID, "already_completed": True, "collections": {}}

    stats: dict[str, Any] = {
        "migration_id": MIGRATION_ID,
        "already_completed": False,
        "collections": {},
    }
    plans: dict[str, list[tuple[dict[str, Any], list[dict[str, Any]]]]] = {}
    invalid_scope: dict[str, int] = {}
    scope_backfills: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for collection_name, keys in _SHARED_COLLECTIONS.items():
        collection = database[collection_name]
        backfill_plan, unresolved = _scope_backfill_plan(database, collection_name, keys)
        scope_backfills[collection_name] = backfill_plan
        invalid_scope[collection_name] = unresolved
        plans[collection_name] = []
        archived = 0
        for duplicate in _duplicates(database, collection_name, keys):
            documents = list(collection.find({"_id": {"$in": duplicate["ids"]}}))
            winner = _winner(documents)
            losers = [doc for doc in documents if doc["_id"] != winner["_id"]]
            plans[collection_name].append((winner, losers))
            archived += len(losers)
        stats["collections"][collection_name] = {
            "duplicate_groups": len(plans[collection_name]),
            "documents_to_archive": archived,
        }

    counter_groups = _duplicates(database, "execution_counter", ("project_id", "date", "chip_id"))
    counter_backfills, counter_unresolved = _scope_backfill_plan(
        database, "execution_counter", ("project_id", "date", "chip_id")
    )
    scope_backfills["execution_counter"] = counter_backfills
    invalid_scope["execution_counter"] = counter_unresolved
    stats["invalid_scope_documents"] = invalid_scope
    stats["scope_backfill_documents"] = {
        collection_name: len(collection_plan)
        for collection_name, collection_plan in scope_backfills.items()
    }
    stats["collections"]["execution_counter"] = {
        "duplicate_groups": len(counter_groups),
        "documents_to_archive": sum(group["count"] - 1 for group in counter_groups),
    }
    if dry_run:
        return stats
    invalid_total = sum(invalid_scope.values())
    if invalid_total:
        unresolved_counts = {
            collection_name: count for collection_name, count in invalid_scope.items() if count
        }
        planned_backfills = {
            collection_name: len(collection_plan)
            for collection_name, collection_plan in scope_backfills.items()
            if collection_plan
        }
        raise RuntimeError(
            f"Cannot migrate {invalid_total} calibration document(s) with missing scope fields; "
            f"unresolved_by_collection={unresolved_counts}; "
            f"planned_project_backfills={planned_backfills}"
        )

    lock = database["migration_lock"]
    acquired_at = datetime.now(timezone.utc)
    try:
        lock.find_one_and_update(
            {
                "_id": MIGRATION_ID,
                "$or": [
                    {"acquired_at": {"$lt": acquired_at - MIGRATION_LOCK_LEASE}},
                    {"acquired_at": {"$exists": False}},
                ],
            },
            {"$set": {"acquired_at": acquired_at}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError as exc:
        raise RuntimeError(f"Migration {MIGRATION_ID} is already running") from exc

    archive = database["migration_archive"]
    try:
        migrated_at = datetime.now(timezone.utc)
        _apply_scope_backfill(database, scope_backfills, migrated_at=migrated_at)

        # Backfilled project IDs can introduce new project-scoped duplicate groups.
        # Recalculate the consolidation plan against the repaired documents.
        for collection_name, keys in _SHARED_COLLECTIONS.items():
            collection = database[collection_name]
            plans[collection_name] = []
            archived = 0
            for duplicate in _duplicates(database, collection_name, keys):
                documents = list(collection.find({"_id": {"$in": duplicate["ids"]}}))
                winner = _winner(documents)
                losers = [doc for doc in documents if doc["_id"] != winner["_id"]]
                plans[collection_name].append((winner, losers))
                archived += len(losers)
            stats["collections"][collection_name] = {
                "duplicate_groups": len(plans[collection_name]),
                "documents_to_archive": archived,
            }
        counter_groups = _duplicates(
            database, "execution_counter", ("project_id", "date", "chip_id")
        )
        stats["collections"]["execution_counter"] = {
            "duplicate_groups": len(counter_groups),
            "documents_to_archive": sum(group["count"] - 1 for group in counter_groups),
        }

        for collection_name, groups in plans.items():
            collection = database[collection_name]
            for winner, losers in groups:
                documents = [winner, *losers]
                for loser in losers:
                    archive.update_one(
                        {
                            "migration_id": MIGRATION_ID,
                            "source_collection": collection_name,
                            "source_id": loser["_id"],
                        },
                        {
                            "$setOnInsert": {
                                "migrated_at": migrated_at,
                                "winner_id": winner["_id"],
                                "document": loser,
                            }
                        },
                        upsert=True,
                    )
                merged_fields = _merged_shared_fields(collection_name, documents)
                if merged_fields:
                    collection.update_one({"_id": winner["_id"]}, {"$set": merged_fields})
                if losers:
                    collection.delete_many({"_id": {"$in": [doc["_id"] for doc in losers]}})
            _replace_unique_index(database, collection_name, _SHARED_COLLECTIONS[collection_name])

        counters = database["execution_counter"]
        for group in counter_groups:
            documents = list(counters.find({"_id": {"$in": group["ids"]}}))
            winner = max(documents, key=lambda doc: (int(doc.get("index", 0)), str(doc["_id"])))
            losers = [doc for doc in documents if doc["_id"] != winner["_id"]]
            for loser in losers:
                archive.update_one(
                    {
                        "migration_id": MIGRATION_ID,
                        "source_collection": "execution_counter",
                        "source_id": loser["_id"],
                    },
                    {
                        "$setOnInsert": {
                            "migrated_at": migrated_at,
                            "winner_id": winner["_id"],
                            "document": loser,
                        }
                    },
                    upsert=True,
                )
            counters.delete_many({"_id": {"$in": [doc["_id"] for doc in losers]}})
        _replace_unique_index(database, "execution_counter", ("project_id", "date", "chip_id"))

        ledger.update_one(
            {"migration_id": MIGRATION_ID},
            {"$set": {"status": "completed", "completed_at": migrated_at, "stats": stats}},
            upsert=True,
        )
    finally:
        lock.delete_one({"_id": MIGRATION_ID})
    return stats


def _copy_tree_without_overwrite(source: Path, target: Path, conflict_root: Path) -> dict[str, int]:
    stats = {"copied": 0, "identical": 0, "conflicts": 0}
    if not source.is_dir():
        return stats
    for source_file in source.rglob("*"):
        if not source_file.is_file():
            continue
        relative = source_file.relative_to(source)
        target_file = target / relative
        if not target_file.exists():
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)
            stats["copied"] += 1
        elif source_file.read_bytes() == target_file.read_bytes():
            stats["identical"] += 1
        else:
            conflict_file = conflict_root / relative
            conflict_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, conflict_file)
            stats["conflicts"] += 1
    return stats


def _rewrite_artifact_path(value: Any, *, sources: list[Path], target: Path) -> Any:
    """Rewrite one legacy execution path while leaving unrelated values untouched."""
    if not isinstance(value, str) or not value:
        return value
    candidate = Path(value)
    for source in sources:
        try:
            relative = candidate.relative_to(source)
        except ValueError:
            continue
        return str(target / relative)
    return value


def _archive_path_document(
    database: Database[Any], *, collection_name: str, document: dict[str, Any]
) -> None:
    """Archive a document before changing its persisted artifact paths."""
    database["migration_archive"].update_one(
        {
            "migration_id": MIGRATION_ID,
            "migration_kind": "artifact_path_rewrite",
            "source_collection": collection_name,
            "source_id": document["_id"],
        },
        {
            "$setOnInsert": {
                "migrated_at": datetime.now(timezone.utc),
                "document": document,
            }
        },
        upsert=True,
    )


def _migrate_execution_document_paths(
    database: Database[Any],
    *,
    execution: dict[str, Any],
    source: Path,
    target: Path,
    dry_run: bool,
) -> int:
    """Rewrite execution, task-result, and derived knowledge artifact paths."""
    stored_root = execution.get("calib_data_path")
    sources = [source]
    if isinstance(stored_root, str) and stored_root:
        sources.append(Path(stored_root))

    updates: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    new_root = _rewrite_artifact_path(stored_root, sources=sources, target=target)
    if new_root != stored_root:
        updates.append(("execution_history", execution, {"calib_data_path": new_root}))

    task_query = {
        "project_id": execution["project_id"],
        "chip_id": execution["chip_id"],
        "execution_id": execution["execution_id"],
    }
    task_documents = list(database["task_result_history"].find(task_query))
    for task_document in task_documents:
        task_updates: dict[str, Any] = {}
        for field in ("figure_path", "json_figure_path", "raw_data_path"):
            old_paths = task_document.get(field)
            if not isinstance(old_paths, list):
                continue
            new_paths = [
                _rewrite_artifact_path(path, sources=sources, target=target) for path in old_paths
            ]
            if new_paths != old_paths:
                task_updates[field] = new_paths
        if task_updates:
            updates.append(("task_result_history", task_document, task_updates))

    task_ids = list(
        dict.fromkeys(
            task_id for task_document in task_documents if (task_id := task_document.get("task_id"))
        )
    )
    if task_ids:
        knowledge_query = {
            "project_id": execution["project_id"],
            "task_id": {"$in": task_ids},
        }
        for knowledge in database["issue_knowledge"].find(knowledge_query):
            old_paths = knowledge.get("figure_paths")
            if not isinstance(old_paths, list):
                continue
            new_paths = [
                _rewrite_artifact_path(path, sources=sources, target=target) for path in old_paths
            ]
            if new_paths != old_paths:
                updates.append(("issue_knowledge", knowledge, {"figure_paths": new_paths}))

    if dry_run:
        return len(updates)
    for collection_name, document, fields in updates:
        _archive_path_document(
            database,
            collection_name=collection_name,
            document=document,
        )
        database[collection_name].update_one({"_id": document["_id"]}, {"$set": fields})
    return len(updates)


def _migrate_classifier_files(
    *,
    sources: dict[str, Path],
    target: Path,
    dry_run: bool,
) -> dict[str, int]:
    """Select the newest classifier per relative path and preserve all conflicts."""
    stats = {"copied": 0, "identical": 0, "conflicts": 0}
    candidates: dict[Path, list[tuple[str, Path]]] = {}
    for username, source in sources.items():
        if not source.is_dir():
            continue
        for source_file in source.rglob("*"):
            if source_file.is_file():
                candidates.setdefault(source_file.relative_to(source), []).append(
                    (username, source_file)
                )

    for relative, files in candidates.items():
        files.sort(key=lambda item: (item[1].stat().st_mtime_ns, item[0]), reverse=True)
        winner_username, winner_file = files[0]
        target_file = target / relative
        if dry_run:
            stats["copied"] += 1
            stats["conflicts"] += max(0, len(files) - 1)
            continue

        target_file.parent.mkdir(parents=True, exist_ok=True)
        preserve_existing = (
            target_file.exists() and target_file.stat().st_mtime_ns > winner_file.stat().st_mtime_ns
        )
        if not target_file.exists():
            shutil.copy2(winner_file, target_file)
            stats["copied"] += 1
        elif target_file.read_bytes() == winner_file.read_bytes():
            stats["identical"] += 1
        elif preserve_existing:
            conflict_file = target.parent / ".migration_conflicts" / winner_username / relative
            conflict_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(winner_file, conflict_file)
            stats["conflicts"] += 1
        else:
            previous = target.parent / ".migration_conflicts" / "preexisting" / relative
            previous.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target_file, previous)
            shutil.copy2(winner_file, target_file)
            stats["copied"] += 1
            stats["conflicts"] += 1

        for username, source_file in files[1:]:
            if source_file.read_bytes() == target_file.read_bytes():
                stats["identical"] += 1
                continue
            conflict_file = target.parent / ".migration_conflicts" / username / relative
            conflict_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, conflict_file)
            stats["conflicts"] += 1
    return stats


def migrate_calibration_files(
    database: Database[Any],
    *,
    base_path: Path,
    dry_run: bool = True,
    allow_missing: bool = False,
) -> dict[str, Any]:
    """Copy legacy user artifacts to project-chip paths without deleting sources."""
    _ensure_migration_archive_index(database)
    stats: dict[str, Any] = {
        "copied": 0,
        "moved": 0,
        "identical": 0,
        "conflicts": 0,
        "missing": 0,
        "missing_artifacts": [],
        "missing_artifacts_reviewed": allow_missing,
        "database_records_updated": 0,
    }
    executions = list(
        database["execution_history"].find(
            {"project_id": {"$exists": True}, "chip_id": {"$exists": True}}
        )
    )
    for execution in executions:
        execution_id = execution.get("execution_id")
        username = execution.get("username")
        if not execution_id or not username:
            stats["missing"] += 1
            stats["missing_artifacts"].append(
                {
                    "execution_id": execution_id,
                    "username": username,
                    "status": execution.get("status"),
                    "calib_data_path": execution.get("calib_data_path"),
                    "reason": "missing execution_id or username",
                    "checked_paths": [],
                }
            )
            continue
        try:
            date_str, index = execution_id.split("-", 1)
        except ValueError:
            stats["missing"] += 1
            stats["missing_artifacts"].append(
                {
                    "execution_id": execution_id,
                    "username": username,
                    "status": execution.get("status"),
                    "calib_data_path": execution.get("calib_data_path"),
                    "reason": "invalid execution_id format",
                    "checked_paths": [],
                }
            )
            continue
        legacy_source = base_path / username / date_str / index
        project_chip_path = (
            base_path / "projects" / execution["project_id"] / "chips" / execution["chip_id"]
        )
        flat_source = project_chip_path / "executions" / execution_id
        target = project_chip_path / "executions" / date_str / index
        if execution.get("calib_data_path") == str(target) and target.is_dir():
            continue
        source = flat_source if flat_source.is_dir() else legacy_source
        if not source.is_dir():
            stats["missing"] += 1
            stats["missing_artifacts"].append(
                {
                    "execution_id": execution_id,
                    "username": username,
                    "status": execution.get("status"),
                    "calib_data_path": execution.get("calib_data_path"),
                    "reason": "legacy artifact directory not found",
                    "checked_paths": [str(flat_source), str(legacy_source)],
                }
            )
            continue
        if dry_run:
            if source == flat_source and not target.exists():
                stats["moved"] += 1
            else:
                stats["copied"] += sum(1 for path in source.rglob("*") if path.is_file())
            stats["database_records_updated"] += _migrate_execution_document_paths(
                database,
                execution=execution,
                source=source,
                target=target,
                dry_run=True,
            )
            continue
        if source == flat_source and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
            stats["moved"] += 1
        else:
            copied = _copy_tree_without_overwrite(
                source,
                target,
                target / ".migration_conflicts" / username,
            )
            for key, count in copied.items():
                stats[key] += count
        stats["database_records_updated"] += _migrate_execution_document_paths(
            database,
            execution=execution,
            source=source,
            target=target,
            dry_run=False,
        )

    for chip in database["chip"].find({"project_id": {"$exists": True}}):
        usernames = {chip.get("username")}
        usernames.update(
            database["execution_history"].distinct(
                "username",
                {"project_id": chip["project_id"], "chip_id": chip["chip_id"]},
            )
        )
        target = (
            base_path
            / "projects"
            / chip["project_id"]
            / "chips"
            / chip["chip_id"]
            / "shared"
            / "classifier"
        )
        classifier_stats = _migrate_classifier_files(
            sources={
                username: base_path / username / ".classifier" for username in usernames if username
            },
            target=target,
            dry_run=dry_run,
        )
        for key, count in classifier_stats.items():
            stats[key] += count
    return stats


def run_from_environment(*, dry_run: bool, allow_missing_artifacts: bool = False) -> dict[str, Any]:
    """Run the migration using the same MongoDB environment as QDash."""
    host = os.getenv("MONGO_HOST", "mongo")
    port = 27017 if host == "mongo" else int(os.getenv("MONGO_PORT", "27017"))
    client: MongoClient[Any] = MongoClient(
        host,
        port=port,
        username=os.getenv("MONGO_INITDB_ROOT_USERNAME"),
        password=os.getenv("MONGO_INITDB_ROOT_PASSWORD"),
    )
    try:
        database = client[os.getenv("MONGO_DB_NAME", "qdash")]
        stats = migrate_project_scoped_calibration(database, dry_run=dry_run)
        artifact_ledger = database["migration_ledger"]
        completed_artifact_migration = artifact_ledger.find_one(
            {"migration_id": ARTIFACT_MIGRATION_ID, "status": "completed"}
        )
        if completed_artifact_migration:
            recorded_stats = completed_artifact_migration.get("stats", {})
            if (
                not dry_run
                and allow_missing_artifacts
                and recorded_stats.get("missing")
                and not recorded_stats.get("missing_artifacts_reviewed")
            ):
                artifact_ledger.update_one(
                    {"migration_id": ARTIFACT_MIGRATION_ID},
                    {
                        "$set": {
                            "stats.missing_artifacts_reviewed": True,
                            "missing_artifacts_reviewed_at": datetime.now(timezone.utc),
                        }
                    },
                )
            stats["files"] = {"already_completed": True}
            return stats
        stats["files"] = migrate_calibration_files(
            database,
            base_path=Path(os.getenv("CALIB_DATA_PATH", "/app/calib_data")),
            dry_run=dry_run,
            allow_missing=allow_missing_artifacts,
        )
        if stats["files"]["missing"]:
            logger.warning(
                "Calibration artifact migration completed with %s missing execution(s): %s",
                stats["files"]["missing"],
                stats["files"]["missing_artifacts"],
            )
        if not dry_run:
            artifact_ledger.update_one(
                {"migration_id": ARTIFACT_MIGRATION_ID},
                {
                    "$set": {
                        "status": "completed",
                        "completed_at": datetime.now(timezone.utc),
                        "stats": stats["files"],
                    }
                },
                upsert=True,
            )
        return stats
    finally:
        client.close()
