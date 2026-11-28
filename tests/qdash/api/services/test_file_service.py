import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from git import Repo

from qdash.api.services.file_service import FileService
from tests.qdash.api._fs_swaps import swap_after_listing, swap_dir_for_link


def test_get_file_content_includes_saved_git_diff_base(tmp_path: Path) -> None:
    config_dir = tmp_path / "qubex-config"
    config_dir.mkdir()
    file_path = config_dir / "settings.yaml"
    file_path.write_text("name: before\n", encoding="utf-8")
    repo = Repo.init(config_dir)
    repo.index.add(["settings.yaml"])
    repo.index.commit("Initial config")
    file_path.write_text("name: after\n", encoding="utf-8")

    result = FileService(config_base_path=config_dir).get_file_content("settings.yaml")

    assert result["content"] == "name: after\n"
    assert result["base_content"] == "name: before\n"
    assert result["is_saved_change"] is True


def test_get_file_content_marks_untracked_file_as_saved_change(tmp_path: Path) -> None:
    config_dir = tmp_path / "qubex-config"
    config_dir.mkdir()
    repo = Repo.init(config_dir)
    tracked_file = config_dir / "tracked.yaml"
    tracked_file.write_text("tracked: true\n", encoding="utf-8")
    repo.index.add(["tracked.yaml"])
    repo.index.commit("Initial config")
    (config_dir / "new.yaml").write_text("new: true\n", encoding="utf-8")

    result = FileService(config_base_path=config_dir).get_file_content("new.yaml")

    assert result["base_content"] == ""
    assert result["is_saved_change"] is True


def test_uses_config_path_from_environment(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "qubex-config"
    config_dir.mkdir()
    (config_dir / "settings.yaml").write_text("name: test\n", encoding="utf-8")
    monkeypatch.setenv("CONFIG_PATH", str(config_dir))

    service = FileService()

    assert service._base_path == config_dir.resolve()
    assert [node.name for node in service.get_file_tree()] == ["settings.yaml"]


def test_falls_back_to_container_qubex_config_path(monkeypatch) -> None:
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.setattr("qdash.common.config.path_resolver.QUBEX_CONFIG_BASE", Path("/tmp"))

    service = FileService()

    assert service._base_path == Path("/tmp")


def test_falls_back_to_repo_local_config_path_when_container_path_is_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.chdir(Path(__file__).parents[4])
    monkeypatch.setattr(
        "qdash.common.config.path_resolver.QUBEX_CONFIG_BASE", Path("/missing/qubex-config")
    )

    service = FileService()

    assert service._base_path == (Path.cwd() / "config/qubex-config").resolve()


def test_explicit_config_base_path_takes_precedence(monkeypatch, tmp_path: Path) -> None:
    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "from-env"))

    service = FileService(config_base_path=explicit_dir)

    assert service._base_path == explicit_dir


def test_download_zip_file_maps_config_parent_to_qubex_config(tmp_path: Path) -> None:
    config_parent = tmp_path / "config"
    config_dir = config_parent / "qubex-config"
    sibling_dir = config_parent / "other-config"
    target_file = config_dir / "64Qv3" / "config" / "wiring.yaml"
    sibling_file = sibling_dir / "secret.yaml"
    target_file.parent.mkdir(parents=True)
    sibling_file.parent.mkdir(parents=True)
    target_file.write_text("wiring: test\n", encoding="utf-8")
    sibling_file.write_text("secret: true\n", encoding="utf-8")

    service = FileService(config_base_path=config_dir)

    response = service.download_zip_file(str(config_parent))

    try:
        assert response.filename is not None
        assert response.filename.startswith("qubex-config_")
        with zipfile.ZipFile(response.path) as archive:
            file_names = [name for name in archive.namelist() if not name.endswith("/")]
            assert file_names == ["64Qv3/config/wiring.yaml"]
            assert archive.read("64Qv3/config/wiring.yaml").decode() == "wiring: test\n"
    finally:
        shutil.rmtree(Path(response.path).parent, ignore_errors=True)


def test_download_zip_file_preserves_tree_for_relative_root(tmp_path: Path) -> None:
    """Zipping the relative root (".") keeps each file's chip-relative directory tree."""
    config_dir = tmp_path / "qubex-config"
    first_file = config_dir / "64Q" / "config" / "wiring.yaml"
    second_file = config_dir / "16Qtest" / "config" / "chip.yaml"
    first_file.parent.mkdir(parents=True)
    second_file.parent.mkdir(parents=True)
    first_file.write_text("wiring: test\n", encoding="utf-8")
    second_file.write_text("chip: test\n", encoding="utf-8")

    response = FileService(config_base_path=config_dir).download_zip_file(".")

    try:
        with zipfile.ZipFile(response.path) as archive:
            file_names = sorted(name for name in archive.namelist() if not name.endswith("/"))
            assert file_names == ["16Qtest/config/chip.yaml", "64Q/config/wiring.yaml"]
    finally:
        shutil.rmtree(Path(response.path).parent, ignore_errors=True)


