"""Task-knowledge drafts: one task's knowledge directory, uploaded as a zip.

A draft is knowledge someone wants to try before proposing it to the
knowledge repository. It is stored under its project, named by the zip's
SHA-256 and never changed, and only the evaluation runs and prompt previews
that name it read it: the shared ``task-knowledge.json`` stays as it is.

Layout under ``<calib_data>/projects/<project_id>/knowledge-drafts/<sha256>/``:
``draft.zip`` (the upload), ``draft.json`` (who uploaded it, the generator's
warnings) and ``task/<TaskName>/`` (the extracted directory the knowledge is
parsed from).
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import shutil
import stat
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

from qdash.common.config.paths import CALIB_DATA_BASE
from qdash.common.utils.datetime import now
from qdash.datamodel.task_knowledge import get_task_knowledge, parse_task_dir

if TYPE_CHECKING:
    from qdash.datamodel.task_knowledge import TaskKnowledge

logger = logging.getLogger(__name__)

DRAFTS_DIR_NAME = "knowledge-drafts"
MAX_ZIP_BYTES = 20 * 1024 * 1024
MAX_EXTRACTED_BYTES = 50 * 1024 * 1024
MAX_ENTRIES = 200
ALLOWED_SUFFIXES = frozenset({".md", ".png", ".jpg", ".jpeg", ".webp"})

_DRAFT_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_TASK_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
_CHUNK = 64 * 1024


@dataclass(frozen=True)
class KnowledgeDraft:
    """One stored draft and the knowledge parsed from it."""

    draft_id: str
    task_name: str
    filename: str
    uploaded_by: str
    created_at: datetime
    warnings: list[str]
    knowledge: TaskKnowledge


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _is_junk(path: PurePosixPath) -> bool:
    """Archive noise a zip tool adds: macOS resource forks, dotfiles."""
    return path.parts[0] == "__MACOSX" or any(part.startswith(".") for part in path.parts)


def _task_members(
    archive: zipfile.ZipFile,
) -> tuple[list[tuple[zipfile.ZipInfo, PurePosixPath]], str | None]:
    """The files of the one task in the archive, relative to its directory.

    Accepts ``index.md`` at the top or inside a single top-level directory,
    whose name is returned. Rejects absolute or escaping paths, links, and
    file types a task directory does not hold.
    """
    files: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        if "\\" in info.filename:
            raise _bad_request(f"{info.filename}: backslashes are not allowed in paths")
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts:
            raise _bad_request(f"{info.filename}: paths must stay inside the task directory")
        if _is_junk(path):
            continue
        if stat.S_ISLNK(info.external_attr >> 16):
            raise _bad_request(f"{info.filename}: links are not allowed")
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            raise _bad_request(
                f"{info.filename}: only {', '.join(sorted(ALLOWED_SUFFIXES))} files are allowed"
            )
        files.append((info, path))
    if len(files) > MAX_ENTRIES:
        raise _bad_request(f"the zip holds more than {MAX_ENTRIES} files")
    if sum(info.file_size for info, _ in files) > MAX_EXTRACTED_BYTES:
        raise _bad_request(f"the zip expands to more than {MAX_EXTRACTED_BYTES // 2**20} MB")

    if any(path == PurePosixPath("index.md") for _, path in files):
        return files, None
    roots = {path.parts[0] for _, path in files if len(path.parts) > 1}
    if len(roots) != 1 or any(len(path.parts) == 1 for _, path in files):
        raise _bad_request(
            "the zip must hold one task directory: index.md at the top or in a single folder"
        )
    root = roots.pop()
    if not any(path == PurePosixPath(root, "index.md") for _, path in files):
        raise _bad_request(f"{root}/index.md is missing")
    return [(info, PurePosixPath(*path.parts[1:])) for info, path in files], root


def _h1_title(index_md: bytes) -> str | None:
    for line in index_md.decode("utf-8", errors="replace").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _extract(data: bytes, dest: Path) -> Path:
    """Write the archive's task directory under ``dest`` and return it."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise _bad_request("the upload is not a zip file") from exc
    with archive:
        files, root = _task_members(archive)
        if root is None:
            index = next(info for info, path in files if path == PurePosixPath("index.md"))
            title = _h1_title(archive.read(index)) or ""
            root = title if _TASK_NAME_RE.fullmatch(title) else "task"
        if not _TASK_NAME_RE.fullmatch(root):
            raise _bad_request(f"{root}: a task directory is named after the task")
        task_dir = dest / root
        written = 0
        for info, relative in files:
            target = task_dir.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as sink:
                # The sizes a zip declares are not trusted: count what comes out.
                while chunk := source.read(_CHUNK):
                    written += len(chunk)
                    if written > MAX_EXTRACTED_BYTES:
                        raise _bad_request(
                            f"the zip expands to more than {MAX_EXTRACTED_BYTES // 2**20} MB"
                        )
                    sink.write(chunk)
    return task_dir


