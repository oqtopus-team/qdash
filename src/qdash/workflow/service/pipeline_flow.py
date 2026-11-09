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
    SPEC_VERSION,
    STEP_CATALOG,
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
    migrate_pipeline_spec,
    step_id,
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
    """The Step object for one spec entry.

    Task calls are passed through unchanged; the Step classes apply the same
    defaults and call id rules as the spec.
    """
    if isinstance(step, ConfigureAllStep):
        return ConfigureAll(
            mux_ids=list(step.mux_ids) if step.mux_ids is not None else None,
            call=step.call,
            step_id=step.step_id,
        )
    if isinstance(step, BringUpStep):
        if step.tasks is not None:
            return BringUp(tasks=list(step.tasks), step_id=step.step_id)
        return BringUp(step_id=step.step_id)
    if isinstance(step, OneQubitCheckStep):
        return OneQubitCheck(
            mode=step.mode,
            tasks=list(step.tasks) if step.tasks is not None else None,
            configure=step.configure,
            step_id=step.step_id,
        )
    if isinstance(step, OneQubitFineTuneStep):
        return OneQubitFineTune(
            mode=step.mode,
            tasks=list(step.tasks) if step.tasks is not None else None,
            configure=step.configure,
            step_id=step.step_id,
        )
    if isinstance(step, CustomOneQubitStep):
        return CustomOneQubit(
            step_name=step.step_name,
            tasks=list(step.tasks),
            mode=step.mode,
            continue_on_failure=step.continue_on_failure,
        )
    if isinstance(step, FilterByStatusStep):
        return FilterByStatus(step=step.step, call_id=step.call_id)
    if isinstance(step, FilterByMetricStep):
        return FilterByMetric(
            metric=step.metric,
            threshold=step.threshold,
            step=step.step,
            call_id=step.call_id,
        )
    if isinstance(step, GenerateCRScheduleStep):
        return GenerateCRSchedule(max_parallel_ops=step.max_parallel_ops, inverse=step.inverse)
    if isinstance(step, TwoQubitCalibrationStep):
        return TwoQubitCalibration(
            tasks=list(step.tasks) if step.tasks is not None else None,
            max_parallel_ops=step.max_parallel_ops,
            step_id=step.step_id,
        )
    if isinstance(step, CustomTwoQubitStep):
        return CustomTwoQubit(
            step_name=step.step_name,
            tasks=list(step.tasks),
            max_parallel_ops=step.max_parallel_ops,
            continue_on_failure=step.continue_on_failure,
        )
    raise ValueError(f"unsupported pipeline step: {step!r}")


def build_steps(spec: CalibrationPipelineSpec) -> list[Step]:
    """Step objects for the whole spec, in order."""
    return [build_step(step) for step in spec.steps]


def pipeline_note(spec: CalibrationPipelineSpec, steps: list[Step]) -> dict[str, Any]:
    """The plan, stored in every execution's note so the API can follow the run.

    Each calibration step gets its own execution (see ``CalibService.run``);
    they share ``note.flow_run_id`` and carry ``step_index``. This adds the
    full step list so a reader of any one execution knows what else is
    planned, which steps run hardware, and the spec it came from.
    """
    return {
        "pipeline": {
            "name": spec.name,
            "spec_version": SPEC_VERSION,
            "spec_digest": spec.plan_digest(),
            "steps": [
                {
                    "index": index,
                    "name": built.name,
                    "step_id": step_id(step),
                    "type": step.type,
                    "kind": STEP_CATALOG[step.type].kind,
                }
                for index, (step, built) in enumerate(zip(spec.steps, steps, strict=True), 1)
            ],
        }
    }


def parse_dispatched_spec(spec: dict[str, Any], logger: Any) -> CalibrationPipelineSpec:
    """Parse a spec handed to the worker, converting a queued version 1 request.

    The API only dispatches version 2 specs. A run queued before the upgrade can
    still carry a version 1 spec; it is converted here, at the flow boundary,
    with :func:`migrate_pipeline_spec` (the same conversion the API offers), and
    the conversion is logged. Nothing else accepts version 1.
    """
    migration = migrate_pipeline_spec(spec)
    if migration.changed:
        logger.warning(
            "Converted a queued version 1 calibration pipeline spec to version 2: "
            + "; ".join(migration.notes or ["task names became TaskCall entries"])
        )
    return CalibrationPipelineSpec.model_validate(migration.spec)


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
            that bypassed the API is still held to the same shape; a queued
            version 1 spec is converted first (see ``parse_dispatched_spec``).
        project_id: Project the execution belongs to (injected by the API).
        flow_name: Display name of the execution; defaults to the spec name.
        tags: Extra tags; merged with the spec's tags.
        backend_name: Hardware backend; defaults to the configured backend.
    """
    logger = get_run_logger()
    parsed = parse_dispatched_spec(spec, logger)
    targets = build_targets(parsed)
    steps = build_steps(parsed)
    all_tags = sorted({*(tags or []), *parsed.tags, "pipeline"})
    name = flow_name or parsed.name

    logger.info(
        f"Pipeline '{name}': {len(steps)} steps, {len(parsed.all_tasks())} task calls per target, "
        f"targets={parsed.targets.model_dump(exclude_none=True)}"
    )

    cal = CalibService(
        username,
        chip_id,
        flow_name=name,
        tags=all_tags,
        project_id=project_id,
        backend_name=backend_name,
        _task_defaults=parsed.canonical_task_parameters(),
        default_run_parameters=parsed.default_run_parameters or None,
        note=pipeline_note(parsed, steps),
    )
    return cal.run(targets, steps=steps)
