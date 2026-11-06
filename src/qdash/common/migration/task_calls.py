"""Find and convert saved Python flows that still list tasks by name.

Since pipeline spec version 2, every step lists its work as ``TaskCall``
entries; ``CustomOneQubit(tasks=["CheckT1"])`` raises at construction. This
module inventories flow files and converts the cases it can prove safe.

It only reads source text and parses it with :mod:`ast`; it never imports,
executes, or evaluates a flow. Conversion writes converted copies to a
separate directory and leaves the originals untouched.

What it converts, keeping comments and formatting elsewhere:

* a list or tuple literal of task-name strings passed as ``tasks=`` to a step,
  or assigned once to a variable that is passed as ``tasks=`` and used nowhere
  else: each string becomes ``TaskCall(name="...")``. A name repeated in one
  list gets explicit call ids ``<Task>``, ``<Task>_2``, ... (rename them to
  describe the calls);
* ``stop_on_failure_tasks=(...)`` on the same step, when the step's list is a
  literal it converts: the named calls get ``on_failure="stop"`` and the
  keyword is removed;
* the ``from qdash.workflow import TaskCall`` import, when a conversion needs it.

What it reports for a person to change: any ``tasks=`` value it cannot prove
holds ``TaskCall`` entries (lists built at run time, variables that are
reassigned, appended to, imported from outside ``qdash``, or not assigned in the
file), task-name lists that are also used outside ``tasks=`` or shared by steps
with different failure policies, step-level ``task_parameters`` (use per-call
settings), and the deprecated ``task_run_parameters``. Names are resolved with
Python's scoping rules, so a local variable that shadows a module-level list is
judged by its own assignment.

Usage::

    python -m qdash.common.migration.task_calls [PATH ...] [--write-to DIR] [--json]

PATH defaults to the user flows directory. Exit status is 0 when nothing needs
attention, 1 when a file needs conversion or manual changes, 2 on a read error.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

STEP_CLASSES = frozenset(
    {
        "BringUp",
        "CustomOneQubit",
        "CustomTwoQubit",
        "OneQubitCheck",
        "OneQubitFineTune",
        "TwoQubitCalibration",
    }
)
TASK_CALL_IMPORT = "from qdash.workflow import TaskCall\n"


@dataclass
class Finding:
    """One place in a flow file that the migration looked at."""

    line: int
    kind: str
    message: str
    converted: bool = False


@dataclass
class FileReport:
    """What the migration found and did in one file."""

    path: str
    findings: list[Finding] = field(default_factory=list)
    converted_source: str | None = None
    error: str | None = None

    @property
    def needs_attention(self) -> bool:
        return self.error is not None or bool(self.findings)

    @property
    def manual(self) -> list[Finding]:
        return [finding for finding in self.findings if not finding.converted]


@dataclass
class _Edit:
    start: tuple[int, int]
    end: tuple[int, int]
    text: str


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _string_items(node: ast.AST) -> list[ast.Constant] | None:
    """The elements of a list/tuple literal when every one is a string constant."""
    if not isinstance(node, ast.List | ast.Tuple) or not node.elts:
        return None
    items: list[ast.Constant] = []
    for element in node.elts:
        if not (isinstance(element, ast.Constant) and isinstance(element.value, str)):
            return None
        items.append(element)
    return items


def _call_texts(names: list[str], stop: set[str]) -> list[str]:
    counts = Counter(names)
    seen: Counter[str] = Counter()
    texts: list[str] = []
    for name in names:
        seen[name] += 1
        arguments = [f'name="{name}"']
        if counts[name] > 1:
            call_id = name if seen[name] == 1 else f"{name}_{seen[name]}"
            arguments.append(f'call_id="{call_id}"')
        if name in stop:
            arguments.append('on_failure="stop"')
        texts.append(f"TaskCall({', '.join(arguments)})")
    return texts


_MUTATING_METHODS = frozenset({"append", "extend", "insert"})
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)


@dataclass(eq=False)
class _Scope:
    """One Python name scope: the module, a function, a class body, or a comprehension."""

    kind: str
    parent: _Scope | None
    bindings: dict[str, list[_Binding]] = field(default_factory=dict)
    global_names: set[str] = field(default_factory=set)
    nonlocal_names: set[str] = field(default_factory=set)


@dataclass(eq=False)
class _Binding:
    """One statement or construct that binds a name in a scope.

    ``kind`` is ``assign`` (``name = value`` or ``name: T = value``), ``augment``
    (``name += value``), ``parameter``, ``import``, or ``other`` (loop targets,
    unpacking, ``with ... as``, ``del``, definitions, and so on).
    """

    kind: str
    line: int
    value: ast.expr | None = None
    statement: ast.Assign | ast.AnnAssign | None = None
    value_scope: _Scope | None = None
    annotation: str = ""
    module: str = ""


@dataclass
class _Load:
    node: ast.Name
    scope: _Scope


@dataclass
class _StepUse:
    call: ast.Call
    name: str
    keywords: dict[str, ast.keyword]
    scope: _Scope


@dataclass
class _Problem:
    kind: str
    line: int
    message: str


class _Collector(ast.NodeVisitor):
    """Record every scope, binding, name load, and step call, without evaluating code."""

    def __init__(self) -> None:
        self.module = _Scope("module", None)
        self.scope = self.module
        self.loads: list[_Load] = []
        self.steps: list[_StepUse] = []
        self.findings: list[Finding] = []
        self.parents: dict[ast.AST, ast.AST] = {}

    # Scopes and bindings ---------------------------------------------------

    def _push(self, kind: str) -> _Scope:
        self.scope = _Scope(kind, self.scope)
        return self.scope

    def _pop(self) -> None:
        assert self.scope.parent is not None
        self.scope = self.scope.parent

    def _target_scope(self, name: str, scope: _Scope) -> _Scope:
        if name in scope.global_names:
            return self.module
        if name in scope.nonlocal_names:
            enclosing = scope.parent
            while enclosing is not None:
                if enclosing.kind == "function" and name in enclosing.bindings:
                    return enclosing
                enclosing = enclosing.parent
        return scope

    def _bind(self, name: str, binding: _Binding, scope: _Scope | None = None) -> None:
        target = self._target_scope(name, scope or self.scope)
        target.bindings.setdefault(name, []).append(binding)

    def _bind_parameters(self, arguments: ast.arguments) -> None:
        every = [
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
            *([arguments.vararg] if arguments.vararg else []),
            *([arguments.kwarg] if arguments.kwarg else []),
        ]
        for argument in every:
            annotation = ast.unparse(argument.annotation) if argument.annotation else ""
            self._bind(
                argument.arg,
                _Binding("parameter", argument.lineno, annotation=annotation.replace(" ", "")),
            )

    def _visit_all(self, nodes: Iterable[ast.AST]) -> None:
        for node in nodes:
            self.visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> None:
        arguments = node.args
        self._visit_all(arguments.defaults)
        self._visit_all(d for d in arguments.kw_defaults if d is not None)
        if not isinstance(node, ast.Lambda):
            self._visit_all(node.decorator_list)
            for argument in [
                *arguments.posonlyargs,
                *arguments.args,
                *arguments.kwonlyargs,
                *([arguments.vararg] if arguments.vararg else []),
                *([arguments.kwarg] if arguments.kwarg else []),
            ]:
                if argument.annotation is not None:
                    self.visit(argument.annotation)
            if node.returns is not None:
                self.visit(node.returns)
            self._bind(node.name, _Binding("other", node.lineno))
        self._push("function")
        self._bind_parameters(arguments)
        if isinstance(node, ast.Lambda):
            self.visit(node.body)
        else:
            self._visit_all(node.body)
        self._pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_all(node.decorator_list)
        self._visit_all(node.bases)
        for keyword in node.keywords:
            self.visit(keyword.value)
        self._bind(node.name, _Binding("other", node.lineno))
        self._push("class")
        self._visit_all(node.body)
        self._pop()

    def _visit_comprehension(
        self,
        node: ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp,
        elements: list[ast.expr],
    ) -> None:
        # The first iterable is evaluated in the enclosing scope.
        self.visit(node.generators[0].iter)
        self._push("comprehension")
        for index, generator in enumerate(node.generators):
            self.visit(generator.target)
            if index:
                self.visit(generator.iter)
            self._visit_all(generator.ifs)
        self._visit_all(elements)
        self._pop()

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node, [node.elt])

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node, [node.elt])

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node, [node.elt])

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node, [node.key, node.value])

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        scope = self.scope
        while scope.kind == "comprehension" and scope.parent is not None:
            scope = scope.parent
        self._bind(node.target.id, _Binding("other", node.lineno), scope)

    def visit_Global(self, node: ast.Global) -> None:
        self.scope.global_names.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.scope.nonlocal_names.update(node.names)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            self._bind(
                node.targets[0].id,
                _Binding("assign", node.lineno, node.value, node, self.scope),
            )
            return
        self._visit_all(node.targets)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)
        if isinstance(node.target, ast.Name):
            if node.value is not None:
                binding = _Binding("assign", node.lineno, node.value, node, self.scope)
            else:
                binding = _Binding("other", node.lineno)
            self._bind(node.target.id, binding)
            return
        self.visit(node.target)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.value)
        if isinstance(node.target, ast.Name):
            self._bind(
                node.target.id,
                _Binding("augment", node.lineno, node.value, value_scope=self.scope),
            )
            return
        self.visit(node.target)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            bound = alias.asname or alias.name.split(".")[0]
            self._bind(bound, _Binding("import", node.lineno, module=alias.name))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        for alias in node.names:
            if alias.name == "*":
                continue
            self._bind(alias.asname or alias.name, _Binding("import", node.lineno, module=module))

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self._bind(node.name, _Binding("other", node.lineno))
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self._bind(node.name, _Binding("other", node.lineno))
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self._bind(node.name, _Binding("other", node.lineno))

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self._bind(node.rest, _Binding("other", node.lineno))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.loads.append(_Load(node, self.scope))
        else:
            self._bind(node.id, _Binding("other", node.lineno))

    # Calls ----------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        keywords = {keyword.arg: keyword for keyword in node.keywords if keyword.arg}
        if name in STEP_CLASSES:
            assert name is not None
            self.steps.append(_StepUse(node, name, keywords, self.scope))
        if name == "CalibService" and "task_run_parameters" in keywords:
            self.findings.append(
                Finding(
                    node.lineno,
                    "task_run_parameters",
                    "CalibService(task_run_parameters=...) is deprecated; move the values to "
                    'task_parameters={"<Task>": {"run": {...}}}',
                )
            )
        self.generic_visit(node)


def _resolve(scope: _Scope, name: str, module: _Scope) -> _Scope | None:
    """The scope whose binding a load of ``name`` in ``scope`` refers to."""
    if name in scope.global_names:
        return module if name in module.bindings else None
    current: _Scope | None = scope
    while current is not None:
        # A class body's names are not visible from functions defined inside it.
        visible = current is scope or current.kind != "class"
        if visible and name not in current.nonlocal_names and name in current.bindings:
            return current
        current = current.parent
    return None


def _is_task_call(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and _call_name(node) == "TaskCall"


class _Analyzer:
    def __init__(self, tree: ast.Module) -> None:
        collector = _Collector()
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                collector.parents[child] = parent
        collector.visit(tree)
        self.module = collector.module
        self.parents = collector.parents
        self.steps = collector.steps
        self.findings: list[Finding] = list(collector.findings)
        self.edits: list[_Edit] = []
        self.pending_keyword_removals: list[tuple[ast.Call, ast.keyword]] = []
        task_values = {
            id(step.keywords["tasks"].value) for step in self.steps if "tasks" in step.keywords
        }
        # Loads of each (scope, name), split into ``tasks=`` arguments and every other use.
        self.task_loads: dict[tuple[int, str], list[_Load]] = {}
        self.other_loads: dict[tuple[int, str], list[_Load]] = {}
        for load in collector.loads:
            target = _resolve(load.scope, load.node.id, self.module)
            if target is None:
                continue
            key = (id(target), load.node.id)
            bucket = self.task_loads if id(load.node) in task_values else self.other_loads
            bucket.setdefault(key, []).append(load)

    # Classification ---------------------------------------------------------

    def _mutation_problems(
        self, scope: _Scope, name: str, seen: set[tuple[int, str]]
    ) -> list[_Problem]:
        """Problems from ``name.append(x)``-style edits that may add task names."""
        problems: list[_Problem] = []
        for use in self.other_loads.get((id(scope), name), []):
            load = use.node
            parent = self.parents.get(load)
            if isinstance(parent, ast.Subscript) and not isinstance(parent.ctx, ast.Load):
                problems.append(
                    _Problem(
                        "dynamic_tasks", load.lineno, f"{name!r} is changed by item assignment"
                    )
                )
                continue
            if not (isinstance(parent, ast.Attribute) and parent.attr in _MUTATING_METHODS):
                continue
            call = self.parents.get(parent)
            if not (isinstance(call, ast.Call) and call.func is parent):
                continue
            added = call.args[-1:] if parent.attr != "extend" else call.args[:1]
            for argument in added:
                if parent.attr == "extend":
                    problems.extend(
                        self._classify(argument, use.scope, seen, f"{name}.extend(...)")
                    )
                elif not _is_task_call(argument):
                    problems.append(
                        _Problem(
                            "dynamic_tasks",
                            load.lineno,
                            f"{name}.{parent.attr}(...) adds an entry that is not a TaskCall",
                        )
                    )
        return problems

    def _classify_name(
        self, node: ast.Name, scope: _Scope, seen: set[tuple[int, str]]
    ) -> list[_Problem]:
        name = node.id
        target = _resolve(scope, name, self.module)
        if target is None:
            return [
                _Problem("dynamic_tasks", node.lineno, f"{name!r} is not assigned in this file")
            ]
        key = (id(target), name)
        if key in seen:
            # Already being classified; its other bindings decide.
            return []
        seen.add(key)
        problems: list[_Problem] = []
        for binding in target.bindings[name]:
            if binding.kind == "import":
                if binding.module != "qdash" and not binding.module.startswith("qdash."):
                    problems.append(
                        _Problem(
                            "dynamic_tasks",
                            binding.line,
                            f"{name!r} is imported from {binding.module or 'a relative module'}",
                        )
                    )
            elif binding.kind == "parameter":
                if "TaskCall" in binding.annotation:
                    continue
                if "str" in binding.annotation:
                    problems.append(_Problem("task_name_parameter", binding.line, name))
                else:
                    problems.append(
                        _Problem(
                            "dynamic_tasks",
                            binding.line,
                            f"parameter {name!r} is not annotated as a list of TaskCall",
                        )
                    )
            elif binding.kind in ("assign", "augment"):
                assert binding.value is not None and binding.value_scope is not None
                problems.extend(
                    self._classify(binding.value, binding.value_scope, seen, repr(name))
                )
            else:
                problems.append(
                    _Problem(
                        "dynamic_tasks",
                        binding.line,
                        f"{name!r} is also bound by a statement this check cannot follow",
                    )
                )
        return problems + self._mutation_problems(target, name, seen)

    def _classify(
        self, node: ast.expr, scope: _Scope, seen: set[tuple[int, str]], where: str
    ) -> list[_Problem]:
        """Why ``node`` might not be a list of ``TaskCall``; empty when it provably is."""
        if isinstance(node, ast.Constant) and node.value is None:
            return []
        if _string_items(node) is not None:
            return [_Problem("dynamic_tasks", node.lineno, f"{where} lists task names")]
        if isinstance(node, ast.List | ast.Tuple):
            problems: list[_Problem] = []
            for element in node.elts:
                if _is_task_call(element):
                    continue
                if isinstance(element, ast.Starred):
                    problems.extend(self._classify(element.value, scope, seen, where))
                elif isinstance(element, ast.Constant) and isinstance(element.value, str):
                    problems.append(
                        _Problem(
                            "dynamic_tasks",
                            element.lineno,
                            f"{where} holds the task name {element.value!r}",
                        )
                    )
                else:
                    problems.append(
                        _Problem(
                            "dynamic_tasks",
                            element.lineno,
                            f"{where} holds {ast.unparse(element)!r}, which is not a TaskCall",
                        )
                    )
            return problems
        if isinstance(node, ast.Name):
            return self._classify_name(node, scope, seen)
        if isinstance(node, ast.BoolOp):
            return [p for value in node.values for p in self._classify(value, scope, seen, where)]
        if isinstance(node, ast.IfExp):
            return self._classify(node.body, scope, seen, where) + self._classify(
                node.orelse, scope, seen, where
            )
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self._classify(node.left, scope, seen, where) + self._classify(
                node.right, scope, seen, where
            )
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("list", "tuple")
            and len(node.args) == 1
            and not node.keywords
            and _resolve(scope, node.func.id, self.module) is None
        ):
            return self._classify(node.args[0], scope, seen, where)
        if isinstance(node, ast.ListComp) and _is_task_call(node.elt):
            return []
        return [
            _Problem(
                "dynamic_tasks",
                node.lineno,
                f"{where} is {ast.unparse(node)!r}, which is computed at run time",
            )
        ]

    # Conversion -------------------------------------------------------------

    def _convert_literal(self, node: ast.expr, stop: set[str], where: str) -> None:
        items = _string_items(node)
        assert items is not None
        names = [str(item.value) for item in items]
        for item, text in zip(items, _call_texts(names, stop), strict=True):
            assert item.end_lineno is not None and item.end_col_offset is not None
            self.edits.append(
                _Edit((item.lineno, item.col_offset), (item.end_lineno, item.end_col_offset), text)
            )
        repeated = sorted(name for name, count in Counter(names).items() if count > 1)
        note = f"; repeated {', '.join(repeated)} got generated call_ids" if repeated else ""
        self.findings.append(
            Finding(node.lineno, "task_names", f"{where}: task names became TaskCall{note}", True)
        )

    def _remove_keyword(
        self, call: ast.Call, keyword: ast.keyword, source_lines: list[str]
    ) -> None:
        index = call.keywords.index(keyword)
        value = keyword.value
        assert value.end_lineno is not None and value.end_col_offset is not None
        start = (keyword.lineno, keyword.col_offset)
        end = (value.end_lineno, value.end_col_offset)
        line = source_lines[end[0] - 1]
        rest = line[end[1] :]
        stripped = rest.lstrip()
        if stripped.startswith(","):
            end = (end[0], end[1] + (len(rest) - len(stripped)) + 1)
        elif index > 0:
            previous = call.keywords[index - 1].value
            assert previous.end_lineno is not None and previous.end_col_offset is not None
            start = (previous.end_lineno, previous.end_col_offset)
        self.edits.append(_Edit(start, end, ""))

    @staticmethod
    def _stop_names(step: _StepUse) -> tuple[ast.keyword | None, set[str] | None]:
        keyword = step.keywords.get("stop_on_failure_tasks")
        if keyword is None:
            return None, set()
        items = _string_items(keyword.value)
        return keyword, ({str(item.value) for item in items} if items is not None else None)

    def _convertible_binding(self, step: _StepUse) -> tuple[_Scope, str, _Binding] | None:
        """The single string-list assignment a step's ``tasks=name`` refers to, if safe."""
        value = step.keywords["tasks"].value
        if not isinstance(value, ast.Name):
            return None
        target = _resolve(step.scope, value.id, self.module)
        if target is None:
            return None
        bindings = target.bindings[value.id]
        if len(bindings) != 1 or bindings[0].kind != "assign":
            return None
        binding = bindings[0]
        assert binding.value is not None
        if _string_items(binding.value) is None:
            return None
        return target, value.id, binding

    def analyze(self) -> None:
        groups: dict[int, tuple[_Scope, str, _Binding, list[_StepUse]]] = {}
        for step in self.steps:
            self._check_step_options(step)
            if "tasks" not in step.keywords:
                self._finish_stop(step, converted=False)
                continue
            value = step.keywords["tasks"].value
            if _string_items(value) is not None:
                _, stop = self._stop_names(step)
                self._convert_literal(value, stop or set(), f"{step.name}(tasks=[...])")
                self._finish_stop(step, converted=True)
                continue
            found = self._convertible_binding(step)
            if found is not None:
                scope, name, binding = found
                groups.setdefault(id(binding), (scope, name, binding, []))[3].append(step)
                continue
            self._report(step, self._classify(value, step.scope, set(), f"{step.name}(tasks=...)"))
            self._finish_stop(step, converted=False)
        for scope, name, binding, uses in groups.values():
            self._convert_group(scope, name, binding, uses)

    def _check_step_options(self, step: _StepUse) -> None:
        if "task_parameters" in step.keywords:
            self.findings.append(
                Finding(
                    step.call.lineno,
                    "step_task_parameters",
                    f"{step.name}(task_parameters=...) is not a step option; put the settings on "
                    'the step\'s calls, e.g. TaskCall(name="CheckRamsey", run={...})',
                )
            )
        if step.call.args or any(keyword.arg is None for keyword in step.call.keywords):
            self.findings.append(
                Finding(
                    step.call.lineno,
                    "dynamic_tasks",
                    f"{step.name}(...) takes positional or **keyword arguments; check by hand that "
                    "any task list it receives holds TaskCall entries",
                )
            )

    def _report(self, step: _StepUse, problems: list[_Problem]) -> None:
        reasons = [problem for problem in problems if problem.kind == "dynamic_tasks"]
        for problem in problems:
            if problem.kind == "task_name_parameter":
                self.findings.append(
                    Finding(
                        problem.line,
                        "task_name_parameter",
                        f"parameter {problem.message!r} is annotated as a list of task names and "
                        f"is passed to {step.name}(tasks=...); annotate it list[TaskCall] (flow "
                        'runs then pass [{"name": "CheckRabi"}, ...]) or convert the names with '
                        "[TaskCall(name=n) for n in names]",
                    )
                )
        if reasons:
            detail = "; ".join(
                f"{problem.message} (line {problem.line})"
                for problem in sorted(reasons, key=lambda problem: problem.line)
            )
            self.findings.append(
                Finding(
                    step.call.lineno,
                    "dynamic_tasks",
                    f"{step.name}(tasks=...) cannot be checked without running the flow: {detail}; "
                    "make sure it yields TaskCall entries, e.g. [TaskCall(name=n) for n in names] "
                    "with a call_id for repeated tasks",
                )
            )

    def _finish_stop(self, step: _StepUse, converted: bool) -> None:
        keyword, stop = self._stop_names(step)
        if keyword is None:
            return
        if converted and stop is not None:
            self.findings.append(
                Finding(
                    step.call.lineno,
                    "stop_on_failure_tasks",
                    'stop_on_failure_tasks became on_failure="stop" on the named calls',
                    True,
                )
            )
            self.pending_keyword_removals.append((step.call, keyword))
            return
        self.findings.append(
            Finding(
                step.call.lineno,
                "stop_on_failure_tasks",
                'replace stop_on_failure_tasks with on_failure="stop" on those calls',
            )
        )

    def _convert_group(
        self, scope: _Scope, name: str, binding: _Binding, uses: list[_StepUse]
    ) -> None:
        other = self.other_loads.get((id(scope), name), [])
        stops = [self._stop_names(step)[1] for step in uses]
        if other:
            lines = ", ".join(str(use.node.lineno) for use in other)
            for step in uses:
                self.findings.append(
                    Finding(
                        step.call.lineno,
                        "shared_list",
                        f"{name} is passed to {step.name}(tasks=...) and also used at line(s) "
                        f"{lines}; convert it to TaskCall entries by hand and update those uses",
                    )
                )
                self._finish_stop(step, converted=False)
            return
        if any(stop is None for stop in stops) or any(stop != stops[0] for stop in stops):
            for step in uses:
                self.findings.append(
                    Finding(
                        step.call.lineno,
                        "shared_list",
                        f"{name} is shared by steps with different stop_on_failure_tasks; give "
                        'each step its own list with on_failure="stop" on the prerequisite calls',
                    )
                )
                self._finish_stop(step, converted=False)
            return
        assert binding.value is not None and stops[0] is not None
        steps = ", ".join(sorted({step.name for step in uses}))
        self._convert_literal(binding.value, stops[0], f"{name} (used by {steps})")
        statement = binding.statement
        if (
            isinstance(statement, ast.AnnAssign)
            and ast.unparse(statement.annotation) == "list[str]"
        ):
            annotation = statement.annotation
            assert annotation.end_lineno is not None and annotation.end_col_offset is not None
            self.edits.append(
                _Edit(
                    (annotation.lineno, annotation.col_offset),
                    (annotation.end_lineno, annotation.end_col_offset),
                    "list[TaskCall]",
                )
            )
        for step in uses:
            self._finish_stop(step, converted=True)


