# ruff: noqa
from qdash.workflow.caltasks.base import BaseTask


def generate_task_instances(
    task_names: list[str],
    task_details: dict,
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
