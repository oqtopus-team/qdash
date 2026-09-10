"""Resolve calibration targets to hardware resources used for execution locking."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml

from qdash.common.config.path_resolver import resolve_config_base_path
from qdash.common.wiring_resources import mux_module_resources


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
    mux_ids = _target_mux_ids(parameters)
    if not normalized_chip_id or mux_ids is None:
        return ExecutionResourceScope(chip_id=normalized_chip_id, exclusive=True)

    resources = {f"mux:{mux_id}" for mux_id in mux_ids}
    wiring = _load_wiring(normalized_chip_id)
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


def resolve_workflow_resource_scope(chip_id: str) -> ExecutionResourceScope:
    """Saved Python flows have unknown future steps: reserve the complete chip."""
    return ExecutionResourceScope(chip_id.strip(), exclusive=True)


def _target_mux_ids(parameters: dict[str, Any]) -> set[int] | None:
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
            resolved.add(int(match.group(1)) // 4)
    return resolved or None


def _load_wiring(chip_id: str) -> dict[int, tuple[str, ...]]:
    path = resolve_config_base_path() / chip_id / "config" / "wiring.yaml"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(raw, dict):
        return {}
    # Match the schedulers' chip-keyed and group-keyed wiring formats.
    groups = [raw[chip_id]] if chip_id in raw else list(raw.values())
    if any(not isinstance(group, list) for group in groups):
        return {}
    result: dict[int, tuple[str, ...]] = {}
    for group in groups:
        for entry in group:
            if not isinstance(entry, dict):
                return {}
            mux_id = entry.get("mux")
            if type(mux_id) is not int or mux_id < 0 or mux_id in result:
                return {}
            ctrl = entry.get("ctrl")
            read_out = entry.get("read_out")
            if (
                not isinstance(ctrl, list)
                or not ctrl
                or any(not isinstance(channel, str) or not channel.strip() for channel in ctrl)
                or not isinstance(read_out, str)
                or not read_out.strip()
            ):
                return {}
            resources = mux_module_resources(entry)
            for key in ("ctrl", "read_out", "read_in", "pump"):
                value = entry.get(key)
                values = value if isinstance(value, list) else [value]
                for channel in values:
                    if channel in (None, ""):
                        continue
                    if not isinstance(channel, str):
                        return {}
                    resources.add(f"channel:{channel}")
            result[mux_id] = tuple(sorted(resources))
    return result
