"""Inspect target defaults without importing or executing user workflow code."""

import ast
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from pydantic import ValidationError

from qdash.datamodel.flow_targets import FlowTargetOverride, TargetMode

_OVERRIDABLE_TARGETS = {"MuxTargets", "QubitTargets", "CouplingTargets"}
_QUBIT_MODES: list[TargetMode] = ["mux_ids", "qids"]


class _Unknown(Exception):
    """The source cannot be resolved to one confident target configuration."""


def flow_parameter_names(code: str, function_name: str) -> set[str]:
    """Return explicitly declared entrypoint parameters."""
    function = _function(ast.parse(code), function_name)
    if function is None:
        return set()
    args = function.args
    return {arg.arg for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]}


def supported_target_modes(code: str, function_name: str) -> list[TargetMode]:
    """Return the override types the execution dialog may offer for this source.

    Pair overrides need every ``CalibService.run`` the entrypoint executes to
    receive ``CouplingTargets`` and a step list with ``SetCRSchedule``, which the
    runtime replaces with the selected pairs. Only the entrypoint is inspected;
    anything the check cannot follow statically keeps the MUX and qubit
    overrides instead (see ``_runs_scheduled_pairs``). A source that writes
    ``execution_mode="manual"`` on a step accepts no override. User code never
    executes.
    """
    from qdash.api.services.flow_service.execution_plan import uses_manual_rounds

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return list(_QUBIT_MODES)
    if uses_manual_rounds(code):
        # Manual rounds name their own targets; no override may replace them.
        return []
    function = _function(tree, function_name)
    if function is not None and _runs_scheduled_pairs(tree, function):
        return ["coupling_pairs"]
    return list(_QUBIT_MODES)


