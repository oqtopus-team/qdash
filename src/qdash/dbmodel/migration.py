"""Database migration utilities.

Run migrations with:
    python -m qdash.dbmodel.migration topology-id          # dry-run
    python -m qdash.dbmodel.migration topology-id --execute  # actual migration
"""

import logging

logger = logging.getLogger(__name__)


def migrate_add_topology_id(dry_run: bool = True) -> dict[str, int]:
    """Add topology_id to chips and chip_history that don't have it.

    Sets topology_id to 'square-lattice-mux-{size}' based on chip size.

    Args:
        dry_run: If True, only reports what would be changed.

    Returns:
        Migration statistics with counts of affected documents.
    """
    from qdash.dbmodel.chip import ChipDocument
    from qdash.dbmodel.chip_history import ChipHistoryDocument

    stats = {"chip": 0, "chip_history": 0}

    # Migrate ChipDocument
    chip_collection = ChipDocument.get_motor_collection()
    chips = list(
        chip_collection.find({"$or": [{"topology_id": None}, {"topology_id": {"$exists": False}}]})
    )
    logger.info(f"Found {len(chips)} chips without topology_id")

    for chip in chips:
        size = chip.get("size", 64)
        topology_id = f"square-lattice-mux-{size}"
        if not dry_run:
            chip_collection.update_one({"_id": chip["_id"]}, {"$set": {"topology_id": topology_id}})
        stats["chip"] += 1
        logger.debug(
            f"{'[DRY RUN] Would set' if dry_run else 'Set'} topology_id={topology_id} on chip {chip.get('chip_id')}"
        )

    # Migrate ChipHistoryDocument
    history_collection = ChipHistoryDocument.get_motor_collection()
    histories = list(
        history_collection.find(
            {"$or": [{"topology_id": None}, {"topology_id": {"$exists": False}}]}
        )
    )
    logger.info(f"Found {len(histories)} chip_history without topology_id")

    for history in histories:
        size = history.get("size", 64)
        topology_id = f"square-lattice-mux-{size}"
        if not dry_run:
            history_collection.update_one(
                {"_id": history["_id"]}, {"$set": {"topology_id": topology_id}}
            )
        stats["chip_history"] += 1

    logger.info(
        f"{'[DRY RUN] Would update' if dry_run else 'Updated'} {stats['chip']} chips, {stats['chip_history']} chip_history"
    )
    return stats


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Database migrations")
    subparsers = parser.add_subparsers(dest="command", help="Migration commands")

    # topology-id migration
    topo_parser = subparsers.add_parser("topology-id", help="Add topology_id to chips")
    topo_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (default is dry-run)",
    )

    args = parser.parse_args()

    if args.command == "topology-id":
        from qdash.dbmodel.initialize import initialize

        initialize()
        stats = migrate_add_topology_id(dry_run=not args.execute)
        logger.info(f"Migration complete: {stats}")
    else:
        parser.print_help()
