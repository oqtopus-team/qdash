"""Generate and check the Qubex configuration files of a chip's Systems.

Shared by chip provisioning (:mod:`provisioner`) and System addition
(:mod:`systems`). Both build the same two things: entries for the shared
catalog files (``chip.yaml``, ``system.yaml``, ``wiring.yaml``) and the files a
System owns (``params/<system_id>/*.yaml``, ``calibration/<system_id>/calib_note.json``).
Before anything touches the live tree, the result is staged in a temporary copy
and loaded with qubex's ``ConfigLoader`` offline, so a missing box or a
wrong ``capture_delay`` unit is reported instead of written.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import warnings
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from qdash.common.config import qubex_params_templates as templates
from qdash.common.config.qubex_config_schema import validate_tree
from qdash.common.config.qubex_layout import CALIB_NOTE_FILE, QubexLayout
from qdash.common.config.system_catalog import DEFAULT_BACKEND
from qdash.common.domain.qubit import qid_to_label

logger = logging.getLogger(__name__)

SHARED_FILE_NAMES = ("chip.yaml", "system.yaml", "wiring.yaml", "box.yaml", "skew.yaml")

ChipValuesLookup = Callable[[str, str], "ChipValues"]
"""(project_id, chip_id) -> the chip's calibration values from the database."""


@dataclass
class ChipValues:
    """Calibration records of a chip keyed the way the params files are keyed."""

    n_qubits: int
    qubits: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    """qubit label (``Q00``) -> ``{parameter: {"value", "unit", ...}}``."""
    couplings: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    """coupling label (``Q00-Q01``) -> records."""
    coupling_ids: list[str] = field(default_factory=list)
    """Coupling qids (``0-1``) of the chip, for files keyed by coupling."""


def empty_chip_values(n_qubits: int) -> ChipValues:
    return ChipValues(n_qubits=n_qubits)


def chip_values_from_db(project_id: str, chip_id: str) -> ChipValues:
    """Read the chip's qubit and coupling calibration records."""
    from qdash.dbmodel.chip import ChipDocument
    from qdash.dbmodel.coupling import CouplingDocument
    from qdash.dbmodel.qubit import QubitDocument

    chip = ChipDocument.find_one({"project_id": project_id, "chip_id": chip_id}).run()
    n_qubits = int(chip.size) if chip is not None else 0
    values = ChipValues(n_qubits=n_qubits)
    if chip is None:
        return values
    for doc in QubitDocument.find({"project_id": project_id, "chip_id": chip_id}).run():
        try:
            label = qid_to_label(doc.qid, n_qubits)
        except ValueError:
            continue
        values.qubits[label] = dict(doc.data or {})
    for doc in CouplingDocument.find({"project_id": project_id, "chip_id": chip_id}).run():
        parts = str(doc.qid).split("-")
        if len(parts) != 2:
            continue
        try:
            label = "-".join(qid_to_label(part, n_qubits) for part in parts)
        except ValueError:
            continue
        values.coupling_ids.append(str(doc.qid))
        values.couplings[label] = dict(doc.data or {})
    return values


# --------------------------------------------------------------------------- #
# Wiring helpers
# --------------------------------------------------------------------------- #


def split_box_port(specifier: str) -> tuple[str, int]:
    """``<box>:<port>`` (or legacy ``<box>-<port>``) -> (box id, port)."""
    separator = ":" if ":" in specifier else "-"
    box_id, found, port_text = specifier.rpartition(separator)
    if not found or not box_id or not port_text:
        raise ValueError(f"Invalid port specifier: {specifier!r}")
    try:
        return box_id, int(port_text)
    except ValueError as exc:
        raise ValueError(f"Invalid port number in specifier: {specifier!r}") from exc