def test_download_zip_file_rejects_paths_outside_qubex_config(tmp_path: Path) -> None:
    config_dir = tmp_path / "config" / "qubex-config"
    outside_dir = tmp_path / "outside"
    config_dir.mkdir(parents=True)
    outside_dir.mkdir()

    service = FileService(config_base_path=config_dir)

    with pytest.raises(HTTPException) as exc_info:
        service.download_zip_file(str(outside_dir))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Path outside config directory"


def _archived_files(response) -> dict[str, bytes]:
    with zipfile.ZipFile(response.path) as archive:
        return {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}


def test_download_zip_file_skips_file_link_outside_config(tmp_path: Path) -> None:
    config_dir = tmp_path / "qubex-config"
    (config_dir / "64Q").mkdir(parents=True)
    (config_dir / "64Q" / "chip.yaml").write_text("chip: test\n", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret\n", encoding="utf-8")
    (config_dir / "64Q" / "leak.yaml").symlink_to(secret)

    response = FileService(config_base_path=config_dir).download_zip_file(".")

    try:
        files = _archived_files(response)
        assert files == {"64Q/chip.yaml": b"chip: test\n"}
        assert all(b"top secret" not in content for content in files.values())
    finally:
        shutil.rmtree(Path(response.path).parent, ignore_errors=True)


def test_download_zip_file_does_not_follow_directory_links(tmp_path: Path) -> None:
    config_dir = tmp_path / "qubex-config"
    (config_dir / "64Q").mkdir(parents=True)
    (config_dir / "64Q" / "chip.yaml").write_text("chip: test\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("top secret\n", encoding="utf-8")
    (config_dir / "outside-link").symlink_to(outside, target_is_directory=True)
    # A link back to an ancestor would loop forever if directory links were followed.
    (config_dir / "64Q" / "loop").symlink_to(config_dir, target_is_directory=True)

    response = FileService(config_base_path=config_dir).download_zip_file(".")

    try:
        assert _archived_files(response) == {"64Q/chip.yaml": b"chip: test\n"}
    finally:
        shutil.rmtree(Path(response.path).parent, ignore_errors=True)


def test_download_zip_file_keeps_file_link_inside_config(tmp_path: Path) -> None:
    config_dir = tmp_path / "qubex-config"
    (config_dir / "shared").mkdir(parents=True)
    (config_dir / "64Q").mkdir()
    (config_dir / "shared" / "params.yaml").write_text("p: 1\n", encoding="utf-8")
    (config_dir / "64Q" / "params.yaml").symlink_to(config_dir / "shared" / "params.yaml")
    (config_dir / "empty").mkdir()

    response = FileService(config_base_path=config_dir).download_zip_file(".")

    try:
        assert _archived_files(response) == {
            "64Q/params.yaml": b"p: 1\n",
            "shared/params.yaml": b"p: 1\n",
        }
        with zipfile.ZipFile(response.path) as archive:
            assert "empty/" in archive.namelist()
            assert archive.testzip() is None
    finally:
        shutil.rmtree(Path(response.path).parent, ignore_errors=True)


def test_download_zip_file_rejects_single_file_link_outside_config(tmp_path: Path) -> None:
    config_dir = tmp_path / "qubex-config"
    config_dir.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret\n", encoding="utf-8")
    (config_dir / "leak.yaml").symlink_to(secret)

    with pytest.raises(HTTPException) as exc_info:
        FileService(config_base_path=config_dir).download_zip_file("leak.yaml")

    assert exc_info.value.status_code == 400


def test_download_zip_file_single_file_keeps_name(tmp_path: Path) -> None:
    config_dir = tmp_path / "qubex-config"
    (config_dir / "64Q").mkdir(parents=True)
    (config_dir / "64Q" / "chip.yaml").write_text("chip: test\n", encoding="utf-8")

    response = FileService(config_base_path=config_dir).download_zip_file("64Q/chip.yaml")

    try:
        assert response.filename is not None
        assert response.filename.startswith("chip.yaml_")
        assert _archived_files(response) == {"chip.yaml": b"chip: test\n"}
    finally:
        shutil.rmtree(Path(response.path).parent, ignore_errors=True)


def test_download_zip_file_skips_link_cycles_and_keeps_valid_files(tmp_path: Path) -> None:
    config_dir = tmp_path / "qubex-config"
    (config_dir / "64Q").mkdir(parents=True)
    (config_dir / "64Q" / "chip.yaml").write_text("chip: test\n", encoding="utf-8")
    (config_dir / "64Q" / "alias.yaml").symlink_to("chip.yaml")
    (config_dir / "64Q" / "self.yaml").symlink_to("self.yaml")
    (config_dir / "64Q" / "ping.yaml").symlink_to("pong.yaml")
    (config_dir / "64Q" / "pong.yaml").symlink_to("ping.yaml")

    response = FileService(config_base_path=config_dir).download_zip_file(".")

    try:
        assert _archived_files(response) == {
            "64Q/alias.yaml": b"chip: test\n",
            "64Q/chip.yaml": b"chip: test\n",
        }
    finally:
        shutil.rmtree(Path(response.path).parent, ignore_errors=True)


def test_download_zip_file_reports_single_link_cycle_as_missing(tmp_path: Path) -> None:
    config_dir = tmp_path / "qubex-config"
    config_dir.mkdir()
    (config_dir / "self.yaml").symlink_to("self.yaml")

    with pytest.raises(HTTPException) as exc_info:
        FileService(config_base_path=config_dir).download_zip_file("self.yaml")

    assert exc_info.value.status_code == 404


@pytest.fixture
def swap_tree(tmp_path: Path) -> tuple[Path, Path]:
    """A config tree with sibling directories and an outside directory with the same layout."""
    config_dir = tmp_path / "qubex-config"
    for name in ("a", "b", "c"):
        (config_dir / name).mkdir(parents=True)
        (config_dir / name / "params.yaml").write_text(f"{name}: inside\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "params.yaml").write_text("top secret\n", encoding="utf-8")
    return config_dir, outside


def test_download_zip_file_refuses_directory_swapped_for_link_before_descent(
    swap_tree: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir, outside = swap_tree
    # "b" is listed as a directory, then swapped for a link while a sibling is read.
    swapped = swap_after_listing(
        monkeypatch,
        [config_dir / "a", config_dir / "c"],
        swap_dir_for_link(config_dir / "b", outside),
    )

    response = FileService(config_base_path=config_dir).download_zip_file(".")

    try:
        assert swapped == [True]
        files = _archived_files(response)
        assert all(b"top secret" not in content for content in files.values())
        assert files["a/params.yaml"] == b"a: inside\n"
        assert files["c/params.yaml"] == b"c: inside\n"
    finally:
        shutil.rmtree(Path(response.path).parent, ignore_errors=True)


def test_download_zip_file_reads_files_from_the_listed_directory(
    swap_tree: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir, outside = swap_tree
    # "b" is swapped for a link after its own entries were listed, before they are read.
    swapped = swap_after_listing(
        monkeypatch, [config_dir / "b"], swap_dir_for_link(config_dir / "b", outside)
    )

    response = FileService(config_base_path=config_dir).download_zip_file(".")

    try:
        assert swapped == [True]
        assert _archived_files(response) == {
            "a/params.yaml": b"a: inside\n",
            "b/params.yaml": b"b: inside\n",
            "c/params.yaml": b"c: inside\n",
        }
    finally:
        shutil.rmtree(Path(response.path).parent, ignore_errors=True)


def test_download_zip_file_refuses_single_file_whose_ancestor_was_swapped(
    swap_tree: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir, outside = swap_tree
    service = FileService(config_base_path=config_dir)
    resolve = service._resolve_download_path

    def resolve_then_swap(path: str) -> Path:
        resolved = resolve(path)
        swap_dir_for_link(config_dir / "b", outside)()
        return resolved

    monkeypatch.setattr(service, "_resolve_download_path", resolve_then_swap)

    with pytest.raises(HTTPException) as exc_info:
        service.download_zip_file("b/params.yaml")

    assert exc_info.value.status_code == 404


# --- Workspaces: the same service serves config and knowledge ---


def _workspace_repo(tmp_path: Path) -> Path:
    repo_dir = tmp_path / "knowledge"
    repo_dir.mkdir()
    (repo_dir / "a").mkdir()
    (repo_dir / "a" / "index.md").write_text("# A\n", encoding="utf-8")
    (repo_dir / "task-knowledge.json").write_text("{}", encoding="utf-8")
    repo = Repo.init(repo_dir)
    repo.index.add(["a/index.md", "task-knowledge.json"])
    repo.index.commit("Initial knowledge")
    return repo_dir


def test_push_leaves_out_excluded_generated_files(tmp_path: Path) -> None:
    service = FileService(
        _workspace_repo(tmp_path), label="knowledge", push_exclude=("task-knowledge.json",)
    )

    assert [p.as_posix() for p in service._workspace_files()] == ["a/index.md"]


def test_save_runs_the_after_save_hook(tmp_path: Path) -> None:
    calls: list[str] = []
    service = FileService(_workspace_repo(tmp_path), after_save=lambda: calls.append("ran"))

    service.save_file_content("a/index.md", "# A edited\n")

    assert calls == ["ran"]
    assert (tmp_path / "knowledge" / "a" / "index.md").read_text() == "# A edited\n"


def test_failing_after_save_hook_keeps_the_file_and_reports(tmp_path: Path) -> None:
    def boom() -> None:
        raise RuntimeError("generator exploded")

    service = FileService(_workspace_repo(tmp_path), label="knowledge", after_save=boom)

    with pytest.raises(HTTPException) as exc_info:
        service.save_file_content("a/index.md", "# A edited\n")

    assert exc_info.value.status_code == 500
    assert "generator exploded" in exc_info.value.detail
    assert (tmp_path / "knowledge" / "a" / "index.md").read_text() == "# A edited\n"


def test_workspace_messages_name_the_workspace_and_its_repo_variable(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("KNOWLEDGE_REPO_URL", raising=False)
    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    service = FileService(plain_dir, label="knowledge", repo_url_env="KNOWLEDGE_REPO_URL")

    assert service.get_git_status()["message"] == "Knowledge directory is not a Git repository"
    with pytest.raises(HTTPException) as exc_info:
        service.git_pull_config()
    assert "KNOWLEDGE_REPO_URL" in exc_info.value.detail


def test_git_env_marks_the_mount_safe_and_keeps_the_token_out_of_urls(
    tmp_path: Path, monkeypatch
) -> None:
    # The bind-mounted repo is owned by the host user; the service must not
    # need a global safe.directory entry to read it, and credentials go through
    # a helper rather than the remote URL that .git/config would keep.
    monkeypatch.setenv("GITHUB_USER", "bot")
    monkeypatch.setenv("GITHUB_TOKEN", "s3cret")
    service = FileService(_workspace_repo(tmp_path))

    env = service._git_env()
    repo = service._open_repo()

    assert env["GIT_CONFIG_KEY_0"] == "safe.directory"
    assert env["GIT_CONFIG_KEY_1"] == "credential.helper"
    assert "s3cret" not in env["GIT_CONFIG_VALUE_1"]
    assert env["QDASH_GIT_TOKEN"] == "s3cret"  # noqa: S105 -- test value
    assert repo.git.environment()["GIT_CONFIG_COUNT"] == "2"
    assert service.get_git_status()["branch"] in {"main", "master"}
    assert [r.url for r in repo.remotes] == []


def test_git_env_without_credentials_only_marks_the_mount_safe(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_USER", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    env = FileService(_workspace_repo(tmp_path))._git_env()

    assert env["GIT_CONFIG_COUNT"] == "1"
    assert "QDASH_GIT_TOKEN" not in env


def test_download_zip_file_closes_descriptors_when_archiving_fails(
    swap_tree: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir, _ = swap_tree
    # Track the resources this download acquires instead of counting every open
    # descriptor in the process, which other tests and garbage collection change.
    opened: list[int] = []
    closed: list[int] = []
    archives: list[zipfile.ZipFile] = []
    temp_dirs: list[str] = []
    real_open, real_close, real_mkdtemp = os.open, os.close, tempfile.mkdtemp

    def tracking_open(*args: Any, **kwargs: Any) -> int:
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def tracking_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    def tracking_mkdtemp(*args: Any, **kwargs: Any) -> str:
        temp_dirs.append(real_mkdtemp(*args, **kwargs))
        return temp_dirs[-1]

    class TrackingZipFile(zipfile.ZipFile):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            archives.append(self)

    def fail(*_args: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "open", tracking_open)
    monkeypatch.setattr(os, "close", tracking_close)
    monkeypatch.setattr(tempfile, "mkdtemp", tracking_mkdtemp)
    monkeypatch.setattr(zipfile, "ZipFile", TrackingZipFile)
    monkeypatch.setattr(FileService, "_archive_file", staticmethod(fail))

    with pytest.raises(HTTPException) as exc_info:
        FileService(config_base_path=config_dir).download_zip_file(".")

    assert exc_info.value.status_code == 500
    # The tree anchor, the walked directory, and the file being archived.
    assert len(opened) >= 3
    assert sorted(closed) == sorted(opened)
    assert len(archives) == 1
    assert archives[0].fp is None
    assert len(temp_dirs) == 1
    assert not Path(temp_dirs[0]).exists()
