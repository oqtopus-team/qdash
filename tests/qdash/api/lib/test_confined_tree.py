import os
from pathlib import Path

import pytest

from qdash.api.lib.confined_tree import ConfinedTree, NotRegularFileError


def _open_fd_count() -> int:
    # /dev/fd lists the descriptors of the current process on Linux and macOS.
    return len(os.listdir("/dev/fd"))


@pytest.fixture
def tree_dir(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "a" / "deep").mkdir(parents=True)
    (root / "a" / "one.txt").write_text("one", encoding="utf-8")
    (root / "a" / "deep" / "two.txt").write_text("two", encoding="utf-8")
    (root / "b").mkdir()
    (root / "b" / "three.txt").write_text("three", encoding="utf-8")
    (root / "empty").mkdir()
    return root


def _read(entry_fd: int) -> str:
    with open(entry_fd, encoding="utf-8", closefd=False) as source:
        return source.read()


def test_walk_yields_directories_and_files_read_from_descriptors(tree_dir: Path) -> None:
    (tree_dir / "b" / "alias.txt").symlink_to(tree_dir / "a" / "one.txt")

    with ConfinedTree(tree_dir) as tree:
        seen = {
            "/".join(entry.parts): None if entry.fd is None else _read(entry.fd)
            for entry in tree.walk()
        }

    assert seen == {
        "a": None,
        "a/one.txt": "one",
        "a/deep": None,
        "a/deep/two.txt": "two",
        "b": None,
        "b/alias.txt": "one",
        "b/three.txt": "three",
        "empty": None,
    }


def test_walk_include_filters_before_opening(tree_dir: Path) -> None:
    with ConfinedTree(tree_dir) as tree:
        parts = [
            entry.parts
            for entry in tree.walk(include=lambda name, is_dir: is_dir or name == "two.txt")
            if not entry.is_dir
        ]

    assert parts == [("a", "deep", "two.txt")]


def test_walk_closes_descriptors_when_stopped_early(tree_dir: Path) -> None:
    baseline = _open_fd_count()

    with ConfinedTree(tree_dir) as tree:
        walk = tree.walk()
        first_file = next(entry for entry in walk if entry.fd is not None)
        assert _read(first_file.fd or -1) == "one"
        walk.close()

    assert _open_fd_count() == baseline


def test_walk_closes_descriptors_when_the_consumer_fails(tree_dir: Path) -> None:
    baseline = _open_fd_count()

    with pytest.raises(RuntimeError, match="consumer failed"), ConfinedTree(tree_dir) as tree:
        for entry in tree.walk():
            if entry.fd is not None:
                raise RuntimeError("consumer failed")

    assert _open_fd_count() == baseline


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_walk_raises_or_skips_unreadable_entries_without_leaking(tree_dir: Path) -> None:
    unreadable = tree_dir / "b" / "three.txt"
    unreadable.chmod(0)
    baseline = _open_fd_count()
    try:
        with pytest.raises(PermissionError), ConfinedTree(tree_dir) as tree:
            list(tree.walk())
        assert _open_fd_count() == baseline

        with ConfinedTree(tree_dir) as tree:
            files = [entry.parts for entry in tree.walk(skip_unreadable=True) if entry.fd]
        assert ("b", "three.txt") not in files
        assert ("a", "one.txt") in files
        assert _open_fd_count() == baseline
    finally:
        unreadable.chmod(0o644)


def test_root_parts_refuse_a_link_and_leave_no_descriptor(tree_dir: Path) -> None:
    (tree_dir / "link").symlink_to(tree_dir / "a", target_is_directory=True)
    baseline = _open_fd_count()

    with pytest.raises(OSError):
        ConfinedTree(tree_dir, ("link",))

    assert _open_fd_count() == baseline


def test_open_file_refuses_links_in_any_component(tree_dir: Path) -> None:
    (tree_dir / "dir-link").symlink_to(tree_dir / "a", target_is_directory=True)
    (tree_dir / "file-link.txt").symlink_to(tree_dir / "a" / "one.txt")

    with ConfinedTree(tree_dir) as tree:
        with pytest.raises(OSError):
            tree.open_file(("dir-link", "one.txt"))
        with pytest.raises(OSError):
            tree.open_file(("file-link.txt",))
        with pytest.raises(NotRegularFileError):
            tree.open_file(("a",))
        with pytest.raises(ValueError):
            tree.open_file(("..", "root", "a", "one.txt"))
