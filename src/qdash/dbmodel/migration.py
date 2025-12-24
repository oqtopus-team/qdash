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
"""

import logging
import os
from typing import Any

from pymongo import MongoClient

logger = logging.getLogger(__name__)

# Constants for migration safety
BATCH_SIZE = 1000  # Process documents in batches for memory efficiency


class MigrationError(Exception):
    """Raised when migration encounters an unrecoverable error."""


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
                f"{name}={value*100:.2f}%" for name, value in doc_info["invalid_params"]
            )
            logger.info(f"  - {doc_info['name']} (qid={doc_info['qid']}): {params_str}")
            stats["details"].append(
                {
                    "task_id": doc_info["task_id"],
                    "name": doc_info["name"],
                    "qid": doc_info["qid"],
                    "invalid_params": {
                        name: f"{value*100:.2f}%" for name, value in doc_info["invalid_params"]
                    },
                }
            )

        if len(invalid_docs) > 10:
            logger.info(f"  ... and {len(invalid_docs) - 10} more")

    if not dry_run and invalid_docs:
        for doc_info in invalid_docs:
            params_str = ", ".join(
                f"{name}={value*100:.2f}%" for name, value in doc_info["invalid_params"]
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
    else:
        parser.print_help()
