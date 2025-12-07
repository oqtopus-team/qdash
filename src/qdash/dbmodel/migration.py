"""Database migration utilities for multi-tenancy support.

This module provides migration functions to add project_id to existing documents
and create default projects for users.
"""

import logging
from collections.abc import Callable
from typing import Any

from bunnet import Document
from qdash.api.lib.project_service import ProjectService
from qdash.dbmodel.backend import BackendDocument
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.chip_history import ChipHistoryDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.coupling_history import CouplingHistoryDocument
from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.flow import FlowDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.qubit_history import QubitHistoryDocument
from qdash.dbmodel.tag import TagDocument
from qdash.dbmodel.task import TaskDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.dbmodel.user import UserDocument

logger = logging.getLogger(__name__)


def migrate_add_project_id_to_all_documents(dry_run: bool = True) -> dict[str, Any]:
    """Migrate all existing documents to have project_id based on their username.

    This migration:
    1. Creates a default project for each user that doesn't have one
    2. Assigns project_id to all documents based on their username

    Args:
        dry_run: If True, only reports what would be changed without modifying data.

    Returns:
        Migration statistics including counts of affected documents.
    """
    stats: dict[str, Any] = {
        "dry_run": dry_run,
        "users_processed": 0,
        "projects_created": 0,
        "documents_updated": {},
        "errors": [],
    }

    service = ProjectService()

    # Step 1: Ensure all users have a default project
    users = list(UserDocument.find_all().run())
    logger.info(f"Found {len(users)} users to process")

    user_project_map: dict[str, str] = {}

    for user in users:
        stats["users_processed"] += 1

        if user.default_project_id:
            # User already has a default project
            project = ProjectDocument.find_by_id(user.default_project_id)
            if project:
                user_project_map[user.username] = user.default_project_id
                logger.debug(f"User {user.username} already has project {user.default_project_id}")
                continue
            logger.warning(f"User {user.username} has invalid default_project_id {user.default_project_id}")

        # Create default project for user
        if not dry_run:
            try:
                project = service.ensure_default_project(user)
                user_project_map[user.username] = project.project_id
                stats["projects_created"] += 1
                logger.info(f"Created project {project.project_id} for user {user.username}")
            except Exception as e:
                error_msg = f"Failed to create project for user {user.username}: {e}"
                logger.error(error_msg)
                stats["errors"].append(error_msg)
        else:
            logger.info(f"[DRY RUN] Would create project for user {user.username}")
            stats["projects_created"] += 1

    # Step 2: Update documents with project_id
    document_classes: list[tuple[str, type[Document], Callable[[Any], str | None]]] = [
        ("chip", ChipDocument, lambda d: d.username),
        ("qubit", QubitDocument, lambda d: d.username),
        ("coupling", CouplingDocument, lambda d: d.username),
        ("execution_history", ExecutionHistoryDocument, lambda d: d.username),
        ("task", TaskDocument, lambda d: d.username),
        ("backend", BackendDocument, lambda d: d.username),
        ("tag", TagDocument, lambda d: d.username),
        ("flow", FlowDocument, lambda d: d.username),
        ("execution_counter", ExecutionCounterDocument, lambda d: d.username),
        ("chip_history", ChipHistoryDocument, lambda d: d.username),
        ("qubit_history", QubitHistoryDocument, lambda d: d.username),
        ("coupling_history", CouplingHistoryDocument, lambda d: d.username),
        ("task_result_history", TaskResultHistoryDocument, lambda d: d.username),
    ]

    for collection_name, doc_class, get_username in document_classes:
        try:
            count = _migrate_collection(
                collection_name=collection_name,
                doc_class=doc_class,
                get_username=get_username,
                user_project_map=user_project_map,
                dry_run=dry_run,
            )
            stats["documents_updated"][collection_name] = count
        except Exception as e:
            error_msg = f"Failed to migrate {collection_name}: {e}"
            logger.error(error_msg)
            stats["errors"].append(error_msg)
            stats["documents_updated"][collection_name] = {"error": str(e)}

    # Step 3: Handle ExecutionLockDocument specially (singleton per project)
    try:
        lock_count = _migrate_execution_locks(user_project_map, dry_run)
        stats["documents_updated"]["execution_lock"] = lock_count
    except Exception as e:
        error_msg = f"Failed to migrate execution_lock: {e}"
        logger.error(error_msg)
        stats["errors"].append(error_msg)

    return stats


