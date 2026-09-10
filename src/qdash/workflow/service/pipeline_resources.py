"""Plan the complete hardware reservation before executing pipeline steps."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qdash.common.execution_resources import (
    ExecutionResourceScope,
    merge_resource_scopes,
    resolve_execution_resource_scope,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from qdash.workflow.service.steps.base import Step
    from qdash.workflow.service.targets import Target


def plan_pipeline_resources(
    chip_id: str, targets: Target, steps: Sequence[Step], muxes: list[int] | None = None
) -> ExecutionResourceScope:
    """Union known step targets; unknown steps conservatively reserve the chip.

    Only exact built-in step classes have known target semantics. Subclasses and
    custom steps may touch additional hardware and therefore require exclusivity.
    No step is executed to discover its resource requirements.
    """
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
        SetCRSchedule,
        TwoQubitCalibration,
    )

    scope = resolve_execution_resource_scope(chip_id, {"qids": targets.to_qids(chip_id)})
    if muxes is not None:
        scope = merge_resource_scopes(
            scope, resolve_execution_resource_scope(chip_id, {"mux_ids": muxes})
        )
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
                scope = merge_resource_scopes(
                    scope, resolve_execution_resource_scope(chip_id, {"mux_ids": step.mux_ids})
                )
        elif type(step) is SetCRSchedule:
            assert isinstance(step, SetCRSchedule)
            qids = [qid for group in step.schedule for pair in group for qid in pair]
            if qids:
                scope = merge_resource_scopes(
                    scope, resolve_execution_resource_scope(chip_id, {"qids": qids})
                )
        elif type(step) not in target_scoped_steps:
            return ExecutionResourceScope(chip_id, exclusive=True)
    return scope