def _offset(lines: list[str], position: tuple[int, int]) -> int:
    line, column = position
    return sum(len(text) for text in lines[: line - 1]) + len(
        lines[line - 1].encode()[:column].decode()
    )


def _apply(source: str, edits: list[_Edit]) -> str:
    lines = source.splitlines(keepends=True)
    result = source
    for edit in sorted(edits, key=lambda item: item.start, reverse=True):
        start = _offset(lines, edit.start)
        end = _offset(lines, edit.end)
        result = result[:start] + edit.text + result[end:]
    return result


def _with_import(source: str, tree: ast.Module) -> str:
    # Only a module-level import binds the name for module-level and function code.
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and any(
            alias.name == "TaskCall" and alias.asname in (None, "TaskCall") for alias in node.names
        ):
            return source
    imports = [node for node in tree.body if isinstance(node, ast.Import | ast.ImportFrom)]
    lines = source.splitlines(keepends=True)
    if imports:
        last = imports[-1]
        assert last.end_lineno is not None
        index = last.end_lineno
    else:
        index = 0
        if tree.body and isinstance(tree.body[0], ast.Expr):
            docstring = tree.body[0]
            assert docstring.end_lineno is not None
            index = docstring.end_lineno
    lines.insert(index, TASK_CALL_IMPORT)
    return "".join(lines)


