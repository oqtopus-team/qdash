"""Qubit utility functions shared between API and Workflow modules."""

import logging
import re
from functools import lru_cache

logger = logging.getLogger(__name__)

DEFAULT_NUM_QUBITS = 64


def qid_to_label(qid: str, num_qubits: int) -> str:
    """Convert a numeric qid string to a label with dynamic zero-padding."""
    if re.fullmatch(r"\d+", qid):
        width = max(2, len(str(num_qubits)))
        return "Q" + qid.zfill(width)
    raise ValueError("Invalid qid format.")


@lru_cache(maxsize=128)
def _get_chip_size(project_id: str, chip_id: str) -> int:
    """Get chip size from DB with caching."""
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
    """Convert a numeric qid string to a label, resolving chip size from DB."""
    num_qubits = _get_chip_size(project_id, chip_id)

    if "-" in qid:
        return "-".join(qid_to_label(q, num_qubits) for q in qid.split("-"))
    return qid_to_label(qid, num_qubits)
