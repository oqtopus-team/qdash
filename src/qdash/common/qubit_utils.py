"""Qubit utility functions shared between API and Workflow modules."""

import logging
import re
from functools import lru_cache

logger = logging.getLogger(__name__)

DEFAULT_NUM_QUBITS = 64


def qid_to_label(qid: str, num_qubits: int) -> str:
    """Convert a numeric qid string to a label with dynamic zero-padding.

    The padding width is determined by the total number of qubits in the system,
    with a minimum of 2 digits. For example:
      - 64-qubit system:  qid='5' -> 'Q05'  (2 digits)
      - 144-qubit system: qid='5' -> 'Q005' (3 digits)

    Args:
    ----
        qid: Numeric qubit identifier as a string (e.g., '0', '5', '63')
        num_qubits: Total number of qubits in the system

    Returns:
    -------
        Qubit label string (e.g., 'Q00', 'Q005')

    Raises:
    ------
        ValueError: If qid is not a purely numeric string

    """
    if re.fullmatch(r"\d+", qid):
        width = max(2, len(str(num_qubits)))
        return "Q" + qid.zfill(width)
    error_message = "Invalid qid format."
    raise ValueError(error_message)


@lru_cache(maxsize=128)
def _get_chip_size(project_id: str, chip_id: str) -> int:
    """Get chip size from DB with caching.

    Results are cached to avoid repeated DB lookups when processing
    many qids for the same chip (e.g., parallel calibration workers).

    """
    from qdash.repository import MongoChipRepository

    chip_repo = MongoChipRepository()
    chip = chip_repo.find_by_id(project_id=project_id, chip_id=chip_id)
    if chip is None:
        logger.warning(
            "Chip not found for project=%s, chip=%s, defaulting to %d qubits",
            project_id,
            chip_id,
            DEFAULT_NUM_QUBITS,
        )
        return DEFAULT_NUM_QUBITS
    return chip.size


def qid_to_label_from_chip(qid: str, *, project_id: str, chip_id: str) -> str:
    """Convert a numeric qid string to a label, resolving chip size from DB.

    Supports both qubit qids (e.g. "16" -> "Q16") and coupling qids
    (e.g. "16-22" -> "Q16-Q22"). The padding width is determined by
    the chip's size stored in MongoDB. Chip size is cached per
    (project_id, chip_id) pair.

    Args:
    ----
        qid: Numeric qubit identifier (e.g., '16') or coupling identifier (e.g., '16-22')
        project_id: Project identifier for DB lookup
        chip_id: Chip identifier for DB lookup

    Returns:
    -------
        Qubit label string (e.g., 'Q16', 'Q016', 'Q16-Q22')

    """
    num_qubits = _get_chip_size(project_id, chip_id)

    if "-" in qid:
        return "-".join(qid_to_label(q, num_qubits) for q in qid.split("-"))
    return qid_to_label(qid, num_qubits)
