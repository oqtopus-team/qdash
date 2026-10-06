"""System flow that runs a declarative calibration pipeline spec.

``CalibrationPipelineSpec`` (``qdash.datamodel.calibration_pipeline``) is what
an agent or the UI submits through ``POST /calibration-pipelines/execute``. The
API validates it; this flow only maps it onto the same Step classes the
templates use and hands them to ``CalibService.run``. Nothing in the spec can
reach code outside that mapping.

Registered on worker startup as the ``system-calibration-pipeline`` deployment
(see ``register_system_flows.py``), so no FlowDocument is needed.
"""

from __future__ import annotations

from typing import Any

from prefect import flow, get_run_logger

from qdash.datamodel.calibration_pipeline import (
    BringUpStep,
    CalibrationPipelineSpec,
    ConfigureAllStep,
    CustomOneQubitStep,
    CustomTwoQubitStep,
    FilterByMetricStep,
    FilterByStatusStep,
    GenerateCRScheduleStep,
    OneQubitCheckStep,
    OneQubitFineTuneStep,
    PipelineStep,
    TwoQubitCalibrationStep,
)
from qdash.workflow.service.calib_service import (
    CalibService,
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
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
    Step,
    TwoQubitCalibration,
)
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target


def build_targets(spec: CalibrationPipelineSpec) -> Target:
    """The Target the spec starts from."""
    targets = spec.targets
    if targets.mux_ids:
        return MuxTargets(mux_ids=list(targets.mux_ids), exclude_qids=list(targets.exclude_qids))
    assert targets.qids is not None  # the spec validator guarantees one of the two
    return QubitTargets(qids=list(targets.qids))


def build_step(step: PipelineStep) -> Step:
    """The Step object for one spec entry."""
    if isinstance(step, ConfigureAllStep):
        return ConfigureAll(mux_ids=list(step.mux_ids) if step.mux_ids is not None else None)
    if isinstance(step, BringUpStep):
        return BringUp(tasks=list(step.tasks)) if step.tasks is not None else BringUp()
    if isinstance(step, OneQubitCheckStep):
        return OneQubitCheck(
            mode=step.mode,
            tasks=list(step.tasks) if step.tasks is not None else None,
            configure=step.configure,
        )
    if isinstance(step, OneQubitFineTuneStep):
        return OneQubitFineTune(
            mode=step.mode,
            tasks=list(step.tasks) if step.tasks is not None else None,
            configure=step.configure,
        )
    if isinstance(step, CustomOneQubitStep):
        return CustomOneQubit(step_name=step.step_name, tasks=list(step.tasks), mode=step.mode)
    if isinstance(step, FilterByStatusStep):
        return FilterByStatus()
    if isinstance(step, FilterByMetricStep):
        return FilterByMetric(metric=step.metric, threshold=step.threshold)
    if isinstance(step, GenerateCRScheduleStep):
        return GenerateCRSchedule(max_parallel_ops=step.max_parallel_ops, inverse=step.inverse)
    if isinstance(step, TwoQubitCalibrationStep):
        return TwoQubitCalibration(
            tasks=list(step.tasks) if step.tasks is not None else None,
            max_parallel_ops=step.max_parallel_ops,
        )
    if isinstance(step, CustomTwoQubitStep):
        return CustomTwoQubit(
            step_name=step.step_name,
            tasks=list(step.tasks),
            max_parallel_ops=step.max_parallel_ops,
        )
    raise ValueError(f"unsupported pipeline step: {step!r}")


def build_steps(spec: CalibrationPipelineSpec) -> list[Step]:
    """Step objects for the whole spec, in order."""
    return [build_step(step) for step in spec.steps]


@flow(
    name="calibration-pipeline",
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def calibration_pipeline(
    username: str,
    chip_id: str,
    spec: dict[str, Any],
    project_id: str | None = None,
    flow_name: str | None = None,
    tags: list[str] | None = None,
    backend_name: str | None = None,
) -> Any:
    """Run one validated pipeline spec as a calibration.

    Args:
        username: User the execution is attributed to.
        chip_id: Chip to calibrate.
        spec: ``CalibrationPipelineSpec`` as JSON. Re-validated here so a spec
            that bypassed the API is still held to the same shape.
        project_id: Project the execution belongs to (injected by the API).
        flow_name: Display name of the execution; defaults to the spec name.
        tags: Extra tags; merged with the spec's tags.
        backend_name: Hardware backend; defaults to the configured backend.
    """
    logger = get_run_logger()
    parsed = CalibrationPipelineSpec.model_validate(spec)
    targets = build_targets(parsed)
    steps = build_steps(parsed)
    all_tags = sorted({*(tags or []), *parsed.tags, "pipeline"})
    name = flow_name or parsed.name

    logger.info(
        f"Pipeline '{name}': {len(steps)} steps, {len(parsed.all_tasks())} task runs, "
        f"targets={parsed.targets.model_dump(exclude_none=True)}"
    )

    cal = CalibService(
        username,
        chip_id,
        flow_name=name,
        tags=all_tags,
        project_id=project_id,
        backend_name=backend_name,
        task_run_parameters=parsed.task_run_parameters or None,
        default_run_parameters=parsed.default_run_parameters or None,
    )
    return cal.run(targets, steps=steps)
