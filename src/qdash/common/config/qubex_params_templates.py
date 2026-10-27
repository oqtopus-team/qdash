"""Templates for the per-file Qubex parameter YAMLs that a System directory holds.

QDash owns the templates (``config/domain/qubex-params/``) so that a chip or System
can be provisioned without the qubex-config repository's ``template/`` directory.

``common/`` holds the physics files that describe the chip itself (frequencies,
coherence times, fidelities). Their values are the same for every System of a chip,
so they are written to every System directory. ``quel1/`` and ``quel3/`` hold the
files whose meaning or unit depends on the control hardware (``capture_delay.yaml``
is ``ndelay`` on QuEL-1 and ``ns`` on QuEL-3; VATT/FSC files exist only on QuEL-1).
Those are written to the directory of the System that uses that backend and nowhere
else, because qubex rejects a file whose unit does not match the backend.

A template is ``{"meta": {description, unit, default, scope}, "data": {}}``. ``scope``
is QDash-only (``qubit``, ``mux`` or ``coupling``) and says what the data keys are; it
is stripped from the rendered file. A file without ``meta`` (``measurement_defaults.yaml``)
is copied verbatim.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from qdash.common.config.loader import ConfigLoader
from qdash.common.domain.qubit import qid_to_label

if TYPE_CHECKING:
    from collections.abc import Iterable

TEMPLATES_DIR = "domain/qubex-params"
COMMON = "common"
SCOPE_QUBIT = "qubit"
SCOPE_MUX = "mux"
SCOPE_COUPLING = "coupling"
_SCOPES = (SCOPE_QUBIT, SCOPE_MUX, SCOPE_COUPLING)
QDASH_ONLY_META_KEYS = ("scope",)


@dataclass(frozen=True)
class ParamsTemplate:
    """One template file and how it is projected."""

    name: str
    """File name, e.g. ``t1.yaml``."""
    path: Path
    backend: str | None
    """``None`` for a common (physics) file, else the backend it belongs to."""
    scope: str | None
    """``qubit`` / ``mux`` / ``coupling``, or ``None`` for a verbatim file."""
    meta: Mapping[str, Any] = field(default_factory=dict)

    @property
    def parameter(self) -> str:
        """Parameter name the file stores (the stem)."""
        return Path(self.name).stem

    @property
    def is_common(self) -> bool:
        return self.backend is None

    @property
    def default(self) -> Any:
        return self.meta.get("default")

    @property
    def unit(self) -> str | None:
        unit = self.meta.get("unit")
        return str(unit) if unit is not None else None


def templates_dir() -> Path:
    """Root of the QDash parameter templates."""
    return ConfigLoader.get_config_dir() / TEMPLATES_DIR


def available_backends() -> list[str]:
    """Backends with a template directory, e.g. ``["quel1", "quel3"]``."""
    root = templates_dir()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and p.name != COMMON)


@lru_cache(maxsize=8)
def _load_dir(directory: Path, backend: str | None) -> tuple[ParamsTemplate, ...]:
    if not directory.is_dir():
        return ()
    items: list[ParamsTemplate] = []
    for path in sorted(directory.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        meta: dict[str, Any] = {}
        scope: str | None = None
        if isinstance(payload, dict) and "meta" in payload:
            raw_meta = payload.get("meta") or {}
            if not isinstance(raw_meta, dict):
                raise ValueError(f"{path}: meta must be a mapping")
            meta = dict(raw_meta)
            scope = str(meta.get("scope") or SCOPE_QUBIT)
            if scope not in _SCOPES:
                raise ValueError(f"{path}: meta.scope must be one of {', '.join(_SCOPES)}")
        items.append(ParamsTemplate(path.name, path, backend, scope, meta))
    return tuple(items)


def clear_cache() -> None:
    """Forget loaded templates (tests swap the configuration directory)."""
    _load_dir.cache_clear()


def common_templates() -> list[ParamsTemplate]:
    """Physics files written to every System directory of a chip."""
    return list(_load_dir(templates_dir() / COMMON, None))


def backend_templates(backend: str) -> list[ParamsTemplate]:
    """Files written only to the directory of a System with this backend."""
    return list(_load_dir(templates_dir() / backend, backend))


def templates_for(backend: str) -> list[ParamsTemplate]:
    """Every file a System of ``backend`` gets; a backend file shadows a common one."""
    specific = {item.name: item for item in backend_templates(backend)}
    merged = [item for item in common_templates() if item.name not in specific]
    merged.extend(specific.values())
    return sorted(merged, key=lambda item: item.name)


def backend_specific_files() -> frozenset[str]:
    """Names of files that depend on the backend for any backend."""
    names: set[str] = set()
    for backend in available_backends():
        names.update(item.name for item in backend_templates(backend))
    return frozenset(names)


def is_common_file(name: str) -> bool:
    """Whether a params file holds chip physics shared by every System."""
    return name not in backend_specific_files()


def labels_for(
    scope: str, *, n_qubits: int, mux_ids: Iterable[int], couplings: Iterable[str]
) -> list[Any]:
    """Data keys of a rendered file: qubit labels, MUX indexes or coupling labels."""
    if scope == SCOPE_MUX:
        return sorted({int(mux) for mux in mux_ids})
    if scope == SCOPE_COUPLING:
        return [
            "-".join(qid_to_label(part, n_qubits) for part in coupling.split("-"))
            for coupling in couplings
        ]
    return [qid_to_label(str(index), n_qubits) for index in range(n_qubits)]


def render(
    template: ParamsTemplate,
    *,
    labels: Iterable[Any],
    values: Mapping[Any, Any] | None = None,
) -> str:
    """Render a template with ``values`` (by label) or its default for every label.

    Labels without a value and without a default are left out, so a file whose
    parameter has not been measured yet has an empty ``data`` section.
    """
    if template.scope is None:
        return template.path.read_text(encoding="utf-8")
    meta = {k: v for k, v in template.meta.items() if k not in QDASH_ONLY_META_KEYS}
    values = values or {}
    data: dict[Any, Any] = {}
    for label in labels:
        value = values.get(label, template.default)
        if value is None:
            continue
        data[label] = value
    payload = {"meta": meta, "data": data}
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=1000)


def value_for_template(template: ParamsTemplate, record: Mapping[str, Any] | None) -> Any:
    """Pick a DB calibration record's value for a template, when the units agree.

    ``record`` is the ``{"value": ..., "unit": ...}`` entry QDash stores for a qubit
    or coupling. A record whose unit differs from the template is skipped (``None``)
    rather than converted, so a wrong unit never reaches the hardware configuration.
    """
    if not isinstance(record, Mapping):
        return None
    value = record.get("value")
    if value is None or isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    unit = record.get("unit")
    if template.unit is not None and unit not in (None, "", template.unit):
        return None
    return value
