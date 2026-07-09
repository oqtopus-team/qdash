"""Database migration utilities.

Run migrations with:
    python -m qdash.dbmodel.migration fix-invalid-fidelity          # dry-run
    python -m qdash.dbmodel.migration fix-invalid-fidelity --execute  # execute

    python -m qdash.dbmodel.migration remove-best-data          # dry-run
    python -m qdash.dbmodel.migration remove-best-data --execute  # execute

    python -m qdash.dbmodel.migration rename-database --from qubex --to qdash  # dry-run
    python -m qdash.dbmodel.migration rename-database --from qubex --to qdash --execute

    python -m qdash.dbmodel.migration slim-execution-history          # dry-run
    python -m qdash.dbmodel.migration slim-execution-history --execute  # execute

    python -m qdash.dbmodel.migration remove-node-edge-info          # dry-run
    python -m qdash.dbmodel.migration remove-node-edge-info --execute  # execute

    python -m qdash.dbmodel.migration remove-coupling-from-qubit          # dry-run
    python -m qdash.dbmodel.migration remove-coupling-from-qubit --execute  # execute

    python -m qdash.dbmodel.migration backfill-user-id          # dry-run
    python -m qdash.dbmodel.migration backfill-user-id --execute  # execute

    python -m qdash.dbmodel.migration metric-notes-to-target-notes          # dry-run
    python -m qdash.dbmodel.migration metric-notes-to-target-notes --execute  # execute

    python -m qdash.dbmodel.migration backfill-forum-thread-numbers          # dry-run
    python -m qdash.dbmodel.migration backfill-forum-thread-numbers --execute  # execute

    python -m qdash.dbmodel.migration migrate-forum-status          # dry-run
    python -m qdash.dbmodel.migration migrate-forum-status --execute  # execute
"""

import logging
import os
from typing import Any

from pymongo import MongoClient

logger = logging.getLogger(__name__)

# Constants for migration safety
BATCH_SIZE = 1000  # Process documents in batches for memory efficiency

USER_ID_FIELD_MIGRATIONS = {
    "project": [("owner_username", "owner_user_id")],
    "project_membership": [
        ("username", "user_id"),
        ("invited_by", "invited_by_user_id"),
    ],
    "notification": [
        ("recipient_username", "recipient_user_id"),
        ("actor_username", "actor_user_id"),
    ],
    "note_event": [("actor", "actor_user_id")],
    "cooldown_wiring_event": [("actor", "actor_user_id")],
    "forum_post": [("username", "user_id")],
    "issue": [("username", "user_id")],
    "issue_knowledge": [("reviewed_by", "reviewed_by_user_id")],
    "backend": [("username", "user_id")],
    "task": [("username", "user_id")],
    "tag": [("username", "user_id")],
    "flows": [("username", "user_id")],
    "execution_history": [("username", "user_id")],
    "execution_counter": [("username", "user_id")],
    "chip": [("username", "user_id")],
    "chip_history": [("username", "user_id")],
    "qubit": [("username", "user_id")],
    "qubit_history": [("username", "user_id")],
    "coupling": [("username", "user_id")],
    "coupling_history": [("username", "user_id")],
    "calibration_note": [("username", "user_id")],
    "task_result_history": [
        ("username", "user_id"),
        ("excluded_by", "excluded_by_user_id"),
    ],
}


class MigrationError(Exception):
    """Raised when migration encounters an unrecoverable error."""


MIGRATED_METRIC_NOTES_MARKER = "<!-- qdash:migrated-metric-notes -->"


def _format_migrated_metric_note_section(notes: list[Any]) -> str:
    """Render metric notes as a compact target summary appendix."""
    lines = [MIGRATED_METRIC_NOTES_MARKER, "## Legacy metric notes"]
    for note in notes:
        updated_at = note.note.updated_at.isoformat() if note.note.updated_at else "unknown time"
        updated_by = note.note.updated_by or "unknown user"
        scope = note.scope_key or note.scope_type or "unknown scope"
        content = (note.note.content or "").strip()
        if not content:
            continue
        lines.extend(
            [
                "",
                f"### {note.metric_key}",
                f"- Scope: `{scope}`",
                f"- Last edited: {updated_by} at {updated_at}",
                "",
                content,
            ]
        )
    return "\n".join(lines).strip()


def _merge_migrated_metric_notes(existing_content: str, section: str) -> tuple[str, bool]:
    """Append migrated metric notes unless this target was already migrated."""
    existing_content = (existing_content or "").strip()
    if not section or MIGRATED_METRIC_NOTES_MARKER in existing_content:
        return existing_content, False
    if not existing_content:
        return section, True
    return f"{existing_content}\n\n---\n\n{section}", True


