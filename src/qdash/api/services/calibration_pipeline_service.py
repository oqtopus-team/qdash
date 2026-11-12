"""Validation of declarative calibration pipelines against a project.

The spec's shape and step order are checked by ``CalibrationPipelineSpec``
itself. This service adds what only the API knows: the chip's qubits, the
backend's task list and each task's type, and the project's task definitions.
Every finding is reported as a problem with a path, so an agent can fix the
spec rather than guess from a 422.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from qdash.api.schemas.calibration_pipeline import (
    PipelineCatalogResponse,
    PipelineProblem,
    PipelineStepTypeInfo,
    ResolvedPipelineStep,
    ResolvedPipelineTargets,
    ResolvedTaskCall,
    ValidatePipelineResponse,
)
from qdash.api.services.calibration_pipeline_preflight import (
    PreflightTask,
    batch_input_problems,
    input_parameter_problems,
    prerequisite_problems,
    run_parameter_problems,
)
from qdash.common.config.backend import (
    get_available_backends,
    get_default_backend,
    get_tasks,
)
from qdash.datamodel.calibration_pipeline import (
    SPEC_VERSION,
    STEP_CATALOG,
    CalibrationPipelineSpec,
    ConfigureAllStep,
    FilterByMetricStep,
    FilterByStatusStep,
    PipelineStep,
    migrate_pipeline_spec,
    pipeline_spec_json_schema,
    pipeline_warnings,
    step_calls,
    step_continue_on_failure,
    step_id,
    step_name,
)
from qdash.datamodel.one_qubit_execution_mode import ONE_QUBIT_EXECUTION_MODES
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.qubit import QubitDocument

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from qdash.api.schemas.task_file import TaskInfo
    from qdash.repository.task_definition import MongoTaskDefinitionRepository

logger = logging.getLogger(__name__)

QUBITS_PER_MUX = 4


def _problem(path: str, message: str) -> PipelineProblem:
    return PipelineProblem(path=path, message=message)


def _pydantic_problems(error: ValidationError) -> list[PipelineProblem]:
    problems: list[PipelineProblem] = []
    for item in error.errors():
        parts: list[str] = []
        for loc in item["loc"]:
            if isinstance(loc, int):
                parts[-1:] = [f"{parts[-1]}[{loc}]"] if parts else [f"[{loc}]"]
            else:
                parts.append(str(loc))
        # Discriminated unions add the chosen tag as a location segment; drop it.
        path = ".".join(part for part in parts if part not in STEP_CATALOG) or "spec"
        message = item["msg"]
        if message.startswith("Value error, "):
            message = message[len("Value error, ") :]
        problems.append(_problem(path, message))
    return problems


class CalibrationPipelineService:
    """Resolve and validate pipeline specs for one project."""

    def __init__(
        self,
        task_definition_repository: MongoTaskDefinitionRepository,
        *,
        default_backend: Callable[[], str] = get_default_backend,
        available_backends: Callable[[], list[str]] = get_available_backends,
        backend_tasks: Callable[[str], list[str]] = get_tasks,
        task_catalog: Callable[[str], Mapping[str, TaskInfo]] | None = None,
        qubit_data: Callable[[str, str, str], Mapping[str, Any]] | None = None,
        source_run_parameters: Callable[[str, str], Mapping[str, Any] | None] | None = None,
    ) -> None:
        """Create the service.

        Args:
            task_definition_repository: Project task definitions (names and types).
            default_backend: The backend to validate against when none is named.
            available_backends: The backends a spec may name.
            backend_tasks: Task names a backend enables.
            task_catalog: backend -> task metadata by name, for the preflight
                checks. When None, the preflight checks are skipped. A LookupError
                from it makes the spec invalid: the preflight fails closed rather
                than pass a spec it could not check.
            qubit_data: (project_id, chip_id, qid) -> the qubit's calibration data.
            source_run_parameters: (project_id, task_id) -> run parameters recorded
                on that task result, or None when the task is unknown.
        """
        self._task_definitions = task_definition_repository
        self._default_backend = default_backend
        self._available_backends = available_backends
        self._backend_tasks = backend_tasks
        self._task_catalog = task_catalog
        self._qubit_data = qubit_data
        self._source_run_parameters = source_run_parameters

    # ------------------------------------------------------------------ catalog

    def resolve_backend(self, backend_name: str | None) -> tuple[str, PipelineProblem | None]:
        """The backend to validate against, or a problem when it is unknown."""
        name = (backend_name or self._default_backend()).strip()
        if name not in self._available_backends():
            return name, _problem("backend_name", f"unknown backend {name!r}")
        return name, None

    def task_types(self, project_id: str, backend_name: str) -> dict[str, str]:
        """task name -> task_type for the tasks this backend exposes.

        Task types come from the project's task definitions; a task enabled in
        the backend config but missing a definition is typed "unknown" and
        reported when a step needs its type.
        """
        enabled = set(self._backend_tasks(backend_name))
        types: dict[str, str] = {}
        for definition in self._task_definitions.list_by_project(project_id, backend_name):
            name = definition.get("name")
            if name in enabled:
                types[name] = str(definition.get("task_type") or "unknown")
        for name in enabled:
            types.setdefault(name, "unknown")
        return types

    def catalog(self, project_id: str, backend_name: str | None) -> PipelineCatalogResponse:
        """Step types, task names, and the spec schema for writing a spec."""
        backend, _ = self.resolve_backend(backend_name)
        by_type: dict[str, list[str]] = {}
        for name, task_type in sorted(self.task_types(project_id, backend).items()):
            by_type.setdefault(task_type, []).append(name)
        return PipelineCatalogResponse(
            backend_name=backend,
            step_types=[
                PipelineStepTypeInfo(
                    type=entry.type,
                    kind=entry.kind,
                    description=entry.description,
                    requires=sorted(entry.requires),
                    provides=sorted(entry.provides),
                    task_scope=entry.task_scope,
                    default_step_id=entry.name if entry.kind == "calibration" else None,
                    default_tasks=list(entry.default_tasks),
                    step_metrics=list(entry.step_metrics),
                )
                for entry in STEP_CATALOG.values()
            ],
            one_qubit_execution_modes=list(ONE_QUBIT_EXECUTION_MODES),
            tasks=by_type,
            spec_version=SPEC_VERSION,
            spec_schema=pipeline_spec_json_schema(),
        )

    # --------------------------------------------------------------- validation

    def validate(
        self,
        *,
        project_id: str,
        chip_id: str,
        spec: dict[str, Any],
        backend_name: str | None,
    ) -> ValidatePipelineResponse:
        """Check a spec against the project. Never raises for a bad spec."""
        backend, backend_problem = self.resolve_backend(backend_name)
        problems: list[PipelineProblem] = [backend_problem] if backend_problem else []

        version = spec.get("spec_version", 1) if isinstance(spec, dict) else None
        if version != SPEC_VERSION:
            return self._reject_old_version(spec, version, backend, problems)

        try:
            parsed = CalibrationPipelineSpec.model_validate(spec)
        except ValidationError as error:
            problems.extend(_pydantic_problems(error))
            return ValidatePipelineResponse(
                valid=False,
                problems=problems,
                backend_name=backend,
                spec_version=SPEC_VERSION,
            )

        targets, target_qids = self._validate_targets(project_id, chip_id, parsed, problems)
        if not backend_problem:
            self._validate_tasks(project_id, backend, parsed, problems)
        self._validate_task_parameters(parsed, problems)
        if not backend_problem:
            self._preflight(project_id, chip_id, backend, parsed, target_qids, problems)

        defaults = parsed.canonical_task_parameters()
        steps = [
            self._resolved_step(index, step, defaults) for index, step in enumerate(parsed.steps, 1)
        ]
        return ValidatePipelineResponse(
            valid=not problems,
            problems=problems,
            warnings=[_problem(path, message) for path, message in pipeline_warnings(parsed)],
            backend_name=backend,
            spec_version=SPEC_VERSION,
            spec=parsed.model_dump(mode="json", exclude_none=True),
            plan_digest=parsed.plan_digest(),
            targets=targets,
            steps=steps,
            # ConfigureAll runs once for its MUXes, not once per target.
            task_run_count=sum(
                len(step_calls(step))
                for step in parsed.steps
                if not isinstance(step, ConfigureAllStep)
            ),
        )

    @staticmethod
    def _reject_old_version(
        spec: Any,
        version: Any,
        backend: str,
        problems: list[PipelineProblem],
    ) -> ValidatePipelineResponse:
        """A version 1 spec is rejected with the same pipeline converted to version 2."""
        try:
            migration = migrate_pipeline_spec(spec)
        except (ValueError, TypeError, AttributeError) as exc:
            problems.append(
                _problem(
                    "spec_version",
                    f"spec_version must be {SPEC_VERSION}: {exc}",
                )
            )
            return ValidatePipelineResponse(valid=False, problems=problems, backend_name=backend)
        notes = "; ".join(migration.notes)
        problems.append(
            _problem(
                "spec_version",
                f"this is a version {version} spec; QDash accepts spec_version "
                f"{SPEC_VERSION}, where tasks are TaskCall objects "
                '({"name": ..., "call_id": ..., "run": ...}) and task_run_parameters '
                "became task_parameters.<task>.run. Submit migrated_spec, which runs the "
                "same tasks with the same settings" + (f" ({notes})" if notes else ""),
            )
        )
        return ValidatePipelineResponse(
            valid=False,
            problems=problems,
            backend_name=backend,
            spec_version=version if isinstance(version, int) else None,
            migrated_spec=migration.spec,
        )

    @staticmethod
    def _resolved_step(
        index: int, step: PipelineStep, defaults: Mapping[str, Any]
    ) -> ResolvedPipelineStep:
        calls = step_calls(step)
        continue_on_failure = step_continue_on_failure(step)
        reference = None
        if isinstance(step, FilterByStatusStep | FilterByMetricStep) and step.step is not None:
            reference = {"step": step.step, "call_id": step.call_id}
        return ResolvedPipelineStep(
            index=index,
            type=step.type,
            name=step_name(step),
            step_id=step_id(step),
            kind=STEP_CATALOG[step.type].kind,
            tasks=[call.name for call in calls],
            calls=[
                ResolvedTaskCall(
                    call_id=call.resolved_call_id,
                    name=call.name,
                    on_failure=call.on_failure or ("continue" if continue_on_failure else "stop"),
                    settings=call.effective_settings(defaults),
                )
                for call in calls
            ],
            reference=reference,
        )

    @staticmethod
    def _step_name(step: PipelineStep) -> str:
        return step_name(step)

    def _validate_targets(
        self,
        project_id: str,
        chip_id: str,
        spec: CalibrationPipelineSpec,
        problems: list[PipelineProblem],
    ) -> tuple[ResolvedPipelineTargets | None, list[str]]:
        """The resolved targets, and the target qubits that exist on the chip."""
        chip = ChipDocument.find_one({"project_id": project_id, "chip_id": chip_id}).run()
        if chip is None:
            problems.append(_problem("chip_id", f"chip {chip_id!r} is not in this project"))
            return None, []
        known = {
            doc.qid
            for doc in QubitDocument.find({"project_id": project_id, "chip_id": chip_id}).run()
        }
        targets = spec.targets
        if targets.qids:
            for index, qid in enumerate(targets.qids):
                if qid not in known:
                    problems.append(
                        _problem(
                            f"targets.qids[{index}]", f"qubit {qid!r} is not on chip {chip_id}"
                        )
                    )
            return (
                ResolvedPipelineTargets(qids=list(targets.qids)),
                [qid for qid in targets.qids if qid in known],
            )

        mux_count = max(1, int(chip.size) // QUBITS_PER_MUX)
        for index, mux in enumerate(targets.mux_ids or []):
            if mux < 0 or mux >= mux_count:
                problems.append(
                    _problem(
                        f"targets.mux_ids[{index}]",
                        f"MUX {mux} is out of range for chip {chip_id} (0-{mux_count - 1})",
                    )
                )
        for index, qid in enumerate(targets.exclude_qids):
            if qid not in known:
                problems.append(
                    _problem(
                        f"targets.exclude_qids[{index}]",
                        f"qubit {qid!r} is not on chip {chip_id}",
                    )
                )
        excluded = set(targets.exclude_qids)
        mux_qids = [
            str(qid)
            for mux in targets.mux_ids or []
            if 0 <= mux < mux_count
            for qid in range(mux * QUBITS_PER_MUX, (mux + 1) * QUBITS_PER_MUX)
        ]
        return (
            ResolvedPipelineTargets(
                qids=[],
                mux_ids=list(targets.mux_ids or []),
                exclude_qids=list(targets.exclude_qids),
            ),
            [qid for qid in mux_qids if qid in known and qid not in excluded],
        )

    def _preflight(
        self,
        project_id: str,
        chip_id: str,
        backend: str,
        spec: CalibrationPipelineSpec,
        target_qids: list[str],
        problems: list[PipelineProblem],
    ) -> None:
        """Report what a task would reject before measuring, from metadata and the database."""
        if self._task_catalog is None:
            return
        try:
            catalog = self._task_catalog(backend)
        except LookupError as exc:
            problems.append(
                _problem(
                    "backend_name",
                    f"task catalog for backend {backend!r} is unavailable, "
                    f"so the spec could not be checked: {exc}",
                )
            )
            return
        tasks = {name: PreflightTask.from_task_info(info) for name, info in catalog.items()}
        if not tasks:
            return
        problems.extend(run_parameter_problems(spec, tasks))
        problems.extend(input_parameter_problems(spec, tasks))
        problems.extend(batch_input_problems(spec))
        if self._qubit_data is None or not target_qids:
            return
        qubit_data = self._qubit_data
        source_run_parameters = self._source_run_parameters
        problems.extend(
            prerequisite_problems(
                spec,
                target_qids,
                tasks,
                lambda qid: qubit_data(project_id, chip_id, qid),
                (
                    (lambda task_id: source_run_parameters(project_id, task_id))
                    if source_run_parameters is not None
                    else None
                ),
            )
        )

    def _validate_tasks(
        self,
        project_id: str,
        backend: str,
        spec: CalibrationPipelineSpec,
        problems: list[PipelineProblem],
    ) -> None:
        """Report explicit calls whose task the backend lacks or whose type the step cannot run.

        Default task lists are the templates' own and are not judged.
        """
        types = self.task_types(project_id, backend)
        for step_index, step in enumerate(spec.steps):
            if isinstance(step, ConfigureAllStep) and step.call is not None:
                if step.call.name not in types:
                    problems.append(
                        _problem(
                            f"steps[{step_index}].call",
                            f"task {step.call.name!r} is not available on backend {backend!r}",
                        )
                    )
                continue
            scope = STEP_CATALOG[step.type].task_scope
            if scope is None:
                continue
            own_tasks = getattr(step, "tasks", None)
            # Default lists are the templates' own; only an explicit list is judged.
            if own_tasks is None:
                continue
            for task_index, call in enumerate(own_tasks):
                path = f"steps[{step_index}].tasks[{task_index}]"
                task = call.name
                task_type = types.get(task)
                if task_type is None:
                    problems.append(
                        _problem(path, f"task {task!r} is not available on backend {backend!r}")
                    )
                elif task_type != scope and task_type != "unknown":
                    problems.append(
                        _problem(
                            path,
                            f"task {task!r} is a {task_type} task; {step.type} runs {scope} tasks",
                        )
                    )

    @staticmethod
    def _validate_task_parameters(
        spec: CalibrationPipelineSpec, problems: list[PipelineProblem]
    ) -> None:
        tasks_in_pipeline = set(spec.all_tasks())
        for task in spec.task_parameters:
            if task not in tasks_in_pipeline:
                problems.append(
                    _problem(
                        f"task_parameters.{task}",
                        f"task {task!r} does not run in this pipeline",
                    )
                )
