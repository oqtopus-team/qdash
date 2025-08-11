"""Task initialization module."""

from qdash.datamodel.task import TaskModel
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.task import TaskDocument
from qdash.workflow.tasks.base import BaseTask


def update_active_tasks(username: str, backend: str) -> list[TaskModel]:
    """Update the active tasks in the registry and return a list of TaskModel instances."""
    task_cls = BaseTask.registry.get(backend)
    return [
        TaskModel(
            username=username,
            name=cls.name,
            description=cls.__doc__,
            backend=cls.backend,
            task_type=cls.task_type,
            input_parameters={name: param.model_dump() for name, param in cls.input_parameters.items()},
            output_parameters={name: param.model_dump() for name, param in cls.output_parameters.items()},
        )
        for cls in task_cls.values()
    ]


def init_task_document(username: str, backend: str) -> None:
    """Initialize the task document."""
    initialize()
    tasks = update_active_tasks(username, backend=backend)
    TaskDocument.insert_tasks(tasks)


if __name__ == "__main__":
    initialize()
    init_task_document("admin", backend="qubex")
