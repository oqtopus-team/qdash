"""Type definitions for task management.

This module provides type definitions and constants for task types used
throughout the calibration workflow system.
"""

from typing import Final, Literal

# Type alias for task types
TaskType = Literal["qubit", "coupling", "global", "system"]


class TaskTypes:
    """Constants for task types.

    Use these constants instead of string literals to ensure type safety
    and enable IDE autocompletion.

    Examples
    --------
    >>> from qdash.workflow.engine.calibration.task.types import TaskTypes
    >>> task_type = TaskTypes.QUBIT
    >>> task_type
    'qubit'

    """

    QUBIT: Final[TaskType] = "qubit"
    COUPLING: Final[TaskType] = "coupling"
    GLOBAL: Final[TaskType] = "global"
    SYSTEM: Final[TaskType] = "system"
