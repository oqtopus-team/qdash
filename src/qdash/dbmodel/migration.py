"""Database migration utilities.

Run migrations with:
    python -m qdash.dbmodel.migration remove-embedded-qubits-couplings          # dry-run
    python -m qdash.dbmodel.migration remove-embedded-qubits-couplings --execute  # execute

    python -m qdash.dbmodel.migration remove-controller-fridge-info          # dry-run
    python -m qdash.dbmodel.migration remove-controller-fridge-info --execute  # execute
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Constants for migration safety
BATCH_SIZE = 1000  # Process documents in batches for memory efficiency


class MigrationError(Exception):
    """Raised when migration encounters an unrecoverable error."""


def migrate_remove_embedded_qubits_couplings(dry_run: bool = True) -> dict[str, int]:
    """Remove embedded qubits and couplings fields from chip and chip_history collections.

    These fields are no longer used as qubit/coupling data is now stored in separate
    QubitDocument/CouplingDocument collections for scalability (256+ qubits).

    Args:
        dry_run: If True, only reports what would be changed.

    Returns:
        Migration statistics with counts of affected documents.
    """
    from qdash.dbmodel.chip import ChipDocument
    from qdash.dbmodel.chip_history import ChipHistoryDocument

    stats: dict[str, int] = {"chip": 0, "chip_history": 0}

    # Fields to remove
    fields_to_unset = {"qubits": "", "couplings": ""}

    # Migrate ChipDocument
    collection = ChipDocument.get_motor_collection()
    filter_query: dict[str, Any] = {
        "$or": [
            {"qubits": {"$exists": True}},
            {"couplings": {"$exists": True}},
        ]
    }
    count = collection.count_documents(filter_query)
    stats["chip"] = count
    logger.info(f"Found {count} chip documents with qubits or couplings")

    if not dry_run and count > 0:
        result = collection.update_many(filter_query, {"$unset": fields_to_unset})
        logger.info(f"Updated {result.modified_count} chip documents")

    # Migrate ChipHistoryDocument
    collection = ChipHistoryDocument.get_motor_collection()
    count = collection.count_documents(filter_query)
    stats["chip_history"] = count
    logger.info(f"Found {count} chip_history documents with qubits or couplings")

    if not dry_run and count > 0:
        result = collection.update_many(filter_query, {"$unset": fields_to_unset})
        logger.info(f"Updated {result.modified_count} chip_history documents")

    prefix = "[DRY RUN] Would update" if dry_run else "Updated"
    logger.info(f"{prefix} documents: {stats}")
    return stats


def migrate_remove_controller_fridge_info(dry_run: bool = True) -> dict[str, int]:
    """Remove controller_info and fridge_info fields from execution_history and task_result_history.

    These fields were never used in production and are being removed from the codebase.

    Args:
        dry_run: If True, only reports what would be changed.

    Returns:
        Migration statistics with counts of affected documents.
    """
    from qdash.dbmodel.execution_history import ExecutionHistoryDocument
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    stats: dict[str, int] = {"execution_history": 0, "task_result_history": 0}

    # Fields to remove
    fields_to_unset = {"controller_info": "", "fridge_info": ""}

    # Migrate ExecutionHistoryDocument
    collection = ExecutionHistoryDocument.get_motor_collection()
    # Find documents that have either field
    filter_query: dict[str, Any] = {
        "$or": [
            {"controller_info": {"$exists": True}},
            {"fridge_info": {"$exists": True}},
        ]
    }
    count = collection.count_documents(filter_query)
    stats["execution_history"] = count
    logger.info(f"Found {count} execution_history documents with controller_info or fridge_info")

    if not dry_run and count > 0:
        result = collection.update_many(filter_query, {"$unset": fields_to_unset})
        logger.info(f"Updated {result.modified_count} execution_history documents")

    # Migrate TaskResultHistoryDocument
    collection = TaskResultHistoryDocument.get_motor_collection()
    count = collection.count_documents(filter_query)
    stats["task_result_history"] = count
    logger.info(f"Found {count} task_result_history documents with controller_info or fridge_info")

    if not dry_run and count > 0:
        result = collection.update_many(filter_query, {"$unset": fields_to_unset})
        logger.info(f"Updated {result.modified_count} task_result_history documents")

    prefix = "[DRY RUN] Would update" if dry_run else "Updated"
    logger.info(f"{prefix} documents: {stats}")
    return stats


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Database migrations")
    subparsers = parser.add_subparsers(dest="command", help="Migration commands")

    # remove-embedded-qubits-couplings migration
    remove_embedded_parser = subparsers.add_parser(
        "remove-embedded-qubits-couplings",
        help="Remove embedded qubits/couplings fields from chip collections",
    )
    remove_embedded_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (default is dry-run)",
    )

    # remove-controller-fridge-info migration
    remove_parser = subparsers.add_parser(
        "remove-controller-fridge-info",
        help="Remove controller_info and fridge_info fields from collections",
    )
    remove_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (default is dry-run)",
    )

    args = parser.parse_args()

    if args.command == "remove-embedded-qubits-couplings":
        from qdash.dbmodel.initialize import initialize

        initialize()
        stats = migrate_remove_embedded_qubits_couplings(dry_run=not args.execute)
        logger.info(f"Migration complete: {stats}")
    elif args.command == "remove-controller-fridge-info":
        from qdash.dbmodel.initialize import initialize

        initialize()
        stats = migrate_remove_controller_fridge_info(dry_run=not args.execute)
        logger.info(f"Migration complete: {stats}")
    else:
        parser.print_help()
