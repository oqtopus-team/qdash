"""Read explicit UI target overrides without changing workflow source or signatures."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qdash.datamodel.flow_targets import TARGET_CONTEXT_KEY, FlowTargetOverride
from qdash.workflow.service.targets import CouplingTargets, MuxTargets, QubitTargets, Target

if TYPE_CHECKING:
    from collections.abc import Sequence

    from qdash.workflow.service.steps.base import Step


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
) -> tuple[Target, list[Step]]:
    """Apply an override to the pipeline targets; the steps are never rewritten.

    A pipeline with a ``manual`` step rejects every override: its rounds name
    their own targets and are never regrouped.

    A coupling override replaces the initial ``CouplingTargets``. Automatic
    two-qubit steps and ``GenerateCRSchedule`` then group exactly the selected
    directed pairs, so the pipeline must consist of built-in steps only (a
    custom step could calibrate other pairs) and run at least one two-qubit
    step.
    """
    from qdash.common.manual_rounds import MANUAL_TARGET_OVERRIDE_REASON

    if override is not None:
        manual = [
            getattr(step, "name", type(step).__name__)
            for step in steps
            if getattr(step, "execution_mode", None) == "manual"
        ]
        if manual:
            # Never replace written rounds with other targets or generated groups.
            raise ValueError(f"{MANUAL_TARGET_OVERRIDE_REASON} Manual steps: {', '.join(manual)}")
    new_target = override_target(target, override)
    if override is not None and override.coupling_pairs is not None:
        _check_pair_pipeline(steps)
    return new_target, list(steps)


def _check_pair_pipeline(steps: Sequence[Step]) -> None:
    """Reject pipelines that could run pairs other than the selected ones."""
    from qdash.workflow.service import steps as builtin

    pair_steps = {builtin.CustomTwoQubit, builtin.TwoQubitCalibration}
    known = {
        *pair_steps,
        builtin.GenerateCRSchedule,
        builtin.BringUp,
        builtin.ConfigureAll,
        builtin.CustomOneQubit,
        builtin.OneQubitCheck,
        builtin.OneQubitFineTune,
        builtin.FilterByMetric,
        builtin.FilterByStatus,
    }
    custom = sorted({type(step).__name__ for step in steps if type(step) not in known})
    if custom:
        raise ValueError(
            f"Coupling pair overrides require built-in steps only; got {', '.join(custom)}"
        )
    if not any(type(step) in pair_steps for step in steps):
        raise ValueError(
            "Coupling pair overrides require a CustomTwoQubit or TwoQubitCalibration step"
        )
