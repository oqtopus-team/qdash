"""Service for task file operations."""

from __future__ import annotations

import ast
import contextlib
import json
import logging
import math
import operator
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from fastapi import HTTPException

from qdash.api.schemas.task_file import (
    BackendConfigResponse,
    ListTaskFileBackendsResponse,
    ListTaskInfoResponse,
    TaskFileBackend,
    TaskFileSettings,
    TaskInfo,
)
from qdash.common.config.backend import (
    get_default_backend,
    get_task_category,
    get_task_groups,
    get_tasks,
    load_backend_config,
)
from qdash.common.config.loader import ConfigLoader
from qdash.common.config.path_resolver import resolve_calibtasks_base_path

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable

TASK_METADATA_CACHE_VERSION = 3
TASK_CATALOG_FILENAME = "task_catalog.json"


class TaskFileService:
    """Service for task discovery and metadata extraction."""

    def __init__(self, calibtasks_base_path: Path | None = None) -> None:
        """Initialize the service.

        Parameters
        ----------
        calibtasks_base_path : Path | None
            Base path for calibration task files. Defaults to CALIBTASKS_DIR.

        """
        self._base_path = calibtasks_base_path or resolve_calibtasks_base_path()
        self._task_cache: dict[str, tuple[float, list[TaskInfo]]] = {}

    def get_settings(self) -> TaskFileSettings:
        """Get task file settings from config/app/settings.yaml.

        Returns
        -------
        TaskFileSettings
            Task file settings including default backend.

        """
        try:
            settings = ConfigLoader.load_settings()
            ui_settings = settings.get("ui", {})
            task_files_settings = ui_settings.get("task_files", {})
            return TaskFileSettings(
                default_backend=get_default_backend(),
                default_view_mode=task_files_settings.get("default_view_mode"),
                sort_order=task_files_settings.get("sort_order"),
            )
        except Exception as e:
            logger.warning(f"Failed to load task file settings: {e}")

        return TaskFileSettings()

    def list_backends(self) -> ListTaskFileBackendsResponse:
        """List all available backend directories.

        Returns
        -------
        ListTaskFileBackendsResponse
            List of backend names and paths.

        Raises
        ------
        HTTPException
            404 if calibtasks directory not found.

        """
        if not self._base_path.exists():
            raise HTTPException(
                status_code=404, detail=f"Caltasks directory not found: {self._base_path}"
            )

        backends = []
        try:
            for item in sorted(self._base_path.iterdir()):
                if item.name.startswith(".") or item.name == "__pycache__" or not item.is_dir():
                    continue
                backends.append(TaskFileBackend(name=item.name, path=item.name))
        except PermissionError:
            logger.warning(f"Permission denied accessing directory: {self._base_path}")

        return ListTaskFileBackendsResponse(backends=backends)

    def get_backend_config(self) -> BackendConfigResponse:
        """Get backend configuration from config/app/backend.yaml.

        Returns
        -------
        BackendConfigResponse
            Backend configuration.

        """
        try:
            config = load_backend_config()
            default_backend = get_default_backend()
            return BackendConfigResponse(
                default_backend=default_backend,
                backends={
                    name: {"description": b.description, "tasks": get_tasks(name)}
                    for name, b in config.backends.items()
                },
                categories=get_task_groups(default_backend),
            )
        except Exception as e:
            logger.warning(f"Failed to load backend config: {e}")
            return BackendConfigResponse()

    def list_task_info(
        self,
        backend: str,
        sort_order: str | None = None,
        enabled_only: bool = False,
    ) -> ListTaskInfoResponse:
        """List all task definitions found in a backend directory.

        Parameters
        ----------
        backend : str
            Backend name (e.g., "qubex", "fake").
        sort_order : str | None
            Sort order for tasks.
        enabled_only : bool
            If True, only return tasks enabled in config/app/backend.yaml.

        Returns
        -------
        ListTaskInfoResponse
            List of task information.

        """
        backend_path = self._base_path / backend

        if not backend_path.exists():
            raise HTTPException(status_code=404, detail=f"Backend directory not found: {backend}")

        if not backend_path.is_dir():
            raise HTTPException(status_code=400, detail=f"Not a directory: {backend}")

        # Check cache
        cache_key = (
            f"v{TASK_METADATA_CACHE_VERSION}:{backend}:{sort_order or 'default'}:{enabled_only}"
        )
        current_mtime = self._get_directory_mtime_sum(backend_path)
        cached = self._task_cache.get(cache_key)

        if cached is not None:
            cached_mtime, cached_tasks = cached
            if cached_mtime == current_mtime:
                logger.debug(f"Using cached task list for backend: {backend}")
                return ListTaskInfoResponse(tasks=cached_tasks)

        tasks = self._load_catalog_tasks(backend)
        if tasks is None:
            logger.debug(f"Parsing task files for backend: {backend}")
            tasks = self._collect_tasks_from_directory(backend_path, backend_path)

        available_tasks = set(get_tasks(backend))
        enriched_tasks = []
        for task in tasks:
            task.category = get_task_category(task.name, backend)
            task.enabled = task.name in available_tasks
            enriched_tasks.append(task)

        if enabled_only:
            enriched_tasks = [t for t in enriched_tasks if t.enabled]

        if sort_order == "name_only":
            enriched_tasks.sort(key=lambda t: t.name)
        elif sort_order == "file_path":
            enriched_tasks.sort(key=lambda t: (t.file_path, t.name))
        elif sort_order == "category":
            task_order = {task_name: index for index, task_name in enumerate(get_tasks(backend))}
            enriched_tasks.sort(
                key=lambda task: (task_order.get(task.name, len(task_order)), task.name)
            )
        else:
            enriched_tasks.sort(key=lambda t: (t.task_type or "", t.name))

        self._task_cache[cache_key] = (current_mtime, enriched_tasks)

        return ListTaskInfoResponse(tasks=enriched_tasks)

    # --- Private helpers ---

    def _load_catalog_tasks(self, backend: str) -> list[TaskInfo] | None:
        """Load generated metadata when a catalog is available for this backend."""
        catalog_path = self._base_path / TASK_CATALOG_FILENAME
        if not catalog_path.is_file():
            return None
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            backend_tasks = catalog["backends"].get(backend)
            if backend_tasks is None:
                return None
            return [TaskInfo.model_validate(task) for task in backend_tasks]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Failed to load task catalog %s: %s", catalog_path, exc)
            return None

    def _extract_task_info_from_file(self, file_path: Path, relative_path: str) -> list[TaskInfo]:
        """Extract task information from a Python file using AST parsing."""
        tasks: list[TaskInfo] = []

        if not self._is_valid_python_file(file_path):
            return tasks

        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            logger.warning(f"Failed to read file: {relative_path}")
            return tasks

        try:
            tree = ast.parse(content)
        except SyntaxError:
            logger.warning(f"Invalid Python syntax in file: {relative_path}")
            return tasks

        constants = self._collect_safe_constants(tree)

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            name_value = None
            task_type_value = None
            input_parameters: dict[str, dict[str, object]] = {}
            run_parameters: dict[str, dict[str, object]] = {}
            docstring = ast.get_docstring(node)

            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if item.target.id == "name":
                        name_value = self._extract_string_value(item.value)
                    elif item.target.id == "task_type":
                        task_type_value = self._extract_string_value(item.value)
                    elif item.target.id in {"run_parameters", "run_spec"}:
                        run_parameters = self._extract_run_parameters(item.value, constants)
                    elif item.target.id in {
                        "input_parameters",
                        "input_spec",
                    }:
                        input_parameters = self._extract_parameter_metadata(item.value, constants)
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            if target.id == "name":
                                name_value = self._extract_string_value(item.value)
                            elif target.id == "task_type":
                                task_type_value = self._extract_string_value(item.value)
                            elif target.id in {
                                "run_parameters",
                                "run_spec",
                            }:
                                run_parameters = self._extract_run_parameters(item.value, constants)
                            elif target.id in {
                                "input_parameters",
                                "input_spec",
                            }:
                                input_parameters = self._extract_parameter_metadata(
                                    item.value, constants
                                )

            if name_value and isinstance(name_value, str):
                tasks.append(
                    TaskInfo(
                        name=name_value,
                        class_name=node.name,
                        task_type=task_type_value,
                        description=docstring,
                        file_path=relative_path,
                        input_parameters=input_parameters,
                        run_parameters=run_parameters,
                    )
                )

        return tasks

    @staticmethod
    def _extract_run_parameters(
        node: ast.expr | None,
        constants: dict[str, object] | None = None,
    ) -> dict[str, dict[str, object]]:
        """Extract literal RunParameterModel metadata without importing workflow code."""
        parameters = TaskFileService._extract_parameter_metadata(node, constants)
        for metadata in parameters.values():
            if "default_value" in metadata:
                metadata["value"] = metadata.pop("default_value")
        return parameters

    @staticmethod
    def _extract_parameter_metadata(
        node: ast.expr | None,
        constants: dict[str, object] | None = None,
    ) -> dict[str, dict[str, object]]:
        """Extract literal parameter metadata without importing workflow code."""
        if not isinstance(node, ast.Dict):
            return {}

        parameters: dict[str, dict[str, object]] = {}
        for key_node, value_node in zip(node.keys, node.values, strict=True):
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                continue
            if isinstance(value_node, ast.Constant) and value_node.value is None:
                # ``None`` declares a calibration dependency whose value is
                # populated from the database during preprocessing.
                parameters[key_node.value] = {}
                continue
            if not isinstance(value_node, ast.Call):
                continue

            metadata: dict[str, object] = {}
            if isinstance(value_node.func, ast.Attribute):
                factory_metadata: dict[str, dict[str, object]] = {
                    "required_database": {
                        "resolution": "database_required",
                        "user_override": "allowed",
                        "default_value": None,
                    },
                    "database_or_default": {
                        "resolution": "database_or_default",
                        "user_override": "allowed",
                    },
                    "default_only": {
                        "resolution": "default_only",
                        "user_override": "allowed",
                    },
                }
                metadata.update(factory_metadata.get(value_node.func.attr, {}))
            for keyword in value_node.keywords:
                metadata_key = "default_value" if keyword.arg == "default" else keyword.arg
                if metadata_key not in {
                    "unit",
                    "value_type",
                    "value",
                    "description",
                    "resolution",
                    "user_override",
                    "default_value",
                    "source",
                    "required",
                    "parameter_name",
                    "qid_role",
                    "greater_than",
                    "less_than",
                }:
                    continue
                try:
                    metadata[metadata_key] = ast.literal_eval(keyword.value)
                except (ValueError, TypeError):
                    with contextlib.suppress(ArithmeticError, TypeError, ValueError):
                        metadata[metadata_key] = TaskFileService._evaluate_parameter_expression(
                            keyword.value, constants or {}
                        )
            parameters[key_node.value] = metadata
        return parameters

    @staticmethod
    def _evaluate_parameter_expression(node: ast.expr, namespace: dict[str, object]) -> object:
        """Evaluate the expression subset allowed in parameter declarations."""
        safe_types = (str, int, float, bool, tuple, list)
        binary_operators: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
        }
        unary_operators: dict[type[ast.unaryop], Callable[[Any], Any]] = {
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
        }
        math_functions: dict[str, Callable[..., float]] = {
            "log": math.log,
            "log10": math.log10,
            "sqrt": math.sqrt,
        }
        if isinstance(node, ast.Constant) and isinstance(node.value, safe_types):
            return node.value
        if isinstance(node, (ast.Tuple, ast.List)):
            values = [
                TaskFileService._evaluate_parameter_expression(item, namespace)
                for item in node.elts
            ]
            return tuple(values) if isinstance(node, ast.Tuple) else values
        if isinstance(node, ast.Name) and node.id in namespace:
            return namespace[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in binary_operators:
            return binary_operators[type(node.op)](
                TaskFileService._evaluate_parameter_expression(node.left, namespace),
                TaskFileService._evaluate_parameter_expression(node.right, namespace),
            )
        if isinstance(node, ast.UnaryOp) and type(node.op) in unary_operators:
            return unary_operators[type(node.op)](
                TaskFileService._evaluate_parameter_expression(node.operand, namespace)
            )
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in {"math", "np"}
            and node.func.attr in math_functions
            and not node.keywords
        ):
            return math_functions[node.func.attr](
                *(
                    cast("Any", TaskFileService._evaluate_parameter_expression(arg, namespace))
                    for arg in node.args
                )
            )
        raise ValueError("unsupported parameter expression")

    @staticmethod
    def _collect_safe_constants(tree: ast.Module) -> dict[str, object]:
        """Collect constants using a restricted, side-effect-free AST evaluator."""
        binary_operators: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
        }
        unary_operators: dict[type[ast.unaryop], Callable[[Any], Any]] = {
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
        }
        math_functions: dict[str, Callable[..., float]] = {
            "log": math.log,
            "log10": math.log10,
            "sqrt": math.sqrt,
        }
        constants: dict[str, object] = {}
        safe_types = (str, int, float, bool, tuple, list)

        def evaluate(node: ast.expr, namespace: dict[str, object]) -> object:
            if isinstance(node, ast.Constant) and isinstance(node.value, safe_types):
                return node.value
            if isinstance(node, (ast.Tuple, ast.List)):
                values = [evaluate(item, namespace) for item in node.elts]
                return tuple(values) if isinstance(node, ast.Tuple) else values
            if isinstance(node, ast.Name) and node.id in namespace:
                return namespace[node.id]
            if isinstance(node, ast.BinOp) and type(node.op) in binary_operators:
                return binary_operators[type(node.op)](
                    evaluate(node.left, namespace), evaluate(node.right, namespace)
                )
            if isinstance(node, ast.UnaryOp) and type(node.op) in unary_operators:
                return unary_operators[type(node.op)](evaluate(node.operand, namespace))
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"math", "np"}
                and node.func.attr in math_functions
                and not node.keywords
            ):
                return math_functions[node.func.attr](
                    *(cast("Any", evaluate(arg, namespace)) for arg in node.args)
                )
            raise ValueError("unsupported constant expression")

        def collect(
            module_tree: ast.Module,
            visited: set[Path],
            current_path: Path | None = None,
        ) -> dict[str, object]:
            collected: dict[str, object] = {}
            assignments: list[tuple[str, ast.expr]] = []
            imports: list[ast.ImportFrom] = []
            for node in module_tree.body:
                if isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node)
                    continue
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    if isinstance(node.targets[0], ast.Name):
                        assignments.append((node.targets[0].id, node.value))
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    if node.value is not None:
                        assignments.append((node.target.id, node.value))

            def resolve_assignments() -> None:
                pending = assignments.copy()
                while pending:
                    unresolved: list[tuple[str, ast.expr]] = []
                    progress = False
                    for name, value_node in pending:
                        try:
                            value = evaluate(value_node, collected)
                        except (ArithmeticError, TypeError, ValueError):
                            unresolved.append((name, value_node))
                            continue
                        if isinstance(value, safe_types):
                            collected[name] = value
                            progress = True
                    if not progress:
                        break
                    pending = unresolved

            resolve_assignments()
            for node in imports:
                requested_names = [name for name in node.names if name.name.isupper()]
                if not requested_names:
                    continue
                if all(name.name in collected for name in requested_names):
                    continue
                if node.module:
                    module_parts = Path(*node.module.split("."))
                    candidates: list[Path] = []
                    if node.level and current_path is not None:
                        relative_root = current_path.parent
                        for _ in range(node.level - 1):
                            relative_root = relative_root.parent
                        candidates.extend(
                            [
                                relative_root / module_parts.with_suffix(".py"),
                                relative_root / module_parts / "__init__.py",
                            ]
                        )
                    else:
                        for root in sys.path:
                            candidates.extend(
                                [
                                    Path(root) / module_parts.with_suffix(".py"),
                                    Path(root) / module_parts / "__init__.py",
                                ]
                            )
                    source_path = next(
                        (path.resolve() for path in candidates if path.is_file()), None
                    )
                    if source_path is None or source_path in visited:
                        continue
                    try:
                        imported_tree = ast.parse(source_path.read_text(encoding="utf-8"))
                    except (OSError, UnicodeDecodeError, SyntaxError):
                        continue
                    imported_constants = collect(
                        imported_tree,
                        {*visited, source_path},
                        source_path,
                    )
                    for imported_name in requested_names:
                        value = imported_constants.get(imported_name.name)
                        if value is not None:
                            collected[imported_name.asname or imported_name.name] = value
            resolve_assignments()
            return collected

        constants.update(collect(tree, set()))
        return constants

    def _collect_tasks_from_directory(self, directory: Path, base_path: Path) -> list[TaskInfo]:
        """Recursively collect task info from all Python files in a directory."""
        tasks = []

        try:
            for item in sorted(directory.iterdir()):
                if item.name.startswith(".") or item.name == "__pycache__":
                    continue

                if item.is_dir():
                    tasks.extend(self._collect_tasks_from_directory(item, base_path))
                elif item.suffix == ".py" and item.name != "__init__.py":
                    relative_path = str(item.relative_to(base_path))
                    tasks.extend(self._extract_task_info_from_file(item, relative_path))
        except PermissionError:
            logger.warning(f"Permission denied accessing directory: {directory}")

        return tasks

    @staticmethod
    def _get_directory_mtime_sum(directory: Path) -> float:
        """Calculate sum of modification times for all Python files in directory."""
        mtime_sum = 0.0
        try:
            for item in directory.rglob("*.py"):
                if item.name.startswith(".") or "__pycache__" in str(item):
                    continue
                with contextlib.suppress(OSError):
                    mtime_sum += item.stat().st_mtime
            catalog_path = directory.parent / TASK_CATALOG_FILENAME
            with contextlib.suppress(OSError):
                mtime_sum += catalog_path.stat().st_mtime
        except PermissionError:
            pass
        return mtime_sum

    @staticmethod
    def _extract_string_value(node: ast.expr | None) -> str | None:
        """Extract string value from AST node."""
        if node is None:
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    @staticmethod
    def _is_valid_python_file(file_path: Path) -> bool:
        """Check if a file is a valid Python file that can be parsed."""
        if not file_path.exists() or not file_path.is_file() or file_path.suffix != ".py":
            return False
        try:
            if file_path.stat().st_size > 1_000_000:
                logger.warning(f"Skipping large file: {file_path}")
                return False
        except OSError:
            return False
        return True
