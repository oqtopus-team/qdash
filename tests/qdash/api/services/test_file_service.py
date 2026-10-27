import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from git import Repo

from qdash.api.services.file_service import FileService


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


def _bare_origin(tmp_path: Path) -> Path:
    bare = tmp_path / "origin.git"
    Repo.init(bare, bare=True, initial_branch="main").close()
    seed = tmp_path / "seed"
    repo = Repo.clone_from(bare, seed)
    (seed / "config").mkdir()
    (seed / "config" / "chip.yaml").write_text("chip-1: {}\n", encoding="utf-8")
    (seed / "params" / "chip-1").mkdir(parents=True)
    (seed / "params" / "chip-1" / "a.yaml").write_text("a: 1\n", encoding="utf-8")
    repo.git.checkout("-b", "main")
    repo.git.add("-A")
    repo.index.commit("seed")
    repo.remotes.origin.push(refspec="main:main")
    repo.close()
    return bare


def _github_service(tmp_path: Path, monkeypatch) -> tuple[FileService, Path]:
    origin = _bare_origin(tmp_path)
    root = tmp_path / "qubex-config"
    Repo.clone_from(origin, root, branch="main").close()
    monkeypatch.setenv("GITHUB_USER", "bot")
    monkeypatch.setenv("GITHUB_TOKEN", "s3cret")
    monkeypatch.setenv("CONFIG_REPO_URL", str(origin))
    return FileService(config_base_path=root), origin


def test_status_reports_the_repository_mode_and_layout(tmp_path: Path, monkeypatch) -> None:
    service, _ = _github_service(tmp_path, monkeypatch)
    (tmp_path / "qubex-config" / "params" / "chip-1" / "a.yaml").write_text("a: 2\n")

    status = service.get_git_status()

    assert status["mode"] == "github" and status["layout"] == "shared"
    assert status["branch"] == "main" and status["is_dirty"] is True
    assert status["changed_files"] == ["params/chip-1/a.yaml"]
    assert status["unpushed_commits"] == 0 and status["review_required"] is False


def test_pull_publishes_owned_edits_and_refuses_edited_shared_files(
    tmp_path: Path, monkeypatch
) -> None:
    service, origin = _github_service(tmp_path, monkeypatch)
    root = tmp_path / "qubex-config"
    (root / "params" / "chip-1" / "a.yaml").write_text("a: 2\n")

    result = service.git_pull_config()

    assert result["success"] is True and result["published"] == ["params/chip-1/a.yaml"]
    assert Repo(origin).git.show("main:params/chip-1/a.yaml").strip() == "a: 2"

    (root / "config" / "chip.yaml").write_text("chip-1: {n_qubits: 4}\n")
    with pytest.raises(HTTPException) as exc_info:
        service.git_pull_config()
    assert exc_info.value.status_code == 409
    assert "config/chip.yaml" in exc_info.value.detail
    assert service.git_pull_config(force=True)["success"] is True
    assert (root / "config" / "chip.yaml").read_text() == "chip-1: {}\n"


def test_push_proposes_only_the_changed_files(tmp_path: Path, monkeypatch) -> None:
    service, origin = _github_service(tmp_path, monkeypatch)
    root = tmp_path / "qubex-config"
    (root / "config" / "chip.yaml").write_text("chip-1: {n_qubits: 4}\n")
    (root / "config" / "wiring.yaml").write_text("chip-1: []\n")
    (root / "config" / "wiring.yaml.lock").write_text("")
    opened: list[dict[str, str]] = []

    def create_pr(settings, *, head, base, title, body):
        opened.append({"head": head, "base": base, "title": title})
        return "https://example.test/pr/1", 1

    monkeypatch.setattr(
        "qdash.common.infrastructure.config_repository.create_github_pull_request", create_pr
    )

    result = service.git_push_config("Resize chip-1")

    assert result["pr_url"] == "https://example.test/pr/1" and result["pr_number"] == 1
    assert result["files"] == ["config/chip.yaml", "config/wiring.yaml"]
    assert opened == [{"head": result["branch"], "base": "main", "title": "Resize chip-1"}]
    assert Repo(origin).git.show("main:config/chip.yaml").strip() == "chip-1: {}"


def test_push_without_credentials_names_the_missing_variables(tmp_path: Path, monkeypatch) -> None:
    for name in ("GITHUB_USER", "GITHUB_TOKEN", "CONFIG_REPO_URL"):
        monkeypatch.delenv(name, raising=False)
    service = FileService(_workspace_repo(tmp_path))

    with pytest.raises(HTTPException) as exc_info:
        service.git_push_config("x")
    assert "CONFIG_REPO_URL" in exc_info.value.detail


def test_validate_file_content_checks_the_layout_schema_of_config_files(tmp_path: Path) -> None:
    from tests.qdash.api.services.chip._trees import write_shared_tree

    write_shared_tree(tmp_path)
    service = FileService(config_base_path=tmp_path)

    good = service.validate_file_content("64Qv3:\n  n_qubits: 64\n", "yaml", "config/chip.yaml")
    bad = service.validate_file_content("64Qv3:\n  n_qubits: many\n", "yaml", "config/chip.yaml")
    other = service.validate_file_content("anything: 1\n", "yaml", "config/cable_delay.yaml")
    no_path = service.validate_file_content("64Qv3:\n  n_qubits: many\n", "yaml")

    assert good["valid"] is True
    assert good["schema"] == "chip.schema.json"
    assert good["problems"] == []
    assert bad["valid"] is False
    assert bad["problems"] == [
        {"location": "64Qv3/n_qubits", "message": "'many' is not of type 'integer'"}
    ]
    assert "schema" not in other
    assert no_path == {"valid": True, "message": "Valid YAML"}


def test_validate_file_content_skips_schemas_outside_the_config_workspace(tmp_path: Path) -> None:
    service = FileService(config_base_path=tmp_path, label="knowledge")

    result = service.validate_file_content("64Qv3:\n  n_qubits: many\n", "yaml", "config/chip.yaml")

    assert result == {"valid": True, "message": "Valid YAML"}