def _migrate_collection(
    collection_name: str,
    doc_class: type[Document],
    get_username: Callable[[Any], str | None],
    user_project_map: dict[str, str],
    dry_run: bool,
) -> int:
    """Migrate a single collection to add project_id."""
    # Find documents without project_id
    docs = list(doc_class.find({"project_id": None}).run())
    updated = 0

    logger.info(f"Found {len(docs)} {collection_name} documents without project_id")

    for doc in docs:
        username = get_username(doc)
        if not username:
            logger.warning(f"Document {doc.id} in {collection_name} has no username, skipping")
            continue

        project_id = user_project_map.get(username)
        if not project_id:
            logger.warning(f"No project found for user {username} (document {doc.id} in {collection_name})")
            continue

        if not dry_run:
            doc.project_id = project_id
            doc.save()
            updated += 1
        else:
            updated += 1
            logger.debug(f"[DRY RUN] Would set project_id={project_id} on {collection_name} {doc.id}")

    logger.info(f"{'[DRY RUN] Would update' if dry_run else 'Updated'} " f"{updated} {collection_name} documents")
    return updated


def _migrate_execution_locks(user_project_map: dict[str, str], dry_run: bool) -> int:
    """Migrate ExecutionLockDocument to be project-scoped.

    Old behavior: Single global lock
    New behavior: One lock per project
    """
    # Find any existing lock without project_id
    old_lock = ExecutionLockDocument.find_one({"project_id": None}).run()
    if not old_lock:
        logger.info("No global execution lock found")
        return 0

    updated = 0

    # Create a lock for each project
    unique_project_ids = set(user_project_map.values())
    for project_id in unique_project_ids:
        existing = ExecutionLockDocument.find_one({"project_id": project_id}).run()
        if existing:
            continue

        if not dry_run:
            new_lock = ExecutionLockDocument(
                project_id=project_id,
                locked=False,
            )
            new_lock.insert()
            updated += 1
        else:
            updated += 1
            logger.debug(f"[DRY RUN] Would create execution lock for project {project_id}")

    # Remove the old global lock
    if not dry_run:
        old_lock.delete()
        logger.info("Deleted global execution lock")
    else:
        logger.info("[DRY RUN] Would delete global execution lock")

    return updated


def migrate_add_system_role() -> dict[str, int]:
    """Add system_role to users who don't have it.

    Returns:
        Migration statistics with count of affected users.
    """
    from qdash.datamodel.user import SystemRole

    stats: dict[str, int] = {
        "system_role_added": 0,
    }

    result = (
        UserDocument.find({"system_role": {"$exists": False}})
        .update_many({"$set": {"system_role": SystemRole.USER}})
        .run()
    )
    stats["system_role_added"] = result.modified_count
    if result.modified_count > 0:
        logger.info(f"Migration: Added system_role to {result.modified_count} users")

    return stats


def migrate_remove_user_default_role() -> dict[str, int]:
    """Remove default_role field from all users.

    This migration:
    - Removes the default_role field from all user documents
    - The simplified permission model no longer uses user-level default_role
    - Users are owners of their own project and viewers when invited elsewhere

    Returns:
        Migration statistics with count of affected users.
    """
    stats: dict[str, int] = {
        "default_role_removed": 0,
    }

    result = UserDocument.find({"default_role": {"$exists": True}}).update_many({"$unset": {"default_role": ""}}).run()
    stats["default_role_removed"] = result.modified_count
    if result.modified_count > 0:
        logger.info(f"Migration: Removed default_role from {result.modified_count} users")

    return stats


