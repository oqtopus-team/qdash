"""Calibration tasks of the Quantum Machines (``qm`` and ``qm-fake``) backends.

The tasks wrap experiments from Quantum Machines' open-source ``qualang-tools``
package (BSD-3-Clause) instead of reimplementing their QUA programs. Importing this
package does not import the QM SDK; each task imports it when it runs on the ``qm``
or ``qm-fake`` backend.

The ``qm-fake`` backend runs these same task classes and the same SDK code path
against a local fake QOP device (``engine/backend/qm_fake_qop.py``), so a fake run
exercises program generation, execution, result fetching, analysis, figures, raw
data and persistence rules. Which tasks it offers is decided in one place, the
``qm-fake`` section of ``config/app/backend.yaml``: each task listed there is routed
to the ``qm`` class of the same name. The fake device interprets only the QUA subset
of the 1D amplitude Rabi; before listing a new QM task under ``qm-fake``, extend that
subset (and its tests) to the statements the task's program uses. ``tests/qdash/workflow/calibtasks/qm/test_qm_fake.py``
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
