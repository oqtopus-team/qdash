"""Read-only access to QDash and dependency source code for Copilot investigations.

The Copilot investigates a failed execution by reading the code that raised the
error. This service exposes a fixed set of source roots (the QDash package and
allowlisted dependencies installed in the API process) for searching and
reading, and nothing else: paths are resolved inside a root, hidden files,
caches and user flows are skipped, only text source files are served, and
every response is size-limited. It never writes.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

# Suffixes of the files a root serves; everything else (data, binaries, keys) is skipped.
SOURCE_SUFFIXES = frozenset(
    {".py", ".pyi", ".toml", ".yaml", ".yml", ".md", ".txt", ".cfg", ".ini", ".json"}
)
# Directory names never entered.
SKIPPED_DIRS = frozenset({"__pycache__", "node_modules", ".venv", "venv", "site-packages"})
# Paths inside the QDash root that hold per-project content; served through the
# project-scoped flow API instead.
QDASH_EXCLUDED_PREFIXES = ("workflow/user_flows",)
# Directories an installed package lives in; the segment after one names the package.
INSTALL_DIRS = frozenset({"site-packages", "dist-packages"})

DEFAULT_DEPENDENCIES = ("qubex", "qubecalib")
MAX_FILE_BYTES = 1_000_000
MAX_READ_LINES = 400
MAX_SEARCH_RESULTS = 200
MAX_SCANNED_FILES = 20_000
MAX_QUERY_LENGTH = 200
MAX_LINE_PREVIEW = 240


class SourceAccessError(Exception):
    """A request the source index refuses; ``status`` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class SourceRoot:
    """One directory of source the Copilot may read."""

    name: str
    path: Path
    kind: str  # "qdash" or "dependency"
    version: str | None = None
    revision: str | None = None
    revision_source: str | None = None
    dirty: bool | None = None
    excluded_prefixes: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class SearchMatch:
    """One hit of a source search."""

    root: str
    path: str
    line: int | None
    text: str | None


@dataclass(frozen=True)
class SourceFile:
    """A line range of one source file."""

    root: str
    path: str
    start_line: int
    end_line: int
    total_lines: int
    content: str
    truncated: bool


