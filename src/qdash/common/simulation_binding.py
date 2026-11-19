"""Rules that keep simulated calibration values on simulation-bound chips.

A chip is a simulation target only when it carries a :class:`SimulationBindingModel`, written
when the chip is created from a simulation preset. Every path that could move calibration values
between QDash and hardware configuration checks the binding here:

* a simulation backend runs only bound chips, and a bound chip runs only on its own backend
  (:func:`check_backend_for_chip`);
* Qubex YAML, props, calibration notes, and GitHub publication refuse bound chips
  (:func:`check_hardware_export`);
* manual and seed writes refuse simulation parameter names on unbound chips
  (:func:`check_parameters_for_chip`);
* agent sessions never commit synthetic outputs (:func:`is_synthetic_output`).

The ``qibocal_`` name prefix is an additional guard, not the reason a write is allowed: values
are adopted only on a chip whose binding matches the run.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qdash.common.qibocal_platform import PlatformTemplate
    from qdash.datamodel.simulation import SimulationBindingModel

SIMULATION_BACKENDS = frozenset({"qibocal"})
SIMULATION_PARAMETER_PREFIXES = ("qibocal_",)
SYNTHETIC_SOURCES = frozenset({"qibolab-emulator"})


class SimulationBindingError(ValueError):
    """A chip's simulation binding forbids the requested action."""


def check_backend_for_chip(
    binding: SimulationBindingModel | None, backend_name: str, chip_id: str
) -> None:
    """Allow a run only when the chip's binding matches ``backend_name``.

    A simulation backend needs a bound chip; a bound chip needs its own backend. Chips without
    a binding keep running on the hardware and fake backends as before.
    """
    if binding is None:
        if backend_name in SIMULATION_BACKENDS:
            raise SimulationBindingError(
                f"Chip '{chip_id}' has no simulation binding, so the '{backend_name}' backend "
                "does not run it. Create a chip from the qibocal preset; existing chips are not "
                "reclassified."
            )
        return
    if binding.backend != backend_name:
        raise SimulationBindingError(
            f"Chip '{chip_id}' is bound to the '{binding.backend}' simulation backend and "
            f"cannot run on '{backend_name}'"
        )


def check_hardware_export(
    binding: SimulationBindingModel | None, chip_id: str, action: str
) -> None:
    """Refuse ``action`` (Qubex YAML, props, notes, GitHub) for a simulation-bound chip."""
    if binding is not None:
        raise SimulationBindingError(
            f"Chip '{chip_id}' is a simulation chip ({binding.backend}/{binding.platform}); "
            f"{action} is not available for simulated calibration values"
        )


def is_simulation_parameter(name: str) -> bool:
    return name.startswith(SIMULATION_PARAMETER_PREFIXES)


def check_parameters_for_chip(
    binding: SimulationBindingModel | None, chip_id: str, names: Iterable[str]
) -> None:
    """Refuse simulation parameter names on a chip without a simulation binding."""
    if binding is not None:
        return
    simulated = sorted(name for name in names if is_simulation_parameter(name))
    if simulated:
        raise SimulationBindingError(
            f"Chip '{chip_id}' has no simulation binding; simulation parameters "
            f"{', '.join(simulated)} cannot be written to it"
        )


def is_synthetic_output(raw: Any) -> bool:
    """Whether a stored task output came from a simulator."""
    if not isinstance(raw, Mapping):
        return False
    provenance = raw.get("provenance")
    if not isinstance(provenance, Mapping):
        return False
    return provenance.get("synthetic") is True or provenance.get("source") in SYNTHETIC_SOURCES


def chip_binding(project_id: str | None, chip_id: str) -> SimulationBindingModel | None:
    """Read the immutable binding; never infer it from chip names or topology."""
    from qdash.dbmodel.chip import ChipDocument

    chip = ChipDocument.find_one({"project_id": project_id, "chip_id": chip_id}).run()
    return chip.simulation_binding if chip is not None else None


def require_qibocal_binding(
    project_id: str | None, chip_id: str, template: PlatformTemplate
) -> SimulationBindingModel:
    binding = chip_binding(project_id, chip_id)
    check_backend_for_chip(binding, "qibocal", chip_id)
    assert binding is not None
    if (
        binding.preset != "qibocal"
        or binding.platform != template.name
        or binding.template_fingerprint != template.fingerprint()
    ):
        raise SimulationBindingError("Qibocal platform/model does not match the chip binding")
    return binding


def check_calibration_write(
    project_id: str | None, chip_id: str, parameters: Mapping[str, Any]
) -> None:
    """Reject legacy, cross-chip, and unbound synthetic writes at the DB boundary."""
    records = {
        name: (
            raw
            if isinstance(raw, Mapping)
            else raw.model_dump()
            if hasattr(raw, "model_dump")
            else {"value": raw}
        )
        for name, raw in parameters.items()
    }
    relevant = any(
        is_simulation_parameter(name)
        or is_synthetic_output(raw)
        or (isinstance(raw, Mapping) and raw.get("measurement_only_reason"))
        for name, raw in records.items()
    )
    if not relevant:
        return
    binding = chip_binding(project_id, chip_id)
    check_parameters_for_chip(binding, chip_id, parameters)
    for name, raw in records.items():
        if is_simulation_parameter(name) and not is_synthetic_output(raw):
            raise SimulationBindingError("Simulation calibration requires matching run provenance")
        if raw.get("measurement_only_reason"):
            raise SimulationBindingError("Legacy measurement-only outputs cannot be adopted")
        if is_synthetic_output(raw):
            provenance = raw["provenance"]
            if (
                binding is None
                or provenance.get("simulation_binding") != binding.model_dump(mode="json")
                or provenance.get("chip_id") != chip_id
                or provenance.get("project_id") != project_id
            ):
                raise SimulationBindingError("Synthetic output does not match the destination chip")
