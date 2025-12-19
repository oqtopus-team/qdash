from prefect import get_run_logger, task
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.task import TaskDocument
from qdash.workflow.calibtasks.base import BaseTask
from qdash.workflow.engine.backend.base import BaseBackend
from qdash.workflow.engine.execution.service import ExecutionService
from qdash.workflow.engine.task.session import TaskSession


def validate_task_name(task_names: list[str], username: str) -> list[str]:
    """Validate task names."""
    tasks = TaskDocument.find({"username": username}).run()
    task_list = [task.name for task in tasks]
    for task_name in task_names:
        if task_name not in task_list:
            raise ValueError(f"Invalid task name: {task_name}")
    return task_names


initialize()


@task(name="execute-dynamic-task-service")
def execute_dynamic_task_by_qid_service(
    backend: BaseBackend,
    execution_service: ExecutionService,
    task_session: TaskSession,
    task_instance: BaseTask,
    qid: str,
) -> tuple[ExecutionService, TaskSession]:
    """Execute dynamic task using ExecutionService and TaskSession.

    This is the new implementation using the simplified architecture.
    """
    logger = get_run_logger()
    logger.debug(f"Starting task execution: session_id={task_session.id}")

    task_name = task_instance.get_name()

    try:
        # Execute via TaskSession's executor
        execution_service, result = task_session.executor.execute(
            task=task_instance,
            backend=backend,
            execution_service=execution_service,
            qid=qid,
        )

        # Save session state
        task_session.save()

    except Exception as e:
        logger.error(f"Failed to execute {task_name}: {e}, id: {task_session.id}")
        raise RuntimeError(f"Task {task_name} failed: {e}")

    return execution_service, task_session


@task(name="execute-dynamic-task-batch-service")
def execute_dynamic_task_batch_service(
    backend: BaseBackend,
    execution_service: ExecutionService,
    task_session: TaskSession,
    task_instance: BaseTask,
    qids: list[str],
) -> tuple[ExecutionService, TaskSession]:
    """Execute dynamic task for batch using ExecutionService and TaskSession."""
    logger = get_run_logger()
    logger.debug(f"Starting batch task execution: session_id={task_session.id}")

    task_name = task_instance.get_name()

    try:
        # Execute task for each qid
        for qid in qids:
            execution_service, result = task_session.executor.execute(
                task=task_instance,
                backend=backend,
                execution_service=execution_service,
                qid=qid,
            )

        # Save session state
        task_session.save()

    except Exception as e:
        logger.error(f"Failed to execute {task_name}: {e}, id: {task_session.id}")
        raise RuntimeError(f"Task {task_name} failed: {e}")

    return execution_service, task_session
