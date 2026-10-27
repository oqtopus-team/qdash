"""Plan-time checks that mirror what a task verifies before it measures anything.

A calibration task refuses to run, before any data is acquired, when a run
parameter has the wrong type, when a ``database_required`` input is missing
from the chip's calibration data, or when the Rabi parameters it restores were
measured under a different readout duration than the session it runs in. Each
of those is visible from the spec, the task metadata, and the database, so the
``/validate`` dry run reports them as problems with a path into the spec rather
than letting the execution fail at step 1 with an empty result.

The checks only use metadata the API already has: :class:`TaskInfo` (declared
inputs, run parameters, and outputs), the qubit calibration data, the run
parameters recorded on the source task of a persisted parameter, and the Qubex
configuration tree (which System drives each target, and whether the wiring's
boxes are defined). They do not import workflow code.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from qdash.api.schemas.calibration_pipeline import PipelineProblem
from qdash.api.services.catalog_task_run import matches_parameter_type, run_override_parts
from qdash.common.config.calibration import DEFAULT_READOUT_DURATION
from qdash.common.config.qubex_config_schema import validate_shared_files
from qdash.datamodel.calibration_pipeline import STEP_CATALOG, step_tasks
from qdash.datamodel.task import compatible_value_type

if TYPE_CHECKING:
    from qdash.api.schemas.task_file import TaskInfo
    from qdash.common.config.system_catalog import SystemCatalog
    from qdash.datamodel.calibration_pipeline import CalibrationPipelineSpec

# Inputs that ``required_rabi_normalization_inputs`` declares; restoring them
# requires the source CheckRabi to have run under the session's readout duration.
RABI_NORMALIZATION_PARAMETERS = frozenset(
    {
        "rabi_amplitude",
        "maximum_rabi_frequency",
        "control_amplitude",
        "rabi_phase",
        "rabi_offset",
        "rabi_angle",
        "rabi_noise",
        "rabi_distance",
        "rabi_reference_phase",
        "rabi_r2",
    }
)
# The parameter whose source task identifies the CheckRabi that produced the set.
RABI_SOURCE_PARAMETER = "rabi_amplitude"

QubitDataLookup = Callable[[str], Mapping[str, Any]]
"""qid -> the qubit's calibration data (``{"name": {"value": ..., "task_id": ...}}``)."""

SourceRunParametersLookup = Callable[[str], "Mapping[str, Any] | None"]
"""task_id -> the run parameters recorded on that task result, or None when unknown."""


@dataclass(frozen=True)
class PreflightTask:
    """The task metadata the checks read, decoupled from the API schema."""

    name: str
    input_parameters: Mapping[str, Mapping[str, Any]]
    run_parameters: Mapping[str, Mapping[str, Any]]
    output_parameters: tuple[str, ...]

    @classmethod
    def from_task_info(cls, info: TaskInfo) -> PreflightTask:
        return cls(
            name=info.name,
            input_parameters=info.input_parameters,
            run_parameters=info.run_parameters,
            output_parameters=tuple(info.output_parameters),
        )


def _problem(path: str, message: str) -> PipelineProblem:
    return PipelineProblem(path=path, message=message)


def _format_qids(qids: Iterable[str]) -> str:
    return ", ".join(sorted(set(qids), key=lambda qid: (len(qid), qid)))


