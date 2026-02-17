"""Qubit utility functions shared between API and Workflow modules."""

import re


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
