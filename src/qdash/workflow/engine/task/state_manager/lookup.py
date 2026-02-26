"""Task lookup and container routing functions.

These functions encapsulate the task_type-based routing logic for finding,
adding, iterating, and creating tasks in the appropriate containers.
"""

from collections.abc import Iterator
from typing import cast

from qdash.datamodel.task import (
    BaseTaskResultModel,
    CouplingTaskModel,
    GlobalTaskModel,
    QubitTaskModel,
    SystemTaskModel,
    TaskResultModel,
    TaskTypes,
)


def find_task(
    task_result: TaskResultModel, task_name: str, task_type: str, qid: str
) -> BaseTaskResultModel | None:
    """Find a task by name in the appropriate container.

    Parameters
    ----------
    task_result : TaskResultModel
        Container for all task results
    task_name : str
        Name of the task to find
    task_type : str
        Type of task (qubit, coupling, global, system)
    qid : str
        Qubit ID (empty for global/system tasks)

    Returns
    -------
    BaseTaskResultModel | None
        The found task, or None if not found

    """
    for task in iter_tasks(task_result, task_type, qid):
        if task.name == task_name:
            return task
    return None


def add_task(
    task_result: TaskResultModel, task: BaseTaskResultModel, task_type: str, qid: str
) -> None:
    """Add a task to the appropriate container.

    Parameters
    ----------
    task_result : TaskResultModel
        Container for all task results
    task : BaseTaskResultModel
        The task to add
    task_type : str
        Type of task (qubit, coupling, global, system)
    qid : str
        Qubit ID (empty for global/system tasks)

    """
    if task_type == TaskTypes.QUBIT:
        # Initialize list if qid doesn't exist (for MUX distribution)
        if qid not in task_result.qubit_tasks:
            task_result.qubit_tasks[qid] = []
        task_result.qubit_tasks[qid].append(cast(QubitTaskModel, task))
    elif task_type == TaskTypes.COUPLING:
        # Initialize list if qid doesn't exist
        if qid not in task_result.coupling_tasks:
            task_result.coupling_tasks[qid] = []
        task_result.coupling_tasks[qid].append(cast(CouplingTaskModel, task))
    elif task_type == TaskTypes.GLOBAL:
        task_result.global_tasks.append(cast(GlobalTaskModel, task))
    elif task_type == TaskTypes.SYSTEM:
        task_result.system_tasks.append(cast(SystemTaskModel, task))


def iter_tasks(
    task_result: TaskResultModel, task_type: str, qid: str
) -> Iterator[BaseTaskResultModel]:
    """Iterate over tasks in the appropriate container (read-only).

    Parameters
    ----------
    task_result : TaskResultModel
        Container for all task results
    task_type : str
        Type of task (qubit, coupling, global, system)
    qid : str
        Qubit ID (empty for global/system tasks)

    Yields
    ------
    BaseTaskResultModel
        Tasks in the container

    """
    if task_type == TaskTypes.QUBIT:
        yield from task_result.qubit_tasks.get(qid, [])
    elif task_type == TaskTypes.COUPLING:
        yield from task_result.coupling_tasks.get(qid, [])
    elif task_type == TaskTypes.GLOBAL:
        yield from task_result.global_tasks
    elif task_type == TaskTypes.SYSTEM:
        yield from task_result.system_tasks


def create_task(
    task_name: str, task_type: str, qid: str, upstream_id: str = ""
) -> BaseTaskResultModel:
    """Create a new task of the appropriate type.

    Parameters
    ----------
    task_name : str
        Name of the task
    task_type : str
        Type of task
    qid : str
        Qubit ID
    upstream_id : str
        Upstream task ID for dependency tracking

    Returns
    -------
    BaseTaskResultModel
        The new task instance

    """
    if task_type == TaskTypes.QUBIT:
        return QubitTaskModel(name=task_name, qid=qid, upstream_id=upstream_id)
    elif task_type == TaskTypes.COUPLING:
        return CouplingTaskModel(name=task_name, qid=qid, upstream_id=upstream_id)
    elif task_type == TaskTypes.GLOBAL:
        return GlobalTaskModel(name=task_name, upstream_id=upstream_id)
    elif task_type == TaskTypes.SYSTEM:
        return SystemTaskModel(name=task_name, upstream_id=upstream_id)
    else:
        raise ValueError(f"Unknown task type: {task_type}")


def ensure_task_exists(
    task_result: TaskResultModel,
    task_name: str,
    task_type: str,
    qid: str,
    upstream_id: str = "",
) -> BaseTaskResultModel:
    """Ensure a task exists in the appropriate container.

    Parameters
    ----------
    task_result : TaskResultModel
        Container for all task results
    task_name : str
        Name of the task
    task_type : str
        Type of task (qubit, coupling, global, system)
    qid : str
        Qubit ID (empty for global/system tasks)
    upstream_id : str
        Upstream task ID for dependency tracking

    Returns
    -------
    BaseTaskResultModel
        The existing or newly created task

    """
    existing = find_task(task_result, task_name, task_type, qid)
    if existing:
        return existing

    task = create_task(task_name, task_type, qid, upstream_id)
    add_task(task_result, task, task_type, qid)
    return task


def get_task(
    task_result: TaskResultModel, task_name: str, task_type: str, qid: str
) -> BaseTaskResultModel:
    """Get an existing task.

    Parameters
    ----------
    task_result : TaskResultModel
        Container for all task results
    task_name : str
        Name of the task
    task_type : str
        Type of task
    qid : str
        Qubit ID

    Returns
    -------
    BaseTaskResultModel
        The task

    Raises
    ------
    ValueError
        If task not found

    """
    task = find_task(task_result, task_name, task_type, qid)
    if task is None:
        raise ValueError(f"Task '{task_name}' not found for {task_type}/{qid}")
    return task
