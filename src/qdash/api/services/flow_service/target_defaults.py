"""Inspect target defaults without importing or executing user workflow code."""

import ast
from contextlib import suppress
from typing import Any

from pydantic import ValidationError

from qdash.datamodel.flow_targets import FlowTargetOverride

_OVERRIDABLE_TARGETS = {"MuxTargets", "QubitTargets"}


class _Unknown(Exception):
    """The source cannot be resolved to one confident target configuration."""


def flow_parameter_names(code: str, function_name: str) -> set[str]:
    """Return explicitly declared entrypoint parameters."""
    function = _function(ast.parse(code), function_name)
    if function is None:
        return set()
    args = function.args
    return {arg.arg for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]}


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
            self.bindings.pop(current, None)
            self.target_names.discard(current)
            pending.extend(self.links.get(current, ()))

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

    def assign(self, name: str, value: ast.expr | None) -> None:
        self.invalidate(name)
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
                if _call_name(node) not in _OVERRIDABLE_TARGETS and not _is_service(node):
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


def _resolve(
    tree: ast.Module,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    parameters: dict[str, Any],
) -> FlowTargetOverride | None:
    # Targets built in other module-level helpers are invisible from the entrypoint.
    for node in tree.body:
        if node is function:
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and (
                _call_name(child).endswith("Targets") or _is_service(child)
            ):
                raise _Unknown

    resolver = _Resolver()
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
        # AllMuxTargets, CouplingTargets, and similar cannot be shown as defaults.
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

    values: dict[str, Any] = {}
    for key, expression in keywords.items():
        if key not in {"mux_ids", "qids", "exclude_qids"}:
            continue
        value = resolver.literal(expression)
        if value is not None:
            values[key] = value
    if not (values.get("mux_ids") or values.get("qids")):
        raise _Unknown
    return FlowTargetOverride.model_validate(values)