def _runs_scheduled_pairs(
    tree: ast.Module, function: ast.FunctionDef | ast.AsyncFunctionDef
) -> bool:
    """Whether every pipeline the entrypoint runs is a scheduled coupling pipeline.

    Conservative by design. Pair mode is rejected when the entrypoint:

    - has no ``CalibService`` ``.run`` call, or runs one inside a loop,
      comprehension or lambda;
    - defines nested functions or classes, or references any function or class
      defined in the module (a helper may run its own pipeline);
    - builds other target types or ``GenerateCRSchedule``;
    - passes targets that are not ``CouplingTargets(...)`` bound in the entrypoint;
    - passes steps that are not a list literal, or a list name whose every
      assignment is a literal containing ``SetCRSchedule`` and which is changed
      only through ``append``, ``extend``, ``insert`` or ``+=`` with step calls.

    Module statements outside functions must not build services or targets.
    Calls into other modules are not followed.
    """
    local_defs = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for node in ast.walk(statement):
            if isinstance(node, ast.Call) and (
                _call_name(node).endswith("Targets") or _is_service(node)
            ):
                return False

    body = ast.Module(body=function.body, type_ignores=[])
    parameters = {
        arg.arg
        for arg in [
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
            *(a for a in (function.args.vararg, function.args.kwarg) if a is not None),
        ]
    }
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(body):
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Global, ast.Nonlocal)
        ):
            return False
        if isinstance(node, ast.Name) and node.id in local_defs:
            return False
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name == "GenerateCRSchedule" or (
                name.endswith("Targets") and name != "CouplingTargets"
            ):
                return False
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    # Every write to each name: the value for plain assignments, else None.
    writes: dict[str, list[ast.expr | None]] = {}
    augmented: set[str] = set()
    for node in ast.walk(body):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    writes.setdefault(target.id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            writes.setdefault(node.target.id, []).append(node.value)
        elif isinstance(node, ast.withitem) and isinstance(node.optional_vars, ast.Name):
            writes.setdefault(node.optional_vars.id, []).append(node.context_expr)
    for node in ast.walk(body):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            parent = parents.get(node)
            plain = (
                (isinstance(parent, ast.Assign) and node in parent.targets)
                or (isinstance(parent, ast.AnnAssign) and parent.target is node)
                or (isinstance(parent, ast.withitem) and parent.optional_vars is node)
            )
            if isinstance(parent, ast.AugAssign):
                # Checked as list extension for steps; unsupported for anything else.
                augmented.add(node.id)
            elif not plain:
                # Loop variables, unpacking, ``del`` and walrus bindings.
                writes.setdefault(node.id, []).append(None)

    def bound(name: str, accept: Callable[[ast.expr], bool], extendable: bool = False) -> bool:
        values = writes.get(name)
        return (
            name not in parameters
            and (extendable or name not in augmented)
            and bool(values)
            and all(value is not None and accept(value) for value in values or [])
        )

    def is_service(node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return bound(node.id, _is_service)
        return _is_service(node)

    def is_coupling(node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            # Only direct constructions; aliases are not followed.
            return bound(node.id, _is_coupling_call)
        return _is_coupling_call(node)

    runs = [
        node
        for node in ast.walk(body)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
        and is_service(node.func.value)
    ]
    if not runs:
        return False
    for run in runs:
        ancestor: ast.AST = run
        while ancestor in parents:
            ancestor = parents[ancestor]
            if isinstance(
                ancestor,
                (ast.For, ast.AsyncFor, ast.While, ast.Lambda, ast.comprehension),
            ):
                return False
        if any(isinstance(arg, ast.Starred) for arg in run.args) or any(
            kw.arg is None for kw in run.keywords
        ):
            return False
        arguments = dict(zip(("targets", "steps"), run.args, strict=False))
        arguments.update({kw.arg: kw.value for kw in run.keywords if kw.arg is not None})
        targets, steps = arguments.get("targets"), arguments.get("steps")
        if targets is None or steps is None or not is_coupling(targets):
            return False
        if not _scheduled_steps(steps, body, parents, set(runs), bound):
            return False
    return True


def _is_coupling_call(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and _call_name(node) == "CouplingTargets"


def _is_step_call(node: ast.expr) -> bool:
    """A direct step constructor call other than ``GenerateCRSchedule``."""
    return isinstance(node, ast.Call) and _call_name(node) not in {"", "GenerateCRSchedule"}


def _scheduled_list(node: ast.expr) -> bool:
    """A step list literal with ``SetCRSchedule`` and only direct step calls."""
    if not isinstance(node, (ast.List, ast.Tuple)):
        return False
    calls = [element for element in node.elts if isinstance(element, ast.Call)]
    return (
        len(calls) == len(node.elts)
        and all(_is_step_call(call) for call in calls)
        and any(_call_name(call) == "SetCRSchedule" for call in calls)
    )


def _scheduled_steps(
    steps: ast.expr,
    body: ast.Module,
    parents: dict[ast.AST, ast.AST],
    runs: set[ast.Call],
    bound: Callable[[str, Callable[[ast.expr], bool], bool], bool],
) -> bool:
    """Whether ``steps`` always holds ``SetCRSchedule`` and never another schedule."""
    if not isinstance(steps, ast.Name):
        return _scheduled_list(steps)
    name = steps.id
    if not bound(name, _scheduled_list, True):
        return False
    for node in ast.walk(body):
        if not (isinstance(node, ast.Name) and node.id == name and node is not steps):
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.keyword):
            parent = parents.get(parent)
        if isinstance(parent, ast.AugAssign):
            if not (
                isinstance(parent.op, ast.Add)
                and isinstance(parent.value, (ast.List, ast.Tuple))
                and all(_is_step_call(element) for element in parent.value.elts)
            ):
                return False
            continue
        if isinstance(parent, (ast.Assign, ast.AnnAssign)) and isinstance(node.ctx, ast.Store):
            continue
        if (
            isinstance(node.ctx, ast.Load)
            and isinstance(parent, ast.Call)
            and node in [*parent.args, *(kw.value for kw in parent.keywords)]
        ):
            # Only a service run call may read the list as an argument.
            if parent in runs:
                continue
            return False
        call = parents.get(parent) if isinstance(parent, ast.Attribute) else None
        if not (
            isinstance(parent, ast.Attribute)
            and isinstance(call, ast.Call)
            and call.func is parent
            and not call.keywords
        ):
            return False
        if parent.attr == "append" and len(call.args) == 1:
            added = call.args
        elif parent.attr == "insert" and len(call.args) == 2:
            added = call.args[1:]
        elif (
            parent.attr == "extend"
            and len(call.args) == 1
            and isinstance(call.args[0], (ast.List, ast.Tuple))
        ):
            added = call.args[0].elts
        else:
            return False
        if not all(_is_step_call(element) for element in added):
            return False
    return True


def _function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    return next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        ),
        None,
    )


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _is_service(node: ast.expr) -> bool:
    """``CalibService(...)`` or ``CalibService.from_context(...)``."""
    if not isinstance(node, ast.Call):
        return False
    if _call_name(node) == "CalibService":
        return True
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "from_context"
        and _call_name(ast.Call(func=func.value, args=[], keywords=[])) == "CalibService"
    )


def _root_name(node: ast.expr) -> str | None:
    """Return the variable at the base of ``a.b[0].c``-style expressions."""
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Starred)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