def migrate_metric_notes_to_target_notes(dry_run: bool = True) -> dict[str, Any]:
    """Copy existing per-metric dashboard notes into target-level pinned summaries.

    The source ``MetricNoteDocument`` rows are preserved. Each target receives one
    appended "Migrated metric notes" section in ``QubitDocument.note`` or
    ``CouplingDocument.note``. The marker keeps the migration idempotent.
    """
    from qdash.common.utils.datetime import now
    from qdash.datamodel.note import NoteModel
    from qdash.dbmodel.coupling import CouplingDocument
    from qdash.dbmodel.metric_note import MetricNoteDocument
    from qdash.dbmodel.qubit import QubitDocument

    metric_notes = [
        note
        for note in MetricNoteDocument.find_all().run()
        if getattr(note, "note", None) is not None and (note.note.content or "").strip()
    ]
    grouped: dict[tuple[str, str, str, str], list[Any]] = {}
    for note in metric_notes:
        key = (note.project_id, note.chip_id, note.target_type, note.target_id)
        grouped.setdefault(key, []).append(note)

    stats: dict[str, Any] = {
        "metric_notes_found": len(metric_notes),
        "targets_found": len(grouped),
        "targets_updated": 0,
        "targets_skipped_already_migrated": 0,
        "targets_missing": 0,
        "targets": [],
    }

    for (project_id, chip_id, target_type, target_id), notes in sorted(grouped.items()):
        notes.sort(
            key=lambda item: (
                item.metric_key,
                item.scope_key,
                item.note.updated_at.isoformat() if item.note.updated_at else "",
            )
        )
        model = QubitDocument if target_type == "qubit" else CouplingDocument
        target_doc = model.find_one(
            model.project_id == project_id,
            model.chip_id == chip_id,
            model.qid == target_id,
        ).run()
        target_info = {
            "project_id": project_id,
            "chip_id": chip_id,
            "target_type": target_type,
            "target_id": target_id,
            "metric_note_count": len(notes),
            "action": "dry_run" if dry_run else "updated",
        }
        if target_doc is None:
            stats["targets_missing"] += 1
            target_info["action"] = "missing_target"
            stats["targets"].append(target_info)
            continue

        existing_note = getattr(target_doc, "note", NoteModel()) or NoteModel()
        section = _format_migrated_metric_note_section(notes)
        merged_content, changed = _merge_migrated_metric_notes(existing_note.content, section)
        if not changed:
            stats["targets_skipped_already_migrated"] += 1
            target_info["action"] = "already_migrated"
            stats["targets"].append(target_info)
            continue

        if not dry_run:
            last_note = max(
                notes,
                key=lambda item: item.note.updated_at or item.system_info.updated_at,
            )
            target_doc.note = NoteModel(
                content=merged_content,
                updated_by=last_note.note.updated_by or "migration",
                updated_at=last_note.note.updated_at or now(),
            )
            target_doc.system_info.update_time()
            target_doc.save()
        stats["targets_updated"] += 1
        stats["targets"].append(target_info)

    return stats


def migrate_backfill_forum_thread_numbers(dry_run: bool = True) -> dict[str, Any]:
    """Backfill project-scoped forum thread numbers for existing posts.

    Root threads receive stable ``#N`` numbers within each project. Replies share
    their root thread number so API responses can display a single discussion ID.
    Existing numbers are preserved and deleted root threads are included to avoid
    future number reuse.
    """
    from qdash.dbmodel.forum import ForumCounterDocument, ForumPostDocument

    collection = ForumPostDocument.get_motor_collection()
    counter_collection = ForumCounterDocument.get_motor_collection()
    project_ids = sorted(
        project_id
        for project_id in collection.distinct("project_id", {"parent_id": None})
        if isinstance(project_id, str) and project_id
    )
    stats: dict[str, Any] = {
        "projects_found": len(project_ids),
        "root_threads_missing_number": 0,
        "root_threads_updated": 0,
        "replies_updated": 0,
        "orphan_replies_found": 0,
        "duplicate_root_numbers": {},
        "counters_updated": 0,
        "projects": [],
    }

    for project_id in project_ids:
        roots = list(
            collection.find({"project_id": project_id, "parent_id": None}).sort(
                [("system_info.created_at", 1), ("_id", 1)]
            )
        )
        root_ids = {str(root["_id"]) for root in roots}
        existing_numbers: dict[int, list[str]] = {}
        for root in roots:
            current_number = root.get("number")
            if isinstance(current_number, int) and current_number > 0:
                existing_numbers.setdefault(current_number, []).append(str(root["_id"]))

        duplicate_numbers = {
            str(number): ids for number, ids in existing_numbers.items() if len(ids) > 1
        }
        if duplicate_numbers:
            stats["duplicate_root_numbers"][project_id] = duplicate_numbers
            if not dry_run:
                raise MigrationError(
                    "Duplicate forum root thread numbers already exist for "
                    f"project {project_id}: {duplicate_numbers}"
                )

        used_numbers = set(existing_numbers)
        next_number = 1
        assignments: list[tuple[Any, int]] = []
        root_number_by_id: dict[str, int] = {}
        for root in roots:
            current_number = root.get("number")
            if isinstance(current_number, int) and current_number > 0:
                root_number = current_number
            else:
                while next_number in used_numbers:
                    next_number += 1
                root_number = next_number
                used_numbers.add(root_number)
                assignments.append((root["_id"], root_number))
                next_number += 1
            root_number_by_id[str(root["_id"])] = root_number

        reply_updates = 0
        for root_id, root_number in root_number_by_id.items():
            reply_filter = {
                "project_id": project_id,
                "parent_id": root_id,
                "$or": [
                    {"number": {"$exists": False}},
                    {"number": None},
                    {"number": {"$ne": root_number}},
                ],
            }
            if dry_run:
                reply_updates += collection.count_documents(reply_filter)
            else:
                result = collection.update_many(reply_filter, {"$set": {"number": root_number}})
                reply_updates += result.modified_count

        orphan_reply_filter = {
            "project_id": project_id,
            "parent_id": {"$nin": [None, *root_ids]},
            "is_deleted": False,
        }
        orphan_replies = collection.count_documents(orphan_reply_filter)
        stats["orphan_replies_found"] += orphan_replies

        max_number = max(used_numbers) if used_numbers else 0
        current_counter = counter_collection.find_one({"project_id": project_id})
        current_counter_value = (
            int(current_counter.get("value") or 0) if isinstance(current_counter, dict) else 0
        )
        counter_value = max(max_number, current_counter_value)
        project_info = {
            "project_id": project_id,
            "root_threads": len(roots),
            "root_threads_missing_number": len(assignments),
            "replies_to_update": reply_updates,
            "orphan_replies": orphan_replies,
            "duplicate_root_numbers": duplicate_numbers,
            "max_number": max_number,
            "counter_value": counter_value,
            "action": "blocked_duplicate_numbers"
            if duplicate_numbers
            else ("dry_run" if dry_run else "updated"),
        }
        stats["root_threads_missing_number"] += len(assignments)
        stats["replies_updated"] += reply_updates

        if not dry_run:
            for root_id, root_number in assignments:
                result = collection.update_one({"_id": root_id}, {"$set": {"number": root_number}})
                stats["root_threads_updated"] += result.modified_count
            counter_collection.update_one(
                {"project_id": project_id},
                {"$max": {"value": counter_value}, "$setOnInsert": {"project_id": project_id}},
                upsert=True,
            )
            stats["counters_updated"] += 1

        stats["projects"].append(project_info)

    logger.info("Forum thread number migration: %s", stats)
    return stats


