"""Wiring configuration loading shared by the 1-qubit and CR schedulers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths


def load_wiring_config(chip_id: str, wiring_config_path: str | Path | None) -> list[dict[str, Any]]:
    """MUX entries of the chip's ``wiring.yaml``.

    ``wiring_config_path`` defaults to the QubexPaths wiring path of ``chip_id``.
    A top-level ``chip_id`` key selects that chip's list; otherwise the top-level
    keys are group names (e.g. ``"A2"``) whose lists are flattened in file order.

    Raises:
        FileNotFoundError: The wiring file does not exist.
    """
    if wiring_config_path is not None:
        wiring_path = Path(wiring_config_path)
    else:
        wiring_path = get_qubex_paths().wiring_yaml(chip_id)

    if not wiring_path.exists():
        msg = f"Wiring config not found: {wiring_path}"
        raise FileNotFoundError(msg)

    yaml_data = yaml.safe_load(wiring_path.read_text())
    if chip_id in yaml_data:
        entries: list[dict[str, Any]] = yaml_data[chip_id]
        return entries
    return [entry for group in yaml_data.values() for entry in group]
