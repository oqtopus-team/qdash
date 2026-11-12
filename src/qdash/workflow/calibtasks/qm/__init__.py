"""Calibration tasks of the Quantum Machines (``qm`` and ``qm-fake``) backends.

The tasks wrap experiments from Quantum Machines' open-source ``qualang-tools``
package (BSD-3-Clause) instead of reimplementing their QUA programs. Importing this
package does not import the QM SDK; each task imports it when it runs on the ``qm``
backend.

The ``qm-fake`` backend runs these same task classes against a local synthetic
device response, so a fake run exercises the task's parameters, analysis, figures,
raw data and persistence rules. Which tasks it offers is decided in one place, the
``qm-fake`` section of ``config/app/backend.yaml``: each task listed there is routed
to the ``qm`` class of the same name. To make a new QM task available on ``qm-fake``,
give it a branch for ``session.is_fake`` that asks the fake device for its response,
then list it under ``qm-fake``. ``tests/qdash/workflow/calibtasks/qm/test_qm_fake.py``
fails when that list names a task the ``qm`` backend does not define.
"""

import logging

from qdash.workflow.calibtasks.qm.base import QMTask
from qdash.workflow.calibtasks.qm.qm_amplitude_rabi import QMAmplitudeRabi, simulator_run_parameters

__all__ = [
    "QMAmplitudeRabi",
    "QMTask",
    "simulator_run_parameters",
]

logger = logging.getLogger(__name__)

QM_FAKE_BACKEND = "qm-fake"


def _use_qm_tasks_with_qm_fake_backend() -> None:
    """Route every task configured for the qm-fake backend to its qm class."""
    from qdash.common.config.backend import get_tasks
    from qdash.workflow.calibtasks.base import BaseTask

    qm_registry = BaseTask.registry.get(QMTask.backend, {})
    fake_registry = BaseTask.registry.setdefault(QM_FAKE_BACKEND, {})
    for task_name in get_tasks(QM_FAKE_BACKEND):
        if task_name in fake_registry:
            continue
        qm_task = qm_registry.get(task_name)
        if qm_task is None:
            logger.error(
                "backend.yaml lists '%s' for the qm-fake backend, but qm defines no such task",
                task_name,
            )
            continue
        fake_registry[task_name] = qm_task


_use_qm_tasks_with_qm_fake_backend()
