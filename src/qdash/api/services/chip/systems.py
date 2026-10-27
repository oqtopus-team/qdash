"""List the Systems of a chip and add one on another backend.

A System is a partition of a chip's MUXes driven by one backend
(:class:`~qdash.common.config.system_catalog.SystemCatalog`). Adding a System,
for example QuEL-3 next to an existing QuEL-1 System, means:

* a new ``system.yaml`` entry ``<chip_id>-<backend>``;
* moving the chosen MUX rows in ``wiring.yaml`` from their current System to the
  new key (optionally with the rows rewritten for the new hardware);
* a ``params/<system_id>/`` directory projected from the chip's database values
  plus that backend's template files, and ``calibration/<system_id>/calib_note.json``
  projected from the chip's master calibration note.

Existing Systems' directories are not touched. A wiring row that references a box
missing from ``box.yaml`` is refused before anything is written, since qubex
would refuse to load it too.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import yaml

from qdash.api.schemas.chip import (
    AddChipSystemRequest,
    AddChipSystemResponse,
    ChipPublishStatus,
    ChipSystemInfo,
    ChipSystemsResponse,
)
from qdash.api.services.chip.system_files import (
    ChipValuesLookup,
    PublishOutcome,
    SharedEntries,
    SystemFiles,
    TreeWriter,
    box_ids_of,
    build_system_files,
    chip_values_from_db,
    manifest_warning,
    publish_changes,
    validate_staged,
    validate_wiring_rows,
)
from qdash.common.config.qubex_layout import LayoutKind, QubexLayout
from qdash.common.config.system_catalog import SystemCatalog, SystemEntry

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

logger = logging.getLogger(__name__)


class ChipSystemsError(ValueError):
    """The System cannot be listed or added as asked; the message is for the user."""


class ChipSystemsService:
    """Read and extend the System partition of a chip."""

    def __init__(
        self,
        *,
        layout_factory: Callable[[], QubexLayout] = QubexLayout.detect,
        repository_factory: Callable[..., Any] | None = None,
        chip_values: ChipValuesLookup = chip_values_from_db,
        master_note: Callable[[str, str], Mapping[str, Any] | None] | None = None,
        validate: Callable[[QubexLayout, SharedEntries, list[SystemFiles]], None] = validate_staged,
    ) -> None:
        self._layout_factory = layout_factory
        self._repository_factory = repository_factory
        self._chip_values = chip_values
        self._master_note = master_note
        self._validate = validate

    # ------------------------------------------------------------------ read

    def list_systems(self, *, chip_id: str) -> ChipSystemsResponse:
        layout = self._layout_factory()
        response = ChipSystemsResponse(
            chip_id=chip_id,
            layout=layout.kind.value,
            provisionable=layout.kind is LayoutKind.SHARED,
        )
        catalog = SystemCatalog(layout, chip_id)
        try:
            entries = catalog.systems()
            rows = catalog.wiring_rows()
        except (OSError, ValueError, LookupError) as exc:
            response.message = f"Configuration for chip {chip_id} could not be read: {exc}"
            return response
        rows_by_system: dict[str, list[dict[str, Any]]] = {e.system_id: [] for e in entries}
        for row in rows:
            rows_by_system[catalog.system_of_mux(int(row["mux"]))].append(row)
        default_id = _default_system_id(catalog, entries)
        response.systems = [
            _system_info(layout, entry, rows_by_system[entry.system_id], default_id)
            for entry in entries
        ]
        return response

    # ------------------------------------------------------------------ write

    def add_system(
        self, *, project_id: str, username: str, chip_id: str, request: AddChipSystemRequest
    ) -> AddChipSystemResponse:
        layout = self._layout_factory()
        if layout.kind is not LayoutKind.SHARED:
            raise ChipSystemsError("Systems can only be added in the shared configuration layout")
        catalog = SystemCatalog(layout, chip_id)
        try:
            entries = catalog.systems()
            rows = catalog.wiring_rows()
        except (OSError, ValueError, LookupError) as exc:
            raise ChipSystemsError(
                f"Configuration for chip {chip_id} could not be read: {exc}"
            ) from exc
        if catalog.is_implicit:
            raise ChipSystemsError(
                f"Chip {chip_id} has no system.yaml entry; provision the chip in the shared layout first"
            )
        system_id = f"{chip_id}-{request.backend}"
        same_backend = [entry.system_id for entry in entries if entry.backend == request.backend]
        if same_backend or any(entry.system_id == system_id for entry in entries):
            raise ChipSystemsError(
                f"Chip {chip_id} already has a {request.backend} System "
                f"({', '.join(same_backend or [system_id])}); one System per backend"
            )

        wired = {int(row["mux"]) for row in rows}
        requested = sorted(set(request.mux_ids))
        unknown = [mux for mux in requested if mux not in wired]
        if unknown:
            raise ChipSystemsError(
                f"MUX {', '.join(map(str, unknown))} are not wired for chip {chip_id}"
            )
        new_rows = self._rows_for_new_system(rows, requested, request.wiring)

        missing_boxes = self._missing_boxes(layout, new_rows)
        if missing_boxes:
            raise ChipSystemsError(
                "Register these boxes in box.yaml first: " + ", ".join(sorted(missing_boxes))
            )

        wiring_entries: dict[str, Any] = {system_id: new_rows}
        moved = set(requested)
        for entry in entries:
            kept = [
                row for row in rows if catalog.system_of_mux(int(row["mux"])) == entry.system_id
            ]
            kept = [row for row in kept if int(row["mux"]) not in moved]
            wiring_entries[entry.system_id] = kept
        settings: dict[str, Any] = {
            "chip_id": catalog.qubex_chip_id,
            "backend": request.backend,
            request.backend: dict(request.settings),
        }
        shared_entries: dict[str, dict[str, Any]] = {
            "system.yaml": {system_id: settings},
            "wiring.yaml": wiring_entries,
        }
        values = self._chip_values(project_id, chip_id)
        system_files = build_system_files(
            system_id,
            request.backend,
            values,
            mux_ids=requested,
            calib_note=self._note(project_id, chip_id),
        )
        self._validate(layout, shared_entries, [system_files])

        writer = TreeWriter(layout)
        writer.write_shared(shared_entries)
        owned = writer.write_system(system_files)
        outcome = self._publish(layout, username, chip_id, shared_entries, owned)

        info = _system_info(
            layout,
            SystemEntry(
                system_id=system_id,
                chip_id=catalog.qubex_chip_id,
                driver=entries[0].driver,
                backend=request.backend,
                mux_ids=frozenset(requested),
                settings=settings,
            ),
            new_rows,
            default_id=_default_system_id(catalog, entries),
        )
        warnings: list[str] = []
        if not values.qubits:
            warnings.append(
                "The chip has no calibration values yet; template defaults were written"
            )
        if (manifest := manifest_warning(layout)) is not None:
            warnings.append(manifest)
        return AddChipSystemResponse(
            system=info,
            files=[str(layout.repo_relpath(path)) for path in writer.written],
            publish=_status(outcome),
            warnings=warnings,
        )

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _rows_for_new_system(
        rows: list[dict[str, Any]],
        mux_ids: list[int],
        wiring: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        if wiring is None:
            return [dict(row) for row in rows if int(row["mux"]) in set(mux_ids)]
        checked = validate_wiring_rows(wiring, where="wiring")
        given = sorted(int(row["mux"]) for row in checked)
        if given != mux_ids:
            raise ChipSystemsError(
                f"wiring covers MUX {given} but mux_ids asks for {mux_ids}; they must match"
            )
        return checked

    @staticmethod
    def _missing_boxes(layout: QubexLayout, rows: list[dict[str, Any]]) -> set[str]:
        path = layout.box_yaml()
        catalog: Any = {}
        if path.is_file():
            catalog = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(catalog, dict):
            raise ChipSystemsError("box.yaml is not a mapping at the top level")
        return {box for box in box_ids_of(rows) if box not in catalog}

    def _note(self, project_id: str, chip_id: str) -> Mapping[str, Any]:
        if self._master_note is not None:
            return self._master_note(project_id, chip_id) or {}
        from qdash.repository.calibration_note import MongoCalibrationNoteRepository

        latest = MongoCalibrationNoteRepository().find_latest_master(
            chip_id=chip_id, project_id=project_id
        )
        return dict(latest.note) if latest is not None else {}

    def _publish(
        self,
        layout: QubexLayout,
        username: str,
        chip_id: str,
        entries: SharedEntries,
        owned: list[Any],
    ) -> PublishOutcome:
        try:
            if self._repository_factory is not None:
                repository = self._repository_factory(layout, actor=username)
            else:
                from qdash.common.infrastructure.config_repository import get_config_repository

                repository = get_config_repository(layout, actor=username)
        except Exception as exc:
            return PublishOutcome(
                status="failed", message=f"Configuration repository unavailable: {exc}"
            )
        return publish_changes(
            repository,
            chip_id=chip_id,
            entries=entries,
            owned_paths=owned,
            message=f"Add System to chip {chip_id}",
        )


def _default_system_id(catalog: SystemCatalog, entries: list[SystemEntry]) -> str:
    try:
        return catalog.default_system_id()
    except ValueError:
        return entries[0].system_id if entries else catalog.chip_id


def _system_info(
    layout: QubexLayout,
    entry: SystemEntry,
    rows: list[dict[str, Any]],
    default_id: str,
) -> ChipSystemInfo:
    try:
        boxes = box_ids_of(rows)
    except ValueError:
        boxes = []
    return ChipSystemInfo(
        system_id=entry.system_id,
        chip_id=entry.chip_id,
        driver=entry.driver,
        backend=entry.backend,
        mux_ids=sorted(entry.mux_ids),
        box_ids=boxes,
        is_default=entry.system_id == default_id,
        has_params=layout.params_dir(entry.system_id).is_dir(),
        has_calib_note=layout.calib_note_path(entry.system_id).is_file(),
        settings=dict(entry.settings),
    )


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
