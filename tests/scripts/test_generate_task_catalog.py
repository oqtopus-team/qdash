"""Task documentation in the generated task catalog."""

import ast
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from qdash.datamodel.task import TaskDocumentation
from qdash.workflow.calibtasks.base import BaseTask

ROOT = Path(__file__).resolve().parents[2]


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "generate_task_catalog", ROOT / "scripts/generate_task_catalog.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_catalog_refuses_unreadable_documentation(tmp_path: Path) -> None:
    backend_dir = tmp_path / "qubex"
    backend_dir.mkdir()
    (backend_dir / "task.py").write_text(
        "class Task:\n"
        '    name = "Task"\n'
        '    task_type = "qubit"\n'
        "    documentation = TaskDocumentation(description=DESCRIPTION)\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match=r"task\.py:Task: TaskDocumentation\.description"):
        _load_generator().build_catalog(tmp_path)


def test_static_documentation_matches_the_runtime_declaration() -> None:
    import qdash.workflow.calibtasks.qubex  # noqa: F401 - registers the qubex tasks

    catalog = _load_generator().build_catalog(ROOT / "src/qdash/workflow/calibtasks")
    entries = {task["name"]: task for task in catalog["backends"]["qubex"]}  # type: ignore[index]

    documented = {
        name: cls
        for name, cls in BaseTask.registry["qubex"].items()
        if cls.documentation is not None
    }
    assert {"CheckChevron", "CheckRabi", "CheckRamsey", "CheckT1"} <= documented.keys()
    for name, cls in documented.items():
        assert cls.documentation is not None
        assert entries[name]["documentation"] == cls.documentation.model_dump(mode="json")
        assert entries[name]["description"] == cls.documentation.description


# Task names used by templates, step defaults, and the pi-qdash calibration skills must carry
# documentation in the packaged catalog that the API serves.
CATALOG_PATH = ROOT / "src/qdash/workflow/calibtasks/task_catalog.json"
TEMPLATE_DIR = ROOT / "src/qdash/workflow/templates"
SKILL_DIR = ROOT / "packages/pi-qdash/skills"


def _packaged_catalog() -> dict[str, dict[str, Any]]:
    """Packaged catalog entries keyed by task name; fake entries fill qubex gaps."""
    backends = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["backends"]
    entries: dict[str, dict[str, Any]] = {}
    for backend in ("fake", "qubex"):
        entries.update({task["name"]: task for task in backends[backend]})
    return entries


def _template_task_names(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        name = (
            function.id
            if isinstance(function, ast.Name)
            else (function.attr if isinstance(function, ast.Attribute) else None)
        )
        if name != "TaskCall":
            continue
        task_name = next((kw.value for kw in node.keywords if kw.arg == "name"), None)
        assert isinstance(task_name, ast.Constant) and isinstance(task_name.value, str), (
            "Template TaskCall must declare a literal name for coverage verification"
        )
        names.add(task_name.value)
    return names


def _used_task_names() -> set[str]:
    from qdash.datamodel.calibration_pipeline import (
        BRINGUP_TASKS,
        CHECK_1Q_TASKS,
        CONFIGURE_ALL_CALL,
        CONFIGURE_CALL,
        FULL_1Q_TASKS,
        FULL_2Q_TASKS,
    )

    defaults = [*BRINGUP_TASKS, *CHECK_1Q_TASKS, *FULL_1Q_TASKS, *FULL_2Q_TASKS]
    names = {call.name for call in defaults} | {CONFIGURE_CALL.name, CONFIGURE_ALL_CALL.name}
    for path in TEMPLATE_DIR.glob("*.py"):
        names |= _template_task_names(path.read_text(encoding="utf-8"))
    words: set[str] = set()
    for path in SKILL_DIR.glob("*/SKILL.md"):
        words |= set(re.findall(r"\b[A-Z]\w+\b", path.read_text(encoding="utf-8")))
    # Discover declarations from source independently of the generated catalog.
    declared: set[str] = set()
    for path in (ROOT / "src/qdash/workflow/calibtasks").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                value = None
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if item.target.id == "name":
                        value = item.value
                elif isinstance(item, ast.Assign):
                    if any(isinstance(t, ast.Name) and t.id == "name" for t in item.targets):
                        value = item.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    declared.add(value.value)
    return names | (words & declared)


def test_tasks_used_by_templates_and_skills_are_documented() -> None:
    catalog = _packaged_catalog()
    used = _used_task_names()
    assert used <= catalog.keys(), f"Tasks missing from catalog: {sorted(used - catalog.keys())}"
    # Guard the inventory itself so a parsing change cannot silently shrink it.
    assert {
        "ConfigureAll",
        "CorrectCaptureDelay",
        "CheckResonatorSpectroscopy",
        "CreateDRAGHPIPulse",
        "CheckGEFRelaxation",
        "CheckCrossResonance",
        "ZX90InterleavedRandomizedBenchmarking",
        "FakeBringUp",
    } <= used
    undocumented = sorted(name for name in used if not catalog[name].get("documentation"))
    assert undocumented == []
    for name in used:
        documentation = TaskDocumentation.model_validate(catalog[name]["documentation"])
        assert documentation.when_to_use, name
        assert catalog[name]["description"] == documentation.description


def test_template_inventory_is_independent_of_catalog_and_quote_style() -> None:
    source = """
TaskCall(name = 'MissingFromCatalog')
workflow.TaskCall(
    name="AnotherMissingTask", run={"shots": 100}
)
OtherObject(name="NotATask")
"""
    assert _template_task_names(source) == {"MissingFromCatalog", "AnotherMissingTask"}


def test_missing_catalog_task_fails_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = _packaged_catalog()
    del catalog["CheckRabi"]
    monkeypatch.setattr(__import__(__name__, fromlist=["_"]), "_packaged_catalog", lambda: catalog)
    with pytest.raises(AssertionError, match=r"Tasks missing from catalog.*CheckRabi"):
        test_tasks_used_by_templates_and_skills_are_documented()