class _Resolver:
    """Track literal name bindings and drop any binding that may change.

    This is intentionally not an interpreter: anything beyond literal assignment
    invalidates the affected names so callers report "unknown" instead of a guess.
    """

    # Constructors known not to mutate their arguments; names passed to them stay bound.
    pure_calls: frozenset[str] = frozenset(_OVERRIDABLE_TARGETS)

    def __init__(self) -> None:
        self.bindings: dict[str, Any] = {}
        # Names that may share a mutable object; invalidating one invalidates all.
        self.links: dict[str, set[str]] = {}
        self.target_names: set[str] = set()
        self.service_names: set[str] = set()

    def is_service_run(self, node: ast.Call) -> bool:
        return (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and _root_name(node.func.value) in self.service_names
        )

    def invalidate(self, name: str) -> None:
        pending = [name]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            self._forget(current)
            pending.extend(self.links.get(current, ()))

    def _forget(self, name: str) -> None:
        """Drop everything known about one name."""
        self.bindings.pop(name, None)
        self.target_names.discard(name)

    def link(self, name: str, value: ast.expr) -> None:
        for node in ast.walk(value):
            if isinstance(node, ast.Name) and node.id != name:
                self.links.setdefault(name, set()).add(node.id)
                self.links.setdefault(node.id, set()).add(name)

    def literal(self, node: ast.expr) -> Any:
        if isinstance(node, ast.Name):
            if node.id not in self.bindings:
                raise _Unknown
            return self.bindings[node.id]
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            # ``exclude_qids or []``: the first truthy operand, else the last.
            for operand in node.values[:-1]:
                value = self.literal(operand)
                if value:
                    return value
            return self.literal(node.values[-1])
        try:
            return ast.literal_eval(node)
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError) as exc:
            raise _Unknown from exc

    def rebind(self, name: str) -> None:
        """Forget a name before a plain assignment gives it a new value."""
        self.invalidate(name)

    def assign(self, name: str, value: ast.expr | None) -> None:
        self.rebind(name)
        if value is None:
            return
        self.link(name, value)
        with suppress(_Unknown):
            self.bindings[name] = self.literal(value)
        if isinstance(value, ast.Call):
            if _call_name(value) in _OVERRIDABLE_TARGETS:
                self.target_names.add(name)
            elif _is_service(value):
                self.service_names.add(name)

    def bind(self, statement: ast.stmt) -> None:
        """Record simple ``name = value`` statements; invalidate every other write."""
        simple = False
        if isinstance(statement, ast.Assign) and all(
            isinstance(target, ast.Name) for target in statement.targets
        ):
            self.invalidate_writes(statement.value)
            for target in statement.targets:
                assert isinstance(target, ast.Name)
                self.assign(target.id, statement.value)
            simple = True
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            if statement.value is not None:
                self.invalidate_writes(statement.value)
            self.assign(statement.target.id, statement.value)
            simple = True
        if not simple:
            self.invalidate_writes(statement)

    def enter(self, item: ast.withitem) -> None:
        """Bind ``with CalibService(...) as cal`` before visiting the block."""
        self.invalidate_writes(item.context_expr)
        if item.optional_vars is not None:
            self.invalidate_writes(item.optional_vars)
        if isinstance(item.optional_vars, ast.Name) and _is_service(item.context_expr):
            self.service_names.add(item.optional_vars.id)

    def truth(self, test: ast.expr) -> bool:
        """Evaluate ``x``, ``not x``, ``x is None`` and ``x is not None`` tests."""
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            return not self.truth(test.operand)
        if (
            isinstance(test, ast.Compare)
            and len(test.ops) == 1
            and isinstance(test.ops[0], (ast.Is, ast.IsNot))
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value is None
        ):
            is_none = self.literal(test.left) is None
            return is_none if isinstance(test.ops[0], ast.Is) else not is_none
        return bool(self.literal(test))

    def invalidate_writes(self, tree: ast.AST) -> None:
        """Drop bindings that ``tree`` may rebind or mutate."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                self.invalidate(node.id)
            elif isinstance(node, (ast.Subscript, ast.Attribute)) and isinstance(
                node.ctx, (ast.Store, ast.Del)
            ):
                root = _root_name(node.value)
                if root is not None:
                    self.invalidate(root)
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                for name in node.names:
                    self.invalidate(name)
            elif isinstance(node, ast.Call):
                # Method calls (qids.sort()) and calls receiving a name
                # (shuffle(qids)) may mutate it in place. CalibService.run only
                # reads its targets, so it keeps them resolvable.
                if self.is_service_run(node):
                    continue
                if isinstance(node.func, ast.Attribute):
                    root = _root_name(node.func.value)
                    if root is not None:
                        self.invalidate(root)
                if _call_name(node) not in self.pure_calls and not _is_service(node):
                    for argument in [*node.args, *(kw.value for kw in node.keywords)]:
                        root = _root_name(argument)
                        if root is not None:
                            self.invalidate(root)


def resolve_target_defaults(
    code: str, function_name: str, parameters: dict[str, Any]
) -> FlowTargetOverride | None:
    """Return a single literal target configuration, never guess across differing targets.

    Only literals and simple name bindings in the entrypoint are inspected. Dynamic
    expressions, mutated values, unsupported target types, and ambiguous sources
    return ``None`` so the UI shows the targets as unknown.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    function = _function(tree, function_name)
    if function is None:
        return None
    try:
        return _resolve(tree, function, parameters)
    except (_Unknown, ValidationError):
        return None


