from __future__ import annotations

from typing import TYPE_CHECKING

from prefect import get_run_logger, task
from qdash.dbmodel.initialize import initialize
from qdash.workflow.calibtasks.base import BaseTask
from qdash.workflow.engine.backend.base import BaseBackend
from qdash.workflow.engine.execution.service import ExecutionService
from qdash.workflow.engine.task.context import TaskContext

if TYPE_CHECKING:
    from qdash.repository.protocols import TaskRepository


def validate_task_name(
    task_names: list[str],
    username: str,
    task_repo: TaskRepository | None = None,
) -> list[str]:
    """Validate task names.

    Parameters
    ----------
    task_names : list[str]
        List of task names to validate
    username : str
        Username to look up tasks for
    task_repo : TaskRepository | None
        Repository for task lookup. If None, uses MongoTaskRepository.

    Returns
    -------
    list[str]
        The validated task names

    Raises
    ------
    ValueError
        If any task name is invalid

    """
    if task_repo is None:
        from qdash.repository import MongoTaskRepository

        task_repo = MongoTaskRepository()

    task_list = task_repo.get_task_names(username)
    for task_name in task_names:
        if task_name not in task_list:
            raise ValueError(f"Invalid task name: {task_name}")
    return task_names


initialize()


@task(name="execute-dynamic-task-service")
def execute_dynamic_task_by_qid_service(
    backend: BaseBackend,
    execution_service: ExecutionService,
    task_context: TaskContext,
    task_instance: BaseTask,
    qid: str,
) -> tuple[ExecutionService, TaskContext]:
    """Execute dynamic task using ExecutionService and TaskContext.

    This is the new implementation using the simplified architecture.
    """
    logger = get_run_logger()
    logger.debug(f"Starting task execution: session_id={task_context.id}")

    task_name = task_instance.get_name()

    try:
        # Execute via TaskContext's executor
        execution_service, result = task_context.executor.execute(
            task=task_instance,
            backend=backend,
            execution_service=execution_service,
            qid=qid,
        )

        # Save session state
        task_context.save()

    except Exception as e:
        logger.error(f"Failed to execute {task_name}: {e}, id: {task_context.id}")
        raise RuntimeError(f"Task {task_name} failed: {e}")

    return execution_service, task_context


@task(name="execute-dynamic-task-batch-service")
def execute_dynamic_task_batch_service(
    backend: BaseBackend,
    execution_service: ExecutionService,
    task_context: TaskContext,
    task_instance: BaseTask,
    qids: list[str],
) -> tuple[ExecutionService, TaskContext]:
    """Execute dynamic task for batch using ExecutionService and TaskContext."""
    logger = get_run_logger()
    logger.debug(f"Starting batch task execution: session_id={task_context.id}")

    task_name = task_instance.get_name()

    try:
        # Execute task for each qid
        for qid in qids:
            execution_service, result = task_context.executor.execute(
                task=task_instance,
                backend=backend,
                execution_service=execution_service,
                qid=qid,
            )

        # Save session state
        task_context.save()

    except Exception as e:
        logger.error(f"Failed to execute {task_name}: {e}, id: {task_context.id}")
        raise RuntimeError(f"Task {task_name} failed: {e}")

    return execution_service, task_context