def box_ids_of(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Box ids referenced by wiring rows, in first-seen order."""
    seen: list[str] = []
    for row in rows:
        specifiers: list[Any] = [row.get("read_out"), row.get("read_in"), row.get("pump")]
        ctrl = row.get("ctrl")
        if isinstance(ctrl, list):
            specifiers.extend(ctrl)
        for specifier in specifiers:
            if not isinstance(specifier, str) or not specifier.strip():
                continue
            box_id, _ = split_box_port(specifier)
            if box_id not in seen:
                seen.append(box_id)
    return seen


def validate_wiring_rows(rows: Iterable[Mapping[str, Any]], *, where: str) -> list[dict[str, Any]]:
    """Check the shape of MUX rows and return plain copies."""
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"{where}[{index}] must be a mapping")
        mux = row.get("mux")
        if type(mux) is not int or mux < 0:
            raise ValueError(f"{where}[{index}] needs a non-negative integer 'mux'")
        if mux in seen:
            raise ValueError(f"{where}: MUX {mux} appears twice")
        seen.add(mux)
        ctrl = row.get("ctrl")
        if not isinstance(ctrl, list) or not ctrl or any(not isinstance(c, str) for c in ctrl):
            raise ValueError(f"{where}[{index}] needs a non-empty list of 'ctrl' ports")
        for key in ("read_out", "read_in"):
            if not isinstance(row.get(key), str) or not str(row.get(key)).strip():
                raise ValueError(f"{where}[{index}] needs a '{key}' port")
        for specifier in [*ctrl, row["read_out"], row["read_in"], row.get("pump")]:
            if specifier is not None:
                split_box_port(str(specifier))
        result.append(dict(row))
    return result


# --------------------------------------------------------------------------- #
# System files
# --------------------------------------------------------------------------- #


def system_id_for(chip_id: str, backend: str, *, is_default: bool) -> str:
    """``<chip_id>`` for the chip's default System, else ``<chip_id>-<backend>``."""
    return chip_id if is_default else f"{chip_id}-{backend}"


def render_params_files(
    backend: str,
    values: ChipValues,
    *,
    mux_ids: Iterable[int],
    coupling_ids: Iterable[str] | None = None,
) -> dict[str, str]:
    """File name -> content for one System directory.

    Physics files take the chip's DB values where the unit matches the template,
    else the template default; backend files only exist for ``backend``.
    """
    couplings = list(coupling_ids) if coupling_ids is not None else list(values.coupling_ids)
    mux_list = sorted({int(m) for m in mux_ids})
    files: dict[str, str] = {}
    for template in templates.templates_for(backend):
        if template.scope is None:
            files[template.name] = templates.render(template, labels=())
            continue
        labels = templates.labels_for(
            template.scope, n_qubits=values.n_qubits, mux_ids=mux_list, couplings=couplings
        )
        records = values.couplings if template.scope == templates.SCOPE_COUPLING else values.qubits
        rendered: dict[Any, Any] = {}
        if template.scope != templates.SCOPE_MUX:
            for label in labels:
                value = templates.value_for_template(
                    template, (records.get(label) or {}).get(template.parameter)
                )
                if value is not None:
                    rendered[label] = value
        files[template.name] = templates.render(template, labels=labels, values=rendered)
    return files


@dataclass
class SystemFiles:
    """Everything one System owns, ready to write."""

    system_id: str
    backend: str
    params: dict[str, str]
    calib_note: dict[str, Any] = field(default_factory=dict)

    def write(self, layout: QubexLayout) -> list[Path]:
        """Write under the layout; returns the paths written."""
        written: list[Path] = []
        params_dir = layout.params_dir(self.system_id)
        params_dir.mkdir(parents=True, exist_ok=True)
        for name, content in self.params.items():
            path = params_dir / name
            path.write_text(content, encoding="utf-8")
            written.append(path)
        note_path = layout.calib_note_path(self.system_id)
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(
            json.dumps(self.calib_note, indent=4, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(note_path)
        return written


def build_system_files(
    system_id: str,
    backend: str,
    values: ChipValues,
    *,
    mux_ids: Iterable[int],
    calib_note: Mapping[str, Any] | None = None,
) -> SystemFiles:
    return SystemFiles(
        system_id=system_id,
        backend=backend or DEFAULT_BACKEND,
        params=render_params_files(backend or DEFAULT_BACKEND, values, mux_ids=mux_ids),
        calib_note=dict(calib_note or {}),
    )


# --------------------------------------------------------------------------- #
# Staging and offline validation
# --------------------------------------------------------------------------- #

SharedEntries = Mapping[str, Mapping[str, Any]]
"""``{"system.yaml": {key: value_or_None}, ...}`` as ``ConfigRepository.upsert_shared`` takes."""


def apply_shared_entries(config_dir: Path, entries: SharedEntries) -> None:
    """Apply key upserts to plain copies of shared files (staging only; no comments kept)."""
    for name, keys in entries.items():
        path = config_dir / name
        data: Any = {}
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{path.name} is not a mapping at the top level")
        for key, value in keys.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def stage_tree(
    layout: QubexLayout,
    entries: SharedEntries,
    systems: Iterable[SystemFiles],
) -> Path:
    """Copy the shared files into a temporary root and lay the new files over them.

    The caller removes the directory (``shutil.rmtree``).
    """
    root = Path(tempfile.mkdtemp(prefix="qdash-config-stage-"))
    staged = QubexLayout(root=root, kind=layout.kind)
    source_dir = layout.config_dir()
    target_dir = staged.config_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    if source_dir.is_dir():
        for path in source_dir.glob("*.yaml"):
            shutil.copy2(path, target_dir / path.name)
    apply_shared_entries(target_dir, entries)
    for system in systems:
        system.write(staged)
    return root


def validate_system_offline(layout: QubexLayout, system_id: str) -> None:
    """Load one System with qubex without connecting; raises ValueError on problems."""
    try:
        from qubex.system import ConfigLoader
    except ImportError as exc:  # pragma: no cover - qubex is a runtime dependency
        raise ValueError("qubex is not installed; cannot validate the configuration") from exc
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            loader = ConfigLoader(
                system_id=system_id,
                config_dir=layout.config_dir(),
                params_dir=layout.params_dir(system_id),
            )
            loader.get_experiment_system()
    except Exception as exc:
        raise ValueError(f"System {system_id!r}: {exc}") from exc


def validate_staged(
    layout: QubexLayout,
    entries: SharedEntries,
    systems: list[SystemFiles],
) -> None:
    """Stage, validate every System offline, and discard the staging directory."""
    root = stage_tree(layout, entries, systems)
    try:
        staged = QubexLayout(root=root, kind=layout.kind)
        schema_problems = validate_tree(staged, system_ids=[system.system_id for system in systems])
        if schema_problems:
            shown = "; ".join(str(problem) for problem in schema_problems[:5])
            raise ValueError(f"generated files violate the layout schema: {shown}")
        for system in systems:
            validate_system_offline(staged, system.system_id)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def calib_note_file_name() -> str:
    return CALIB_NOTE_FILE


def manifest_warning(layout: QubexLayout) -> str | None:
    """Warning for a shared tree whose repository does not declare its layout version yet."""
    if not layout.is_shared or layout.manifest_path.is_file():
        return None
    return (
        "The configuration repository has no qubex-config.json; add one declaring "
        f'"layout_version": "{layout.version}" so the layout is declared rather than inferred'
    )


# --------------------------------------------------------------------------- #
# Writing the live tree and publishing
# --------------------------------------------------------------------------- #


def upsert_yaml_keys(path: Path, keys: Mapping[str, Any]) -> None:
    """Replace top-level keys of a live shared file, keeping other keys and comments."""
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap

    ruamel = YAML()
    ruamel.preserve_quotes = True
    ruamel.width = 4096
    data: Any = None
    if path.exists():
        with path.open(encoding="utf-8") as f:
            data = ruamel.load(f)
    if data is None:
        data = CommentedMap()
    if not isinstance(data, CommentedMap):
        raise ValueError(f"{path.name} is not a mapping at the top level")
    for key, value in keys.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        ruamel.dump(data, f)
    tmp.replace(path)


class TreeWriter:
    """Write shared entries and System files, remembering how to undo them."""

    def __init__(self, layout: QubexLayout) -> None:
        self.layout = layout
        self._previous: dict[Path, bytes | None] = {}
        self.written: list[Path] = []

    def _remember(self, path: Path) -> None:
        if path in self._previous:
            return
        self._previous[path] = path.read_bytes() if path.exists() else None

    def write_shared(self, entries: SharedEntries) -> list[Path]:
        paths: list[Path] = []
        for name, keys in entries.items():
            path = self.layout.config_dir() / name
            self._remember(path)
            upsert_yaml_keys(path, keys)
            paths.append(path)
            self.written.append(path)
        return paths

    def write_system(self, system: SystemFiles) -> list[Path]:
        params_dir = self.layout.params_dir(system.system_id)
        for name in system.params:
            self._remember(params_dir / name)
        self._remember(self.layout.calib_note_path(system.system_id))
        paths = system.write(self.layout)
        self.written.extend(paths)
        return paths

    def rollback(self) -> None:
        """Restore every file to its previous content, removing files that were new."""
        for path, content in self._previous.items():
            _restore_file(path, content)
        for path, content in self._previous.items():
            if content is None:
                _remove_empty_dir(path.parent)


def _restore_file(path: Path, content: bytes | None) -> None:
    try:
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(content)
    except OSError as exc:
        logger.warning("Could not roll back %s: %s", path, exc)


def _remove_empty_dir(directory: Path) -> None:
    try:
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    except OSError:
        pass


@dataclass
class PublishOutcome:
    """What happened when the written files were handed to the repository."""

    status: str
    """published | recorded | failed | skipped"""
    mode: str | None = None
    commit: str | None = None
    message: str | None = None


def publish_changes(
    repository: Any,
    *,
    chip_id: str,
    entries: SharedEntries,
    owned_paths: Iterable[Path],
    message: str,
) -> PublishOutcome:
    """Publish shared entries and owned files; never raises.

    The files are already on disk, so a remote failure leaves them (and the
    database records the caller made) in place and is reported as ``failed``.
    """
    owned = list(owned_paths)
    if not entries and not owned:
        return PublishOutcome(status="skipped")
    mode = getattr(getattr(repository, "mode", None), "value", None)
    commit: str | None = None
    try:
        if entries:
            result = repository.upsert_shared(entries, message, chip_id=chip_id)
            commit = getattr(result, "commit", None) or commit
        if owned:
            result = repository.publish_owned(owned, message, chip_id=chip_id)
            commit = getattr(result, "commit", None) or commit
    except Exception as exc:
        logger.warning("Publishing configuration for chip %s failed: %s", chip_id, exc)
        return PublishOutcome(status="failed", mode=mode, message=str(exc))
    status = "published" if commit else "recorded"
    return PublishOutcome(status=status, mode=mode, commit=commit)