def _prepare(
    tree: ast.Module,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    parameters: dict[str, Any],
    resolver: _Resolver,
) -> None:
    """Bind module literals, then the entrypoint's defaults and the known parameters."""
    # Targets built in other module-level helpers are invisible from the entrypoint.
    for node in tree.body:
        if node is function:
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and (
                _call_name(child).endswith("Targets") or _is_service(child)
            ):
                raise _Unknown

    for statement in tree.body:
        if statement is function:
            # The entrypoint body is resolved statement by statement below.
            continue
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Other functions may run at any time, so anything they could write
            # or mutate is unknown.
            resolver.invalidate_writes(statement)
        else:
            resolver.bind(statement)

    args = function.args
    declared = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    # Function arguments shadow module bindings, including required arguments.
    for arg in [*declared, *(a for a in (args.vararg, args.kwarg) if a is not None)]:
        resolver.invalidate(arg.arg)
    positional = [*args.posonlyargs, *args.args]
    for arg, default in zip(
        positional[len(positional) - len(args.defaults) :], args.defaults, strict=True
    ):
        resolver.assign(arg.arg, default)
    for arg, keyword_default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        if keyword_default is not None:
            resolver.assign(arg.arg, keyword_default)
    for arg in declared:
        if arg.arg in parameters:
            resolver.bindings[arg.arg] = parameters[arg.arg]


def _resolve(
    tree: ast.Module,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    parameters: dict[str, Any],
) -> FlowTargetOverride | None:
    resolver = _Resolver()
    _prepare(tree, function, parameters, resolver)

    candidates: list[FlowTargetOverride] = []

    def collect(tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                candidate = _candidate(node, resolver)
                if candidate is not None:
                    candidates.append(candidate)

    def visit(statements: list[ast.stmt]) -> None:
        for statement in statements:
            if isinstance(statement, ast.If):
                try:
                    taken = resolver.truth(statement.test)
                except _Unknown:
                    pass
                else:
                    # Only the branch the known parameters select can run.
                    visit(statement.body if taken else statement.orelse)
                    continue
            if isinstance(statement, (ast.With, ast.AsyncWith)):
                for item in statement.items:
                    collect(item)
                    resolver.enter(item)
                visit(statement.body)
                continue
            resolver.bind(statement)
            collect(statement)

    visit(function.body)
    if candidates and all(candidate == candidates[0] for candidate in candidates):
        return candidates[0]
    return None


def _candidate(node: ast.Call, resolver: _Resolver) -> FlowTargetOverride | None:
    name = _call_name(node)
    if name.endswith("Targets") and name not in _OVERRIDABLE_TARGETS:
        # AllMuxTargets and similar cannot be shown as defaults.
        raise _Unknown
    if resolver.is_service_run(node):
        target = (
            node.args[0]
            if node.args
            else next((kw.value for kw in node.keywords if kw.arg == "targets"), None)
        )
        if target is None:
            raise _Unknown
        if isinstance(target, ast.Call) and _call_name(target) in _OVERRIDABLE_TARGETS:
            return None
        if isinstance(target, ast.Name) and target.id in resolver.target_names:
            return None
        raise _Unknown
    if name not in _OVERRIDABLE_TARGETS:
        return None
    if any(isinstance(arg, ast.Starred) for arg in node.args) or any(
        kw.arg is None for kw in node.keywords
    ):
        raise _Unknown

    keywords: dict[str, ast.expr] = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
    if name == "MuxTargets":
        for key, arg in zip(("mux_ids", "exclude_qids"), node.args[:2], strict=False):
            keywords.setdefault(key, arg)
    elif name == "QubitTargets" and node.args:
        keywords.setdefault("qids", node.args[0])
    elif name == "CouplingTargets" and node.args:
        keywords.setdefault("pairs", node.args[0])

    values: dict[str, Any] = {}
    for key, expression in keywords.items():
        if key not in {"mux_ids", "qids", "exclude_qids", "pairs"}:
            continue
        value = resolver.literal(expression)
        if value is None:
            continue
        if key == "pairs":
            if not isinstance(value, (list, tuple)):
                raise _Unknown
            values["coupling_pairs"] = [
                list(pair) if isinstance(pair, (list, tuple)) else pair for pair in value
            ]
        else:
            values[key] = value
    if not (values.get("mux_ids") or values.get("qids") or values.get("coupling_pairs")):
        raise _Unknown
    return FlowTargetOverride.model_validate(values)
