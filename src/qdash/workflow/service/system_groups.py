"""Group MUX-level work by Qubex System and decide which Systems run concurrently.

One Qubex ``Experiment`` drives one System, so every isolated session must stay
inside a System. Systems of the same chip share no hardware when their backends
differ (quel1 vs quel3) and can run at the same time; Systems with the same
backend may share a clock master, so they run one after another unless
``workflow.yaml`` ``systems.parallel_same_backend`` is true.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from qdash.common.config.loader import ConfigLoader

if TYPE_CHECKING:
    from collections.abc import Sequence

    from qdash.common.config.system_catalog import SystemCatalog

logger = logging.getLogger(__name__)


def parallel_same_backend_enabled() -> bool:
    """``workflow.yaml`` ``systems.parallel_same_backend`` (default false)."""
    settings = ConfigLoader.load_workflow()
    systems = settings.get("systems") if isinstance(settings, dict) else None
    if not isinstance(systems, dict):
        return False
    return bool(systems.get("parallel_same_backend", False))


@dataclass
class SystemWave:
    """Groups that run at the same time, each tagged with its System.

    ``groups[i]`` is driven by ``group_system_ids[i]``; ``None`` means the chip's
    System could not be resolved and the session derives it from its targets.
    """

    system_ids: tuple[str, ...]
    groups: list[list[str]] = field(default_factory=list)
    group_system_ids: list[str | None] = field(default_factory=list)

    @property
    def qids(self) -> list[str]:
        return [qid for group in self.groups for qid in group]

    def worker_kwargs(self, name: str) -> dict[str, list[str | None]]:
        """``{name: group_system_ids}`` when a System is known, else nothing."""
        if all(system_id is None for system_id in self.group_system_ids):
            return {}
        return {name: list(self.group_system_ids)}


def system_of_group(catalog: SystemCatalog, group: Sequence[str]) -> str | None:
    """The System of a MUX group, or None when the catalog cannot say."""
    if not group:
        return None
    try:
        systems = {catalog.system_of_qid(qid) for qid in group}
    except (OSError, ValueError, LookupError, TypeError) as exc:
        logger.debug("Could not resolve the System of %s: %s", list(group), exc)
        return None
    if any(not isinstance(system_id, str) for system_id in systems):
        return None
    if len(systems) != 1:
        raise ValueError(f"MUX group {list(group)} spans Systems {sorted(systems)}")
    return next(iter(systems))


def plan_system_waves(
    groups: Sequence[Sequence[str]],
    catalog: SystemCatalog,
    *,
    parallel_same_backend: bool | None = None,
) -> list[SystemWave]:
    """Split parallel groups into waves that may run concurrently.

    Groups of one System stay together. Systems whose backends differ share a
    wave; Systems with the same backend get separate waves unless
    ``parallel_same_backend`` is true. Groups whose System is unknown form a
    wave of their own, keeping today's behaviour for unreadable configurations.
    """
    if parallel_same_backend is None:
        parallel_same_backend = parallel_same_backend_enabled()

    by_system: dict[str | None, list[list[str]]] = {}
    for group in groups:
        if not group:
            continue
        by_system.setdefault(system_of_group(catalog, group), []).append(list(group))
    if not by_system:
        return []

    waves: list[SystemWave] = []
    unknown = by_system.pop(None, None)
    if unknown:
        waves.append(SystemWave((), unknown, [None] * len(unknown)))
    if len(by_system) == 1:
        (system_id, system_groups), *_ = by_system.items()
        assert system_id is not None
        waves.append(SystemWave((system_id,), system_groups, [system_id] * len(system_groups)))
        return waves

    backends: dict[str, str] = {}
    for system_id in by_system:
        assert system_id is not None
        try:
            backends[system_id] = catalog.entry(system_id).backend
        except (KeyError, OSError, ValueError):
            backends[system_id] = system_id
    placed: list[tuple[list[str], dict[str, Any]]] = []  # (system ids, wave payload)
    for system_id, system_groups in by_system.items():
        assert system_id is not None
        target: dict[str, Any] | None = None
        for ids, payload in placed:
            if parallel_same_backend or all(
                backends[other] != backends[system_id] for other in ids
            ):
                ids.append(system_id)
                target = payload
                break
        if target is None:
            target = {"groups": [], "systems": []}
            placed.append(([system_id], target))
        target["groups"].extend(system_groups)
        target["systems"].extend([system_id] * len(system_groups))
    for ids, payload in placed:
        waves.append(SystemWave(tuple(ids), payload["groups"], payload["systems"]))
    return waves
