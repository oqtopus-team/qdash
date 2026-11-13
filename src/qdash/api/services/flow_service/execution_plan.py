"""Read the steps a saved workflow states literally, without importing or running it.

The execution dialog previews what a run will do. A Python workflow is not
declarative, so this module only accepts what it can read with certainty: one
or more ``CalibService.run(targets, steps)`` calls in the entrypoint whose step
lists are literal constructor calls of built-in steps, with literal or simply
bound arguments. The bounded resolver of :mod:`.target_defaults` supplies the
literal values. Anything else (branches on values only known at run time,
loops, helper functions, calls the preview does not know) makes the whole plan
unresolved with a reason; a partial plan is never returned.

The plan is the path a run takes when it does not fail. A ``return`` reached
with the known parameters ends the plan; a ``raise`` reached with them leaves
it unresolved, because that run never gets past it. A check that may raise on
a value only known at run time stops a failing run without changing the steps
of one that proceeds, so it does not affect the plan. A ``return`` that may
happen on such a value, or an exception a ``with`` block may suppress, could
skip later runs of a run that succeeds, so any later ``CalibService.run``
leaves the plan unresolved. Without manual rounds the execution dialog may
replace the target parameters, so their saved values count as unknown.

The plan reports what the source states: exact manual rounds, and for
automatic modes only that the scheduler forms the groups at run time (from
the listed pairs of ``CouplingTargets``, or from the candidate qubits).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from qdash.api.services.flow_service.target_defaults import (
    _OVERRIDABLE_TARGETS,
    _call_name,
    _candidate,
    _function,
    _is_service,
    _prepare,
    _Resolver,
    _root_name,
    _Unknown,
    flow_parameter_names,
)
from qdash.datamodel.calibration_pipeline import STEP_CATALOG
from qdash.datamodel.flow_targets import FlowTargetOverride

ONE_QUBIT_MODE_STEPS = frozenset({"OneQubitCheck", "OneQubitFineTune", "CustomOneQubit"})
TWO_QUBIT_MODE_STEPS = frozenset({"TwoQubitCalibration", "CustomTwoQubit"})
STEP_TYPES = frozenset(
    {
        *ONE_QUBIT_MODE_STEPS,
        *TWO_QUBIT_MODE_STEPS,
        "BringUp",
        "ConfigureAll",
        "FilterByStatus",
        "FilterByMetric",
        "GenerateCRSchedule",
    }
)
_DEFAULT_MODES = {
    **dict.fromkeys(ONE_QUBIT_MODE_STEPS, "parallel_by_round"),
    **dict.fromkeys(TWO_QUBIT_MODE_STEPS, "automatic"),
    "BringUp": "parallel_by_mux",
}

# Calls that cannot run a pipeline; any other call makes the plan unresolved.
_KNOWN_FUNCTIONS = frozenset(
    {
        *STEP_TYPES,
        *_OVERRIDABLE_TARGETS,
        "TaskCall",
        "CalibService",
        "resolve_calib_context",
        "get_run_logger",
        "getLogger",
        "print",
        "len",
        "list",
        "dict",
        "set",
        "tuple",
        "str",
        "int",
        "float",
        "bool",
        "sorted",
        "range",
        "enumerate",
        "zip",
        "min",
        "max",
        "sum",
        "any",
        "all",
        "isinstance",
        "Exception",
        "ValueError",
        "RuntimeError",
        "TypeError",
        "KeyError",
    }
)
_KNOWN_METHODS = frozenset(
    {
        "info",
        "debug",
        "warning",
        "error",
        "exception",
        "get",
        "join",
        "format",
        "split",
        "strip",
        "from_context",
    }
)


_EXITS = (ast.Return, ast.Raise, ast.Assert)
_CATCHES = (ast.With, ast.AsyncWith)

_CONDITIONAL_EXPRESSIONS = (
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.IfExp,
    ast.BoolOp,
)


class _Unresolved(Exception):
    """The plan cannot be read with certainty; the message says why."""


@dataclass(frozen=True)
class StaticStep:
    """One step as the source writes it."""

    type: str
    name: str
    execution_mode: str | None
    rounds: Any = None
    tasks: tuple[str, ...] | None = None
    max_parallel_ops: int | None = None
    max_parallel_ops_set: bool = False
    literal: bool = True
    """False when an argument could not be read; such a step is not checked."""


@dataclass(frozen=True)
class StaticRun:
    """One ``CalibService.run`` call; ``targets`` is None when not literal."""

    targets: FlowTargetOverride | None
    steps: tuple[StaticStep, ...]
    target_type: str | None = None
    """Target class, e.g. ``CouplingTargets``, even when its values are not literal."""


@dataclass(frozen=True)
class StaticPlan:
    """The runs of the entrypoint, or the reason they cannot be read."""

    runs: tuple[StaticRun, ...] = ()
    reason: str | None = None
    manual_steps: tuple[StaticStep, ...] = field(default_factory=tuple)

    @property
    def resolved(self) -> bool:
        return self.reason is None


class _PlanResolver(_Resolver):
    """The target resolver, plus bindings of step objects and step lists."""

    pure_calls = frozenset({*_OVERRIDABLE_TARGETS, *STEP_TYPES, "TaskCall"})

    def __init__(self) -> None:
        super().__init__()
        self.step_lists: dict[str, tuple[StaticStep, ...]] = {}
        self.step_values: dict[str, StaticStep] = {}
        self.target_values: dict[str, FlowTargetOverride | None] = {}
        self.target_types: dict[str, str] = {}
        self.unresolved: dict[str, str] = {}

    def rebind(self, name: str) -> None:
        # A plain assignment does not change the object other names still hold
        # (``steps = [one, two]`` after ``steps = [one]`` keeps ``one``); mutation
        # through any name still invalidates every linked name.
        self._forget(name)

    def _forget(self, name: str) -> None:
        super()._forget(name)
        self.step_lists.pop(name, None)
        self.step_values.pop(name, None)
        self.target_values.pop(name, None)
        self.target_types.pop(name, None)
        self.unresolved.pop(name, None)

    def assign(self, name: str, value: ast.expr | None) -> None:
        super().assign(name, value)
        if value is None:
            return
        try:
            if isinstance(value, (ast.List, ast.Tuple)) and any(
                _is_step_call(element) or isinstance(element, ast.Name) for element in value.elts
            ):
                self.step_lists[name] = _static_steps(value, self)
            elif _is_step_call(value):
                assert isinstance(value, ast.Call)
                self.step_values[name] = _static_step(value, self)
            elif isinstance(value, ast.Call) and _call_name(value) in _OVERRIDABLE_TARGETS:
                self.target_types[name] = _call_name(value)
                self.target_values[name] = _target(value, self)
        except _Unresolved as exc:
            self.unresolved[name] = str(exc)


def _is_step_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _call_name(node) in STEP_TYPES


def _target(node: ast.Call, resolver: _Resolver) -> FlowTargetOverride | None:
    try:
        return _candidate(node, resolver)
    except (_Unknown, ValidationError):
        return None


def _literal(resolver: _Resolver, node: ast.expr, what: str) -> Any:
    try:
        return resolver.literal(node)
    except _Unknown as exc:
        raise _Unresolved(f"{what} is not a literal value") from exc


def _task_names(node: ast.expr, resolver: _Resolver) -> tuple[str, ...] | None:
    """Task names of a literal call list; None when any entry is not literal."""
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    names: list[str] = []
    for element in node.elts:
        name_node: ast.expr | None = None
        if isinstance(element, ast.Call) and _call_name(element) == "TaskCall":
            keywords = {kw.arg: kw.value for kw in element.keywords if kw.arg is not None}
            name_node = keywords.get("name") or (element.args[0] if element.args else None)
        elif isinstance(element, ast.Constant):
            name_node = element
        if name_node is None:
            return None
        try:
            name = resolver.literal(name_node)
        except _Unknown:
            return None
        if not isinstance(name, str):
            return None
        names.append(name)
    return tuple(names)


def _static_step(node: ast.Call, resolver: _Resolver) -> StaticStep:
    step_type = _call_name(node)
    label = f"{step_type}(...)"
    if any(isinstance(arg, ast.Starred) for arg in node.args) or any(
        kw.arg is None for kw in node.keywords
    ):
        raise _Unresolved(f"{label} unpacks its arguments")
    keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
    if node.args:
        raise _Unresolved(f"{label} takes positional arguments; pass them by keyword")

    def value(key: str, default: Any = None) -> Any:
        return (
            _literal(resolver, keywords[key], f"{key} of {label}") if key in keywords else default
        )

    entry = STEP_CATALOG.get(step_type)
    if step_type in {"CustomOneQubit", "CustomTwoQubit"}:
        name = value("step_name", entry.name if entry else step_type)
    else:
        name = value("step_id") or (entry.name if entry else step_type)
    if step_type == "FilterByMetric" and "step_id" not in keywords:
        metric = value("metric")
        name = f"filter_by_{metric}" if isinstance(metric, str) else name
    mode = value("execution_mode", _DEFAULT_MODES.get(step_type))
    if mode is not None and not isinstance(mode, str):
        raise _Unresolved(f"execution_mode of {label} is not a string")

    tasks: tuple[str, ...] | None
    if "tasks" in keywords:
        tasks = _task_names(keywords["tasks"], resolver)
    elif entry is not None and entry.task_scope is not None:
        tasks = tuple(call.name for call in entry.default_tasks)
    else:
        tasks = None
    if tasks is not None and "configure" in keywords:
        try:
            configure = resolver.literal(keywords["configure"])
        except _Unknown:
            tasks = None
        else:
            tasks = ("Configure", *tasks) if configure is True else tasks

    cap = value("max_parallel_ops") if "max_parallel_ops" in keywords else None
    return StaticStep(
        type=step_type,
        name=str(name),
        execution_mode=mode,
        rounds=value("rounds"),
        tasks=tasks,
        max_parallel_ops=cap if isinstance(cap, int) and not isinstance(cap, bool) else None,
        max_parallel_ops_set="max_parallel_ops" in keywords,
    )


def _static_steps(node: ast.expr, resolver: _PlanResolver) -> tuple[StaticStep, ...]:
    if isinstance(node, ast.Name):
        if node.id in resolver.step_lists:
            return resolver.step_lists[node.id]
        reason = resolver.unresolved.get(node.id)
        raise _Unresolved(reason or f"the step list {node.id!r} is built or changed at run time")
    if not isinstance(node, (ast.List, ast.Tuple)):
        raise _Unresolved("the steps passed to CalibService.run are not a list of step calls")
    steps: list[StaticStep] = []
    for element in node.elts:
        if isinstance(element, ast.Call):
            if not _is_step_call(element):
                raise _Unresolved(
                    f"{_call_name(element) or 'an expression'}(...) is not a built-in step"
                )
            steps.append(_static_step(element, resolver))
        elif isinstance(element, ast.Name) and element.id in resolver.step_values:
            steps.append(resolver.step_values[element.id])
        else:
            what = element.id if isinstance(element, ast.Name) else "an expression"
            reason = resolver.unresolved.get(what)
            raise _Unresolved(reason or f"step {what!r} is built or changed at run time")
    return tuple(steps)


def _service_runs(node: ast.AST, resolver: _Resolver) -> list[ast.Call]:
    """``CalibService.run`` calls in ``node``; any other ``.run(...)`` is not followed."""
    runs: list[ast.Call] = []
    for child in ast.walk(node):
        if not (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)):
            continue
        if resolver.is_service_run(child):
            runs.append(child)
        elif child.func.attr == "run":
            root = _root_name(child.func.value)
            raise _Unresolved(
                f"the entrypoint calls {root + '.' if root else ''}run(), which is not "
                "a CalibService created in the entrypoint"
            )
    return runs


def _first(node: ast.AST, kinds: tuple[type[ast.stmt], ...]) -> ast.stmt | None:
    """The first statement of one of ``kinds`` in ``node``, itself included."""
    found = [child for child in ast.walk(node) if isinstance(child, kinds)]
    return min(found, key=lambda child: child.lineno) if found else None


def _skip_reason(node: ast.stmt, in_with: bool, why: str) -> str | None:
    """Why ``node`` may end the entrypoint early in a run that does not fail.

    A ``return`` ends a successful run. An exception only fails the run,
    unless a ``with`` block around it may suppress it and continue.
    """
    returned = _first(node, (ast.Return,))
    if returned is not None:
        return (
            f"the return at line {returned.lineno} may end the entrypoint {why}, so a later "
            "CalibService.run may not be called"
        )
    raised = _first(node, (ast.Raise, ast.Assert))
    if raised is not None and (in_with or _first(node, _CATCHES) is not None):
        return (
            f"the exception at line {raised.lineno} may be suppressed by a with block "
            f"{why}, so a later CalibService.run may not be called"
        )
    return None


def _check_calls(function: ast.FunctionDef | ast.AsyncFunctionDef, local_defs: set[str]) -> None:
    """Reject entrypoints whose calls could build or run steps the preview cannot see."""
    for node in ast.walk(ast.Module(body=function.body, type_ignores=[])):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            raise _Unresolved("the entrypoint defines nested functions or classes")
        if isinstance(node, ast.Name) and node.id in local_defs:
            raise _Unresolved(f"the entrypoint uses {node.id}, which is defined in this file")
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            if node.func.id not in _KNOWN_FUNCTIONS:
                raise _Unresolved(f"the entrypoint calls {node.func.id}(), which is not followed")
        elif isinstance(node.func, ast.Attribute):
            attribute = node.func.attr
            if attribute in _KNOWN_METHODS or attribute in {"run", "append", "extend", "insert"}:
                continue
            if _is_service(node) or _call_name(node) in _KNOWN_FUNCTIONS:
                continue
            root = _root_name(node.func.value)
            raise _Unresolved(
                f"the entrypoint calls {root + '.' if root else ''}{attribute}(), "
                "which is not followed"
            )
        else:
            raise _Unresolved("the entrypoint calls an expression that is not followed")


def manual_step_literals(code: str) -> tuple[StaticStep, ...]:
    """Every built-in step call anywhere in the source that writes ``execution_mode="manual"``.

    Values are read with ``ast.literal_eval`` only. Used to reject target
    overrides and to report known-invalid rounds even when the plan itself
    cannot be resolved.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ()
    found: list[StaticStep] = []
    empty = _Resolver()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _call_name(node) in STEP_TYPES):
            continue
        mode = next((kw.value for kw in node.keywords if kw.arg == "execution_mode"), None)
        if not (isinstance(mode, ast.Constant) and mode.value == "manual"):
            continue
        try:
            found.append(_static_step(node, empty))
        except _Unresolved:
            name_node = next(
                (kw.value for kw in node.keywords if kw.arg in {"step_name", "step_id"}), None
            )
            name = name_node.value if isinstance(name_node, ast.Constant) else None
            found.append(
                StaticStep(
                    type=_call_name(node),
                    name=str(name or _call_name(node)),
                    execution_mode="manual",
                    literal=False,
                )
            )
    return tuple(found)


