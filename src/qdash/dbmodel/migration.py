"""Database migration utilities.

Run migrations with:
    python -m qdash.dbmodel.migration topology-id          # dry-run
    python -m qdash.dbmodel.migration topology-id --execute  # actual migration
    python -m qdash.dbmodel.migration datetime-fields          # dry-run
    python -m qdash.dbmodel.migration datetime-fields --execute  # actual migration
"""

import logging

import pendulum

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


def parse_elapsed_time_to_seconds(elapsed_str: str) -> float:
    """Parse elapsed time string to seconds (float).

    Handles formats like:
    - "1:23:45" (hours:minutes:seconds)
    - "0:30" (minutes:seconds)
    - "a few seconds"
    - "2 minutes"
    - "38 seconds"
    - etc.

    Returns:
        float: Elapsed time in seconds
    """
    import re

    if not elapsed_str:
        return 0.0

    elapsed_str = str(elapsed_str).strip()

    # Try numeric format first (H:MM:SS or MM:SS)
    parts = elapsed_str.split(":")
    if len(parts) == 3:
        try:
            hours, minutes, seconds = map(int, parts)
            return float(hours * 3600 + minutes * 60 + seconds)
        except ValueError:
            pass
    elif len(parts) == 2:
        try:
            minutes, seconds = map(int, parts)
            return float(minutes * 60 + seconds)
        except ValueError:
            pass

    # Parse human-readable format with numbers like "38 seconds", "1 minute"
    total_seconds = 0.0
    patterns = [
        (r"([\d.]+)\s*(?:seconds|second)\b", 1),
        (r"([\d.]+)\s*(?:minutes|minute)\b", 60),
        (r"([\d.]+)\s*(?:hours|hour)\b", 3600),
        (r"([\d.]+)\s*secs?\b", 1),
        (r"([\d.]+)\s*mins?\b", 60),
        (r"([\d.]+)\s*hrs?\b", 3600),
    ]

    matched = False
    for pattern, multiplier in patterns:
        for match in re.finditer(pattern, elapsed_str, re.IGNORECASE):
            total_seconds += float(match.group(1)) * multiplier
            matched = True

    if matched:
        return total_seconds

    # Handle approximate formats from pendulum (no numbers)
    if "few second" in elapsed_str.lower():
        return 5.0
    if "second" in elapsed_str.lower():
        return 1.0
    if "minute" in elapsed_str.lower():
        return 60.0
    if "hour" in elapsed_str.lower():
        return 3600.0

    # Try to parse as a plain number
    try:
        return float(elapsed_str)
    except ValueError:
        pass

    return 0.0


