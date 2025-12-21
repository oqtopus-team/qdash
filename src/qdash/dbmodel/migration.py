"""Database migration utilities.

Run migrations with:
    python -m qdash.dbmodel.migration remove-best-data          # dry-run
    python -m qdash.dbmodel.migration remove-best-data --execute  # execute

    python -m qdash.dbmodel.migration rename-database --from qubex --to qdash  # dry-run
    python -m qdash.dbmodel.migration rename-database --from qubex --to qdash --execute
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

    args = parser.parse_args()

    if args.command == "remove-best-data":
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
    else:
        parser.print_help()
