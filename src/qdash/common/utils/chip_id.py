"""Validate chip IDs used as directory names across QDash."""

import re

CHIP_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]*"
RESERVED_CHIP_IDS = frozenset({"template", "archive", "schemas", "scripts"})


def validate_chip_id(chip_id: str) -> str:
    """Reject IDs that cannot safely name a chip directory."""
    if not re.fullmatch(CHIP_ID_PATTERN, chip_id):
        raise ValueError(
            "Chip ID must start with a letter or digit and contain only "
            "letters, digits, '.', '-' and '_'"
        )
    if chip_id in RESERVED_CHIP_IDS:
        raise ValueError(f"Chip ID '{chip_id}' is a reserved configuration directory")
    return chip_id
