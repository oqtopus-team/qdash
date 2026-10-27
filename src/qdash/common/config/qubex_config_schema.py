"""Validate a qubex-config tree against the layout schemas.

The schemas live in ``config/domain/qubex-config-schemas`` and are published at
``https://oqtopus-team.github.io/qdash/schemas/qubex-config/``. They describe two
layout versions agreed with the qubex team: ``1.0`` (per-chip directories, before
qubex 1.5) and ``2.0`` (shared ``config/`` with ``params/<system_id>/`` and
``calibration/<system_id>/``). The manifest ``<root>/qubex-config.json`` names the
version; :mod:`qdash.common.config.qubex_layout` reads it.

Validation here is structural (is this a well-formed chip / system / wiring / box /
skew / params file). Whether the content is consistent (every box exists, no MUX in
two Systems) is :class:`~qdash.common.config.system_catalog.SystemCatalog`'s job.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import yaml

from qdash.common.config.loader import ConfigLoader
from qdash.common.config.qubex_layout import MANIFEST_FILE, LayoutKind, QubexLayout

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

SCHEMAS_DIR = "domain/qubex-config-schemas"
SCHEMA_BASE_URL = "https://oqtopus-team.github.io/qdash/schemas/qubex-config/"

_SHARED_SCHEMAS: dict[str, str] = {
    "chip.yaml": "chip.schema.json",
    "wiring.yaml": "wiring.schema.json",
    "box.yaml": "box.schema.json",
    "skew.yaml": "skew.schema.json",
}
_SYSTEM_SCHEMA: dict[LayoutKind, str] = {
    LayoutKind.LEGACY: "system.v1.schema.json",
    LayoutKind.SHARED: "system.v2.schema.json",
}
PARAMS_FILE_SCHEMA = "params-file.schema.json"
PARAMS_SETTINGS_FILES = frozenset({"measurement_defaults.yaml"})
"""Files in a params directory that hold settings rather than one parameter."""
MANIFEST_SCHEMA = "manifest.schema.json"


@dataclass(frozen=True)
class SchemaProblem:
    """One schema violation in one file."""

    path: str
    """Repository-relative path of the file."""
    location: str
    """JSON pointer-like location inside the document (``144Qv3/n_qubits``)."""
    message: str

    def __str__(self) -> str:
        where = f"{self.path}" + (f" at {self.location}" if self.location else "")
        return f"{where}: {self.message}"


def schemas_dir() -> Path:
    """Directory holding the JSON Schema files."""
    return ConfigLoader.get_config_dir() / SCHEMAS_DIR


@cache
def load_schema(name: str) -> dict[str, Any]:
    """Load one schema by file name."""
    path = schemas_dir() / name
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def schema_names() -> list[str]:
    """Every schema file name shipped with QDash."""
    return sorted(path.name for path in schemas_dir().glob("*.schema.json"))


def schema_for(relpath: str | PurePosixPath, layout: QubexLayout) -> str | None:
    """Schema file name for a repository-relative path, or None when none applies."""
    rel = PurePosixPath(relpath)
    parts = rel.parts
    if not parts:
        return None
    if len(parts) == 1 and parts[0] == MANIFEST_FILE:
        return MANIFEST_SCHEMA
    if layout.is_shared:
        if len(parts) == 2 and parts[0] == "config":
            name = parts[1]
        elif len(parts) == 3 and parts[0] == "params" and rel.suffix == ".yaml":
            return None if rel.name in PARAMS_SETTINGS_FILES else PARAMS_FILE_SCHEMA
        else:
            return None
    else:
        if len(parts) == 3 and parts[1] == "config":
            name = parts[2]
        elif len(parts) == 3 and parts[1] == "params" and rel.suffix == ".yaml":
            return None if rel.name in PARAMS_SETTINGS_FILES else PARAMS_FILE_SCHEMA
        else:
            return None
    if name == "system.yaml":
        return _SYSTEM_SCHEMA[layout.kind]
    return _SHARED_SCHEMAS.get(name)


def _validator(name: str) -> Any:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    registry: Registry[Any] = Registry()
    for schema_name in schema_names():
        schema = load_schema(schema_name)
        resource = Resource.from_contents(schema)
        registry = registry.with_resource(SCHEMA_BASE_URL + schema_name, resource)
    return Draft202012Validator(load_schema(name), registry=registry)


def validate_document(data: Any, schema_name: str, relpath: str) -> list[SchemaProblem]:
    """Problems of an already parsed document against ``schema_name``."""
    problems: list[SchemaProblem] = []
    for error in sorted(_validator(schema_name).iter_errors(data), key=lambda e: list(e.path)):
        location = "/".join(str(part) for part in error.absolute_path)
        problems.append(SchemaProblem(relpath, location, error.message))
    return problems


def validate_text(content: str, relpath: str, layout: QubexLayout) -> list[SchemaProblem]:
    """Problems of file content as it would be stored at ``relpath``.

    Returns an empty list when no schema applies to the path. A document that
    does not parse is reported as a single problem.
    """
    schema_name = schema_for(relpath, layout)
    if schema_name is None:
        return []
    try:
        data = json.loads(content) if relpath.endswith(".json") else yaml.safe_load(content)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        return [SchemaProblem(relpath, "", f"not a valid document: {exc}")]
    return validate_document(data, schema_name, relpath)


def validate_file(path: Path, layout: QubexLayout) -> list[SchemaProblem]:
    """Problems of one file in the tree; a missing file is not a problem."""
    if not path.is_file():
        return []
    relpath = str(layout.repo_relpath(path))
    return validate_text(path.read_text(encoding="utf-8"), relpath, layout)


def validate_shared_files(layout: QubexLayout, chip_id: str | None = None) -> list[SchemaProblem]:
    """Problems of the manifest and the chip/system/wiring/box/skew files."""
    problems = validate_file(layout.manifest_path, layout)
    for method in (
        layout.chip_yaml,
        layout.system_yaml,
        layout.wiring_yaml,
        layout.box_yaml,
        layout.skew_yaml,
    ):
        problems.extend(validate_file(method(chip_id), layout))
    return problems


def validate_params_dir(layout: QubexLayout, system_id: str) -> list[SchemaProblem]:
    """Problems of every ``*.yaml`` in one System's params directory."""
    directory = layout.params_dir(system_id)
    if not directory.is_dir():
        return []
    problems: list[SchemaProblem] = []
    for path in sorted(directory.glob("*.yaml")):
        problems.extend(validate_file(path, layout))
    return problems


