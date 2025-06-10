#!/usr/bin/env python3
"""Script to migrate execution counter documents to include username and chip_id fields."""

import argparse
import logging

from qdash.dbmodel.migration import migrate_execution_counter_v1

logging.basicConfig(level=logging.INFO)


def main() -> None:
    """Run the execution counter migration."""
    parser = argparse.ArgumentParser(description="Migrate execution counter documents")
    parser.add_argument(
        "--username",
        default="admin",
        help="Default username to set for existing documents (default: admin)",
    )
    parser.add_argument(
        "--chip-id",
        default="64Q",
        help="Default chip ID to set for existing documents (default: 64Q)",
    )

    args = parser.parse_args()

    try:
        migrate_execution_counter_v1(username=args.username, chip_id=args.chip_id)
        logging.info("Migration completed successfully")
    except Exception as e:
        logging.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    main()
