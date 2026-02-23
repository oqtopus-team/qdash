"""Execution ID generation utility."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qdash.repository.protocols import ExecutionCounterRepository

from qdash.common.datetime_utils import now

logger = logging.getLogger(__name__)


def generate_execution_id(
    username: str,
    chip_id: str,
    project_id: str | None = None,
    counter_repo: ExecutionCounterRepository | None = None,
) -> str:
    """Generate a unique execution ID based on the current date and an execution index.

    This function creates execution IDs in the format YYYYMMDD-NNN, where:
    - YYYYMMDD is the current date in JST timezone
    - NNN is a zero-padded 3-digit counter for that day

    Args:
        username: Username for the execution
        chip_id: Chip ID for the execution
        project_id: Project ID for the execution (optional)
        counter_repo: Repository for counter operations. If None, uses MongoExecutionCounterRepository.

    Returns:
        Generated execution ID (e.g., "20240101-001")

    Example:
        ```python
        exec_id = generate_execution_id("alice", "chip_1")
        print(exec_id)  # "20240123-001"
        ```

    """
    if counter_repo is None:
        from qdash.repository import MongoExecutionCounterRepository

        counter_repo = MongoExecutionCounterRepository()

    date_str = now().strftime("%Y%m%d")
    execution_index = counter_repo.get_next_index(
        date=date_str,
        username=username,
        chip_id=chip_id,
        project_id=project_id,
    )
    return f"{date_str}-{execution_index:03d}"
