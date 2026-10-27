"""Create a chip together with its Qubex configuration files.

:class:`ChipInitializer` creates the database side of a chip (chip, qubit and
coupling documents). :class:`ChipProvisioningService` wraps it and, in the shared
configuration layout, also generates the files qubex needs to drive the chip:

* a ``chip.yaml`` entry (``name``, ``n_qubits``, ``topology.type``, ``topology.mux_size``);
* one ``system.yaml`` entry and one ``wiring.yaml`` key per System, copied from
  the chip the new one inherits from (default: the previous chip on the
  cool-down's cryostat), or a single empty System when there is nothing to inherit;
* ``params/<system_id>/*.yaml`` from QDash's templates, filled from the inherited
  chip's calibration values where the units agree;
* ``calibration/<system_id>/calib_note.json`` holding ``{}``.

Order: stage and validate offline with qubex -> write the files -> create the
database records (rolling the files back when that fails) -> load the chip into
the cool-down -> publish. A publish failure keeps files and records and is
reported in the response, where the configuration page shows them as unpublished.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from qdash.api.schemas.chip import (
    ChipProvisioningResult,
    ChipPublishStatus,
    ChipResponse,
    CreateChipRequest,
)
from qdash.api.services.chip.initializer import ChipInitializer
from qdash.api.services.chip.system_files import (
    ChipValues,
    ChipValuesLookup,
    PublishOutcome,
    SharedEntries,
    SystemFiles,
    TreeWriter,
    build_system_files,
    chip_values_from_db,
    empty_chip_values,
    manifest_warning,
    publish_changes,
    system_id_for,
    validate_staged,
)
from qdash.common.config.qubex_layout import LayoutKind, QubexLayout
from qdash.common.config.system_catalog import DEFAULT_BACKEND, SystemCatalog

if TYPE_CHECKING:
    from collections.abc import Callable

    from qdash.common.config.topology import TopologyDefinition

logger = logging.getLogger(__name__)

_CHIP_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class ChipProvisioningError(ValueError):
    """The request cannot be provisioned as asked; the message is for the user."""


@dataclass
class InheritedSystem:
    """One System of the chip the new chip copies its hardware from."""

    system_id: str
    backend: str
    settings: dict[str, Any]
    rows: list[dict[str, Any]]
    is_default: bool


@dataclass
class ProvisionPlan:
    """Everything that will be written, before anything is."""

    chip_id: str
    entries: dict[str, dict[str, Any]]
    systems: list[SystemFiles]
    inherited_from: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def system_ids(self) -> list[str]:
        return [system.system_id for system in self.systems]


def topology_type(topology: TopologyDefinition) -> str:
    """The ``chip.yaml`` ``topology.type`` value for a QDash topology template."""
    if topology.layout_type == "grid" and topology.mux.enabled:
        return "square-lattice"
    return topology.layout_type


def chip_entry(
    chip_id: str, topology: TopologyDefinition, display_name: str | None
) -> dict[str, Any]:
    return {
        "name": display_name or chip_id,
        "n_qubits": topology.num_qubits,
        "topology": {
            "type": topology_type(topology),
            "mux_size": topology.mux_size,
            "qdash_topology_id": topology.id,
        },
    }


class ChipProvisioningService:
    """Create chips and, in the shared layout, their configuration files."""

    def __init__(
        self,
        *,
        layout_factory: Callable[[], QubexLayout] = QubexLayout.detect,
        repository_factory: Callable[..., Any] | None = None,
        chip_values: ChipValuesLookup = chip_values_from_db,
        validate: Callable[[QubexLayout, SharedEntries, list[SystemFiles]], None] = validate_staged,
        cooldown_assign: Callable[[str, str, str], None] | None = None,
        previous_chip: Callable[[str, str | None], str | None] | None = None,
    ) -> None:
        self._layout_factory = layout_factory
        self._repository_factory = repository_factory
        self._chip_values = chip_values
        self._validate = validate
        self._cooldown_assign = cooldown_assign
        self._previous_chip = previous_chip

    # ------------------------------------------------------------------ public

    def create_chip(
        self, *, project_id: str, username: str, request: CreateChipRequest
    ) -> ChipResponse:
        """Create the chip; raises :class:`ChipProvisioningError` for bad requests."""
        if not _CHIP_ID.match(request.chip_id):
            raise ChipProvisioningError("chip_id may contain letters, digits, '-' and '_' only")
        layout = self._layout_factory()
        provision = (
            request.provision_config
            if request.provision_config is not None
            else layout.kind is LayoutKind.SHARED
        )
        if provision and layout.kind is not LayoutKind.SHARED:
            raise ChipProvisioningError(
                "Configuration files can only be generated in the shared layout; "
                "convert the configuration tree or create the chip without configuration"
            )
        topology_id, topology = ChipInitializer._load_topology(request.topology_id, request.size)
        if request.size != topology.num_qubits:
            raise ChipProvisioningError(
                f"Size {request.size} does not match topology num_qubits {topology.num_qubits}"
            )

        plan: ProvisionPlan | None = None
        writer: TreeWriter | None = None
        if provision:
            plan = self.plan(
                layout, project_id=project_id, request=request, topology=topology, username=username
            )
            self._validate(layout, plan.entries, plan.systems)
            writer = TreeWriter(layout)
            writer.write_shared(plan.entries)
            for system in plan.systems:
                writer.write_system(system)

        try:
            chip = ChipInitializer.create_chip(
                username=username,
                chip_id=request.chip_id,
                size=request.size,
                project_id=project_id,
                topology_id=topology_id,
            )
        except Exception:
            if writer is not None:
                writer.rollback()
            raise

        warnings: list[str] = list(plan.warnings) if plan else []
        if request.cooldown_id:
            try:
                self._assign_cooldown(project_id, request.cooldown_id, request.chip_id)
            except Exception as exc:  # the chip exists; report rather than undo
                warnings.append(
                    f"Could not load the chip into cool-down {request.cooldown_id}: {exc}"
                )

        provisioning: ChipProvisioningResult | None = None
        if plan is not None and writer is not None:
            if (manifest := manifest_warning(layout)) is not None:
                warnings.append(manifest)
            outcome = self._publish(layout, plan, writer, username)
            provisioning = ChipProvisioningResult(
                provisioned=True,
                layout=layout.kind.value,
                system_ids=plan.system_ids,
                inherited_from=plan.inherited_from,
                files=[str(layout.repo_relpath(path)) for path in writer.written],
                publish=_status(outcome),
                warnings=warnings,
            )
        elif warnings:
            provisioning = ChipProvisioningResult(
                provisioned=False, layout=layout.kind.value, warnings=warnings
            )

        return ChipResponse(
            chip_id=chip.chip_id,
            size=chip.size,
            topology_id=chip.topology_id,
            qubit_count=chip.size,
            coupling_count=0,
            installed_at=chip.installed_at,
            activity_status=chip.activity_status,
            current_cooldown_id=request.cooldown_id if request.cooldown_id else None,
            provisioning=provisioning,
        )

    def plan(
        self,
        layout: QubexLayout,
        *,
        project_id: str,
        request: CreateChipRequest,
        topology: TopologyDefinition,
        username: str,
    ) -> ProvisionPlan:
        """Decide the shared entries and System files without writing anything."""
        chip_id = request.chip_id
        warnings: list[str] = []
        source_id = request.inherit_wiring_from or self._default_source(
            project_id, request.cooldown_id
        )
        inherited: list[InheritedSystem] = []
        values: ChipValues = empty_chip_values(topology.num_qubits)
        if source_id:
            if source_id == chip_id:
                raise ChipProvisioningError("A chip cannot inherit its wiring from itself")
            inherited = self._inherited_systems(layout, source_id)
            source_values = self._chip_values(project_id, source_id)
            if source_values.n_qubits == topology.num_qubits:
                values = source_values
            elif source_values.n_qubits:
                warnings.append(
                    f"Values of {source_id} were not copied: it has {source_values.n_qubits} "
                    f"qubits, the new chip {topology.num_qubits}"
                )
        catalog_mux_ids: dict[str, list[int]] = {}

        system_entries: dict[str, Any] = {}
        wiring_entries: dict[str, Any] = {}
        systems: list[SystemFiles] = []
        if inherited:
            for item in inherited:
                backend = request.backend or item.backend
                system_id = system_id_for(chip_id, backend, is_default=item.is_default)
                settings = dict(item.settings)
                settings["chip_id"] = chip_id
                settings["backend"] = backend
                if request.backend and request.backend != item.backend:
                    # The hardware section of another backend does not apply.
                    settings.pop(item.backend, None)
                    settings.setdefault(backend, {})
                system_entries[system_id] = settings
                wiring_entries[system_id] = item.rows
                mux_ids = [row["mux"] for row in item.rows]
                catalog_mux_ids[system_id] = mux_ids
                systems.append(build_system_files(system_id, backend, values, mux_ids=mux_ids))
        else:
            backend = request.backend or DEFAULT_BACKEND
            system_entries[chip_id] = {"chip_id": chip_id, "backend": backend, backend: {}}
            wiring_entries[chip_id] = []
            systems.append(build_system_files(chip_id, backend, values, mux_ids=[]))
            warnings.append(
                "No chip to inherit wiring from; the System has no MUX rows until wiring is added"
            )

        entries: dict[str, dict[str, Any]] = {
            "chip.yaml": {chip_id: chip_entry(chip_id, topology, request.display_name)},
            "system.yaml": system_entries,
            "wiring.yaml": wiring_entries,
        }
        return ProvisionPlan(
            chip_id=chip_id,
            entries=entries,
            systems=systems,
            inherited_from=source_id,
            warnings=warnings,
        )

    # ----------------------------------------------------------------- helpers

    def _inherited_systems(self, layout: QubexLayout, source_id: str) -> list[InheritedSystem]:
        catalog = SystemCatalog(layout, source_id)
        try:
            entries = catalog.systems()
            rows = catalog.wiring_rows()
        except (OSError, ValueError, LookupError) as exc:
            raise ChipProvisioningError(f"Cannot inherit wiring from {source_id!r}: {exc}") from exc
        if not entries:
            raise ChipProvisioningError(f"Chip {source_id!r} has no Systems to inherit")
        by_system: dict[str, list[dict[str, Any]]] = {entry.system_id: [] for entry in entries}
        for row in rows:
            by_system[catalog.system_of_mux(int(row["mux"]))].append(dict(row))
        default_id = entries[0].system_id
        for entry in entries:
            if entry.system_id == source_id:
                default_id = entry.system_id
        return [
            InheritedSystem(
                system_id=entry.system_id,
                backend=entry.backend,
                settings=dict(entry.settings),
                rows=by_system[entry.system_id],
                is_default=entry.system_id == default_id,
            )
            for entry in entries
        ]

    def _default_source(self, project_id: str, cooldown_id: str | None) -> str | None:
        if self._previous_chip is not None:
            return self._previous_chip(project_id, cooldown_id)
        return previous_chip_on_cryostat(project_id, cooldown_id)

    def _assign_cooldown(self, project_id: str, cooldown_id: str, chip_id: str) -> None:
        if self._cooldown_assign is not None:
            self._cooldown_assign(project_id, cooldown_id, chip_id)
            return
        from qdash.api.services.cooldown_service import CooldownService
        from qdash.repository.cooldown import MongoCooldownRepository
        from qdash.repository.cryostat import MongoCryostatRepository

        CooldownService(MongoCooldownRepository(), MongoCryostatRepository()).assign_chip(
            project_id=project_id, cooldown_id=cooldown_id, chip_id=chip_id
        )

    def _publish(
        self, layout: QubexLayout, plan: ProvisionPlan, writer: TreeWriter, username: str
    ) -> PublishOutcome:
        try:
            repository = self._repository(layout, username)
        except Exception as exc:
            return PublishOutcome(
                status="failed", message=f"Configuration repository unavailable: {exc}"
            )
        owned = [path for path in writer.written if not path.is_relative_to(layout.config_dir())]
        return publish_changes(
            repository,
            chip_id=plan.chip_id,
            entries=plan.entries,
            owned_paths=owned,
            message=f"Provision chip {plan.chip_id}",
        )

    def _repository(self, layout: QubexLayout, username: str) -> Any:
        if self._repository_factory is not None:
            return self._repository_factory(layout, actor=username)
        from qdash.common.infrastructure.config_repository import get_config_repository

        return get_config_repository(layout, actor=username)


def previous_chip_on_cryostat(project_id: str, cooldown_id: str | None) -> str | None:
    """The most recently loaded chip of an earlier cool-down on the same cryostat."""
    if not cooldown_id:
        return None
    from qdash.repository.cooldown import MongoCooldownRepository

    repo = MongoCooldownRepository()
    current = repo.get(project_id=project_id, cooldown_id=cooldown_id)
    if current is None:
        return None
    for doc in repo.list_all(project_id=project_id, cryo_id=current.cryo_id):
        if doc.cooldown_id == cooldown_id or doc.started_at > current.started_at:
            continue
        if doc.chip_ids:
            return str(doc.chip_ids[-1])
    return None


def _status(outcome: PublishOutcome) -> ChipPublishStatus:
    status = (
        outcome.status
        if outcome.status in {"published", "recorded", "failed", "skipped"}
        else "failed"
    )
    return ChipPublishStatus(
        status=status,  # type: ignore[arg-type]
        mode=outcome.mode,
        commit=outcome.commit,
        message=outcome.message,
    )