def migrate_forum_status(dry_run: bool = True) -> dict[str, Any]:
    """Migrate forum threads from ``is_closed`` and legacy labels to ``status``.

    The forum workflow now uses a dedicated status field. Existing closed
    threads and threads with a ``resolved`` label become ``status=resolved``.
    Legacy topic labels are collapsed to a small allowed set:
    ``discussion``/``info``/``mtg`` become ``review`` and ``resolved`` is removed.
    The deprecated ``is_closed`` field is unset when executing the migration.
    """
    from qdash.dbmodel.forum import FORUM_THREAD_STATUSES, ForumPostDocument

    allowed_labels = {"review", "anomaly"}
    label_aliases = {"discussion": "review", "info": "review", "mtg": "review"}
    collection = ForumPostDocument.get_motor_collection()
    docs = list(collection.find({}))
    stats: dict[str, Any] = {
        "posts_found": len(docs),
        "posts_to_update": 0,
        "status_from_is_closed": 0,
        "status_from_resolved_label": 0,
        "status_defaulted_open": 0,
        "labels_changed": 0,
        "is_closed_removed": 0,
    }

    for doc in docs:
        current_status = doc.get("status")
        labels = doc.get("labels") if isinstance(doc.get("labels"), list) else []
        normalized_labels: list[str] = []
        has_resolved_label = False
        labels_changed = False

        for raw_label in labels:
            if not isinstance(raw_label, str):
                labels_changed = True
                continue
            label = raw_label.strip().lower()
            if label == "resolved":
                has_resolved_label = True
                labels_changed = True
                continue
            label = label_aliases.get(label, label)
            if label not in allowed_labels:
                label = "review"
                labels_changed = True
            if label not in normalized_labels:
                normalized_labels.append(label)
            if label != raw_label:
                labels_changed = True

        if len(normalized_labels) > 1:
            normalized_labels = normalized_labels[:1]
            labels_changed = True

        next_status = current_status if current_status in FORUM_THREAD_STATUSES else None
        if has_resolved_label:
            if next_status != "resolved":
                stats["status_from_resolved_label"] += 1
            next_status = "resolved"
        elif doc.get("is_closed") is True:
            if next_status != "resolved":
                stats["status_from_is_closed"] += 1
            next_status = "resolved"
        elif next_status is None:
            next_status = "open"
            stats["status_defaulted_open"] += 1

        update: dict[str, Any] = {}
        unset: dict[str, str] = {}
        if current_status != next_status:
            update["status"] = next_status
        if labels_changed or labels != normalized_labels:
            update["labels"] = normalized_labels
            stats["labels_changed"] += 1
        if "is_closed" in doc:
            unset["is_closed"] = ""
            stats["is_closed_removed"] += 1

        if update or unset:
            stats["posts_to_update"] += 1
            if not dry_run:
                operation: dict[str, Any] = {}
                if update:
                    operation["$set"] = update
                if unset:
                    operation["$unset"] = unset
                collection.update_one({"_id": doc["_id"]}, operation)

    logger.info("Forum status migration: %s", stats)
    return stats


