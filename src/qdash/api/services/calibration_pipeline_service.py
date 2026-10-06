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
    ValidatePipelineResponse,
)
from qdash.common.config.backend import (
    get_available_backends,
    get_default_backend,
    get_tasks,
)
from qdash.datamodel.calibration_pipeline import (
    ONE_QUBIT_MODES,
    STEP_CATALOG,
    CalibrationPipelineSpec,
    FilterByMetricStep,
    PipelineStep,
    pipeline_spec_json_schema,
    step_tasks,
)
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.qubit import QubitDocument

if TYPE_CHECKING:
    from collections.abc import Callable

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
    ) -> None:
        self._task_definitions = task_definition_repository
        self._default_backend = default_backend
        self._available_backends = available_backends
        self._backend_tasks = backend_tasks

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
                    default_tasks=list(entry.default_tasks),
                )
                for entry in STEP_CATALOG.values()
            ],
            one_qubit_modes=list(ONE_QUBIT_MODES),
            tasks=by_type,
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

        try:
            parsed = CalibrationPipelineSpec.model_validate(spec)
        except ValidationError as error:
            problems.extend(_pydantic_problems(error))
            return ValidatePipelineResponse(valid=False, problems=problems, backend_name=backend)

        targets = self._validate_targets(project_id, chip_id, parsed, problems)
        if not backend_problem:
            self._validate_tasks(project_id, backend, parsed, problems)
        self._validate_run_parameters(parsed, problems)

        steps = [
            ResolvedPipelineStep(
                index=index,
                type=step.type,
                name=self._step_name(step),
                kind=STEP_CATALOG[step.type].kind,
                tasks=step_tasks(step),
            )
            for index, step in enumerate(parsed.steps, start=1)
        ]
        return ValidatePipelineResponse(
            valid=not problems,
            problems=problems,
            backend_name=backend,
            spec=parsed.model_dump(mode="json"),
            targets=targets,
            steps=steps,
            task_run_count=len(parsed.all_tasks()),
        )

    @staticmethod
    def _step_name(step: PipelineStep) -> str:
        step_name = getattr(step, "step_name", None)
        if step_name:
            return str(step_name)
        if isinstance(step, FilterByMetricStep):
            return f"filter_by_{step.metric}"
        names = {
            "ConfigureAll": "configure_all",
            "BringUp": "bringup",
            "OneQubitCheck": "one_qubit_check",
            "OneQubitFineTune": "one_qubit_fine_tune",
            "FilterByStatus": "filter_by_status",
            "GenerateCRSchedule": "generate_cr_schedule",
            "TwoQubitCalibration": "two_qubit_calibration",
        }
        return names.get(step.type, step.type)

    def _validate_targets(
        self,
        project_id: str,
        chip_id: str,
        spec: CalibrationPipelineSpec,
        problems: list[PipelineProblem],
    ) -> ResolvedPipelineTargets | None:
        chip = ChipDocument.find_one({"project_id": project_id, "chip_id": chip_id}).run()
        if chip is None:
            problems.append(_problem("chip_id", f"chip {chip_id!r} is not in this project"))
            return None
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
            return ResolvedPipelineTargets(qids=list(targets.qids))

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
        return ResolvedPipelineTargets(
            qids=[],
            mux_ids=list(targets.mux_ids or []),
            exclude_qids=list(targets.exclude_qids),
        )

    def _validate_tasks(
        self,
        project_id: str,
        backend: str,
        spec: CalibrationPipelineSpec,
        problems: list[PipelineProblem],
    ) -> None:
        types = self.task_types(project_id, backend)
        for step_index, step in enumerate(spec.steps):
            scope = STEP_CATALOG[step.type].task_scope
            if scope is None:
                continue
            own_tasks = getattr(step, "tasks", None)
            # Default lists are the templates' own; only an explicit list is judged.
            if own_tasks is None:
                continue
            for task_index, task in enumerate(own_tasks):
                path = f"steps[{step_index}].tasks[{task_index}]"
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
    def _validate_run_parameters(
        spec: CalibrationPipelineSpec, problems: list[PipelineProblem]
    ) -> None:
        tasks_in_pipeline = set(spec.all_tasks())
        for task in spec.task_run_parameters:
            if task not in tasks_in_pipeline:
                problems.append(
                    _problem(
                        f"task_run_parameters.{task}",
                        f"task {task!r} does not run in this pipeline",
                    )
                )
