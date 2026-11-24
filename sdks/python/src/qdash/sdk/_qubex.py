"""The Qubex configuration a device gateway runs with: the config tree and the calibration note.

``QDash.qubex.download_config("./qubex-config")`` exports the server's Qubex configuration tree
and the project's latest calibration note into a local directory, such as the ``qubex-config``
directory a device gateway reads. Everything is fetched and checked before the first file is
written; the archive is unpacked member by member, never with ``extractall``.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import secrets
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from qdash.sdk._http import api_errors, read_options
from qdash.sdk._runs import _file_content
from qdash.sdk.errors import QDashTransportError

if TYPE_CHECKING:
    from qdash.sdk._config import QDashConfig
    from qdash.sdk._generated.client import QDashApi
    from qdash.sdk._generated.core.request_options import RequestOptions
    from qdash.sdk._generated.types.calibration_note_response import CalibrationNoteResponse

CALIBRATION_NOTE_FILE = "calib_note.json"


class UnsafeArchiveError(QDashTransportError):
    """The configuration archive has a member the SDK will not write, such as ``../x``."""


def _unsafe(message: str) -> UnsafeArchiveError:
    return UnsafeArchiveError(f"refusing the configuration archive: {message}")


def _member_parts(name: str) -> tuple[str, ...]:
    """The relative path of an archive member, or an error for a path that could escape."""
    if "\\" in name:
        raise _unsafe(f"member {name!r} contains a backslash")
    if name.startswith("/"):
        raise _unsafe(f"member {name!r} is an absolute path")
    parts = tuple(part for part in PurePosixPath(name).parts if part != ".")
    if any(part == ".." for part in parts):
        raise _unsafe(f"member {name!r} refers to a parent directory")
    if parts and ":" in parts[0]:
        raise _unsafe(f"member {name!r} names a drive")
    if any("\x00" in part for part in parts):
        raise _unsafe(f"member {name!r} contains a NUL character")
    return parts


def _plan(
    archive: zipfile.ZipFile, *, skip: tuple[str, ...] | None
) -> tuple[set[tuple[str, ...]], dict[tuple[str, ...], zipfile.ZipInfo]]:
    """The directories and files the archive holds, after rejecting unsafe members.

    ``skip`` is a file path left out because the caller writes it itself.
    """
    directories: set[tuple[str, ...]] = set()
    files: dict[tuple[str, ...], zipfile.ZipInfo] = {}
    seen: set[tuple[str, ...]] = set()
    spellings: dict[tuple[str, ...], tuple[str, ...]] = {}

    def register(parts: tuple[str, ...]) -> None:
        # Check every component, including implicit parents and the generated note path.
        # Reject on all platforms so an export has the same layout on macOS and Linux.
        for depth in range(1, len(parts) + 1):
            prefix = parts[:depth]
            key = tuple(part.casefold() for part in prefix)
            previous = spellings.setdefault(key, prefix)
            if previous != prefix:
                raise _unsafe(
                    f"paths {'/'.join(previous)!r} and {'/'.join(prefix)!r} differ only in case"
                )

    if skip is not None:
        register(skip)
    for info in archive.infolist():
        parts = _member_parts(info.filename)
        register(parts)
        mode = info.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if info.is_dir():
            if kind not in (0, stat.S_IFDIR):
                raise _unsafe(f"member {info.filename!r} is not a regular directory")
            if parts:
                directories.add(parts)
            continue
        if kind not in (0, stat.S_IFREG):
            raise _unsafe(f"member {info.filename!r} is a link or special file")
        if not parts:
            raise _unsafe(f"member {info.filename!r} has no file name")
        if parts in seen:
            raise _unsafe(f"member {info.filename!r} appears more than once")
        seen.add(parts)
        if parts == skip:
            continue
        files[parts] = info
    for parts in list(files) + list(directories):
        for depth in range(1, len(parts)):
            directories.add(parts[:depth])
    planned = list(files) + ([skip] if skip is not None else [])
    clashes = sorted("/".join(parts) for parts in planned if parts in directories)
    if clashes:
        raise _unsafe(f"{clashes[0]!r} is both a file and a directory")
    return directories, files


def _check_destination(
    root: Path,
    directories: set[tuple[str, ...]],
    files: list[tuple[str, ...]],
    *,
    overwrite: bool,
) -> None:
    """Raise before writing when an existing path would block or redirect the export."""
    existing: list[str] = []
    for parts in sorted(directories):
        path = root.joinpath(*parts)
        if path.is_symlink():
            raise FileExistsError(f"{path} is a symbolic link; the SDK does not write through it")
        if path.exists() and not path.is_dir():
            raise FileExistsError(f"{path} exists and is not a directory")
    for parts in files:
        path = root.joinpath(*parts)
        if path.is_symlink():
            raise FileExistsError(f"{path} is a symbolic link; the SDK does not write through it")
        if path.is_dir():
            raise IsADirectoryError(f"{path} is a directory; the archive has a file there")
        if path.exists():
            if not path.is_file():
                raise FileExistsError(f"{path} exists and is not a regular file")
            existing.append(str(path))
    if existing and not overwrite:
        shown = ", ".join(existing[:5]) + (", ..." if len(existing) > 5 else "")
        raise FileExistsError(
            f"{len(existing)} file(s) exist in {root}: {shown}; pass overwrite=True to replace them"
        )


def _write_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path) -> None:
    with archive.open(info) as source, target.open("xb") as sink:
        shutil.copyfileobj(source, sink)


def _sibling(target: Path) -> Path:
    """An unused hidden name beside ``target``, for a file or directory being assembled."""
    return target.with_name(f".{target.name}.{secrets.token_hex(8)}.partial")


def _commit_file(target: Path, write: Any, *, overwrite: bool) -> None:
    """Write through ``write(path)`` to a new file beside ``target``, then commit it as ``target``.

    With ``overwrite``, the new file atomically replaces ``target``. Without it, the new file is
    hard-linked as ``target``, which fails with ``FileExistsError`` and leaves ``target`` as it
    is when ``target`` already exists, even if it appeared after the destination was checked;
    a file system without hard links raises its ``OSError`` instead of falling back to a check
    and a replace. The new file is created like any other, so it gets the default permissions.
    """
    temporary = _sibling(target)
    try:
        write(temporary)
        if overwrite:
            os.replace(temporary, target)
            return
        os.link(temporary, target)
    except BaseException:
        # Do not let a failed cleanup hide the error that stopped the write.
        with contextlib.suppress(OSError):
            temporary.unlink(missing_ok=True)
        raise
    # ``target`` is committed; a failure to remove the extra name propagates so that a stray
    # hidden file is reported rather than left silently.
    temporary.unlink()


class Qubex:
    """The Qubex configuration of the server, reached as ``QDash.qubex``."""

    def __init__(self, api: QDashApi, config: QDashConfig) -> None:
        self._api = api
        self._config = config

    def calibration_note(self) -> CalibrationNoteResponse:
        """The latest calibration note of the session's project, as the server stores it.

        ``note`` is the content Qubex reads as ``calib_note.json``. Raises
        ``QDashNotFoundError`` when the project has none.
        """
        with api_errors():
            return self._api.calibration.get_calibration_note(
                request_options=read_options(self._config)
            )

    def _archive(self) -> bytes:
        options: RequestOptions = read_options(self._config)
        options["additional_headers"] = {"Accept": "application/zip, */*"}
        with api_errors():
            # "." is the root of the configuration tree the server is configured with.
            raw = self._api.file.with_raw_response.download_zip_file(
                path=".", request_options=options
            )
        content = _file_content(raw.response)
        if not zipfile.is_zipfile(io.BytesIO(content)):
            raise QDashTransportError(
                f"{raw.response.status_code}: the configuration download is not a ZIP archive",
                status_code=raw.response.status_code,
                headers=dict(raw.response.headers),
            )
        return content

    def download_config(
        self,
        destination: str | os.PathLike[str],
        *,
        include_calibration_note: bool = True,
        overwrite: bool = False,
    ) -> Path:
        """Export the Qubex configuration tree into the directory ``destination``.

        Downloads the server's whole configuration tree (the root the server is configured
        with, not a path on this machine) as a ZIP archive and unpacks it into
        ``destination``, keeping the archive's layout, including any ``.git`` directory it
        holds. Nothing in it is executed. With ``include_calibration_note``, the project's
        latest calibration note is written as ``calib_note.json`` at the top of the
        directory, as JSON of the note's ``note`` field; it replaces a ``calib_note.json``
        that the archive holds. The note and the archive are two separate reads, not one
        snapshot of the server.

        ``destination`` may be missing, and is then created, or an existing directory; its
        parent must exist. Files of the archive that already exist raise
        ``FileExistsError`` unless ``overwrite`` is true; files the archive does not have are
        never removed. Members that would escape the directory (absolute paths, ``..``,
        drive letters, backslashes), links and other special files, duplicate or case-alias paths and
        file-or-directory clashes raise :class:`UnsafeArchiveError`, and a symbolic link
        among the paths to write raises ``FileExistsError``.

        The note and the archive are fetched and checked, and the destination is checked for
        conflicts, before anything is written, so a failed request, a missing note
        (``QDashNotFoundError``), a response that is not a ZIP archive or an unsafe archive
        leaves the file system unchanged. A new ``destination`` is assembled in a temporary
        directory beside it and renamed into place. Into an existing directory, each file is
        committed atomically: with ``overwrite`` it replaces the file there, and without it a
        file that appeared after the check is kept and raises ``FileExistsError``. A failure
        part way, including such a file, can leave some files written and others not. Returns
        ``destination``.
        """
        root = Path(destination)
        if root.is_symlink() and not root.is_dir():
            raise FileExistsError(f"{root} is a symbolic link that does not point to a directory")
        if root.exists() and not root.is_dir():
            raise NotADirectoryError(f"{root} exists and is not a directory")
        if not root.exists() and not root.parent.is_dir():
            raise FileNotFoundError(f"{root.parent} does not exist; create it first")

        note_bytes: bytes | None = None
        if include_calibration_note:
            note = self.calibration_note().note
            text = json.dumps(note, indent=2, ensure_ascii=False) + "\n"
            note_bytes = text.encode("utf-8")
        content = self._archive()

        note_parts = (CALIBRATION_NOTE_FILE,) if note_bytes is not None else None
        try:
            opened = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as error:
            raise QDashTransportError(
                f"the configuration archive cannot be read: {error}"
            ) from None
        with opened as archive:
            directories, files = _plan(archive, skip=note_parts)
            try:
                broken = archive.testzip()
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
                raise _unsafe(f"the archive cannot be read: {error}") from None
            if broken is not None:
                raise _unsafe(f"member {broken!r} is corrupt")
            targets = list(files) + ([note_parts] if note_parts is not None else [])
            if root.exists():
                _check_destination(root, directories, targets, overwrite=overwrite)
                self._write_into(root, archive, directories, files, note_bytes, overwrite=overwrite)
            else:
                self._write_new(root, archive, directories, files, note_bytes)
        return root

    @staticmethod
    def _write_new(
        root: Path,
        archive: zipfile.ZipFile,
        directories: set[tuple[str, ...]],
        files: dict[tuple[str, ...], zipfile.ZipInfo],
        note: bytes | None,
    ) -> None:
        staging = _sibling(root)
        staging.mkdir()
        try:
            for parts in sorted(directories):
                staging.joinpath(*parts).mkdir(exist_ok=True)
            for parts, info in files.items():
                _write_member(archive, info, staging.joinpath(*parts))
            if note is not None:
                staging.joinpath(CALIBRATION_NOTE_FILE).write_bytes(note)
            # Fails, leaving nothing behind, when a file or a non-empty directory appeared.
            staging.rename(root)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    @staticmethod
    def _write_into(
        root: Path,
        archive: zipfile.ZipFile,
        directories: set[tuple[str, ...]],
        files: dict[tuple[str, ...], zipfile.ZipInfo],
        note: bytes | None,
        *,
        overwrite: bool,
    ) -> None:
        for parts in sorted(directories):
            root.joinpath(*parts).mkdir(exist_ok=True)
        for parts, info in files.items():
            _commit_file(
                root.joinpath(*parts),
                lambda path, info=info: _write_member(archive, info, path),
                overwrite=overwrite,
            )
        if note is not None:
            _commit_file(
                root / CALIBRATION_NOTE_FILE,
                lambda path: path.write_bytes(note),
                overwrite=overwrite,
            )
