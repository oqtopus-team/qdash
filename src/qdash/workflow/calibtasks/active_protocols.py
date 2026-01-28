from typing import Any

# ruff: noqa
from qdash.workflow.calibtasks.base import BaseTask


def is_mux_task(task_name: str, backend: str) -> bool:
    """Check if a task is a MUX-level task.

    MUX-level tasks are executed once per MUX (for the representative qubit),
    not for every qubit. This is determined by the `is_mux_level` class attribute.

    Note: task_type remains "qubit" for frontend compatibility, but
    is_mux_level=True indicates this task runs once per MUX.

    Args:
        task_name: Name of the task
        backend: Backend name (e.g., 'qubex', 'fake')

    Returns:
        True if the task is a MUX-level task, False otherwise
    """
    backend_registry = BaseTask.registry.get(backend)
    if backend_registry is None:
        return False

    task_class = backend_registry.get(task_name)
    if task_class is None:
        return False

    return getattr(task_class, "is_mux_level", False)


def generate_task_instances(
    task_names: list[str],
    task_details: dict[str, Any],
    backend: str,
) -> dict[str, BaseTask]:
    task_instances = {}

    backend_registry = BaseTask.registry.get(backend)
    if backend_registry is None:
        raise ValueError(f"バックエンド '{backend}' のタスクレジストリが存在しません")

    for task_name in task_names:
        task_class = backend_registry.get(task_name)
        if task_class is None:
            raise ValueError(f"タスク '{task_name}' は backend '{backend}' に登録されていません")
        task_instance = task_class(task_details[task_name])
        task_instances[task_name] = task_instance

    return task_instances
