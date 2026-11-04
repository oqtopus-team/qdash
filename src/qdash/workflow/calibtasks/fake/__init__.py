"""Calibration tasks of the fake backend.

The fake backend runs the production qubex task implementations against ``FakeExperiment``,
a QUBEX-compatible simulator, so a fake execution exercises the same task code, parameter
declarations and result shapes as a hardware run. The only task the package implements itself
is ``FakeBringUp``, which seeds a fresh project with the simulator's device parameters in place
of the hardware bring-up tasks the simulator does not emulate.

Which qubex tasks the fake backend offers is decided in one place, the ``fake`` section of
``config/app/backend.yaml``: every task listed there that the fake package does not implement
is routed to the qubex class of the same name. ``tests/qdash/workflow/calibtasks/
test_fake_backend_sync.py`` fails when that list names a task qubex no longer has, or when the
default fake calibration chain can no longer resolve its inputs.
"""

import logging

from qdash.workflow.calibtasks.active_protocols import generate_task_instances
from qdash.workflow.calibtasks.fake.base import FakeTask
from qdash.workflow.calibtasks.fake.fake_bring_up import FakeBringUp

__all__ = [
    "FakeBringUp",
    "FakeTask",
    "generate_task_instances",
]

logger = logging.getLogger(__name__)


def _use_qubex_tasks_with_fake_backend() -> None:
    """Route every configured fake task without a fake implementation to its qubex class."""
    import qdash.workflow.calibtasks.qubex  # noqa: F401
    from qdash.common.config.backend import get_tasks
    from qdash.workflow.calibtasks.base import BaseTask

    qubex_registry = BaseTask.registry.get("qubex", {})
    fake_registry = BaseTask.registry.setdefault("fake", {})
    for task_name in get_tasks("fake"):
        if task_name in fake_registry:
            continue
        qubex_task = qubex_registry.get(task_name)
        if qubex_task is None:
            logger.error(
                "backend.yaml lists '%s' for the fake backend, but qubex defines no such task",
                task_name,
            )
            continue
        fake_registry[task_name] = qubex_task


_use_qubex_tasks_with_fake_backend()
