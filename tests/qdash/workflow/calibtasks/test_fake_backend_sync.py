"""The fake backend stays in step with the qubex task set.

The fake backend runs the qubex task implementations on a simulator. These tests fail when
``config/app/backend.yaml`` lists a fake task that qubex no longer defines, when a stale fake
implementation shadows a qubex task, or when the default fake calibration chain can no longer
resolve the inputs its tasks require from the tasks before them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import qdash.workflow.calibtasks.fake  # noqa: F401  (registers and routes the fake tasks)
from qdash.common.config.backend import get_tasks
from qdash.workflow.calibtasks.base import BaseTask
from qdash.workflow.templates.fake_backend import FAKE_CALIBRATION_TASKS

if TYPE_CHECKING:
    from qdash.datamodel.task import InputParameterSpec

# Tasks the fake package implements itself; everything else must be the qubex class.
FAKE_ONLY_TASKS = {"FakeBringUp"}


def _registries() -> tuple[dict[str, type[BaseTask]], dict[str, type[BaseTask]]]:
    return BaseTask.registry["fake"], BaseTask.registry["qubex"]


def _required_names(spec: InputParameterSpec, key: str) -> set[str]:
    """Database names that satisfy one declared input."""
    return {spec.parameter_name or key, *spec.parameter_aliases, *spec.fallback_parameter_names}


def test_every_configured_fake_task_is_the_qubex_implementation_or_a_declared_seed() -> None:
    fake, qubex = _registries()
    for task_name in get_tasks("fake"):
        assert task_name in fake, f"{task_name} is listed for the fake backend but not registered"
        if task_name in FAKE_ONLY_TASKS:
            assert task_name not in qubex, f"{task_name} must not shadow a qubex task"
        else:
            assert fake[task_name] is qubex[task_name], (
                f"{task_name} on the fake backend must be the qubex class, not a copy"
            )


def test_fake_registry_holds_exactly_the_configured_tasks() -> None:
    fake, _ = _registries()
    assert set(fake) == set(get_tasks("fake"))


def test_fake_only_tasks_are_listed_for_the_fake_backend() -> None:
    assert set(get_tasks("fake")) >= FAKE_ONLY_TASKS


def test_template_default_chain_is_available_on_the_fake_backend() -> None:
    assert set(FAKE_CALIBRATION_TASKS) <= set(get_tasks("fake"))
    assert FAKE_CALIBRATION_TASKS[0] == "FakeBringUp"


def test_default_chain_resolves_every_required_input_from_earlier_tasks() -> None:
    """A fresh fake project has no stored values: each task's required inputs must come from
    the outputs of the tasks before it (through the declared aliases and fallbacks)."""
    fake, _ = _registries()
    available: set[str] = set()
    for task_name in FAKE_CALIBRATION_TASKS:
        task_cls = fake[task_name]
        for key, spec in task_cls.input_spec.items():
            if spec.resolution != "database_required":
                continue
            assert _required_names(spec, key) & available, (
                f"{task_name} requires '{key}', which no earlier task in "
                f"{FAKE_CALIBRATION_TASKS} produces"
            )
        available |= set(task_cls.output_spec)


def test_bring_up_seeds_what_the_first_qubex_task_requires() -> None:
    fake, _ = _registries()
    seeded = set(fake["FakeBringUp"].output_spec)
    first_qubex = fake[FAKE_CALIBRATION_TASKS[1]]
    for key, spec in first_qubex.input_spec.items():
        if spec.resolution == "database_required":
            assert _required_names(spec, key) & seeded, f"FakeBringUp does not seed '{key}'"