def _numeric(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def effective_readout_duration(spec: CalibrationPipelineSpec) -> float | None:
    """The readout duration the pipeline's Qubex session will use.

    The orchestrator starts the session from ``DEFAULT_READOUT_DURATION`` and
    takes the shared ``default_run_parameters.readout_duration`` when set. Returns
    None when the shared value is set but not a finite positive number; that case
    is reported by :func:`run_parameter_problems`.
    """
    if "readout_duration" not in spec.default_run_parameters:
        return float(DEFAULT_READOUT_DURATION)
    value, _ = run_override_parts(spec.default_run_parameters["readout_duration"])
    if value is None:
        return float(DEFAULT_READOUT_DURATION)
    return _numeric(value)


def _value_type_problem(declared: Mapping[str, Any], override: object) -> tuple[str | None, object]:
    """Return (message, value) for a run value against its declaration."""
    value, requested = run_override_parts(override)
    if value is None:
        # ``{"value": null}`` leaves the task default in place at run time.
        return None, None
    declared_type = declared.get("value_type")
    if not compatible_value_type(declared_type, requested):
        return f"declares {declared_type} and cannot take {requested}", value
    effective = requested if requested is not None else declared_type
    if not matches_parameter_type(value, effective):
        return f"must be {effective}", value
    return None, value


def run_parameter_problems(
    spec: CalibrationPipelineSpec,
    tasks: Mapping[str, PreflightTask],
) -> list[PipelineProblem]:
    """Problems with ``task_run_parameters`` and ``default_run_parameters``.

    Mirrors what task creation and ``QubexTask.resolve_run_parameters`` reject:
    undeclared names, values of an incompatible type, a non-positive readout
    duration, and a per-task ``readout_duration`` that differs from the session.
    Tasks without metadata are skipped; an unavailable task is reported elsewhere.
    """
    problems: list[PipelineProblem] = []
    pipeline_tasks = list(dict.fromkeys(spec.all_tasks()))
    session_duration = effective_readout_duration(spec)

    for name, override in spec.default_run_parameters.items():
        path = f"default_run_parameters.{name}"
        if name == "readout_duration" and session_duration is None:
            problems.append(_problem(path, "readout_duration must be a finite positive number"))
            continue
        declaring = [
            task for task in pipeline_tasks if task in tasks and name in tasks[task].run_parameters
        ]
        known = [task for task in pipeline_tasks if task in tasks]
        if not declaring and known and len(known) == len(pipeline_tasks):
            problems.append(
                _problem(
                    path,
                    f"no task in this pipeline declares run parameter {name!r}; it would be ignored",
                )
            )
            continue
        for task in declaring:
            message, _ = _value_type_problem(tasks[task].run_parameters[name], override)
            if message:
                problems.append(_problem(path, f"task {task!r} {message}"))

    for task_name, parameters in spec.task_run_parameters.items():
        declared_task = tasks.get(task_name)
        if declared_task is None:
            continue
        for name, override in parameters.items():
            path = f"task_run_parameters.{task_name}.{name}"
            declared = declared_task.run_parameters.get(name)
            if declared is None:
                problems.append(
                    _problem(path, f"task {task_name!r} does not declare run parameter {name!r}")
                )
                continue
            message, value = _value_type_problem(declared, override)
            if message:
                problems.append(_problem(path, f"task {task_name!r} {message}"))
                continue
            if name != "readout_duration" or value is None or session_duration is None:
                continue
            requested_duration = _numeric(value)
            if requested_duration is None:
                problems.append(_problem(path, "readout_duration must be a finite positive number"))
            elif not math.isclose(requested_duration, session_duration):
                problems.append(
                    _problem(
                        path,
                        "readout_duration is session-scoped in Qubex: "
                        f"task {task_name!r} asks for {requested_duration:g} ns but the session "
                        f"runs at {session_duration:g} ns; set it through "
                        "default_run_parameters.readout_duration instead",
                    )
                )
    return problems


def _lookup_keys(name: str, metadata: Mapping[str, Any]) -> tuple[str, ...]:
    """The database keys a task tries for one input, in resolution order."""
    keys = [str(metadata.get("parameter_name") or name)]
    for field in ("parameter_aliases", "fallback_parameter_names"):
        extra = metadata.get(field) or ()
        keys.extend(str(key) for key in extra)
    return tuple(dict.fromkeys(keys))


def _has_value(data: Mapping[str, Any], key: str) -> bool:
    entry = data.get(key)
    if entry is None:
        return False
    if isinstance(entry, Mapping):
        return entry.get("value") is not None
    return True


def _recorded_value(parameters: Mapping[str, Any] | None, name: str) -> object:
    if not parameters:
        return None
    entry = parameters.get(name)
    if isinstance(entry, Mapping):
        return entry.get("value")
    return entry


def _source_readout_duration(
    data: Mapping[str, Any],
    source_run_parameters: SourceRunParametersLookup,
) -> float | None:
    """The readout duration the persisted Rabi parameters were measured with."""
    entry = data.get(RABI_SOURCE_PARAMETER)
    task_id = entry.get("task_id") if isinstance(entry, Mapping) else None
    if not task_id:
        return None
    recorded = _recorded_value(source_run_parameters(str(task_id)), "readout_duration")
    if isinstance(recorded, bool) or not isinstance(recorded, int | float):
        return None
    return float(recorded)


def prerequisite_problems(
    spec: CalibrationPipelineSpec,
    qids: Iterable[str],
    tasks: Mapping[str, PreflightTask],
    qubit_data: QubitDataLookup,
    source_run_parameters: SourceRunParametersLookup | None = None,
) -> list[PipelineProblem]:
    """Problems with the calibration data the pipeline's qubit tasks need.

    Walks the calibration steps in order. A ``database_required`` input of a task
    is satisfied when an earlier task in the pipeline writes it, or when every
    target qubit already has it in its calibration data. Tasks that restore Rabi
    parameters are also checked against the readout duration those parameters
    were measured with, since the task rejects a mismatch with the session.

    Coupling steps are not checked; their inputs span two qubits and a coupling.
    """
    problems: list[PipelineProblem] = []
    target_qids = list(dict.fromkeys(qids))
    if not target_qids:
        return problems
    session_duration = effective_readout_duration(spec)
    data_cache: dict[str, Mapping[str, Any]] = {}

    def data_for(qid: str) -> Mapping[str, Any]:
        if qid not in data_cache:
            data_cache[qid] = qubit_data(qid) or {}
        return data_cache[qid]

    produced: set[str] = set()
    for step_index, step in enumerate(spec.steps):
        entry = STEP_CATALOG[step.type]
        if entry.kind != "calibration" or entry.task_scope != "qubit":
            continue
        for task_index, task_name in enumerate(step_tasks(step)):
            task = tasks.get(task_name)
            if task is None:
                continue
            path = f"steps[{step_index}].tasks[{task_index}]"
            missing: dict[str, list[str]] = {}
            restores_rabi = False
            for name, metadata in task.input_parameters.items():
                if metadata.get("resolution") != "database_required":
                    continue
                if (metadata.get("qid_role") or "self") not in {"self", ""}:
                    continue
                keys = _lookup_keys(name, metadata)
                if produced.intersection(keys):
                    continue
                if keys[0] in RABI_NORMALIZATION_PARAMETERS:
                    restores_rabi = True
                for qid in target_qids:
                    if not any(_has_value(data_for(qid), key) for key in keys):
                        missing.setdefault(keys[0], []).append(qid)
            for parameter, qids_missing in missing.items():
                problems.append(
                    _problem(
                        path,
                        f"task {task_name!r} needs calibrated {parameter!r} for qubit(s) "
                        f"{_format_qids(qids_missing)}, which is not in the calibration data "
                        "and no earlier task in this pipeline writes it",
                    )
                )
            if (
                restores_rabi
                and RABI_SOURCE_PARAMETER not in produced
                and source_run_parameters is not None
                and session_duration is not None
            ):
                rabi_missing = set(missing.get(RABI_SOURCE_PARAMETER, ()))
                unrecorded: list[str] = []
                mismatched: dict[float, list[str]] = {}
                for qid in target_qids:
                    if qid in rabi_missing:
                        continue
                    source_duration = _source_readout_duration(data_for(qid), source_run_parameters)
                    if source_duration is None:
                        unrecorded.append(qid)
                    elif not math.isclose(source_duration, session_duration):
                        mismatched.setdefault(source_duration, []).append(qid)
                if unrecorded:
                    problems.append(
                        _problem(
                            path,
                            f"task {task_name!r} restores Rabi parameters for qubit(s) "
                            f"{_format_qids(unrecorded)} whose source readout_duration is not "
                            "recorded; run CheckRabi earlier in this pipeline",
                        )
                    )
                for source_duration, qids_mismatched in sorted(mismatched.items()):
                    problems.append(
                        _problem(
                            path,
                            f"task {task_name!r} restores Rabi parameters for qubit(s) "
                            f"{_format_qids(qids_mismatched)} measured with readout_duration "
                            f"{source_duration:g} ns, but this pipeline runs the session at "
                            f"{session_duration:g} ns; run CheckRabi earlier in this pipeline "
                            "or set default_run_parameters.readout_duration to "
                            f"{source_duration:g}",
                        )
                    )
            produced.update(task.output_parameters)
    return problems


# --------------------------------------------------------------------------- #
# Configuration tree checks
# --------------------------------------------------------------------------- #


def default_system_catalog(chip_id: str) -> SystemCatalog | None:
    """The chip's :class:`SystemCatalog`, or None when the tree has nothing for it.

    A missing configuration tree (the fake backend, CI) is not a problem the spec
    can fix, so it is skipped; a tree that has the chip's directory or the shared
    catalog but cannot be read is reported by :func:`configuration_problems`.
    """
    from qdash.common.config.qubex_layout import QubexLayout
    from qdash.common.config.system_catalog import SystemCatalog

    try:
        layout = QubexLayout.detect()
        config_dir = layout.config_dir(chip_id)
    except ValueError:
        return None
    if not config_dir.is_dir():
        return None
    return SystemCatalog(layout, chip_id)


def configuration_problems(
    catalog: SystemCatalog,
    chip_id: str,
    qids: Iterable[str],
) -> list[PipelineProblem]:
    """Problems the Qubex configuration tree would raise for these targets.

    One session drives one System, so targets that resolve to several Systems
    are reported with the split, as are boxes the wiring references but
    ``box.yaml`` does not define, and a tree that cannot be read at all.
    """
    problems: list[PipelineProblem] = []
    try:
        rows = catalog.wiring_rows()
    except (OSError, ValueError, LookupError) as exc:
        problems.append(
            _problem("chip_id", f"configuration for chip {chip_id!r} could not be read: {exc}")
        )
        return problems

    for schema_problem in validate_shared_files(catalog.layout, chip_id):
        problems.append(
            _problem("chip_id", f"configuration file violates its schema: {schema_problem}")
        )

    missing_boxes = _missing_boxes(catalog, rows)
    if missing_boxes:
        problems.append(
            _problem(
                "chip_id",
                f"wiring of chip {chip_id!r} references boxes missing from box.yaml: "
                + ", ".join(sorted(missing_boxes)),
            )
        )

    target_qids = list(dict.fromkeys(qids))
    if not target_qids:
        return problems
    assignment: dict[str, list[str]] = {}
    unwired: list[str] = []
    for qid in target_qids:
        system_id = _system_of(catalog, qid)
        if system_id is None:
            unwired.append(qid)
        else:
            assignment.setdefault(system_id, []).append(qid)
    if unwired:
        problems.append(
            _problem(
                "targets",
                f"qubit(s) {_format_qids(unwired)} are on MUXes that are not wired "
                f"for chip {chip_id!r}",
            )
        )
    if len(assignment) > 1:
        split = "; ".join(
            f"{system_id}: {_format_qids(members)}" for system_id, members in assignment.items()
        )
        problems.append(
            _problem(
                "targets",
                f"targets span {len(assignment)} Systems of chip {chip_id!r} ({split}); "
                "one run drives one System, so run them as separate pipelines",
            )
        )
    return problems


def _system_of(catalog: SystemCatalog, qid: str) -> str | None:
    try:
        return catalog.system_of_qid(qid)
    except (KeyError, ValueError):
        return None


def _missing_boxes(catalog: SystemCatalog, rows: list[dict[str, Any]]) -> set[str]:
    import yaml

    try:
        path = catalog.layout.box_yaml(catalog.chip_id)
    except ValueError:
        return set()
    if not path.is_file():
        boxes: dict[str, Any] = {}
    else:
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            return set()
        boxes = loaded if isinstance(loaded, dict) else {}
    referenced: set[str] = set()
    for row in rows:
        specifiers: list[Any] = [row.get("read_out"), row.get("read_in"), row.get("pump")]
        ctrl = row.get("ctrl")
        if isinstance(ctrl, list):
            specifiers.extend(ctrl)
        for specifier in specifiers:
            if not isinstance(specifier, str) or not specifier.strip():
                continue
            separator = ":" if ":" in specifier else "-"
            box_id, found, _ = specifier.rpartition(separator)
            if found and box_id:
                referenced.add(box_id)
    return {box for box in referenced if box not in boxes}
