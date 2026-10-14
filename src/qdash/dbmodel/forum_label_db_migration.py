"""Forum label backfill migration.

Registers a label definition for every label key that existing forum threads use
but that has no ForumLabelDocument yet. Run it manually, after
``migrate-forum-status`` has been executed:

    python -m qdash.dbmodel.migration migrate-forum-status --execute

    python -m qdash.dbmodel.forum_label_db_migration          # dry-run
    python -m qdash.dbmodel.forum_label_db_migration --execute  # execute

Created labels use the key as the name and a neutral gray color. Existing label
definitions and threads are never modified, so the script is safe to re-run.
"""

import logging
from typing import Any

from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

NEUTRAL_FORUM_LABEL_COLOR = "#6b7280"


def backfill_forum_labels(dry_run: bool = True) -> dict[str, Any]:
    """Create missing ForumLabelDocument entries for label keys used by forum threads.

    Distinct ``(project_id, label)`` pairs are collected from all forum posts,
    including deleted ones. Only pairs without an existing label definition are
    created, with ``name`` set to the key, an empty description and a neutral
    color. Existing labels and posts are left untouched.
    """
    from qdash.dbmodel.forum import ForumLabelDocument, ForumPostDocument

    pairs: set[tuple[str, str]] = set()
    for doc in ForumPostDocument.get_motor_collection().find({}, {"project_id": 1, "labels": 1}):
        project_id = doc.get("project_id")
        labels = doc.get("labels")
        if not isinstance(project_id, str) or not project_id or not isinstance(labels, list):
            continue
        for label in labels:
            if isinstance(label, str) and label:
                pairs.add((project_id, label))

    existing_pairs = {
        (doc["project_id"], doc["key"])
        for doc in ForumLabelDocument.get_motor_collection().find({}, {"project_id": 1, "key": 1})
    }
    missing = sorted(pairs - existing_pairs)
    stats: dict[str, Any] = {
        "labels_found": len(pairs),
        "labels_to_create": len(missing),
        "labels_created": 0,
        "labels_existing": len(pairs) - len(missing),
    }

    if not dry_run:
        for project_id, label in missing:
            try:
                ForumLabelDocument(
                    project_id=project_id,
                    key=label,
                    name=label,
                    description="",
                    color=NEUTRAL_FORUM_LABEL_COLOR,
                ).insert()
            except DuplicateKeyError:
                stats["labels_existing"] += 1
                continue
            stats["labels_created"] += 1

    logger.info("Forum label backfill: %s", stats)
    return stats


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Register label definitions for label keys used by existing forum threads"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (default is dry-run)",
    )
    args = parser.parse_args()

    from qdash.dbmodel.initialize import initialize

    initialize()
    backfill_forum_labels(dry_run=not args.execute)