@lru_cache(maxsize=32)
def _parse(task_dir: Path, category: str) -> tuple[TaskKnowledge | None, tuple[str, ...]]:
    """A stored draft's knowledge; drafts never change, so one parse per worker."""
    knowledge, warnings = parse_task_dir(task_dir, category=category)
    return knowledge, tuple(warnings)


def _category(task_name: str) -> str:
    published = get_task_knowledge(task_name)
    return published.category if published else ""


class KnowledgeDraftStore:
    """Create and read a project's task-knowledge drafts."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or CALIB_DATA_BASE

    def _drafts_dir(self, project_id: str) -> Path:
        if not _PROJECT_ID_RE.fullmatch(project_id):
            raise _bad_request(f"invalid project id: {project_id}")
        return self._base_dir / "projects" / project_id / DRAFTS_DIR_NAME

    def create(
        self, project_id: str, data: bytes, *, filename: str, uploaded_by: str
    ) -> KnowledgeDraft:
        """Store an uploaded zip as a draft, or return the draft it already is.

        Raises 400 when the zip is not one usable task directory and 503 when
        the knowledge repository's generator is not available to parse it.
        """
        if len(data) > MAX_ZIP_BYTES:
            raise _bad_request(f"the zip exceeds {MAX_ZIP_BYTES // 2**20} MB")
        draft_id = hashlib.sha256(data).hexdigest()
        drafts_dir = self._drafts_dir(project_id)
        if (drafts_dir / draft_id / "draft.json").is_file():
            return self.get(project_id, draft_id)

        drafts_dir.mkdir(parents=True, exist_ok=True)
        staging = drafts_dir / f".staging-{uuid.uuid4().hex}"
        try:
            task_dir = _extract(data, staging / "task")
            title = _h1_title((task_dir / "index.md").read_bytes()) or task_dir.name
            try:
                knowledge, warnings = parse_task_dir(task_dir, category=_category(title))
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
                ) from exc
            if knowledge is None:
                raise _bad_request(
                    "index.md could not be read as task knowledge: "
                    + ("; ".join(warnings) or "no H1 title")
                )
            (staging / "draft.zip").write_bytes(data)
            meta = {
                "draft_id": draft_id,
                "task_name": knowledge.name,
                "task_dir": task_dir.name,
                "filename": filename,
                "uploaded_by": uploaded_by,
                "created_at": now().isoformat(),
                "warnings": warnings,
            }
            (staging / "draft.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            try:
                os.replace(staging, drafts_dir / draft_id)
            except OSError:
                # The same zip was stored concurrently; that copy stands.
                if not (drafts_dir / draft_id / "draft.json").is_file():
                    raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        logger.info("knowledge draft %s for %s stored by %s", draft_id, knowledge.name, uploaded_by)
        return self.get(project_id, draft_id)

    def get(self, project_id: str, draft_id: str) -> KnowledgeDraft:
        """A stored draft of the project; 404 when the project holds no such draft."""
        not_found = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"knowledge draft {draft_id} not found"
        )
        if not _DRAFT_ID_RE.fullmatch(draft_id):
            raise not_found
        draft_dir = self._drafts_dir(project_id) / draft_id
        try:
            meta = json.loads((draft_dir / "draft.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise not_found from exc
        task_name = str(meta.get("task_name") or "")
        try:
            knowledge, _ = _parse(
                draft_dir / "task" / str(meta.get("task_dir") or ""), _category(task_name)
            )
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
        if knowledge is None:
            raise not_found
        return KnowledgeDraft(
            draft_id=draft_id,
            task_name=task_name,
            filename=str(meta.get("filename") or ""),
            uploaded_by=str(meta.get("uploaded_by") or ""),
            created_at=datetime.fromisoformat(str(meta.get("created_at"))),
            warnings=[str(warning) for warning in meta.get("warnings") or []],
            knowledge=knowledge,
        )