def migrate_datetime_fields(dry_run: bool = True) -> dict[str, int]:
    """Migrate string datetime fields to native datetime types.

    This migration converts:
    - ISO8601 strings to datetime objects
    - elapsed_time strings to timedelta (stored as seconds)
    - SystemInfoModel.created_at/updated_at to datetime

    Args:
        dry_run: If True, only reports what would be changed.

    Returns:
        Migration statistics with counts of affected documents.
    """
    from qdash.dbmodel.calibration_note import CalibrationNoteDocument
    from qdash.dbmodel.chip import ChipDocument
    from qdash.dbmodel.chip_history import ChipHistoryDocument
    from qdash.dbmodel.execution_history import ExecutionHistoryDocument
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    stats: dict[str, int] = {}

    from typing import Any

    # Helper function to convert ISO8601 string to datetime
    def to_datetime(value: str | None) -> Any:
        if value is None or value == "":
            return None
        try:
            return pendulum.parse(value)
        except Exception:
            return None

    # Migrate ExecutionHistoryDocument
    collection = ExecutionHistoryDocument.get_motor_collection()
    docs = list(
        collection.find(
            {
                "$or": [
                    {"start_at": {"$type": "string"}},
                    {"end_at": {"$type": "string"}},
                    {"elapsed_time": {"$type": "string"}},
                ]
            }
        )
    )
    stats["execution_history"] = len(docs)
    logger.info(f"Found {len(docs)} execution_history with string datetime fields")

    for doc in docs:
        updates: dict[str, Any] = {}
        if isinstance(doc.get("start_at"), str):
            if doc["start_at"] == "":
                updates["start_at"] = None
            else:
                dt = to_datetime(doc["start_at"])
                if dt:
                    updates["start_at"] = dt
        if isinstance(doc.get("end_at"), str):
            if doc["end_at"] == "":
                updates["end_at"] = None
            else:
                dt = to_datetime(doc["end_at"])
                if dt:
                    updates["end_at"] = dt
        if isinstance(doc.get("elapsed_time"), str):
            if doc["elapsed_time"] == "":
                updates["elapsed_time"] = None
            else:
                seconds = parse_elapsed_time_to_seconds(doc["elapsed_time"])
                updates["elapsed_time"] = seconds

        # Update system_info
        system_info = doc.get("system_info", {})
        if isinstance(system_info, dict):
            if isinstance(system_info.get("created_at"), str):
                if system_info["created_at"] == "":
                    updates["system_info.created_at"] = None
                else:
                    dt = to_datetime(system_info["created_at"])
                    if dt:
                        updates["system_info.created_at"] = dt
            if isinstance(system_info.get("updated_at"), str):
                if system_info["updated_at"] == "":
                    updates["system_info.updated_at"] = None
                else:
                    dt = to_datetime(system_info["updated_at"])
                    if dt:
                        updates["system_info.updated_at"] = dt

        if updates and not dry_run:
            collection.update_one({"_id": doc["_id"]}, {"$set": updates})

    # Migrate TaskResultHistoryDocument
    collection = TaskResultHistoryDocument.get_motor_collection()
    docs = list(
        collection.find(
            {
                "$or": [
                    {"start_at": {"$type": "string"}},
                    {"end_at": {"$type": "string"}},
                    {"elapsed_time": {"$type": "string"}},
                ]
            }
        )
    )
    stats["task_result_history"] = len(docs)
    logger.info(f"Found {len(docs)} task_result_history with string datetime fields")

    for doc in docs:
        updates = {}
        if isinstance(doc.get("start_at"), str):
            if doc["start_at"] == "":
                updates["start_at"] = None
            else:
                dt = to_datetime(doc["start_at"])
                if dt:
                    updates["start_at"] = dt
        if isinstance(doc.get("end_at"), str):
            if doc["end_at"] == "":
                updates["end_at"] = None
            else:
                dt = to_datetime(doc["end_at"])
                if dt:
                    updates["end_at"] = dt
        if isinstance(doc.get("elapsed_time"), str):
            if doc["elapsed_time"] == "":
                updates["elapsed_time"] = None
            else:
                seconds = parse_elapsed_time_to_seconds(doc["elapsed_time"])
                updates["elapsed_time"] = seconds

        system_info = doc.get("system_info", {})
        if isinstance(system_info, dict):
            if isinstance(system_info.get("created_at"), str):
                if system_info["created_at"] == "":
                    updates["system_info.created_at"] = None
                else:
                    dt = to_datetime(system_info["created_at"])
                    if dt:
                        updates["system_info.created_at"] = dt
            if isinstance(system_info.get("updated_at"), str):
                if system_info["updated_at"] == "":
                    updates["system_info.updated_at"] = None
                else:
                    dt = to_datetime(system_info["updated_at"])
                    if dt:
                        updates["system_info.updated_at"] = dt

        if updates and not dry_run:
            collection.update_one({"_id": doc["_id"]}, {"$set": updates})

    # Migrate ChipDocument (installed_at, system_info)
    collection = ChipDocument.get_motor_collection()
    docs = list(collection.find({"installed_at": {"$type": "string"}}))
    stats["chip"] = len(docs)
    logger.info(f"Found {len(docs)} chip with string datetime fields")

    for doc in docs:
        updates = {}
        if isinstance(doc.get("installed_at"), str):
            if doc["installed_at"] == "":
                updates["installed_at"] = None
            else:
                dt = to_datetime(doc["installed_at"])
                if dt:
                    updates["installed_at"] = dt

        system_info = doc.get("system_info", {})
        if isinstance(system_info, dict):
            if isinstance(system_info.get("created_at"), str):
                if system_info["created_at"] == "":
                    updates["system_info.created_at"] = None
                else:
                    dt = to_datetime(system_info["created_at"])
                    if dt:
                        updates["system_info.created_at"] = dt
            if isinstance(system_info.get("updated_at"), str):
                if system_info["updated_at"] == "":
                    updates["system_info.updated_at"] = None
                else:
                    dt = to_datetime(system_info["updated_at"])
                    if dt:
                        updates["system_info.updated_at"] = dt

        if updates and not dry_run:
            collection.update_one({"_id": doc["_id"]}, {"$set": updates})

    # Migrate ChipHistoryDocument
    collection = ChipHistoryDocument.get_motor_collection()
    docs = list(collection.find({"installed_at": {"$type": "string"}}))
    stats["chip_history"] = len(docs)
    logger.info(f"Found {len(docs)} chip_history with string datetime fields")

    for doc in docs:
        updates = {}
        if isinstance(doc.get("installed_at"), str):
            if doc["installed_at"] == "":
                updates["installed_at"] = None
            else:
                dt = to_datetime(doc["installed_at"])
                if dt:
                    updates["installed_at"] = dt

        system_info = doc.get("system_info", {})
        if isinstance(system_info, dict):
            if isinstance(system_info.get("created_at"), str):
                if system_info["created_at"] == "":
                    updates["system_info.created_at"] = None
                else:
                    dt = to_datetime(system_info["created_at"])
                    if dt:
                        updates["system_info.created_at"] = dt
            if isinstance(system_info.get("updated_at"), str):
                if system_info["updated_at"] == "":
                    updates["system_info.updated_at"] = None
                else:
                    dt = to_datetime(system_info["updated_at"])
                    if dt:
                        updates["system_info.updated_at"] = dt

        if updates and not dry_run:
            collection.update_one({"_id": doc["_id"]}, {"$set": updates})

    # Migrate CalibrationNoteDocument
    collection = CalibrationNoteDocument.get_motor_collection()
    docs = list(collection.find({"timestamp": {"$type": "string"}}))
    stats["calibration_note"] = len(docs)
    logger.info(f"Found {len(docs)} calibration_note with string datetime fields")

    for doc in docs:
        updates = {}
        if isinstance(doc.get("timestamp"), str):
            if doc["timestamp"] == "":
                updates["timestamp"] = None
            else:
                dt = to_datetime(doc["timestamp"])
                if dt:
                    updates["timestamp"] = dt

        system_info = doc.get("system_info", {})
        if isinstance(system_info, dict):
            if isinstance(system_info.get("created_at"), str):
                if system_info["created_at"] == "":
                    updates["system_info.created_at"] = None
                else:
                    dt = to_datetime(system_info["created_at"])
                    if dt:
                        updates["system_info.created_at"] = dt
            if isinstance(system_info.get("updated_at"), str):
                if system_info["updated_at"] == "":
                    updates["system_info.updated_at"] = None
                else:
                    dt = to_datetime(system_info["updated_at"])
                    if dt:
                        updates["system_info.updated_at"] = dt

        if updates and not dry_run:
            collection.update_one({"_id": doc["_id"]}, {"$set": updates})

    prefix = "[DRY RUN] Would update" if dry_run else "Updated"
    logger.info(f"{prefix} datetime fields: {stats}")
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

    # datetime-fields migration
    dt_parser = subparsers.add_parser(
        "datetime-fields", help="Convert string datetime fields to native datetime"
    )
    dt_parser.add_argument(
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
    elif args.command == "datetime-fields":
        from qdash.dbmodel.initialize import initialize

        initialize()
        stats = migrate_datetime_fields(dry_run=not args.execute)
        logger.info(f"Migration complete: {stats}")
    else:
        parser.print_help()