def validate_tree(
    layout: QubexLayout, chip_id: str | None = None, system_ids: Iterable[str] = ()
) -> list[SchemaProblem]:
    """Shared files plus the params directories of ``system_ids``."""
    problems = validate_shared_files(layout, chip_id)
    for system_id in system_ids:
        problems.extend(validate_params_dir(layout, system_id))
    return problems


TREE_SCHEMAS_DIR = "schemas"
"""Directory where a qubex-config tree keeps its own copy of the schemas."""


def schemas_status(layout: QubexLayout) -> str:
    """How the tree's ``schemas/`` copy compares with the schemas QDash ships.

    ``"absent"`` when the tree has no copy, ``"match"`` when every shipped schema is
    present with identical content, ``"differs"`` otherwise (missing, extra or changed
    files). QDash validates with its own copy either way; this is informational.
    """
    tree_dir = layout.root / TREE_SCHEMAS_DIR
    if not tree_dir.is_dir():
        return "absent"
    shipped = schema_names()
    present = sorted(path.name for path in tree_dir.glob("*.schema.json"))
    if present != shipped:
        return "differs"
    for name in shipped:
        try:
            tree_doc = json.loads((tree_dir / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "differs"
        if tree_doc != load_schema(name):
            return "differs"
    return "match"


def manifest_document(
    layout_kind: LayoutKind, *, converted_from: LayoutKind | None = None, generated_by: str
) -> Mapping[str, Any]:
    """The manifest QDash writes for a tree of ``layout_kind``."""
    from qdash.common.utils.datetime import now_iso

    doc: dict[str, Any] = {
        "$schema": SCHEMA_BASE_URL + MANIFEST_SCHEMA,
        "layout_version": layout_kind.version,
        "generated_by": generated_by,
    }
    if converted_from is not None:
        doc["converted_from"] = converted_from.version
        doc["converted_at"] = now_iso()
    return doc