def _git_revision(path: Path) -> tuple[str | None, bool | None]:
    """The commit a checkout is at and whether it has local changes; (None, None) without git."""
    try:
        head = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "-C", str(path), "rev-parse", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if head.returncode != 0:
            return None, None
        status = subprocess.run(  # noqa: S603
            ["git", "-C", str(path), "status", "--porcelain", "--", "."],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        dirty = bool(status.stdout.strip()) if status.returncode == 0 else None
        return head.stdout.strip() or None, dirty
    except (OSError, subprocess.SubprocessError):
        return None, None


def _qdash_root() -> SourceRoot | None:
    """The QDash package source: ``QDASH_SOURCE_ROOT`` or the imported package's directory."""
    configured = os.getenv("QDASH_SOURCE_ROOT", "").strip()
    if configured:
        path = Path(configured)
    else:
        spec = importlib.util.find_spec("qdash")
        locations = list(spec.submodule_search_locations or []) if spec else []
        if not locations:
            return None
        path = Path(locations[0])
    if not path.is_dir():
        logger.warning("QDash source root %s is not a directory", path)
        return None

    revision = os.getenv("QDASH_SOURCE_REVISION", "").strip() or None
    revision_source = "QDASH_SOURCE_REVISION" if revision else None
    dirty: bool | None = None
    if revision is None:
        revision, dirty = _git_revision(path)
        revision_source = "git" if revision else None
    return SourceRoot(
        name="qdash",
        path=path.resolve(),
        kind="qdash",
        revision=revision,
        revision_source=revision_source,
        dirty=dirty,
        excluded_prefixes=QDASH_EXCLUDED_PREFIXES,
    )


def _distribution_for(module: str) -> importlib.metadata.Distribution | None:
    installed = {dist.metadata["Name"]: dist for dist in importlib.metadata.distributions()}
    names = importlib.metadata.packages_distributions().get(module, [module])
    return next((installed[name] for name in names if name in installed), None)


def _dependency_root(module: str) -> SourceRoot | None:
    """An installed dependency's package directory, with the version and VCS commit it records."""
    try:
        spec = importlib.util.find_spec(module)
    except (ImportError, ValueError):
        return None
    locations = list(spec.submodule_search_locations or []) if spec else []
    if not locations or not Path(locations[0]).is_dir():
        return None

    version: str | None = None
    revision: str | None = None
    revision_source: str | None = None
    dist = _distribution_for(module)
    if dist is not None:
        version = dist.version
        # PEP 610: a VCS install records the exact commit it was built from.
        direct_url = dist.read_text("direct_url.json")
        if direct_url:
            try:
                vcs = json.loads(direct_url).get("vcs_info") or {}
                revision = vcs.get("commit_id")
                revision_source = "direct_url.json" if revision else None
            except ValueError:
                pass
    return SourceRoot(
        name=module,
        path=Path(locations[0]).resolve(),
        kind="dependency",
        version=version,
        revision=revision,
        revision_source=revision_source,
    )


def _configured_dependencies() -> tuple[str, ...]:
    raw = os.getenv("QDASH_SOURCE_DEPENDENCIES")
    if raw is None:
        return DEFAULT_DEPENDENCIES
    return tuple(name.strip() for name in raw.split(",") if name.strip().isidentifier())


@lru_cache(maxsize=1)
def discover_roots() -> tuple[SourceRoot, ...]:
    """Every source root available to this API process, computed once."""
    roots: list[SourceRoot] = []
    qdash = _qdash_root()
    if qdash is not None:
        roots.append(qdash)
    for module in _configured_dependencies():
        if module == "qdash":
            continue
        root = _dependency_root(module)
        if root is not None:
            roots.append(root)
    return tuple(roots)


class SourceAccessService:
    """Search and read source files under a fixed set of roots."""

    def __init__(self, roots: tuple[SourceRoot, ...] | None = None) -> None:
        self._roots = roots

    @property
    def roots(self) -> tuple[SourceRoot, ...]:
        return self._roots if self._roots is not None else discover_roots()

    def missing_dependencies(self) -> list[str]:
        """Allowlisted dependencies that are not installed here, so the model can say so."""
        present = {root.name for root in self.roots}
        return [name for name in _configured_dependencies() if name not in present]

    def _root(self, name: str) -> SourceRoot:
        for root in self.roots:
            if root.name == name:
                return root
        known = ", ".join(root.name for root in self.roots) or "none"
        raise SourceAccessError(f"Unknown source root '{name}'. Available: {known}", status=404)

    @staticmethod
    def _allowed(root: SourceRoot, relative: PurePosixPath) -> bool:
        parts = relative.parts
        if not parts or any(part.startswith(".") or part in SKIPPED_DIRS for part in parts):
            return False
        text = relative.as_posix()
        if any(
            text == prefix or text.startswith(prefix + "/") for prefix in root.excluded_prefixes
        ):
            return False
        return relative.suffix in SOURCE_SUFFIXES

    def _resolve(self, root: SourceRoot, path: str) -> tuple[Path, PurePosixPath]:
        candidate = PurePosixPath(path.strip().replace("\\", "/").lstrip("/"))
        if not candidate.parts or ".." in candidate.parts:
            raise SourceAccessError("Path must be relative to the source root")
        resolved = (root.path / candidate).resolve()
        if not resolved.is_relative_to(root.path):
            raise SourceAccessError("Path is outside the source root")
        relative = PurePosixPath(resolved.relative_to(root.path).as_posix())
        if not self._allowed(root, relative):
            raise SourceAccessError(f"'{relative}' is not a readable source file", status=403)
        if not resolved.is_file():
            raise SourceAccessError(f"'{relative}' does not exist in '{root.name}'", status=404)
        return resolved, relative

    def locate(self, path: str) -> tuple[SourceRoot, str] | None:
        """Map a path as it appears in a traceback onto a root and a path inside it.

        A traceback from the workflow worker names files such as
        ``/app/qdash/workflow/engine/x.py`` or
        ``/app/.venv/lib/python3.11/site-packages/qubex/y.py``. Under
        ``site-packages`` the package is the segment that follows it. Elsewhere
        the QDash root wins over dependencies, because QDash's own tree has
        directories named after them (``workflow/calibtasks/qubex/``); within a
        root, the last segment with its name is used.
        """
        parts = PurePosixPath(path.strip().replace("\\", "/")).parts
        by_name = {root.name: root for root in self.roots}
        installed = [i for i, part in enumerate(parts) if part in INSTALL_DIRS]
        if installed:
            index = installed[-1] + 1
            root = by_name.get(parts[index]) if index + 1 < len(parts) else None
            if root is None:
                return None
            return root, PurePosixPath(*parts[index + 1 :]).as_posix()
        ordered = sorted(self.roots, key=lambda root: root.kind != "qdash")
        for root in ordered:
            for index in range(len(parts) - 2, -1, -1):
                if parts[index] == root.name:
                    return root, PurePosixPath(*parts[index + 1 :]).as_posix()
        return None

    def read(
        self,
        root_name: str | None,
        path: str,
        start_line: int = 1,
        end_line: int | None = None,
    ) -> SourceFile:
        """Read a line range of one file; at most ``MAX_READ_LINES`` lines."""
        if root_name:
            root = self._root(root_name)
            relative_path = path
        else:
            located = self.locate(path)
            if located is None:
                raise SourceAccessError(
                    "Could not tell which source root the path belongs to; pass root", status=404
                )
            root, relative_path = located
        resolved, relative = self._resolve(root, relative_path)
        if resolved.stat().st_size > MAX_FILE_BYTES:
            raise SourceAccessError(f"'{relative}' is too large to read", status=413)
        lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)
        start = max(1, start_line)
        requested_end = end_line if end_line is not None else start + MAX_READ_LINES - 1
        end = min(total, requested_end, start + MAX_READ_LINES - 1)
        # Cut short of the request, or (without an end) more of the file follows.
        truncated = end < min(total, requested_end) or (end_line is None and end < total)
        numbered = [f"{number:>5}  {lines[number - 1]}" for number in range(start, end + 1)]
        return SourceFile(
            root=root.name,
            path=relative.as_posix(),
            start_line=start,
            end_line=end if end >= start else start - 1,
            total_lines=total,
            content="\n".join(numbered),
            truncated=truncated,
        )

    def _iter_files(
        self, root: SourceRoot, prefix: str | None
    ) -> Iterator[tuple[Path, PurePosixPath]]:
        base = root.path
        if prefix:
            clean = PurePosixPath(prefix.strip().strip("/"))
            if ".." in clean.parts:
                raise SourceAccessError("path_prefix must stay inside the source root")
            base = (root.path / clean).resolve()
            if not base.is_relative_to(root.path):
                raise SourceAccessError("path_prefix must stay inside the source root")
            if base.is_file():
                relative = PurePosixPath(base.relative_to(root.path).as_posix())
                if self._allowed(root, relative):
                    yield base, relative
                return
            if not base.is_dir():
                return
        for directory, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(
                d for d in dirnames if not d.startswith(".") and d not in SKIPPED_DIRS
            )
            for filename in sorted(filenames):
                file_path = Path(directory) / filename
                relative = PurePosixPath(file_path.relative_to(root.path).as_posix())
                # Enforce exclusions on both the alias and its resolved target.
                resolved = file_path.resolve()
                if not resolved.is_relative_to(root.path):
                    continue
                target = PurePosixPath(resolved.relative_to(root.path).as_posix())
                if self._allowed(root, relative) and self._allowed(root, target):
                    yield resolved, relative

    def search(
        self,
        query: str,
        *,
        root_name: str | None = None,
        path_prefix: str | None = None,
        mode: str = "content",
        case_sensitive: bool = False,
        limit: int = 50,
    ) -> tuple[list[SearchMatch], bool]:
        """Literal search in file contents (``content``) or file paths (``path``).

        Returns the matches and whether the search stopped at a limit.
        """
        needle = query.strip()
        if not needle:
            raise SourceAccessError("query must not be empty")
        if len(needle) > MAX_QUERY_LENGTH:
            raise SourceAccessError(f"query must be at most {MAX_QUERY_LENGTH} characters")
        if mode not in {"content", "path"}:
            raise SourceAccessError("mode must be 'content' or 'path'")
        limit = max(1, min(limit, MAX_SEARCH_RESULTS))
        folded = needle if case_sensitive else needle.lower()
        roots = [self._root(root_name)] if root_name else list(self.roots)

        matches: list[SearchMatch] = []
        scanned = 0
        for root in roots:
            for file_path, relative in self._iter_files(root, path_prefix):
                scanned += 1
                if scanned > MAX_SCANNED_FILES:
                    return matches, True
                rel = relative.as_posix()
                if mode == "path":
                    haystack = rel if case_sensitive else rel.lower()
                    if folded in haystack:
                        matches.append(SearchMatch(root=root.name, path=rel, line=None, text=None))
                        if len(matches) >= limit:
                            return matches, True
                    continue
                try:
                    if file_path.stat().st_size > MAX_FILE_BYTES:
                        continue
                    text = file_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if folded not in (text if case_sensitive else text.lower()):
                    continue
                for number, line in enumerate(text.splitlines(), start=1):
                    if folded in (line if case_sensitive else line.lower()):
                        matches.append(
                            SearchMatch(
                                root=root.name,
                                path=rel,
                                line=number,
                                text=line.strip()[:MAX_LINE_PREVIEW],
                            )
                        )
                        if len(matches) >= limit:
                            return matches, True
        return matches, False
