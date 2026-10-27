"""Resolve calibration targets to hardware resources used for execution locking."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from qdash.common.config.path_resolver import resolve_config_base_path
from qdash.common.config.qubex_layout import QubexLayout
from qdash.common.config.system_catalog import DEFAULT_MUX_SIZE, SystemCatalog

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionResourceScope:
    """Hardware scope claimed by one calibration execution."""

    chip_id: str
    resources: tuple[str, ...] = ()
    exclusive: bool = False


def resolve_execution_resource_scope(
    chip_id: str,
    parameters: dict[str, Any],
) -> ExecutionResourceScope:
    """Resolve flow parameters into a conservative hardware resource scope.

    Explicit MUX targets and qubit/coupling targets are mapped to their wiring
    modules and channels. Unresolved targets or wiring claim the whole chip.
    """
    normalized_chip_id = chip_id.strip()
    if not normalized_chip_id:
        return ExecutionResourceScope(chip_id=normalized_chip_id, exclusive=True)
    catalog = _catalog(normalized_chip_id)
    mux_ids = _target_mux_ids(parameters, _mux_size(catalog))
    if mux_ids is None:
        return ExecutionResourceScope(chip_id=normalized_chip_id, exclusive=True)

    resources = {f"mux:{mux_id}" for mux_id in mux_ids}
    wiring = _load_wiring(catalog)
    if any(mux_id not in wiring for mux_id in mux_ids):
        return ExecutionResourceScope(chip_id=normalized_chip_id, exclusive=True)
    for mux_id in mux_ids:
        resources.update(wiring[mux_id])
    return ExecutionResourceScope(
        chip_id=normalized_chip_id,
        resources=tuple(sorted(resources)),
    )


def scopes_conflict(left: ExecutionResourceScope, right: ExecutionResourceScope) -> bool:
    """Return whether two scopes contend for the same physical hardware."""
    if left.chip_id and right.chip_id and left.chip_id != right.chip_id:
        return False
    if left.exclusive or right.exclusive:
        return True
    return bool(set(left.resources).intersection(right.resources))


def merge_resource_scopes(
    left: ExecutionResourceScope, right: ExecutionResourceScope
) -> ExecutionResourceScope:
    """Keep every reservation when planning additional steps on the same chip."""
    if left.chip_id != right.chip_id:
        raise ValueError("A pipeline cannot change chips within its hardware reservation")
    return ExecutionResourceScope(
        left.chip_id,
        tuple(sorted(set(left.resources).union(right.resources))),
        left.exclusive or right.exclusive,
    )


def scope_contains(reserved: ExecutionResourceScope, requested: ExecutionResourceScope) -> bool:
    """Whether an operation is entirely covered by the original reservation."""
    if reserved.chip_id != requested.chip_id:
        return False
    return reserved.exclusive or (
        not requested.exclusive and set(requested.resources).issubset(reserved.resources)
    )


def resolve_workflow_resource_scope(
    chip_id: str, system_id: str | None = None
) -> ExecutionResourceScope:
    """Saved Python flows have unknown future steps: reserve the complete chip.

    A flow that declares the Qubex ``system_id`` it drives reserves every
    resource of that System instead, so Systems of the same chip can run
    concurrently. An unknown System or unreadable configuration falls back to
    the whole chip.
    """
    chip = chip_id.strip()
    if system_id:
        try:
            resources = _catalog(chip).resources_of(str(system_id).strip())
        except (OSError, ValueError, LookupError, TypeError):
            return ExecutionResourceScope(chip, exclusive=True)
        return ExecutionResourceScope(chip, tuple(resources), exclusive=False)
    return ExecutionResourceScope(chip, exclusive=True)


def _catalog(chip_id: str) -> SystemCatalog:
    return SystemCatalog(QubexLayout.detect(resolve_config_base_path()), chip_id)


def _mux_size(catalog: SystemCatalog) -> int:
    try:
        return catalog.mux_size()
    except (OSError, ValueError, LookupError):
        return DEFAULT_MUX_SIZE


def _target_mux_ids(
    parameters: dict[str, Any], mux_size: int = DEFAULT_MUX_SIZE
) -> set[int] | None:
    mux_ids = parameters.get("mux_ids")
    if isinstance(mux_ids, list) and mux_ids:
        try:
            return {int(mux_id) for mux_id in mux_ids}
        except (TypeError, ValueError):
            return None

    targets: list[Any] | None = None
    qids = parameters.get("qids")
    if isinstance(qids, list) and qids:
        targets = qids
    elif parameters.get("qid") not in (None, ""):
        targets = [parameters["qid"]]
    if targets is None:
        return None

    resolved: set[int] = set()
    for target in targets:
        parts = str(target).split("-")
        for part in parts:
            match = re.search(r"(\d+)$", part.strip())
            if match is None:
                return None
            resolved.add(int(match.group(1)) // mux_size)
    return resolved or None


def _load_wiring(catalog: SystemCatalog) -> dict[int, tuple[str, ...]]:
    """MUX -> lockable resources of the chip's Systems; empty when unreadable.

    The catalog reads only the rows of Systems that drive this chip, so a shared
    ``wiring.yaml`` holding other chips does not make the lock fall back to the
    whole chip. Any configuration error does: callers treat ``{}`` as exclusive.
    """
    try:
        return catalog.mux_resources()
    except (OSError, ValueError, LookupError, TypeError) as exc:
        logger.warning(
            "Wiring for chip %s is unusable for resource locking: %s", catalog.chip_id, exc
        )
        return {}
