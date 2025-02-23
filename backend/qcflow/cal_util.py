import json
import re
from pathlib import Path

from prefect import get_run_logger, task


def label_to_qid(qid: str) -> str:
    """Convert QXX to XX. e.g. "Q0" -> "0", "Q01" -> "1"."""
    if re.fullmatch(r"Q\d+", qid):
        return qid[1:]
    error_message = "Invalid qid format."
    raise ValueError(error_message)


def qid_to_label(qid: str) -> str:
    """Convert QXX to QXX. e.g. '0' -> 'Q0'."""
    if re.fullmatch(r"\d+", qid):
        return "Q" + qid
    error_message = "Invalid qid format."
    raise ValueError(error_message)


@task
def update_active_output_parameters() -> None:
    """Update the active output parameters in the input file.

    Args:
    ----
        file_path: The path to the input file.

    """
    from qcflow.protocols.base import BaseTask

    logger = get_run_logger()
    all_outputs = {name: cls.output_parameters for name, cls in BaseTask.registry.items()}
    unique_elements = list({param for params in all_outputs.values() for param in params})
    logger.info(f"Active output parameters: {unique_elements}")
    with Path("active_output_parameters.json").open("w") as f:
        json.dump(all_outputs, f)
    with Path("unique_output_parameters.json").open("w") as f:
        json.dump(unique_elements, f)

    all_descriptions = {name: cls.__doc__ for name, cls in BaseTask.registry.items()}
    with Path("task_descriptions.json").open("w") as f:
        json.dump(all_descriptions, f)
    logger.info(f"Task descriptions: {all_descriptions}")
