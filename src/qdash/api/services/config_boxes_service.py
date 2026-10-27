"""Read and extend the shared Qubex box catalog (``config/box.yaml``).

Boxes are the control units (QuEL-1, QuEL-3, QuBE) that ``wiring.yaml`` rows
reference by id. qubex loads only the boxes a System's wiring references and
refuses to load when one is missing, so a box is registered here before a
System that uses it is added. Only administrators may change the catalog; it is
shared by every chip in the configuration tree.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import yaml

from qdash.api.schemas.chip import ChipPublishStatus
from qdash.api.schemas.config_boxes import (
    ConfigBox,
    ListConfigBoxesResponse,
    UpsertConfigBoxResponse,
)
from qdash.api.services.chip.system_files import PublishOutcome, TreeWriter, publish_changes
from qdash.common.config.qubex_layout import LayoutKind, QubexLayout

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

_KNOWN_KEYS = ("name", "type", "address", "adapter", "options")

# qubex ``BoxType`` values; the import is deferred because qubex is heavy.
_FALLBACK_BOX_TYPES = (
    "quel3",
    "quel1se-fujitsu11-a",
    "quel1se-fujitsu11-b",
    "quel1se-riken8",
    "quel1-a",
    "quel1-b",
    "qube-riken-a",
    "qube-riken-b",
    "qube-ou-a",
    "qube-ou-b",
)
_ADDRESS_FREE_TYPES = frozenset({"quel3"})


def box_types() -> list[str]:
    """Box types qubex accepts."""
    try:
        from qubex.system import BoxType
    except ImportError:  # pragma: no cover - qubex is a runtime dependency
        return list(_FALLBACK_BOX_TYPES)
    return [item.value for item in BoxType]


class ConfigBoxesError(ValueError):
    """The catalog cannot be read or changed as asked; the message is for the user."""


class ConfigBoxesService:
    """List and upsert ``box.yaml`` entries."""

    def __init__(
        self,
        *,
        layout_factory: Callable[[], QubexLayout] = QubexLayout.detect,
        repository_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._layout_factory = layout_factory
        self._repository_factory = repository_factory

    def list_boxes(self, *, chip_id: str | None = None) -> ListConfigBoxesResponse:
        layout = self._layout_factory()
        response = ListConfigBoxesResponse(
            layout=layout.kind.value,
            editable=layout.kind is LayoutKind.SHARED,
            box_types=box_types(),
        )
        try:
            catalog = self._read(layout, chip_id)
        except ConfigBoxesError as exc:
            response.message = str(exc)
            return response
        response.boxes = [_to_box(box_id, entry) for box_id, entry in catalog.items()]
        return response

    def upsert_box(self, *, username: str, box: ConfigBox) -> UpsertConfigBoxResponse:
        layout = self._layout_factory()
        if layout.kind is not LayoutKind.SHARED:
            raise ConfigBoxesError(
                "Boxes can only be registered in the shared configuration layout"
            )
        types = box_types()
        if box.type not in types:
            raise ConfigBoxesError(f"Unknown box type {box.type!r}; one of: {', '.join(types)}")
        if box.type not in _ADDRESS_FREE_TYPES and not (box.address and box.adapter):
            raise ConfigBoxesError(f"Boxes of type {box.type!r} need both address and adapter")
        catalog = self._read(layout, None)
        created = box.box_id not in catalog
        entry = _to_entry(box)
        writer = TreeWriter(layout)
        entries = {"box.yaml": {box.box_id: entry}}
        writer.write_shared(entries)
        outcome = self._publish(layout, username, entries)
        return UpsertConfigBoxResponse(
            box=_to_box(box.box_id, entry), created=created, publish=_status(outcome)
        )

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _read(layout: QubexLayout, chip_id: str | None) -> dict[str, Any]:
        try:
            path = layout.box_yaml(chip_id)
        except ValueError as exc:
            raise ConfigBoxesError(
                "The legacy layout keeps one box.yaml per chip; pass chip_id"
            ) from exc
        if not path.is_file():
            return {}
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigBoxesError(f"box.yaml is not valid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigBoxesError("box.yaml is not a mapping at the top level")
        return {str(key): value for key, value in data.items() if isinstance(value, dict)}

    def _publish(
        self, layout: QubexLayout, username: str, entries: dict[str, dict[str, Any]]
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
        box_id = next(iter(entries["box.yaml"]))
        return publish_changes(
            repository,
            chip_id="",
            entries=entries,
            owned_paths=[],
            message=f"Register box {box_id}",
        )


def _to_box(box_id: str, entry: dict[str, Any]) -> ConfigBox:
    options = entry.get("options")
    return ConfigBox(
        box_id=box_id,
        name=str(entry.get("name") or box_id),
        type=str(entry.get("type") or ""),
        address=str(entry["address"]) if entry.get("address") is not None else None,
        adapter=str(entry["adapter"]) if entry.get("adapter") is not None else None,
        options=[str(item) for item in options] if isinstance(options, list) else None,
        extra={k: v for k, v in entry.items() if k not in _KNOWN_KEYS},
    )


def _to_entry(box: ConfigBox) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": box.name, "type": box.type}
    if box.address is not None:
        entry["address"] = box.address
    if box.adapter is not None:
        entry["adapter"] = box.adapter
    if box.options:
        entry["options"] = list(box.options)
    for key, value in box.extra.items():
        if key not in entry:
            entry[key] = value
    return entry


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
