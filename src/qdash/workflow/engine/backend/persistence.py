"""Closed QDash adoption policies selected by backend definitions.

These policies govern acceptance into QDash calibration state, not measurement or
native library execution. Native notes and parameter updates remain backend hooks.
"""

from __future__ import annotations

import math
from copy import deepcopy
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, cast

from qdash.common.qibocal_platform import CALIBRATION_FIELDS_BY_NAME

if TYPE_CHECKING:
    from qdash.datamodel.simulation import SimulationBindingModel
    from qdash.workflow.engine.backend.base import BaseBackend
    from qdash.workflow.engine.task.types import TaskProtocol


class PersistencePolicy(Enum):
    """Supported save workflows; new backends must select a policy explicitly."""

    QUBEX_COMPATIBLE = "qubex-compatible"
    BOUND_SIMULATION = "bound-simulation"

    def accepts_task(self, task: TaskProtocol) -> bool:
        """Keep fake's compatibility with qubex tasks without accepting arbitrary names."""
        return task.backend in _TASK_BACKENDS[self]


_TASK_BACKENDS = {
    PersistencePolicy.QUBEX_COMPATIBLE: ("qubex", "fake"),
    PersistencePolicy.BOUND_SIMULATION: ("qibocal",),
}


def require_persistence_policy(backend: BaseBackend) -> PersistencePolicy:
    """Reject absent/unknown policies, including unconfigured test doubles."""
    policy = backend.persistence_policy
    if not isinstance(policy, PersistencePolicy):
        raise ValueError(f"No calibration persistence policy for backend '{backend.name}'")
    return policy


def policy_for_task(backend: BaseBackend, task: TaskProtocol) -> PersistencePolicy:
    """Validate task compatibility before any calibration or native side effect."""
    policy = require_persistence_policy(backend)
    if not policy.accepts_task(task):
        raise ValueError(f"No calibration persistence policy for backend '{task.backend}'")
    return policy


class BoundSimulationBackend(Protocol):
    """Adapter supplies the verified destination binding, never an inferred prefix."""

    def binding(self) -> SimulationBindingModel: ...


def prepare_simulation_outputs(
    task: TaskProtocol,
    backend: BaseBackend,
    *,
    chip_id: str,
    project_id: str | None,
    task_model: Any,
) -> dict[str, Any]:
    """Validate destination and values before the DB-only policy can adopt them."""
    from qdash.workflow.engine.task.measurement_only import output_provenance

    binding = cast("BoundSimulationBackend", backend).binding()
    provenance = output_provenance(task)
    if (
        provenance.get("simulation_binding") != binding.model_dump(mode="json")
        or provenance.get("chip_id") != chip_id
        or provenance.get("project_id") != project_id
    ):
        raise ValueError("Simulation output does not match the destination chip binding")
    task_model.note["provenance"] = deepcopy(provenance)
    outputs = {
        name: value.model_dump() if hasattr(value, "model_dump") else dict(value)
        for name, value in task_model.output_parameters.items()
    }
    for name, parameter in outputs.items():
        parameter["provenance"] = deepcopy(provenance)
        value = parameter.get("value")
        if name in CALIBRATION_FIELDS_BY_NAME:
            CALIBRATION_FIELDS_BY_NAME[name].validate(value)
        elif (
            not name.startswith("qibocal_")
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"Invalid Qibocal output {name}")
    task_model.output_parameters = outputs
    return outputs
