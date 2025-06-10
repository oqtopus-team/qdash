import logging

from qdash.db.init.initialize import initialize
from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.menu import MenuDocument

logging.basicConfig(level=logging.INFO)


def migrate_v1_0_16_to_v1_0_17(
    username: str = "admin",
    chip_id: str = "64Q",
) -> None:
    """Migrate from version 1.0.16 to 1.0.17.

    This function migrates the database from version 1.0.16 to 1.0.17 by
    updating the execution history documents to include the new fields
    introduced in version 1.0.17.

    Args:
    ----
        username (str): The username for the migration.
        chip_id (str): The chip ID for the migration.

    """
    try:
        # Initialize coupling data
        initialize()
        menus = MenuDocument.find({"username": username}).run()
        for menu in menus:
            logging.info(f"Updated menu: {menu.username} - {menu.name} with chip ID: {chip_id}")
            logging.info(
                f"Migration from v1.0.16 to v1.0.17 completed successfully (username: {username})"
            )
            menu.chip_id = chip_id
            menu.save()
    except Exception as e:
        logging.error(f"Error during migration: {e}")
        raise


def migrate_execution_counter_v1(
    username: str = "admin",
    chip_id: str = "64Q",
) -> None:
    """Migrate execution counter documents to include username and chip_id fields.

    This function updates all existing execution counter documents to include
    the new username and chip_id fields. For existing documents, it sets these
    fields to the provided default values.

    Args:
    ----
        username (str): The default username to set for existing documents
        chip_id (str): The default chip ID to set for existing documents

    """
    try:
        initialize()
        # Find all execution counter documents
        counters = ExecutionCounterDocument.find_all().run()
        for counter in counters:
            logging.info(f"Updating execution counter for date: {counter.date}")
            # Add the new fields
            counter.username = username
            counter.chip_id = chip_id
            counter.save()
            logging.info(
                f"Updated execution counter: {counter.date} with username: {username}, chip_id: {chip_id}"
            )
        logging.info("Execution counter migration completed successfully")
    except Exception as e:
        logging.error(f"Error during execution counter migration: {e}")
        raise