def migrate_backfill_user_id(dry_run: bool = True) -> dict[str, Any]:
    """Backfill opaque user IDs and relationship user_id fields.

    Existing username fields are retained as login/display snapshots. This migration
    adds user_id values to users and denormalized relationship fields so application
    code can use user_id for identity while preserving backwards-compatible display.
    """
    from qdash.datamodel.user import generate_user_id
    from qdash.dbmodel.user import UserDocument

    user_collection = UserDocument.get_motor_collection()
    stats: dict[str, Any] = {
        "users_without_user_id": 0,
        "users_updated": 0,
        "collections": {},
        "unresolved": {},
    }

    missing_user_filter: dict[str, Any] = {
        "$or": [{"user_id": {"$exists": False}}, {"user_id": None}, {"user_id": ""}]
    }
    users_without_user_id = list(user_collection.find(missing_user_filter, {"username": 1}))
    stats["users_without_user_id"] = len(users_without_user_id)

    if users_without_user_id:
        logger.info("Found %s users without user_id", len(users_without_user_id))
    generated_user_ids = {
        user["username"]: generate_user_id()
        for user in users_without_user_id
        if isinstance(user.get("username"), str) and user.get("username")
    }
    if not dry_run:
        for user in users_without_user_id:
            user_id = generated_user_ids.get(user.get("username"))
            if user_id is None:
                continue
            result = user_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"user_id": user_id}},
            )
            stats["users_updated"] += result.modified_count

    username_to_user_id = {
        user["username"]: user["user_id"]
        for user in user_collection.find(
            {
                "username": {"$type": "string"},
                "user_id": {"$type": "string"},
            },
            {"username": 1, "user_id": 1},
        )
    }
    username_to_user_id.update(generated_user_ids)

    database = user_collection.database
    for collection_name, field_pairs in USER_ID_FIELD_MIGRATIONS.items():
        collection = database[collection_name]
        collection_stats = {"matched": 0, "updated": 0}
        unresolved: dict[str, int] = {}

        for username_field, user_id_field in field_pairs:
            query = {
                username_field: {"$type": "string", "$ne": ""},
                "$or": [
                    {user_id_field: {"$exists": False}},
                    {user_id_field: None},
                    {user_id_field: ""},
                ],
            }
            docs = list(collection.find(query, {username_field: 1}))
            collection_stats["matched"] += len(docs)
            for doc in docs:
                username = doc.get(username_field)
                user_id = username_to_user_id.get(username)
                if not user_id:
                    unresolved[username] = unresolved.get(username, 0) + 1
                    continue
                if not dry_run:
                    result = collection.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {user_id_field: user_id}},
                    )
                    collection_stats["updated"] += result.modified_count

        stats["collections"][collection_name] = collection_stats
        if unresolved:
            stats["unresolved"][collection_name] = unresolved
            logger.warning("Unresolved user references in %s: %s", collection_name, unresolved)

    prefix = "[DRY RUN] Would backfill" if dry_run else "Backfilled"
    logger.info("%s user_id fields: %s", prefix, stats)
    return stats


def migrate_fix_invalid_fidelity(dry_run: bool = True) -> dict[str, Any]:
    """Mark task results with fidelity > 100% as failed.

    Fidelity values exceeding 100% (1.0) indicate measurement or calculation
    errors. This migration finds such records and updates their status to
    'failed' with an appropriate message.

    Args:
        dry_run: If True, only reports what would be changed.

    Returns:
        Migration statistics with counts of affected documents.
    """
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    stats: dict[str, Any] = {
        "total_checked": 0,
        "invalid_found": 0,
        "updated": 0,
        "details": [],
    }

    collection = TaskResultHistoryDocument.get_motor_collection()

    # Find all completed tasks that have fidelity-related output parameters
    # We need to check each document's output_parameters for fidelity > 1.0
    filter_query: dict[str, Any] = {"status": "completed"}

    cursor = collection.find(filter_query)
    invalid_docs: list[dict[str, Any]] = []

    for doc in cursor:
        stats["total_checked"] += 1
        output_params = doc.get("output_parameters", {})

        if not output_params:
            continue

        # Check all parameters containing 'fidelity' in their name
        invalid_params: list[tuple[str, float]] = []
        for param_name, param_data in output_params.items():
            if "fidelity" not in param_name.lower():
                continue

            # Handle both dict format and direct value
            if isinstance(param_data, dict):
                value = param_data.get("value")
            else:
                value = param_data

            if value is not None and isinstance(value, (int, float)) and value > 1.0:
                invalid_params.append((param_name, float(value)))

        if invalid_params:
            invalid_docs.append(
                {
                    "_id": doc["_id"],
                    "task_id": doc.get("task_id", ""),
                    "name": doc.get("name", ""),
                    "qid": doc.get("qid", ""),
                    "invalid_params": invalid_params,
                }
            )

    stats["invalid_found"] = len(invalid_docs)

    if invalid_docs:
        logger.info(f"Found {len(invalid_docs)} documents with invalid fidelity values:")
        for doc_info in invalid_docs[:10]:  # Show first 10
            params_str = ", ".join(
                f"{name}={value * 100:.2f}%" for name, value in doc_info["invalid_params"]
            )
            logger.info(f"  - {doc_info['name']} (qid={doc_info['qid']}): {params_str}")
            stats["details"].append(
                {
                    "task_id": doc_info["task_id"],
                    "name": doc_info["name"],
                    "qid": doc_info["qid"],
                    "invalid_params": {
                        name: f"{value * 100:.2f}%" for name, value in doc_info["invalid_params"]
                    },
                }
            )

        if len(invalid_docs) > 10:
            logger.info(f"  ... and {len(invalid_docs) - 10} more")

    if not dry_run and invalid_docs:
        for doc_info in invalid_docs:
            params_str = ", ".join(
                f"{name}={value * 100:.2f}%" for name, value in doc_info["invalid_params"]
            )
            message = f"Fidelity exceeds 100%: {params_str}"

            result = collection.update_one(
                {"_id": doc_info["_id"]},
                {
                    "$set": {
                        "status": "failed",
                        "message": message,
                    }
                },
            )
            if result.modified_count > 0:
                stats["updated"] += 1

        logger.info(f"Updated {stats['updated']} documents to status='failed'")

    prefix = "[DRY RUN] Would update" if dry_run else "Updated"
    logger.info(f"{prefix} {stats['invalid_found']} documents with invalid fidelity values")

    return stats


