"""Translate an optional ``system_id`` query into the qubits and MUXes it covers.

Chip pages and metrics show the whole chip by default. A ``system_id`` narrows
current-value endpoints to the qubits of that Qubex System (via the wiring) and
history endpoints to task results recorded with that ``system_id``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import HTTPException

from qdash.common.config.qubex_layout import QubexLayout
from qdash.common.config.system_catalog import SystemCatalog

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SystemScope:
    """Qubits and MUXes driven by one System of a chip."""

    chip_id: str
    system_id: str
    qids: frozenset[str]
    mux_ids: frozenset[int]

    def includes(self, target: str) -> bool:
        """Whether a qubit (``"3"``) or coupling (``"3-4"``) lies entirely in the System."""
        return all(part in self.qids for part in str(target).split("-"))

    def filter_targets(self, targets: list[str] | None) -> list[str]:
        """``targets`` restricted to the System; every System qubit when ``targets`` is None."""
        if targets is None:
            return sorted(self.qids, key=_qid_sort_key)
        return [target for target in targets if self.includes(target)]


def _qid_sort_key(qid: str) -> tuple[int, str]:
    return (int(qid), qid) if qid.isdigit() else (1 << 30, qid)


def _catalog(chip_id: str) -> SystemCatalog:
    return SystemCatalog(QubexLayout.detect(), chip_id)


def resolve_system_scope(chip_id: str, system_id: str | None) -> SystemScope | None:
    """The scope of ``system_id`` on ``chip_id``; None when no System was requested.

    Raises:
        HTTPException: 404 when the System does not drive the chip or the
            configuration cannot be read.

    """
    if system_id is None or not str(system_id).strip():
        return None
    wanted = str(system_id).strip()
    try:
        catalog = _catalog(chip_id)
        entry = catalog.entry(wanted)
        size = catalog.mux_size()
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"System {wanted} does not drive chip {chip_id}"
        ) from None
    except (OSError, ValueError, LookupError) as exc:
        logger.warning("Could not read the Systems of chip %s: %s", chip_id, exc)
        raise HTTPException(
            status_code=404, detail=f"Systems of chip {chip_id} are not configured"
        ) from None
    qids = frozenset(
        str(mux_id * size + offset) for mux_id in entry.mux_ids for offset in range(size)
    )
    return SystemScope(chip_id=chip_id, system_id=wanted, qids=qids, mux_ids=entry.mux_ids)
