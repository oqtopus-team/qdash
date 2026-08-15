"""Generate API-facing task metadata by statically parsing task source files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING

from qdash.api.services.task_file_service import TaskFileService

if TYPE_CHECKING:
    from qdash.api.schemas.task_file import TaskInfo

DEFAULT_OUTPUT = Path("src/qdash/workflow/calibtasks/task_catalog.json")


def build_catalog(base_path: Path) -> dict[str, object]:
    """Build deterministic task metadata without importing workflow modules."""
    service = TaskFileService(calibtasks_base_path=base_path)
    discovered_backends: dict[str, dict[str, TaskInfo]] = {}
    for backend_path in sorted(base_path.iterdir()):
        if not backend_path.is_dir() or backend_path.name.startswith("_"):
            continue
        discovered = service._collect_tasks_from_directory(backend_path, backend_path)
        tasks_by_name: dict[str, TaskInfo] = {}
        for task in discovered:
            current = tasks_by_name.get(task.name)
            task_score = (
                task.file_path == "qubex_compat.py",
                task.task_type is not None,
                len(task.input_parameters) + len(task.run_parameters),
            )
            current_score = (
                (
                    current.file_path == "qubex_compat.py",
                    current.task_type is not None,
                    len(current.input_parameters) + len(current.run_parameters),
                )
                if current is not None
                else (False, False, -1)
            )
            if current is None or task_score > current_score:
                tasks_by_name[task.name] = task
        discovered_backends[backend_path.name] = tasks_by_name

    # Fake adapters inherit their parameter declarations from the production
    # task. Resolve that inheritance from the already parsed qubex metadata.
    qubex_tasks = discovered_backends.get("qubex", {})
    for task in discovered_backends.get("fake", {}).values():
        if task.file_path != "qubex_compat.py":
            continue
        inherited = qubex_tasks.get(task.name)
        if inherited is None:
            continue
        task.task_type = task.task_type or inherited.task_type
        task.input_parameters = task.input_parameters or inherited.input_parameters
        task.run_parameters = task.run_parameters or inherited.run_parameters

    backends: dict[str, list[dict[str, object]]] = {}
    for backend, tasks_by_name in discovered_backends.items():
        backends[backend] = [
            task.model_dump(mode="json", exclude={"category", "enabled"})
            for task in sorted(tasks_by_name.values(), key=lambda task: task.name)
        ]
    return {"version": 1, "backends": backends}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the existing catalog differs from generated metadata",
    )
    args = parser.parse_args()

    output = args.output.resolve()
    catalog = build_catalog(DEFAULT_OUTPUT.parent.resolve())
    rendered = json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"Task catalog is stale; run: uv run {__file__}")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