def migrate_full(dry_run: bool = True) -> dict[str, Any]:
    """Run full migration for systems without project_id.

    This migration:
    1. Adds system_role to users (if missing)
    2. Removes deprecated default_role from users
    3. Creates projects for users and adds project_id to all documents

    Args:
        dry_run: If True, only reports what would be changed.

    Returns:
        Combined migration statistics.
    """
    stats: dict[str, Any] = {
        "dry_run": dry_run,
        "system_role_added": 0,
        "default_role_removed": 0,
        "project_migration": {},
    }

    # Step 1: Add system_role to users
    if not dry_run:
        role_stats = migrate_add_system_role()
        stats["system_role_added"] = role_stats["system_role_added"]
    else:
        count = UserDocument.find({"system_role": {"$exists": False}}).count()
        stats["system_role_added"] = count
        if count > 0:
            logger.info(f"[DRY RUN] Would add system_role to {count} users")

    # Step 2: Remove deprecated default_role
    if not dry_run:
        role_stats = migrate_remove_user_default_role()
        stats["default_role_removed"] = role_stats["default_role_removed"]
    else:
        count = UserDocument.find({"default_role": {"$exists": True}}).count()
        stats["default_role_removed"] = count
        if count > 0:
            logger.info(f"[DRY RUN] Would remove default_role from {count} users")

    # Step 3: Add project_id to all documents
    project_stats = migrate_add_project_id_to_all_documents(dry_run=dry_run)
    stats["project_migration"] = project_stats

    return stats


def run_migration(dry_run: bool = True) -> None:
    """Run the migration with logging output.

    Args:
        dry_run: If True, only shows what would be changed.
    """
    from qdash.dbmodel.initialize import initialize

    initialize()

    logger.info(f"Starting migration (dry_run={dry_run})")
    stats = migrate_add_project_id_to_all_documents(dry_run=dry_run)

    logger.info("=" * 50)
    logger.info("Migration Summary")
    logger.info("=" * 50)
    logger.info(f"Dry run: {stats['dry_run']}")
    logger.info(f"Users processed: {stats['users_processed']}")
    logger.info(f"Projects created: {stats['projects_created']}")
    logger.info("Documents updated:")
    for collection, count in stats["documents_updated"].items():
        logger.info(f"  - {collection}: {count}")
    if stats["errors"]:
        logger.error(f"Errors: {len(stats['errors'])}")
        for error in stats["errors"]:
            logger.error(f"  - {error}")
    logger.info("=" * 50)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Database migrations")
    subparsers = parser.add_subparsers(dest="command", help="Migration commands")

    # Full migration (recommended for fresh systems)
    full_parser = subparsers.add_parser("full", help="Full migration: system_role + project_id (recommended)")
    full_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (default is dry-run)",
    )

    # project-id migration (for systems that already have system_role)
    project_parser = subparsers.add_parser("project-id", help="Add project_id to all documents only")
    project_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (default is dry-run)",
    )

    # list migrations
    subparsers.add_parser("list", help="List available migrations")

    args = parser.parse_args()

    if args.command == "full":
        from qdash.dbmodel.initialize import initialize

        initialize()
        logger.info(f"Starting full migration (dry_run={not args.execute})")
        stats = migrate_full(dry_run=not args.execute)

        logger.info("=" * 50)
        logger.info("Full Migration Summary")
        logger.info("=" * 50)
        logger.info(f"Dry run: {stats['dry_run']}")
        logger.info(f"system_role added: {stats['system_role_added']}")
        logger.info(f"default_role removed: {stats['default_role_removed']}")
        logger.info(f"Users processed: {stats['project_migration'].get('users_processed', 0)}")
        logger.info(f"Projects created: {stats['project_migration'].get('projects_created', 0)}")
        logger.info("Documents updated:")
        for collection, count in stats["project_migration"].get("documents_updated", {}).items():
            logger.info(f"  - {collection}: {count}")
        if stats["project_migration"].get("errors"):
            logger.error(f"Errors: {len(stats['project_migration']['errors'])}")
            for error in stats["project_migration"]["errors"]:
                logger.error(f"  - {error}")
        logger.info("=" * 50)

    elif args.command == "project-id":
        run_migration(dry_run=not args.execute)

    elif args.command == "list":
        print("Available migrations:")
        print("")
        print("  full        - Full migration for systems without project_id (recommended)")
        print("                1. Adds system_role to users")
        print("                2. Removes deprecated default_role")
        print("                3. Creates projects for users")
        print("                4. Adds project_id to all documents")
        print("")
        print("  project-id  - Add project_id to documents only")
        print("                (use if system_role is already set)")
        print("")
        print("Usage:")
        print("  python -m qdash.dbmodel.migration full          # dry-run")
        print("  python -m qdash.dbmodel.migration full --execute  # actual migration")

    else:
        parser.print_help()
