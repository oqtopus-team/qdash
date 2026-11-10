"""Read explicit UI target overrides without changing workflow source or signatures."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from qdash.datamodel.flow_targets import TARGET_CONTEXT_KEY, FlowTargetOverride
from qdash.workflow.service.targets import CouplingTargets, MuxTargets, QubitTargets, Target

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from qdash.workflow.service.steps.base import Step

PairSchedule = list[list[tuple[str, str]]]


def read_target_override() -> FlowTargetOverride | None:
    """Read only the current flow's override; isolated child tasks keep their subsets."""
    try:
        from prefect.context import FlowRunContext
    except ImportError:
        return None

    context = FlowRunContext.get()
    if context is None or context.flow_run is None:
        return None
    value = context.flow_run.context.get(TARGET_CONTEXT_KEY)
    return FlowTargetOverride.model_validate(value) if value is not None else None


def override_target(target: Target, override: FlowTargetOverride | None) -> Target:
    """Replace initial pipeline targets only, preserving later filtering steps."""
    if override is None:
        return target
    if override.coupling_pairs is not None:
        if not isinstance(target, CouplingTargets):
            raise ValueError("Coupling pair overrides require CouplingTargets")
    elif not isinstance(target, (MuxTargets, QubitTargets)):
        raise ValueError("Execution target overrides require MuxTargets or QubitTargets")
    return target_from_override(override)


def target_from_override(override: FlowTargetOverride) -> Target:
    """Build a fresh target so caller mutation cannot alter the run context."""
    if override.mux_ids is not None:
        return MuxTargets(list(override.mux_ids), list(override.exclude_qids))
    if override.coupling_pairs is not None:
        return CouplingTargets(override.pairs())
    return QubitTargets(list(override.qids or []))


def override_pipeline(
    target: Target,
    steps: Sequence[Step],
    override: FlowTargetOverride | None,
    schedule_pairs: Callable[[list[tuple[str, str]]], PairSchedule],
) -> tuple[Target, list[Step]]:
    """Apply an override to the pipeline targets and, for pairs, to its CR schedule.

    A coupling override replaces every ``SetCRSchedule`` with a schedule that
    ``schedule_pairs`` builds from the selected pairs, so a source schedule can
    neither add pairs nor reverse them. Pipelines without ``SetCRSchedule``, or
    with ``GenerateCRSchedule`` (which rebuilds pairs from qubits), are rejected
    because they would calibrate pairs other than the selection.
    """
    from qdash.workflow.service.steps import GenerateCRSchedule, SetCRSchedule

    new_target = override_target(target, override)
    if override is None or override.coupling_pairs is None:
        return new_target, list(steps)
    if any(isinstance(step, GenerateCRSchedule) for step in steps):
        raise ValueError("Coupling pair overrides cannot run with GenerateCRSchedule")
    if not any(isinstance(step, SetCRSchedule) for step in steps):
        raise ValueError("Coupling pair overrides require a SetCRSchedule step")
    schedule = schedule_pairs(override.pairs())
    return new_target, [
        replace(step, schedule=[list(group) for group in schedule])
        if isinstance(step, SetCRSchedule)
        else step
        for step in steps
    ]
