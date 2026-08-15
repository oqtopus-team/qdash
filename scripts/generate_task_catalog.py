"""Generate API-facing task metadata from loaded workflow task classes."""

from __future__ import annotations

import argparse
import inspect
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

# Importing workflow task classes currently initializes modules that read the
# application settings. Catalog generation does not use those services, but it
# still needs deterministic placeholder values in environments without a .env,
# such as CI.
os.environ.setdefault("ENV", "catalog")
os.environ.setdefault("PREFECT_API_URL", "http://localhost:4200/api")
os.environ.setdefault("POSTGRES_DATA_PATH", ".qdash/catalog/postgres")
os.environ.setdefault("MONGO_DATA_PATH", ".qdash/catalog/mongo")
os.environ.setdefault("CALIB_DATA_PATH", ".qdash/catalog/calib")

from qdash.datamodel.task import CalibrationInputSpec
from qdash.workflow.calibtasks import BaseTask

if TYPE_CHECKING:
    from collections.abc import Mapping

DEFAULT_OUTPUT = Path("src/qdash/workflow/calibtasks/task_catalog.json")


def _serialize_parameters(parameters: Mapping[str, object]) -> dict[str, dict[str, Any]]:
    serialized: dict[str, dict[str, Any]] = {}
    for name, value in parameters.items():
        if isinstance(value, (CalibrationInputSpec, BaseModel)):
            serialized[name] = value.model_dump(mode="json", exclude_defaults=True)
        elif value is None:
            serialized[name] = {}
    return serialized


def build_catalog(base_path: Path) -> dict[str, object]:
    """Build deterministic task metadata for every registered backend."""
    backends: dict[str, list[dict[str, object]]] = {}
    for backend, registered_tasks in sorted(BaseTask.registry.items()):
        tasks: list[dict[str, object]] = []
        for name, task_class in sorted(registered_tasks.items()):
            source_path = inspect.getsourcefile(task_class)
            if source_path is None:
                raise RuntimeError(f"Source file not found for {task_class.__name__}")
            path = Path(source_path).resolve()
            try:
                file_path = str(path.relative_to((base_path / backend).resolve()))
            except ValueError:
                file_path = str(path.relative_to(base_path.resolve()))

            tasks.append(
                {
                    "name": name,
                    "class_name": task_class.__name__,
                    "task_type": task_class.task_type,
                    "description": inspect.getdoc(task_class),
                    "file_path": file_path,
                    "input_parameters": _serialize_parameters(task_class.input_spec),
                    "run_parameters": _serialize_parameters(task_class.run_spec),
                }
            )
        backends[backend] = tasks
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