def uses_manual_rounds(code: str) -> bool:
    """Whether the source writes ``execution_mode="manual"`` on a built-in step."""
    return bool(manual_step_literals(code))


def resolve_execution_plan(code: str, function_name: str, parameters: dict[str, Any]) -> StaticPlan:
    """The runs the entrypoint states literally, or the reason they cannot be read."""
    manual = manual_step_literals(code)
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return StaticPlan(reason=f"the saved source does not parse: {exc.msg}", manual_steps=manual)
    function = _function(tree, function_name)
    if function is None:
        return StaticPlan(
            reason=f"the entrypoint {function_name}() is not defined", manual_steps=manual
        )
    # Without manual rounds the execution dialog may override the targets, and
    # the service then passes them as these parameters; their saved values are
    # not what such a run receives.
    selected = (
        set()
        if manual
        else set(FlowTargetOverride.model_fields) & flow_parameter_names(code, function_name)
    )
    try:
        runs = _resolve_runs(tree, function, parameters, selected)
    except _Unresolved as exc:
        return StaticPlan(reason=str(exc), manual_steps=manual)
    return StaticPlan(runs=runs, manual_steps=manual)


def _resolve_runs(
    tree: ast.Module,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    parameters: dict[str, Any],
    selected: set[str],
) -> tuple[StaticRun, ...]:
    resolver = _PlanResolver()
    try:
        _prepare(tree, function, parameters, resolver)
    except _Unknown as exc:
        raise _Unresolved("targets or a CalibService are built outside the entrypoint") from exc
    for name in selected:
        resolver.invalidate(name)
    local_defs = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node is not function
    }
    _check_calls(function, local_defs)

    runs: list[StaticRun] = []
    # Set once a successful run may leave the entrypoint early; later runs are then uncertain.
    may_skip: str | None = None

    def record(run: ast.Call) -> None:
        if may_skip is not None:
            raise _Unresolved(may_skip)
        if any(isinstance(arg, ast.Starred) for arg in run.args) or any(
            kw.arg is None for kw in run.keywords
        ):
            raise _Unresolved("CalibService.run unpacks its arguments")
        arguments = dict(zip(("targets", "steps"), run.args, strict=False))
        arguments.update({kw.arg: kw.value for kw in run.keywords if kw.arg is not None})
        targets, steps = arguments.get("targets"), arguments.get("steps")
        if targets is None or steps is None:
            raise _Unresolved("CalibService.run is called without targets and steps")
        target_type: str | None = None
        if isinstance(targets, ast.Call) and _call_name(targets) in _OVERRIDABLE_TARGETS:
            target = _target(targets, resolver)
            target_type = _call_name(targets)
        elif isinstance(targets, ast.Name):
            target = resolver.target_values.get(targets.id)
            target_type = resolver.target_types.get(targets.id)
        else:
            target = None
        runs.append(
            StaticRun(
                targets=target,
                steps=_static_steps(steps, resolver),
                target_type=target_type,
            )
        )

    def may_end(statement: ast.stmt, in_with: bool, why: str) -> None:
        nonlocal may_skip
        if may_skip is None:
            may_skip = _skip_reason(statement, in_with, why)

    def raises(statement: ast.stmt) -> _Unresolved:
        if may_skip is not None:
            return _Unresolved(may_skip)
        return _Unresolved(
            f"with the saved parameters the entrypoint raises an exception at line "
            f"{statement.lineno}, so the run fails there"
        )

    def visit(statements: list[ast.stmt], in_with: bool = False) -> bool:
        """Visit statements in order; True once the entrypoint has certainly ended."""
        for statement in statements:
            if isinstance(statement, ast.If):
                try:
                    taken = resolver.truth(statement.test)
                except _Unknown:
                    if _service_runs(statement, resolver):
                        raise _Unresolved(
                            "an if statement whose condition is only known at run time "
                            "decides whether CalibService.run is called"
                        ) from None
                    may_end(statement, in_with, "on a condition only known at run time")
                else:
                    if visit(statement.body if taken else statement.orelse, in_with):
                        return True
                    continue
            elif isinstance(statement, (ast.With, ast.AsyncWith)):
                for item in statement.items:
                    if _service_runs(item.context_expr, resolver):
                        raise _Unresolved("CalibService.run is called inside a with item")
                    resolver.enter(item)
                if visit(statement.body, in_with=True):
                    return True
                continue
            elif isinstance(statement, ast.Raise):
                if _service_runs(statement, resolver):
                    raise _Unresolved("CalibService.run is called inside a raise statement")
                raise raises(statement)
            elif isinstance(statement, ast.Assert):
                if _service_runs(statement, resolver):
                    raise _Unresolved("CalibService.run is called inside an assert statement")
                try:
                    holds = resolver.truth(statement.test)
                except _Unknown:
                    may_end(statement, in_with, "on a condition only known at run time")
                else:
                    if not holds:
                        raise raises(statement)
            elif not isinstance(statement, (ast.Expr, ast.Assign, ast.AnnAssign, ast.Return)):
                if _service_runs(statement, resolver):
                    kind = type(statement).__name__.lower()
                    raise _Unresolved(
                        f"CalibService.run is called inside a {kind} block, so the number "
                        "of runs is only known at run time"
                    )
                kind = type(statement).__name__.lower()
                may_end(statement, in_with, f"from inside a {kind} block")
            else:
                for node in ast.walk(statement):
                    if isinstance(node, _CONDITIONAL_EXPRESSIONS) and _service_runs(node, resolver):
                        raise _Unresolved(
                            "CalibService.run is called inside a comprehension or conditional "
                            "expression, so the number of runs is only known at run time"
                        )
                for run in _service_runs(statement, resolver):
                    record(run)
                if isinstance(statement, ast.Return):
                    if not runs:
                        raise _Unresolved(
                            f"the entrypoint returns at line {statement.lineno} before any "
                            "CalibService.run(targets, steps) call"
                        )
                    return True
            resolver.bind(statement)
        return False

    visit(function.body)
    if not runs:
        raise _Unresolved("the entrypoint has no CalibService.run(targets, steps) call")
    return tuple(runs)
