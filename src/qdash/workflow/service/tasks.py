"""Default task lists for calibration workflows.

This module defines the standard task lists used across calibration workflows.
Import these lists instead of hardcoding task names in templates.

Task Lists:
    BRINGUP_TASKS: MUX-level bring-up tasks (resonator spectroscopy, etc.)
    CHECK_1Q_TASKS: Basic 1Q characterization (run first)
    FULL_1Q_TASKS_AFTER_CHECK: Advanced 1Q calibration (run after check)
    FULL_1Q_TASKS: Complete 1Q task list (CHECK + AFTER_CHECK)
    FULL_2Q_TASKS: Complete 2Q task list

Example:
    from qdash.workflow.service import CalibService
    from qdash.workflow.service.steps import CustomOneQubit, BringUp
    from qdash.workflow.service.tasks import CHECK_1Q_TASKS, BRINGUP_TASKS
    from qdash.workflow.service.targets import MuxTargets

    # Use in calibration
    cal = CalibService(username, chip_id)
    targets = MuxTargets([0, 1, 2, 3])
    results = cal.run(targets, steps=[BringUp(), CustomOneQubit(tasks=CHECK_1Q_TASKS)])
"""

# The lists live in ``qdash.datamodel.calibration_pipeline`` so the API, which
# validates declarative pipeline specs without a Prefect runtime, resolves a
# step's default tasks exactly as the worker does. This module keeps the names
# templates import.
from qdash.datamodel.calibration_pipeline import (
    BRINGUP_TASKS,
    CHECK_1Q_TASKS,
    FULL_1Q_TASKS,
    FULL_1Q_TASKS_AFTER_CHECK,
    FULL_2Q_TASKS,
)

__all__ = [
    "BRINGUP_TASKS",
    "CHECK_1Q_TASKS",
    "FULL_1Q_TASKS",
    "FULL_1Q_TASKS_AFTER_CHECK",
    "FULL_2Q_TASKS",
]
