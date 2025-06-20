# ruff: noqa
from qdash.workflow.tasks.base import BaseTask


def generate_task_instances(task_names: list[str], task_details: dict) -> dict[str, BaseTask]:
    task_instances = {}
    for task_name in task_names:
        task_class = BaseTask.registry.get(task_name)
        if task_class is None:
            raise ValueError(f"タスク '{task_name}' は登録されていません")
        task_instance = task_class(task_details[task_name])
        task_instances[task_name] = task_instance
    return task_instances
