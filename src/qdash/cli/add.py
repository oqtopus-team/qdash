import logging
from typing import cast

from qdash.datamodel.parameter import ParameterModel
from qdash.db.init.chip import generate_coupling_data, generate_qubit_data
from qdash.db.init.coupling import bi_direction, generate_coupling
from qdash.db.init.initialize import initialize
from qdash.db.init.qubit import generate_dummy_data, qubit_lattice
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.menu import MenuDocument
from qdash.workflow.tasks.base import BaseTask

logging.basicConfig(level=logging.INFO)


CHIP_SIZE_64 = 64
CHIP_SIZE_144 = 144
CHIP_SIZE_256 = 256
CHIP_SIZE_1024 = 1024


def add_new_chip(
    username: str = "admin",
    chip_id: str = "64Q",
    size: int = CHIP_SIZE_64,
) -> None:
    """Add a new chip to the database.

    This function adds a new chip to the database by initializing the
    necessary data.

    Args:
    ----
        username (str): The username for the initialization.
        chip_id (str): The chip ID for the initialization.
        size (int): The size of the chip, either CHIP_SIZE_64 or CHIP_SIZE_144.

    """
    try:
        # Initialize chip data
        initialize()

        if size not in [CHIP_SIZE_64, CHIP_SIZE_144, CHIP_SIZE_256, CHIP_SIZE_1024]:
            msg = "Size must be either CHIP_SIZE_64 or CHIP_SIZE_144 or CHIP_SIZE_256."
            raise ValueError(msg)  # noqa: TRY301
        # Removed unused variable 'd'
        if size == CHIP_SIZE_64:
            d = 4
        elif size == CHIP_SIZE_144:
            d = 6
        elif size == CHIP_SIZE_256:
            d = 8
        elif size == CHIP_SIZE_1024:
            d = 16
        _, edges, pos = qubit_lattice(size, d)
        nodes, edges, pos = qubit_lattice(size, d)
        qubits = generate_qubit_data(size, pos, chip_id)
        couplings = generate_coupling_data(edges, chip_id)
        chip = ChipDocument(
            username=username,
            chip_id=chip_id,
            size=size,
            qubits=qubits,
            couplings=couplings,
            system_info={},
        )
        chip.save()
        ## Initialize qubit data
        nodes, edges, pos = qubit_lattice(size, d)
        dummy_data = generate_dummy_data(size, pos, username=username, chip_id=chip_id)
        for data in dummy_data:
            data.insert()
        ## Initialize coupling data
        _, edges, _ = qubit_lattice(size, d)
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


def convert_output_parameters(username: str, outputs: dict[str, any]) -> dict[str, dict]:  # type: ignore # noqa: PGH003
    """Convert the output parameters to the Parameter class."""
    converted = {}
    for param_name, output in outputs.items():
        param = ParameterModel(
            username=username,
            name=param_name,
            unit=cast(ParameterModel, output).unit,
            description=cast(ParameterModel, output).description,
        )  # type: ignore # noqa: PGH003
        converted[param_name] = param.model_dump()
    return converted


def update_active_output_parameters(username: str) -> list[ParameterModel]:
    """Update the active output parameters in the input file.

    Args:
    ----
        username (str): The username for the initialization.

    """
    all_outputs = {name: cls.output_parameters for name, cls in BaseTask.registry.items()}
    converted_outputs = {
        task_name: convert_output_parameters(username=username, outputs=outputs)
        for task_name, outputs in all_outputs.items()
    }

    unique_parameter_names = {
        param_name for outputs in converted_outputs.values() for param_name in outputs
    }
    return [
        ParameterModel(
            username=username,
            name=name,
            unit=converted_outputs[
                next(task for task in converted_outputs if name in converted_outputs[task])
            ][name]["unit"],
            description=converted_outputs[
                next(task for task in converted_outputs if name in converted_outputs[task])
            ][name]["description"],
        )
        for name in unique_parameter_names
    ]
