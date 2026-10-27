"""Refuse runs whose targets span several Qubex Systems with one HTTP 400.

One run is one ``Experiment`` and one Experiment drives one System. The
pipeline strategies split MUX groups by System themselves; a single run from
the Tasks page, a saved flow with explicit targets, or a coupling whose qubits
sit on different Systems cannot be split and is rejected before dispatch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from qdash.common.config.qubex_layout import QubexLayout
from qdash.common.config.system_catalog import SystemCatalog, SystemSplitRequired

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger(__name__)

SYSTEM_SPLIT_CODE = "system_split_required"


def system_split_detail(exc: SystemSplitRequired) -> dict[str, Any]:
    """The 400 payload: ``{"message", "code", "chip_id", "systems": {id: [targets]}}``."""
    return {
        "message": str(exc),
        "code": SYSTEM_SPLIT_CODE,
        "chip_id": exc.chip_id,
        "systems": {system_id: list(qids) for system_id, qids in exc.assignment.items()},
    }


def _catalog(chip_id: str) -> SystemCatalog:
    return SystemCatalog(QubexLayout.detect(), chip_id)


def ensure_single_system(
    chip_id: str,
    qids: Iterable[str] | None,
    *,
    mux_ids: Iterable[int] | None = None,
) -> str | None:
    """The System that drives every target, or None when it cannot be determined.

    Raises:
        HTTPException: 400 with :func:`system_split_detail` when the targets span
            Systems or a coupling crosses a System boundary.

    """
    chip = str(chip_id or "").strip()
    targets = [str(qid).strip() for qid in (qids or []) if str(qid).strip()]
    muxes = [int(mux) for mux in mux_ids] if mux_ids is not None else None
    if not chip or (not targets and not muxes):
        return None
    try:
        return _catalog(chip).resolve_single(targets, mux_ids=muxes)
    except SystemSplitRequired as exc:
        raise HTTPException(status_code=400, detail=system_split_detail(exc)) from exc
    except (OSError, ValueError, LookupError, TypeError) as exc:
        logger.debug("Could not resolve the System of %s on %s: %s", targets, chip, exc)
        return None


def targets_from_parameters(parameters: dict[str, Any]) -> tuple[list[str], list[int] | None]:
    """``(qids, mux_ids)`` named by run parameters (``qid``, ``qids``, ``mux_ids``)."""
    qids: list[str] = []
    single = parameters.get("qid")
    if isinstance(single, str) and single.strip():
        qids.append(single.strip())
    many = parameters.get("qids")
    if isinstance(many, list):
        qids.extend(str(qid).strip() for qid in many if str(qid).strip())
    mux_ids = parameters.get("mux_ids")
    muxes: list[int] | None = None
    if isinstance(mux_ids, list) and mux_ids:
        try:
            muxes = [int(mux) for mux in mux_ids]
        except (TypeError, ValueError):
            muxes = None
    return qids, muxes
