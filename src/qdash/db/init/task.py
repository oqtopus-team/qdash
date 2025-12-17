"""Task initialization module."""

from qdash.datamodel.task import TaskModel
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.task import TaskDocument
from qdash.workflow.caltasks.base import BaseTask


def update_active_tasks(username: str, backend: str) -> list[TaskModel]:
    """Update the active tasks in the registry and return a list of TaskModel instances.

    Args:
        username: The username to associate with the tasks
        backend: The backend type (e.g., 'qubex', 'fake')

    Returns:
        List of TaskModel instances for the specified backend

    Raises:
        ValueError: If the backend is not registered in the task registry

    """
    task_cls = BaseTask.registry.get(backend)
    if task_cls is None:
        supported_backends = list(BaseTask.registry.keys())
        msg = f"Unknown backend '{backend}'. Supported backends: {supported_backends}"
        raise ValueError(msg)
    return [
        TaskModel(
            username=username,
            name=cls.name,
            description=cls.__doc__,
            backend=cls.backend,
            task_type=cls.task_type,
            input_parameters={
                name: param.model_dump() for name, param in cls.input_parameters.items()
            },
            output_parameters={
                name: param.model_dump() for name, param in cls.output_parameters.items()
            },
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
