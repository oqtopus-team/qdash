"""Plan the complete hardware reservation before executing pipeline steps."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qdash.common.execution_resources import (
    ExecutionResourceScope,
    merge_resource_scopes,
    resolve_execution_resource_scope,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from qdash.common.mux_mapping import MuxMapping
    from qdash.workflow.service.steps.base import Step
    from qdash.workflow.service.targets import Target


def plan_pipeline_resources(
    chip_id: str,
    targets: Target,
    steps: Sequence[Step],
    muxes: list[int] | None = None,
    *,
    mux_mapping: MuxMapping | None = None,
) -> ExecutionResourceScope:
    """Union known step targets; unknown steps conservatively reserve the chip.

    Only exact built-in step classes have known target semantics. Subclasses and
    custom steps may touch additional hardware and therefore require exclusivity.
    No step is executed to discover its resource requirements.

    ``mux_mapping`` is the chip's MUX membership; without it the legacy
    ``qid // 4`` mapping applies. Targets outside the mapping reserve the chip.
    """
    from qdash.common.mux_mapping import MuxMappingError

    def scope_of(parameters: dict[str, Any]) -> ExecutionResourceScope:
        return resolve_execution_resource_scope(chip_id, parameters, mux_mapping=mux_mapping)

    from qdash.workflow.service.steps import (
        BringUp,
        ConfigureAll,
        CustomOneQubit,
        CustomTwoQubit,
        FilterByMetric,
        FilterByStatus,
        GenerateCRSchedule,
        OneQubitCheck,
        OneQubitFineTune,
        TwoQubitCalibration,
    )

    try:
        qids = targets.to_qids(chip_id, mux_mapping=mux_mapping)
    except MuxMappingError:
        return ExecutionResourceScope(chip_id, exclusive=True)
    scope = scope_of({"qids": qids})
    if muxes is not None:
        scope = merge_resource_scopes(scope, scope_of({"mux_ids": muxes}))
    target_scoped_steps = {
        BringUp,
        CustomOneQubit,
        CustomTwoQubit,
        OneQubitCheck,
        OneQubitFineTune,
        TwoQubitCalibration,
        FilterByMetric,
        FilterByStatus,
        GenerateCRSchedule,
    }
    for step in steps:
        if type(step) is ConfigureAll:
            assert isinstance(step, ConfigureAll)
            if step.mux_ids is not None:
                scope = merge_resource_scopes(scope, scope_of({"mux_ids": step.mux_ids}))
        elif type(step) not in target_scoped_steps:
            return ExecutionResourceScope(chip_id, exclusive=True)
        manual = getattr(step, "rounds", None) if type(step) in target_scoped_steps else None
        if manual and getattr(step, "execution_mode", None) == "manual":
            # Manual rounds name their own qubits; reserve them too.
            qids = [
                qid
                for round_ in manual
                for target in round_
                for qid in ((target,) if isinstance(target, str) else target)
            ]
            scope = merge_resource_scopes(scope, scope_of({"qids": qids}))
    return scope
