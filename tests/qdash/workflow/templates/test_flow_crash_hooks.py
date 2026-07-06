"""Registration guard for the on_crashed hook (Issue #1111).

Every flow that finalizes its execution on cancellation must also finalize it on
a crash — otherwise an OOM SIGKILL leaves the execution stuck 'running' forever
(Issue #1111). This test asserts, by parsing the source, that any ``@flow`` whose
decorator sets ``on_cancellation`` also sets ``on_crashed``.

It is source/AST based on purpose: in the test environment ``prefect`` is mocked,
so the ``@flow`` decorator is a no-op and the runtime flow object carries no hook
metadata to inspect. Parsing the decorator keywords is robust to that.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import qdash.workflow

_WORKFLOW_DIR = Path(qdash.workflow.__file__).resolve().parent
_TEMPLATES_DIR = _WORKFLOW_DIR / "templates"
_EXTRA_FLOW_FILES = [_WORKFLOW_DIR / "service" / "single_task_flow.py"]


def _flow_decorator_keywords(decorator: ast.expr) -> set[str] | None:
    """Return the keyword arg names of an ``@flow(...)`` decorator, else None."""
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    is_flow = (isinstance(func, ast.Name) and func.id == "flow") or (
        isinstance(func, ast.Attribute) and func.attr == "flow"
    )
    if not is_flow:
        return None
    return {kw.arg for kw in decorator.keywords if kw.arg is not None}


def _iter_flow_definitions() -> list[tuple[Path, str, set[str]]]:
    """Yield (file, function_name, decorator_keywords) for every @flow(...) found."""
    files = sorted(_TEMPLATES_DIR.glob("*.py")) + _EXTRA_FLOW_FILES
    results: list[tuple[Path, str, set[str]]] = []
    for path in files:
        if not path.exists() or path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                keywords = _flow_decorator_keywords(decorator)
                if keywords is not None:
                    results.append((path, node.name, keywords))
    return results


def test_flow_definitions_are_discovered():
    """Sanity: the AST scan actually finds the flow templates."""
    definitions = _iter_flow_definitions()
    # 11 templates + single_task_flow at time of writing; guard against a broken scan.
    assert len(definitions) >= 10


@pytest.mark.parametrize(
    "path,func,keywords",
    [
        pytest.param(p, f, kw, id=f"{p.stem}:{f}")
        for (p, f, kw) in _iter_flow_definitions()
        if "on_cancellation" in kw
    ],
)
def test_flows_with_cancellation_also_register_on_crashed(path, func, keywords):
    """Any flow handling on_cancellation must also handle on_crashed (Issue #1111)."""
    assert "on_crashed" in keywords, (
        f"{path.name}:{func} registers on_cancellation but not on_crashed — "
        "an OOM SIGKILL would leave its execution stuck 'running' (Issue #1111)."
    )