def migrate_remove_best_data(dry_run: bool = True) -> dict[str, int]:
    """Remove best_data field from qubit and coupling collections.

    The best_data field is no longer used as metrics are now calculated
    on-demand at retrieval time instead of being stored.

    Args:
        dry_run: If True, only reports what would be changed.

    Returns:
        Migration statistics with counts of affected documents.
    """
    from qdash.dbmodel.coupling import CouplingDocument
    from qdash.dbmodel.coupling_history import CouplingHistoryDocument
    from qdash.dbmodel.qubit import QubitDocument
    from qdash.dbmodel.qubit_history import QubitHistoryDocument

    stats: dict[str, int] = {
        "qubit": 0,
        "qubit_history": 0,
        "coupling": 0,
        "coupling_history": 0,
    }

    # Field to remove
    fields_to_unset = {"best_data": ""}
    filter_query: dict[str, Any] = {"best_data": {"$exists": True}}

    # Migrate QubitDocument
    collection = QubitDocument.get_motor_collection()
    count = collection.count_documents(filter_query)
    stats["qubit"] = count
    logger.info(f"Found {count} qubit documents with best_data")

    if not dry_run and count > 0:
        result = collection.update_many(filter_query, {"$unset": fields_to_unset})
        logger.info(f"Updated {result.modified_count} qubit documents")

    # Migrate QubitHistoryDocument
    collection = QubitHistoryDocument.get_motor_collection()
    count = collection.count_documents(filter_query)
    stats["qubit_history"] = count
    logger.info(f"Found {count} qubit_history documents with best_data")

    if not dry_run and count > 0:
        result = collection.update_many(filter_query, {"$unset": fields_to_unset})
        logger.info(f"Updated {result.modified_count} qubit_history documents")

    # Migrate CouplingDocument
    collection = CouplingDocument.get_motor_collection()
    count = collection.count_documents(filter_query)
    stats["coupling"] = count
    logger.info(f"Found {count} coupling documents with best_data")

    if not dry_run and count > 0:
        result = collection.update_many(filter_query, {"$unset": fields_to_unset})
        logger.info(f"Updated {result.modified_count} coupling documents")

    # Migrate CouplingHistoryDocument
    collection = CouplingHistoryDocument.get_motor_collection()
    count = collection.count_documents(filter_query)
    stats["coupling_history"] = count
    logger.info(f"Found {count} coupling_history documents with best_data")

    if not dry_run and count > 0:
        result = collection.update_many(filter_query, {"$unset": fields_to_unset})
        logger.info(f"Updated {result.modified_count} coupling_history documents")

    prefix = "[DRY RUN] Would update" if dry_run else "Updated"
    logger.info(f"{prefix} documents: {stats}")
    return stats


def migrate_slim_execution_history(dry_run: bool = True) -> dict[str, Any]:
    """Remove task_results and calib_data fields from execution_history collection.

    These fields are no longer stored in execution_history:
    - task_results: Now stored in task_result_history collection
    - calib_data: Now stored in qubit/coupling collections

    This migration removes these deprecated fields to reduce document size,
    which is critical for supporting 256+ qubit systems (avoiding MongoDB's
    16MB document limit).

    Args:
        dry_run: If True, only reports what would be changed.

    Returns:
        Migration statistics with counts of affected documents and size savings.

    Raises:
        ConnectionError: If database connection cannot be established.
        RuntimeError: If database is not properly initialized.
    """
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

    from qdash.dbmodel.execution_history import ExecutionHistoryDocument

    stats: dict[str, Any] = {
        "total_documents": 0,
        "with_task_results": 0,
        "with_calib_data": 0,
        "updated": 0,
        "estimated_size_saved_mb": 0.0,
    }

    collection = ExecutionHistoryDocument.get_motor_collection()

    # Verify database connection health
    try:
        # This will raise an exception if the connection is unhealthy
        collection.database.command("ping")
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        raise ConnectionError(f"Failed to connect to MongoDB: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Database health check failed: {e}") from e

    # Count total documents
    stats["total_documents"] = collection.count_documents({})
    logger.info(f"Total execution_history documents: {stats['total_documents']}")

    # Find documents with task_results field
    task_results_query: dict[str, Any] = {"task_results": {"$exists": True, "$ne": {}}}
    stats["with_task_results"] = collection.count_documents(task_results_query)
    logger.info(f"Documents with task_results: {stats['with_task_results']}")

    # Find documents with calib_data field
    calib_data_query: dict[str, Any] = {"calib_data": {"$exists": True, "$ne": {}}}
    stats["with_calib_data"] = collection.count_documents(calib_data_query)
    logger.info(f"Documents with calib_data: {stats['with_calib_data']}")

    # Estimate size savings by sampling a few documents
    if stats["with_task_results"] > 0 or stats["with_calib_data"] > 0:
        sample_query: dict[str, Any] = {
            "$or": [
                {"task_results": {"$exists": True, "$ne": {}}},
                {"calib_data": {"$exists": True, "$ne": {}}},
            ]
        }
        sample_docs = list(collection.find(sample_query).limit(10))
        if sample_docs:
            import json

            total_field_size = 0
            for doc in sample_docs:
                if task_results := doc.get("task_results"):
                    total_field_size += len(json.dumps(task_results, default=str))
                if calib_data := doc.get("calib_data"):
                    total_field_size += len(json.dumps(calib_data, default=str))
            avg_size = total_field_size / len(sample_docs)
            affected_docs = max(stats["with_task_results"], stats["with_calib_data"])
            stats["estimated_size_saved_mb"] = round((avg_size * affected_docs) / (1024 * 1024), 2)
            logger.info(f"Estimated size savings: ~{stats['estimated_size_saved_mb']} MB")

    # Perform the migration
    if not dry_run:
        # Remove both fields in a single update operation
        update_query: dict[str, Any] = {
            "$or": [
                {"task_results": {"$exists": True}},
                {"calib_data": {"$exists": True}},
            ]
        }
        result = collection.update_many(
            update_query,
            {"$unset": {"task_results": "", "calib_data": ""}},
        )
        stats["updated"] = result.modified_count
        logger.info(f"Updated {stats['updated']} documents")

    prefix = "[DRY RUN] Would remove" if dry_run else "Removed"
    logger.info(
        f"{prefix} task_results and calib_data from execution_history. "
        f"Affected: {max(stats['with_task_results'], stats['with_calib_data'])} documents"
    )

    return stats