def analyze_source(source: str, path: str = "<source>") -> FileReport:
    """Report, and where safe convert, one flow's source text."""
    report = FileReport(path=path)
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        report.error = f"cannot parse: {exc}"
        return report
    analyzer = _Analyzer(tree)
    analyzer.analyze()
    source_lines = source.splitlines(keepends=True)
    for call, keyword in analyzer.pending_keyword_removals:
        analyzer._remove_keyword(call, keyword, source_lines)
    unique = {(f.line, f.kind, f.message, f.converted): f for f in analyzer.findings}
    report.findings = sorted(unique.values(), key=lambda finding: finding.line)
    if analyzer.edits:
        converted = _apply(source, analyzer.edits)
        converted = _with_import(converted, ast.parse(converted))
        ast.parse(converted)  # the conversion must stay valid Python
        report.converted_source = converted
    return report


def _flow_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(p for p in path.rglob("*.py") if "__pycache__" not in p.parts))
        else:
            files.append(path)
    return files


def _default_paths() -> list[Path]:
    from qdash.common.config.path_resolver import resolve_user_flows_dir

    return [resolve_user_flows_dir()]


def run(paths: list[Path], write_to: Path | None) -> list[FileReport]:
    """Analyze flow files and, with ``write_to``, write converted copies there."""
    reports: list[FileReport] = []
    files = _flow_files(paths)
    roots = [path if path.is_dir() else path.parent for path in paths]
    for file in files:
        try:
            source = file.read_text(encoding="utf-8")
        except OSError as exc:
            reports.append(FileReport(path=str(file), error=str(exc)))
            continue
        report = analyze_source(source, str(file))
        reports.append(report)
        if write_to is not None and report.converted_source is not None:
            root = next((root for root in roots if file.is_relative_to(root)), file.parent)
            destination = write_to / file.relative_to(root)
            if destination.resolve() == file.resolve():
                raise ValueError(f"--write-to would overwrite {file}; choose another directory")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(report.converted_source, encoding="utf-8")
    return reports


