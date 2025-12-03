from prefect import get_run_logger, task
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.task import TaskDocument
from qdash.workflow.caltasks.base import BaseTask
from qdash.workflow.engine.backend.base import BaseBackend
from qdash.workflow.engine.calibration.execution.manager import ExecutionManager
from qdash.workflow.engine.calibration.task.manager import TaskManager


def validate_task_name(task_names: list[str], username: str) -> list[str]:
    """Validate task names."""
    tasks = TaskDocument.find({"username": username}).run()
    task_list = [task.name for task in tasks]
    for task_name in task_names:
        if task_name not in task_list:
            raise ValueError(f"Invalid task name: {task_name}")
    return task_names


initialize()


@task(name="execute-dynamic-task")
def execute_dynamic_task_by_qid(
    backend: BaseBackend,
    execution_manager: ExecutionManager,
    task_manager: TaskManager,
    task_instance: BaseTask,
    qid: str,
) -> tuple[ExecutionManager, TaskManager]:
    """Execute dynamic task (simplified version using TaskManager.execute_task)."""
    logger = get_run_logger()
    task_manager.diagnose()

    task_name = task_instance.get_name()

    try:
        # TaskManager's integrated execution and save processing
        execution_manager, task_manager = task_manager.execute_task(task_instance, backend, execution_manager, qid)
    except Exception as e:
        logger.error(f"Failed to execute {task_name}: {e}, id: {task_manager.id}")
        raise RuntimeError(f"Task {task_name} failed: {e}")

    return execution_manager, task_manager


@task(name="execute-dynamic-task-batch")
def execute_dynamic_task_batch(
    backend: BaseBackend,
    execution_manager: ExecutionManager,
    task_manager: TaskManager,
    task_instance: BaseTask,
    qids: list[str],
) -> tuple[ExecutionManager, TaskManager]:
    """Execute dynamic task for batch (simplified version using TaskManager.execute_task)."""
    logger = get_run_logger()
    task_manager.diagnose()

    task_name = task_instance.get_name()

    try:
        # Execute task for each qid using TaskManager's integrated processing
        for qid in qids:
            execution_manager, task_manager = task_manager.execute_task(task_instance, backend, execution_manager, qid)
    except Exception as e:
        logger.error(f"Failed to execute {task_name}: {e}, id: {task_manager.id}")
        raise RuntimeError(f"Task {task_name} failed: {e}")

    return execution_manager, task_manager
