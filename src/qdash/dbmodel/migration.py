"""Database migration utilities.

Run migrations with:
    python -m qdash.dbmodel.migration remove-best-data          # dry-run
    python -m qdash.dbmodel.migration remove-best-data --execute  # execute
"""

import logging
from typing import Any

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

    args = parser.parse_args()

    if args.command == "remove-best-data":
        from qdash.dbmodel.initialize import initialize

        initialize()
        stats = migrate_remove_best_data(dry_run=not args.execute)
        logger.info(f"Migration complete: {stats}")
    else:
        parser.print_help()