def migrate_remove_node_edge_info(dry_run: bool = True) -> dict[str, int]:
    """Remove deprecated node_info and edge_info fields from collections.

    These fields were used for UI visualization but are no longer needed:
    - node_info: Removed from qubit and qubit_history collections
    - edge_info: Removed from coupling and coupling_history collections

    Args:
        dry_run: If True, only reports what would be changed.

    Returns:
        Migration statistics with counts of affected documents.
    """
    from qdash.dbmodel.coupling import CouplingDocument
    from qdash.dbmodel.coupling_history import CouplingHistoryDocument
    from qdash.dbmodel.qubit import QubitDocument
    from qdash.dbmodel.qubit_history import QubitHistoryDocument

    stats: dict[str, int] = {
        "qubit": 0,
        "qubit_history": 0,
        "coupling": 0,
        "coupling_history": 0,
    }

    # Remove node_info from QubitDocument
    collection = QubitDocument.get_motor_collection()
    filter_query: dict[str, Any] = {"node_info": {"$exists": True}}
    count = collection.count_documents(filter_query)
    stats["qubit"] = count
    logger.info(f"Found {count} qubit documents with node_info")

    if not dry_run and count > 0:
        result = collection.update_many(filter_query, {"$unset": {"node_info": ""}})
        logger.info(f"Updated {result.modified_count} qubit documents")

    # Remove node_info from QubitHistoryDocument
    collection = QubitHistoryDocument.get_motor_collection()
    count = collection.count_documents(filter_query)
    stats["qubit_history"] = count
    logger.info(f"Found {count} qubit_history documents with node_info")

    if not dry_run and count > 0:
        result = collection.update_many(filter_query, {"$unset": {"node_info": ""}})
        logger.info(f"Updated {result.modified_count} qubit_history documents")

    # Remove edge_info from CouplingDocument
    collection = CouplingDocument.get_motor_collection()
    filter_query = {"edge_info": {"$exists": True}}
    count = collection.count_documents(filter_query)
    stats["coupling"] = count
    logger.info(f"Found {count} coupling documents with edge_info")

    if not dry_run and count > 0:
        result = collection.update_many(filter_query, {"$unset": {"edge_info": ""}})
        logger.info(f"Updated {result.modified_count} coupling documents")

    # Remove edge_info from CouplingHistoryDocument
    collection = CouplingHistoryDocument.get_motor_collection()
    count = collection.count_documents(filter_query)
    stats["coupling_history"] = count
    logger.info(f"Found {count} coupling_history documents with edge_info")

    if not dry_run and count > 0:
        result = collection.update_many(filter_query, {"$unset": {"edge_info": ""}})
        logger.info(f"Updated {result.modified_count} coupling_history documents")

    prefix = "[DRY RUN] Would update" if dry_run else "Updated"
    logger.info(f"{prefix} documents: {stats}")
    return stats


def migrate_remove_coupling_from_qubit(dry_run: bool = True) -> dict[str, Any]:
    """Remove invalid QubitDocuments created by the seed import bug.

    Due to a bug in SeedImportService, two types of invalid QubitDocuments
    were created:

    1. Coupling-format qids (e.g. "024-Q025", "059-Q062") from coupling
       parameter YAML files were saved as QubitDocument instead of being
       skipped.
    2. Zero-padded duplicate qids (e.g. "000", "001") were created alongside
       the correct non-padded qids (e.g. "0", "1") because the seed import
       normalized "Q000" to "000" which didn't match the existing "0".

    Valid qubit qids are non-padded numeric strings: "0", "1", ..., "143".
    This migration deletes entries matching either invalid pattern.

    Args:
        dry_run: If True, only reports what would be deleted.

    Returns:
        Migration statistics with counts of affected documents.
    """
    from qdash.dbmodel.qubit import QubitDocument

    stats: dict[str, Any] = {
        "total_qubit_documents": 0,
        "coupling_qids": 0,
        "zero_padded_duplicates": 0,
        "total_invalid": 0,
        "deleted": 0,
        "sample_coupling_qids": [],
        "sample_padded_qids": [],
    }

    collection = QubitDocument.get_motor_collection()

    stats["total_qubit_documents"] = collection.count_documents({})

    # 1. Find coupling-format qids (containing "-")
    coupling_filter: dict[str, Any] = {"qid": {"$regex": "-"}}
    stats["coupling_qids"] = collection.count_documents(coupling_filter)

    if stats["coupling_qids"] > 0:
        sample_docs = list(collection.find(coupling_filter, {"qid": 1, "chip_id": 1}).limit(10))
        stats["sample_coupling_qids"] = [
            {"qid": doc["qid"], "chip_id": doc.get("chip_id", "")} for doc in sample_docs
        ]
        logger.info(f"Coupling qids found: {stats['coupling_qids']}")
        for item in stats["sample_coupling_qids"]:
            logger.info(f"  - chip_id={item['chip_id']}, qid={item['qid']}")

    # 2. Find zero-padded duplicate qids (e.g. "000", "001", "023")
    #    Valid qids are: "0" through "N" (no leading zeros except "0" itself)
    #    Invalid: any pure-numeric qid starting with "0" that has length >= 2
    #    Exclude coupling qids (already counted above)
    padded_filter: dict[str, Any] = {
        "qid": {"$regex": "^0\\d+$"},  # anchored: pure-numeric, no "-"
    }
    stats["zero_padded_duplicates"] = collection.count_documents(padded_filter)

    if stats["zero_padded_duplicates"] > 0:
        sample_docs = list(collection.find(padded_filter, {"qid": 1, "chip_id": 1}).limit(10))
        stats["sample_padded_qids"] = [
            {"qid": doc["qid"], "chip_id": doc.get("chip_id", "")} for doc in sample_docs
        ]
        logger.info(f"Zero-padded duplicate qids found: {stats['zero_padded_duplicates']}")
        for item in stats["sample_padded_qids"]:
            logger.info(f"  - chip_id={item['chip_id']}, qid={item['qid']}")

    # Use $or for the actual delete, and count the union to get accurate total
    combined_filter: dict[str, Any] = {
        "$or": [coupling_filter, padded_filter],
    }
    stats["total_invalid"] = collection.count_documents(combined_filter)

    logger.info(
        f"Total QubitDocuments: {stats['total_qubit_documents']}, "
        f"invalid: {stats['total_invalid']} "
        f"(coupling={stats['coupling_qids']}, zero-padded={stats['zero_padded_duplicates']}), "
        f"valid after cleanup: {stats['total_qubit_documents'] - stats['total_invalid']}"
    )

    if not dry_run and stats["total_invalid"] > 0:
        result = collection.delete_many(combined_filter)
        stats["deleted"] = result.deleted_count
        logger.info(f"Deleted {stats['deleted']} invalid QubitDocuments")

    prefix = "[DRY RUN] Would delete" if dry_run else "Deleted"
    logger.info(f"{prefix} {stats['total_invalid']} invalid entries from QubitDocument collection")

    return stats


