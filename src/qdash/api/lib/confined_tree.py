"""Read a directory tree through descriptors without leaving it.

Checking a path with ``Path.resolve()`` and then opening it by name races with a
concurrent swap of any path component for a symbolic link. ``ConfinedTree``
opens its root directory once and reaches every entry below it relative to that
descriptor, one component at a time with ``O_NOFOLLOW``. A component that is a
link when it is opened is refused, so a directory swapped for a link after it
was listed cannot lead outside the tree, and a file is read from the descriptor
that was checked.

Directory links are never followed. A file link is followed only when its
target resolves to a regular file inside the tree; the target is then opened
through the same no-follow traversal from the root.
"""

from __future__ import annotations

import errno
import logging
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from types import TracebackType

logger = logging.getLogger(__name__)

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
# O_NONBLOCK keeps a FIFO from blocking the open; it is refused as non-regular.
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC

# The entry is no longer a confined file or directory: a link (ELOOP, or EMLINK
# on FreeBSD), a component that is not a directory, or an entry that vanished.
_NOT_CONFINED_ERRNOS = frozenset({errno.ELOOP, errno.EMLINK, errno.ENOTDIR, errno.ENOENT})


class NotRegularFileError(OSError):
    """Raised when an entry that should be a regular file is something else."""


@dataclass(frozen=True)
class TreeEntry:
    """A directory or regular file found by :meth:`ConfinedTree.walk`."""

    parts: tuple[str, ...]
    """Path components relative to the walk start."""
    stat: os.stat_result
    """Status of the opened object (the link target for a followed file link)."""
    fd: int | None = None
    """Read-only descriptor of a file; ``None`` for a directory.

    The walk owns the descriptor and closes it when it advances.
    """

    @property
    def is_dir(self) -> bool:
        """Whether the entry is a directory."""
        return self.fd is None


