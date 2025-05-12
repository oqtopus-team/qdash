import logging

from qdash.db.init.chip import generate_coupling_data, generate_qubit_data
from qdash.db.init.coupling import bi_direction, generate_coupling
from qdash.db.init.initialize import initialize
from qdash.db.init.qubit import generate_dummy_data, qubit_lattice
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.menu import MenuDocument

logging.basicConfig(level=logging.INFO)


def add_new_chip(
    username: str = "admin",
    chip_id: str = "64Q",
) -> None:
    """Add a new chip to the database.

    This function adds a new chip to the database by initializing the
    necessary data.

    Args:
    ----
        username (str): The username for the initialization.
        chip_id (str): The chip ID for the initialization.

    """
    try:
        # Initialize chip data
        initialize()
        num_qubits = 64
        _, edges, pos = qubit_lattice(64, 4)
        nodes, edges, pos = qubit_lattice(64, 4)
        qubits = generate_qubit_data(num_qubits, pos, chip_id)
        couplings = generate_coupling_data(edges, chip_id)
        chip = ChipDocument(
            username=username,
            chip_id=chip_id,
            size=64,
            qubits=qubits,
            couplings=couplings,
            system_info={},
        )
        chip.save()
        ## Initialize qubit data
        nodes, edges, pos = qubit_lattice(64, 4)
        dummy_data = generate_dummy_data(num_qubits, pos, username=username, chip_id=chip_id)
        for data in dummy_data:
            data.insert()
        ## Initialize coupling data
        _, edges, _ = qubit_lattice(n=64, d=4)
        edges = bi_direction(edges)
        couplings = generate_coupling(edges, username=username, chip_id=chip_id)
        for c in couplings:
            c.insert()
        logging.info(f"New chip added: {chip_id} for user: {username}")
    except Exception as e:
        logging.error(f"Error adding new chip: {e}")
        raise


def rename_all_menu_with_chip_id(
    username: str = "admin",
    chip_id: str = "64Q",
) -> None:
    """Rename menu with chip ID.

    This function renames the menu with the given chip ID.

    Args:
    ----
        username (str): The username for the initialization.
        chip_id (str): The chip ID for the initialization.

    """
    try:
        # Initialize menu data
        initialize()
        menus = MenuDocument.find({"username": username}).run()
        for menu in menus:
            menu.chip_id = chip_id
            menu.save()
            logging.info(f"Updated menu: {menu.username} - {menu.name} with chip ID: {chip_id}")
        logging.info(f"Menu renamed with chip ID: {chip_id} for user: {username}")
    except Exception as e:
        logging.error(f"Error renaming menu with chip ID: {e}")
        raise