def _get_mongo_client() -> MongoClient[Any]:
    """Get MongoDB client for migration."""
    return MongoClient(
        os.getenv("MONGO_HOST", "mongo"),
        port=27017,
        username=os.getenv("MONGO_INITDB_ROOT_USERNAME"),
        password=os.getenv("MONGO_INITDB_ROOT_PASSWORD"),
    )


def migrate_rename_database(
    source_db: str,
    target_db: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Copy all collections from source database to target database.

    This migration copies all data from the source database to the target database.
    After successful migration, you should:
    1. Update MONGO_DB_NAME environment variable to the new database name
    2. Restart services
    3. Verify the application works correctly
    4. Optionally drop the old database

    Args:
        source_db: Source database name (e.g., 'qubex')
        target_db: Target database name (e.g., 'qdash')
        dry_run: If True, only reports what would be done

    Returns:
        Migration statistics with document counts per collection

    Raises:
        MigrationError: If source database doesn't exist or target already has data
    """
    client = _get_mongo_client()

    # Verify source database exists
    db_names = client.list_database_names()
    if source_db not in db_names:
        raise MigrationError(f"Source database '{source_db}' does not exist")

    source = client[source_db]
    target = client[target_db]

    # Get all collections (excluding system collections)
    collections = [c for c in source.list_collection_names() if not c.startswith("system.")]

    if not collections:
        logger.warning(f"No collections found in source database '{source_db}'")
        return {"collections": 0, "documents": 0}

    # Check if target database already has data
    target_collections = target.list_collection_names()
    if target_collections and not dry_run:
        existing = [c for c in target_collections if not c.startswith("system.")]
        if existing:
            logger.warning(
                f"Target database '{target_db}' already has collections: {existing}. "
                "Data will be merged/overwritten."
            )

    stats: dict[str, Any] = {
        "source_db": source_db,
        "target_db": target_db,
        "collections": {},
        "total_documents": 0,
    }

    for collection_name in collections:
        source_col = source[collection_name]
        doc_count = source_col.count_documents({})
        stats["collections"][collection_name] = doc_count
        stats["total_documents"] += doc_count

        logger.info(f"Collection '{collection_name}': {doc_count} documents")

        if not dry_run and doc_count > 0:
            target_col = target[collection_name]

            # Copy indexes first
            indexes = list(source_col.list_indexes())
            for index in indexes:
                if index["name"] != "_id_":  # Skip default _id index
                    try:
                        keys = list(index["key"].items())
                        options = {k: v for k, v in index.items() if k not in ("key", "v", "ns")}
                        target_col.create_index(keys, **options)
                        logger.debug(f"  Created index: {index['name']}")
                    except Exception as e:
                        logger.warning(f"  Failed to create index {index['name']}: {e}")

            # Copy documents in batches
            copied = 0
            cursor = source_col.find({})
            batch: list[dict[str, Any]] = []

            for doc in cursor:
                batch.append(doc)
                if len(batch) >= BATCH_SIZE:
                    target_col.insert_many(batch, ordered=False)
                    copied += len(batch)
                    batch = []
                    logger.debug(f"  Copied {copied}/{doc_count} documents")

            # Insert remaining documents
            if batch:
                target_col.insert_many(batch, ordered=False)
                copied += len(batch)

            logger.info(f"  Copied {copied} documents to '{target_db}.{collection_name}'")

    if dry_run:
        logger.info(
            f"[DRY RUN] Would copy {len(collections)} collections "
            f"({stats['total_documents']} documents) from '{source_db}' to '{target_db}'"
        )
    else:
        logger.info(
            f"Successfully copied {len(collections)} collections "
            f"({stats['total_documents']} documents) from '{source_db}' to '{target_db}'"
        )
        logger.info(
            f"\nNext steps:\n"
            f"  1. Update MONGO_DB_NAME={target_db} in .env\n"
            f"  2. Restart services: docker compose restart\n"
            f"  3. Verify the application works correctly\n"
            f"  4. (Optional) Drop old database: db.dropDatabase() on '{source_db}'"
        )

    return stats


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Database migrations")
    subparsers = parser.add_subparsers(dest="command", help="Migration commands")

    # fix-invalid-fidelity migration
    fix_fidelity_parser = subparsers.add_parser(
        "fix-invalid-fidelity",
        help="Mark task results with fidelity > 100% as failed",
    )
    fix_fidelity_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (default is dry-run)",
    )

    # remove-best-data migration
    remove_best_data_parser = subparsers.add_parser(
        "remove-best-data",
        help="Remove best_data field from qubit and coupling collections",
    )
    remove_best_data_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (default is dry-run)",
    )

    # rename-database migration
    rename_db_parser = subparsers.add_parser(
        "rename-database",
        help="Copy all collections from source database to target database",
    )
    rename_db_parser.add_argument(
        "--from",
        dest="source_db",
        required=True,
        help="Source database name (e.g., 'qubex')",
    )
    rename_db_parser.add_argument(
        "--to",
        dest="target_db",
        required=True,
        help="Target database name (e.g., 'qdash')",
    )
    rename_db_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (default is dry-run)",
    )

    # slim-execution-history migration
    slim_history_parser = subparsers.add_parser(
        "slim-execution-history",
        help="Remove task_results and calib_data from execution_history (for 256+ qubit support)",
    )
    slim_history_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (default is dry-run)",
    )

    # remove-node-edge-info migration
    remove_node_edge_parser = subparsers.add_parser(
        "remove-node-edge-info",
        help="Remove deprecated node_info and edge_info fields from qubit/coupling collections",
    )
    remove_node_edge_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (default is dry-run)",
    )

    # remove-coupling-from-qubit migration
    remove_coupling_parser = subparsers.add_parser(
        "remove-coupling-from-qubit",
        help="Remove coupling data incorrectly stored as QubitDocument (seed import bug fix)",
    )
    remove_coupling_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (default is dry-run)",
    )

    # backfill-user-id migration
    backfill_user_id_parser = subparsers.add_parser(
        "backfill-user-id",
        help="Backfill user.user_id and denormalized relationship user_id fields",
    )
    backfill_user_id_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (default is dry-run)",
    )

    metric_notes_parser = subparsers.add_parser(
        "metric-notes-to-target-notes",
        help="Append existing per-metric dashboard notes to target-level pinned summaries",
    )
    metric_notes_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (default is dry-run)",
    )

    forum_numbers_parser = subparsers.add_parser(
        "backfill-forum-thread-numbers",
        help="Backfill project-scoped #numbers for existing forum threads",
    )
    forum_numbers_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (default is dry-run)",
    )

    forum_status_parser = subparsers.add_parser(
        "migrate-forum-status",
        help="Migrate forum is_closed and legacy labels to status",
    )
    forum_status_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (default is dry-run)",
    )

    args = parser.parse_args()

    if args.command == "fix-invalid-fidelity":
        from qdash.dbmodel.initialize import initialize

        initialize()
        stats = migrate_fix_invalid_fidelity(dry_run=not args.execute)
        logger.info(f"Migration complete: {stats}")
    elif args.command == "remove-best-data":
        from qdash.dbmodel.initialize import initialize

        initialize()
        stats = migrate_remove_best_data(dry_run=not args.execute)
        logger.info(f"Migration complete: {stats}")
    elif args.command == "rename-database":
        stats = migrate_rename_database(
            source_db=args.source_db,
            target_db=args.target_db,
            dry_run=not args.execute,
        )
        logger.info(f"Migration complete: {stats}")
    elif args.command == "slim-execution-history":
        from qdash.dbmodel.initialize import initialize

        initialize()
        stats = migrate_slim_execution_history(dry_run=not args.execute)
        logger.info(f"Migration complete: {stats}")
    elif args.command == "remove-node-edge-info":
        from qdash.dbmodel.initialize import initialize

        initialize()
        stats = migrate_remove_node_edge_info(dry_run=not args.execute)
        logger.info(f"Migration complete: {stats}")
    elif args.command == "remove-coupling-from-qubit":
        from qdash.dbmodel.initialize import initialize

        initialize()
        stats = migrate_remove_coupling_from_qubit(dry_run=not args.execute)
        logger.info(f"Migration complete: {stats}")
    elif args.command == "backfill-user-id":
        from qdash.dbmodel.initialize import initialize

        initialize()
        stats = migrate_backfill_user_id(dry_run=not args.execute)
        logger.info(f"Migration complete: {stats}")
    elif args.command == "metric-notes-to-target-notes":
        from qdash.dbmodel.initialize import initialize

        initialize()
        stats = migrate_metric_notes_to_target_notes(dry_run=not args.execute)
        logger.info(f"Migration complete: {stats}")
    elif args.command == "backfill-forum-thread-numbers":
        from qdash.dbmodel.initialize import initialize

        initialize()
        stats = migrate_backfill_forum_thread_numbers(dry_run=not args.execute)
        logger.info(f"Migration complete: {stats}")
    elif args.command == "migrate-forum-status":
        from qdash.dbmodel.initialize import initialize

        initialize()
        stats = migrate_forum_status(dry_run=not args.execute)
        logger.info(f"Migration complete: {stats}")
    else:
        parser.print_help()