class ConfinedTree:
    """A directory tree opened by descriptor; use it as a context manager.

    Parameters
    ----------
    anchor : Path
        Trusted directory to start from. Links in this path are followed.
    root_parts : tuple[str, ...]
        Components below ``anchor`` that lead to the tree root. They are opened
        without following links, so a component swapped for a link is refused.

    """

    def __init__(self, anchor: Path, root_parts: tuple[str, ...] = ()) -> None:
        anchor_path = os.path.realpath(anchor)
        anchor_fd = os.open(anchor_path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self._fd = self._descend(anchor_fd, root_parts)
        self.root = Path(anchor_path, *root_parts)

    def close(self) -> None:
        """Close the root descriptor."""
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def __enter__(self) -> ConfinedTree:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def lstat(self, parts: tuple[str, ...]) -> os.stat_result:
        """Return the status of an entry without following a final link."""
        if not parts:
            return os.fstat(self._fd)
        dir_fd = self._open_dir(parts[:-1])
        try:
            return os.stat(self._check_part(parts[-1]), dir_fd=dir_fd, follow_symlinks=False)
        finally:
            os.close(dir_fd)

    def open_file(self, parts: tuple[str, ...]) -> int:
        """Open a regular file below the root; the caller closes the descriptor.

        Raises
        ------
        OSError
            When a component is a link or not a directory, or the entry is
            missing or not a regular file (:class:`NotRegularFileError`).

        """
        if not parts:
            raise NotRegularFileError(errno.EISDIR, "Not a regular file", str(self.root))
        dir_fd = self._open_dir(parts[:-1])
        try:
            return self._open_regular(dir_fd, parts[-1])
        finally:
            os.close(dir_fd)

    def walk(
        self,
        start: tuple[str, ...] = (),
        *,
        include: Callable[[str, bool], bool] | None = None,
        skip_unreadable: bool = False,
    ) -> Generator[TreeEntry, None, None]:
        """Yield the directories and regular files below ``start``.

        Each directory is yielded before its contents; ``start`` itself is not
        yielded. Entries of one directory come in name order. Links,
        special files, and entries that change type or vanish during the walk
        are skipped and logged.

        Parameters
        ----------
        start : tuple[str, ...]
            Components of the directory to walk, relative to the root.
        include : Callable[[str, bool], bool] | None
            Called with an entry name and whether it is a directory; entries
            it rejects are skipped silently, before they are opened.
        skip_unreadable : bool
            Skip and log entries that cannot be opened for another reason,
            such as missing permission, instead of raising.

        Raises
        ------
        OSError
            When ``start`` cannot be opened as a directory, or, unless
            ``skip_unreadable`` is set, when an entry cannot be read.

        """
        pending: list[tuple[str, ...]] = [()]
        while pending:
            relative = pending.pop()
            dir_parts = (*start, *relative)
            try:
                dir_fd = self._open_dir(dir_parts)
            except OSError as exc:
                if not relative:
                    raise
                self._skip(exc, dir_parts, skip_unreadable)
                continue
            try:
                if relative:
                    yield TreeEntry(relative, os.fstat(dir_fd))
                subdirs: list[tuple[str, ...]] = []
                for name in sorted(os.listdir(dir_fd)):
                    entry_parts = (*dir_parts, name)
                    try:
                        entry_stat = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
                        if stat.S_ISDIR(entry_stat.st_mode):
                            if include is None or include(name, True):
                                subdirs.append((*relative, name))
                            continue
                        if include is not None and not include(name, False):
                            continue
                        file_fd = self._open_entry_file(dir_fd, dir_parts, name, entry_stat)
                    except OSError as exc:
                        self._skip(exc, entry_parts, skip_unreadable)
                        continue
                    if file_fd is None:
                        continue
                    try:
                        yield TreeEntry((*relative, name), os.fstat(file_fd), file_fd)
                    finally:
                        os.close(file_fd)
                pending.extend(reversed(subdirs))
            finally:
                os.close(dir_fd)

    def _open_entry_file(
        self, dir_fd: int, dir_parts: tuple[str, ...], name: str, entry_stat: os.stat_result
    ) -> int | None:
        """Open a listed non-directory entry as a regular file, or return ``None``."""
        if stat.S_ISLNK(entry_stat.st_mode):
            target = self._resolve_link(dir_fd, dir_parts, name)
            if target is None:
                logger.warning(
                    "Skipping link outside %s: %s", self.root, self._display(dir_parts, name)
                )
                return None
            return self.open_file(target)
        if stat.S_ISREG(entry_stat.st_mode):
            return self._open_regular(dir_fd, name)
        logger.warning("Skipping special file: %s", self._display(dir_parts, name))
        return None

    def _resolve_link(
        self, dir_fd: int, dir_parts: tuple[str, ...], name: str
    ) -> tuple[str, ...] | None:
        """Return the root-relative components of a link target, or ``None`` outside.

        The result only names the candidate; :meth:`open_file` still opens it
        without following links, so a loop or a swapped component is refused.
        """
        target = os.readlink(name, dir_fd=dir_fd)
        # realpath() does not raise on a link loop; the no-follow open refuses it.
        canonical = os.path.realpath(os.path.join(self.root, *dir_parts, target))
        relative = os.path.relpath(canonical, self.root)
        if (
            relative == os.curdir
            or relative == os.pardir
            or relative.startswith(os.pardir + os.sep)
        ):
            return None
        return Path(relative).parts

    def _open_dir(self, parts: tuple[str, ...]) -> int:
        return self._descend(os.open(os.curdir, _DIR_FLAGS, dir_fd=self._fd), parts)

    @classmethod
    def _descend(cls, fd: int, parts: tuple[str, ...]) -> int:
        """Open ``parts`` below ``fd`` without following links; always consumes ``fd``."""
        try:
            for part in parts:
                parent_fd, fd = fd, os.open(cls._check_part(part), _DIR_FLAGS, dir_fd=fd)
                os.close(parent_fd)
        except BaseException:
            os.close(fd)
            raise
        return fd

    @classmethod
    def _open_regular(cls, dir_fd: int, name: str) -> int:
        fd = os.open(cls._check_part(name), _FILE_FLAGS, dir_fd=dir_fd)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise NotRegularFileError(errno.EINVAL, "Not a regular file", name)
        except BaseException:
            os.close(fd)
            raise
        return fd

    @staticmethod
    def _check_part(name: str) -> str:
        if name in {"", os.curdir, os.pardir} or os.sep in name or "\0" in name:
            raise ValueError(f"Invalid path component: {name!r}")
        return name

    def _display(self, dir_parts: tuple[str, ...], name: str) -> Path:
        return self.root.joinpath(*dir_parts, name)

    def _skip(self, exc: OSError, parts: tuple[str, ...], skip_unreadable: bool) -> None:
        if not (
            skip_unreadable
            or isinstance(exc, NotRegularFileError)
            or exc.errno in _NOT_CONFINED_ERRNOS
        ):
            raise exc
        logger.warning("Skipping %s: %s", self.root.joinpath(*parts), exc.strerror or exc)