def _print_text(reports: list[FileReport], write_to: Path | None) -> None:
    for report in reports:
        if not report.needs_attention:
            continue
        print(report.path)
        if report.error:
            print(f"  error: {report.error}")
        for finding in report.findings:
            status = "converted" if finding.converted else "manual"
            print(f"  line {finding.line}: [{status}] {finding.message}")
        if report.converted_source is not None and write_to is None:
            print("  (run with --write-to DIR to write the converted copy)")
    attention = [report for report in reports if report.needs_attention]
    print(f"{len(reports)} file(s) checked, {len(attention)} need attention")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m qdash.common.migration.task_calls",
        description="Find saved flows that list tasks by name and convert them to TaskCall.",
    )
    parser.add_argument("paths", nargs="*", type=Path, help="Flow files or directories")
    parser.add_argument(
        "--write-to", type=Path, default=None, help="Write converted copies to this directory"
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON")
    args = parser.parse_args(argv)
    paths = args.paths or _default_paths()
    reports = run(paths, args.write_to)
    if args.json:
        payload = [
            {
                "path": report.path,
                "error": report.error,
                "converted": report.converted_source is not None,
                "findings": [asdict(finding) for finding in report.findings],
            }
            for report in reports
        ]
        print(json.dumps(payload, indent=2))
    else:
        _print_text(reports, args.write_to)
    if any(report.error for report in reports):
        return 2
    return 1 if any(report.needs_attention for report in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
