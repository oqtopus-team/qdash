"""Deterministic filesystem swaps for path-race regression tests.

The helpers replace a directory with a symbolic link at a chosen point of a
traversal, without timing: right after a watched directory has been listed.
Listing is hooked through ``os.listdir`` and ``os.scandir``, which every
traversal in the services under test uses, by path or by descriptor.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest


def swap_dir_for_link(directory: Path, target: Path) -> Callable[[], None]:
    """Return a callback that moves ``directory`` aside and links its name to ``target``."""

    def swap() -> None:
        directory.rename(directory.with_name(f"{directory.name}.moved"))
        directory.symlink_to(target, target_is_directory=True)

    return swap


def swap_after_listing(
    monkeypatch: pytest.MonkeyPatch,
    watched: list[Path],
    swap: Callable[[], None],
) -> list[bool]:
    """Run ``swap`` once, right after the first listing of any directory in ``watched``.

    Returns a one-element list that becomes ``[True]`` when the swap ran.
    """
    watched_ids = {_identity(os.stat(path)) for path in watched}
    swapped = [False]
    real_listdir = os.listdir
    real_scandir = os.scandir

    def after_listing(listed: Any) -> None:
        if swapped[0]:
            return
        try:
            listed_stat = os.fstat(listed) if isinstance(listed, int) else os.stat(listed)
        except (OSError, TypeError):
            return
        if _identity(listed_stat) in watched_ids:
            swapped[0] = True
            swap()

    def listdir(path: Any = ".") -> list[str]:
        names = real_listdir(path)
        after_listing(path)
        return names

    def scandir(path: Any = ".") -> _Listing:
        with real_scandir(path) as entries:
            listing = _Listing(entries)
        after_listing(path)
        return listing

    monkeypatch.setattr(os, "listdir", listdir)
    monkeypatch.setattr(os, "scandir", scandir)
    return swapped


class _Listing(list[os.DirEntry[str]]):
    """A materialized ``os.scandir`` result that still works as a context manager."""

    def __enter__(self) -> _Listing:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def _identity(file_stat: os.stat_result) -> tuple[int, int]:
    return (file_stat.st_dev, file_stat.st_ino)
