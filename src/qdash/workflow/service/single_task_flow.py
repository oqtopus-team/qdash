"""System flow for single-task re-execution.

This flow is registered as a Prefect deployment on worker startup
and allows re-executing a single calibration task from the task detail page.

Unlike user flows, this flow does not require a FlowDocument to exist.
It is always available as a system deployment.
"""

from __future__ import annotations

import contextlib
from typing import Any

from prefect import flow, get_run_logger
from qdash.workflow.service.calib_service import CalibService


@flow(name="single-task-executor")
def single_task_executor(
    username: str,
    chip_id: str,
    qid: str,
    task_name: str,
    source_execution_id: str,
    project_id: str | None = None,
    flow_name: str | None = None,
    tags: list[str] | None = None,
    source_task_id: str | None = None,
    parameter_overrides: dict[str, dict[str, Any]] | None = None,
) -> Any:
    """Execute a single calibration task.

    This system flow runs one task for one qubit, using snapshot parameters
    from a previous execution. It is designed to be triggered from the
    task detail page's "Re-execute" button.

    Args:
        username: User name
        chip_id: Chip ID
        qid: Qubit ID to calibrate
        task_name: Name of the task to execute (e.g., 'CheckRabi')
        source_execution_id: Execution ID to load snapshot parameters from
        project_id: Project ID (auto-injected)
        flow_name: Flow name for display (auto-injected)
        tags: Tags for categorization
        source_task_id: Task result ID that triggered this re-execution

    Returns:
        Task execution result dictionary
    """
    logger = get_run_logger()
    logger.info(
        f"Single-task executor: task={task_name}, qid={qid}, "
        f"source={source_execution_id}, chip={chip_id}"
    )

    cal = CalibService(
        username,
        chip_id,
        qids=[qid],
        source_execution_id=source_execution_id,
        flow_name=flow_name or f"re-execute:{task_name}",
        tags=tags,
        project_id=project_id,
        enable_github=False,
        parameter_overrides=parameter_overrides,
        source_task_id=source_task_id,
    )

    try:
        result = cal.execute_task(task_name, qid)
        cal.finish_calibration()

        logger.info(f"Single-task executor completed: {task_name} / {qid}")
        return result
    except Exception as e:
        logger.error(f"Single-task executor failed: {e}")
        with contextlib.suppress(Exception):
            cal.fail_calibration(str(e))
        raise
