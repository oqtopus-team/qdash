"""Read explicit UI target overrides without changing workflow source or signatures."""

from qdash.datamodel.flow_targets import TARGET_CONTEXT_KEY, FlowTargetOverride
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target


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
    if not isinstance(target, (MuxTargets, QubitTargets)):
        raise ValueError("Execution target overrides require MuxTargets or QubitTargets")
    return target_from_override(override)


def target_from_override(override: FlowTargetOverride) -> Target:
    """Build a fresh target so caller mutation cannot alter the run context."""
    if override.mux_ids is not None:
        return MuxTargets(list(override.mux_ids), list(override.exclude_qids))
    return QubitTargets(list(override.qids or []))
