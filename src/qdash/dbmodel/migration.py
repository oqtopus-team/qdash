import logging

from qdash.db.init.initialize import initialize
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
