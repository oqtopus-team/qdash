"""ConfigRepository: one access layer over the configuration tree in three modes."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from git import Repo

from qdash.common.config.qubex_layout import QubexLayout
from qdash.common.infrastructure.config_repository import (
    ConfigRepository,
    ConfigRepositoryError,
    DirtySharedFiles,
    GitHubSettings,
    RepoMode,
)


class RecordingSink:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


def _seed_tree(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "chip.yaml").write_text("chip-1:\n  n_qubits: 16\n", encoding="utf-8")
    (root / "config" / "system.yaml").write_text(
        "chip-1:\n  chip_id: chip-1\n  backend: quel1\n", encoding="utf-8"
    )
    (root / "params" / "chip-1").mkdir(parents=True, exist_ok=True)
    (root / "params" / "chip-1" / "readout_frequency.yaml").write_text(
        "data:\n  Q00: 7.0\n", encoding="utf-8"
    )
    (root / "calibration" / "chip-1").mkdir(parents=True, exist_ok=True)
    (root / "calibration" / "chip-1" / "calib_note.json").write_text("{}", encoding="utf-8")


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    """A bare origin with the shared layout committed on ``main``."""
    bare = tmp_path / "origin.git"
    Repo.init(bare, bare=True, initial_branch="main").close()
    seed = tmp_path / "seed"
    repo = Repo.clone_from(bare, seed)
    _seed_tree(seed)
    repo.git.checkout("-b", "main")
    repo.git.add("-A")
    repo.index.commit("seed")
    repo.remotes.origin.push(refspec="main:main")
    repo.close()
    return bare


def _settings(origin: Path, **overrides: Any) -> GitHubSettings:
    values: dict[str, Any] = {
        "repo_url": str(origin),
        "user": "bot",
        "token": "s3cret",
        "branch": "main",
    }
    values.update(overrides)
    return GitHubSettings(**values)


def _github_repo(
    origin: Path, root: Path, **overrides: Any
) -> tuple[ConfigRepository, RecordingSink]:
    sink = RecordingSink()
    repo = ConfigRepository(
        QubexLayout.detect(root) if (root / "config" / "chip.yaml").exists() else root,
        _settings(origin, **overrides),
        change_log=sink,
        actor="tester",
        pull_request_creator=lambda settings, **kw: (f"https://example.test/pr/{kw['head']}", 7),
    )
    return repo, sink


def _clone_root(origin: Path, root: Path) -> None:
    Repo.clone_from(origin, root, branch="main").close()


def _remote_file(origin: Path, rel: str) -> str:
    return str(Repo(origin).git.show(f"main:{rel}"))


# --- Modes --------------------------------------------------------------------------------


def test_mode_detection(tmp_path: Path, origin: Path) -> None:
    root = tmp_path / "root"
    _seed_tree(root)
    layout = QubexLayout.detect(root)

    assert ConfigRepository(layout, GitHubSettings()).mode is RepoMode.PLAIN
    Repo.init(root).close()
    assert ConfigRepository(layout, GitHubSettings()).mode is RepoMode.LOCAL_GIT
    assert ConfigRepository(layout, _settings(origin)).mode is RepoMode.GITHUB


def test_plain_mode_records_every_write_and_touches_no_git(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _seed_tree(root)
    sink = RecordingSink()
    repo = ConfigRepository(
        QubexLayout.detect(root), GitHubSettings(), change_log=sink, actor="ann"
    )

    published = repo.publish_owned(
        [root / "params/chip-1/readout_frequency.yaml"], "edit", chip_id="chip-1"
    )
    repo.upsert_shared(
        {"system.yaml": {"chip-1-quel3": {"chip_id": "chip-1", "backend": "quel3"}}}, "add"
    )
    assert repo.pull() is None

    assert published.mode is RepoMode.PLAIN and published.commit is None
    assert (
        yaml.safe_load((root / "config/system.yaml").read_text())["chip-1-quel3"]["backend"]
        == "quel3"
    )
    assert [(r["chip_id"], r["paths"], r["actor"], r["mode"]) for r in sink.records] == [
        ("chip-1", ["params/chip-1/readout_frequency.yaml"], "ann", "plain"),
        (None, ["config/system.yaml"], "ann", "plain"),
    ]
    assert not (root / ".git").exists()


def test_owned_and_shared_paths_follow_the_layout(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    _seed_tree(shared)
    repo = ConfigRepository(QubexLayout.detect(shared), GitHubSettings())
    assert repo.is_owned_path(shared / "params/chip-1/x.yaml")
    assert repo.is_owned_path(shared / "calibration/chip-1/calib_note.json")
    assert repo.is_shared_path(shared / "config/wiring.yaml")
    assert not repo.is_owned_path(shared / "config/wiring.yaml")
    with pytest.raises(ValueError, match="System-owned"):
        repo.publish_owned([shared / "config/wiring.yaml"], "nope")

    legacy = tmp_path / "legacy"
    (legacy / "chip-1" / "config").mkdir(parents=True)
    (legacy / "chip-1" / "config" / "chip.yaml").write_text("{}")
    legacy_repo = ConfigRepository(QubexLayout.detect(legacy), GitHubSettings())
    assert legacy_repo.is_owned_path(legacy / "chip-1/params/x.yaml")
    assert legacy_repo.is_shared_path(legacy / "chip-1/config/chip.yaml")
    with pytest.raises(ConfigRepositoryError, match="shared layout"):
        legacy_repo.upsert_shared({"chip.yaml": {"a": {}}}, "x")


# --- LOCAL_GIT ------------------------------------------------------------------------------


def test_local_git_commits_only_the_given_paths(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _seed_tree(root)
    git = Repo.init(root, initial_branch="main")
    git.git.add("-A")
    git.index.commit("seed")
    sink = RecordingSink()
    repo = ConfigRepository(QubexLayout.detect(root), GitHubSettings(), change_log=sink)
    (root / "params/chip-1/readout_frequency.yaml").write_text("data:\n  Q00: 7.5\n")
    (root / "params/chip-1/other.yaml").write_text("data: {}\n")

    result = repo.publish_owned([root / "params/chip-1/readout_frequency.yaml"], "tune Q00")

    assert result.mode is RepoMode.LOCAL_GIT and result.changed and result.commit
    assert str(git.head.commit.message).startswith("[ENV=")
    assert "tune Q00" in str(git.head.commit.message)
    assert [item.a_path for item in git.head.commit.diff("HEAD~1")] == [
        "params/chip-1/readout_frequency.yaml"
    ]
    assert git.untracked_files == ["params/chip-1/other.yaml"]
    assert repo.pull() == git.head.commit.hexsha[:8]
    status = repo.status()
    assert status.untracked_paths == ["params/chip-1/other.yaml"]
    assert status.unpushed_commits == 0 and status.is_git_repo

    unchanged = repo.publish_owned([root / "params/chip-1/readout_frequency.yaml"], "again")
    assert unchanged.changed is False
    assert len(sink.records) == 1


def test_local_git_propose_is_a_commit_without_pull_request(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _seed_tree(root)
    git = Repo.init(root, initial_branch="main")
    git.git.add("-A")
    git.index.commit("seed")
    repo = ConfigRepository(QubexLayout.detect(root), GitHubSettings())
    (root / "config/chip.yaml").write_text("chip-1:\n  n_qubits: 64\n")

    result = repo.propose([root / "config/chip.yaml", root / ".qdash-repository.lock"], "resize")

    assert result.paths == ["config/chip.yaml"]
    assert result.pr_url is None and result.commit == git.head.commit.hexsha[:8]


# --- GITHUB ---------------------------------------------------------------------------------


def test_pull_clones_into_an_empty_root_and_keeps_existing_files(
    tmp_path: Path, origin: Path
) -> None:
    empty = tmp_path / "empty"
    empty_repo, _ = _github_repo(origin, empty)
    assert empty_repo.pull() == Repo(origin).head.commit.hexsha[:8]
    assert (empty / "config" / "chip.yaml").exists()

    # A directory that already holds files (a bind mount) adopts the remote history.
    root = tmp_path / "root"
    (root / "config").mkdir(parents=True)
    (root / "config" / "chip.yaml").write_text("chip-1:\n  n_qubits: 16\n", encoding="utf-8")
    (root / "params" / "chip-1").mkdir(parents=True)
    (root / "params" / "chip-1" / "readout_frequency.yaml").write_text("data:\n  Q00: 9.9\n")
    repo, sink = _github_repo(origin, root)

    commit = repo.pull()

    assert commit == Repo(origin).head.commit.hexsha[:8]
    assert (root / "config" / "system.yaml").exists()
    # The local owned edit was published before the reset, not discarded.
    assert "9.9" in _remote_file(origin, "params/chip-1/readout_frequency.yaml")
    assert "9.9" in (root / "params/chip-1/readout_frequency.yaml").read_text()
    assert sink.records[0]["paths"] == ["params/chip-1/readout_frequency.yaml"]


def test_pull_refuses_dirty_shared_files_unless_forced(tmp_path: Path, origin: Path) -> None:
    root = tmp_path / "root"
    _clone_root(origin, root)
    (root / "config/chip.yaml").write_text("chip-1:\n  n_qubits: 1\n")
    repo, _ = _github_repo(origin, root)

    with pytest.raises(DirtySharedFiles) as exc_info:
        repo.pull()
    assert exc_info.value.paths == ["config/chip.yaml"]
    assert "n_qubits: 1" in (root / "config/chip.yaml").read_text()

    assert repo.pull(force=True) is not None
    assert "n_qubits: 16" in (root / "config/chip.yaml").read_text()


def test_publish_owned_pushes_from_the_root_without_resetting_other_edits(
    tmp_path: Path, origin: Path
) -> None:
    root = tmp_path / "root"
    _clone_root(origin, root)
    repo, sink = _github_repo(origin, root)
    (root / "params/chip-1/readout_frequency.yaml").write_text("data:\n  Q00: 7.1\n")
    (root / "params/chip-1/control_frequency.yaml").write_text(
        "data:\n  Q00: 5.0\n"
    )  # another session

    result = repo.publish_owned(
        [root / "params/chip-1/readout_frequency.yaml"], "Q00 readout", chip_id="chip-1"
    )

    assert result.mode is RepoMode.GITHUB and result.changed
    assert result.commit == Repo(origin).head.commit.hexsha[:8]
    assert "7.1" in _remote_file(origin, "params/chip-1/readout_frequency.yaml")
    assert (root / "params/chip-1/control_frequency.yaml").read_text() == "data:\n  Q00: 5.0\n"
    assert Repo(root).untracked_files == ["params/chip-1/control_frequency.yaml"]
    assert sink.records[-1]["commit"] == result.commit and sink.records[-1]["chip_id"] == "chip-1"
    assert "s3cret" not in (root / ".git" / "config").read_text()


def test_two_sessions_publish_without_losing_each_others_changes(
    tmp_path: Path, origin: Path
) -> None:
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    _clone_root(origin, root_a)
    _clone_root(origin, root_b)
    repo_a, _ = _github_repo(origin, root_a)
    repo_b, _ = _github_repo(origin, root_b)
    (root_a / "params/chip-1/readout_frequency.yaml").write_text("data:\n  Q00: 1.0\n")
    (root_b / "params/chip-1/control_frequency.yaml").write_text("data:\n  Q01: 2.0\n")
    (root_b / "params/chip-1/pending.yaml").write_text("data: {}\n")  # unpublished, must survive

    repo_a.publish_owned([root_a / "params/chip-1/readout_frequency.yaml"], "A")
    # B is now behind origin: the push is rejected once and rebased.
    result_b = repo_b.publish_owned([root_b / "params/chip-1/control_frequency.yaml"], "B")

    assert result_b.changed
    assert "1.0" in _remote_file(origin, "params/chip-1/readout_frequency.yaml")
    assert "2.0" in _remote_file(origin, "params/chip-1/control_frequency.yaml")
    assert (root_b / "params/chip-1/pending.yaml").read_text() == "data: {}\n"
    assert "1.0" in (root_b / "params/chip-1/readout_frequency.yaml").read_text()


def test_upsert_shared_edits_only_its_keys_from_a_fresh_clone(tmp_path: Path, origin: Path) -> None:
    root = tmp_path / "root"
    _clone_root(origin, root)
    # The remote moved on (another instance added chip-2); the stale root must not undo it.
    other = tmp_path / "other"
    _clone_root(origin, other)
    (other / "config/chip.yaml").write_text(
        "chip-1:\n  n_qubits: 16\nchip-2: # second instance\n  n_qubits: 64\n"
    )
    other_repo = Repo(other)
    other_repo.git.add("-A")
    other_repo.index.commit("chip-2")
    other_repo.remotes.origin.push(refspec="main:main")
    repo, sink = _github_repo(origin, root)

    result = repo.upsert_shared(
        {
            "chip.yaml": {"chip-3": {"n_qubits": 144}},
            "system.yaml": {"chip-3": {"chip_id": "chip-3", "backend": "quel3"}},
        },
        "add chip-3",
        chip_id="chip-3",
    )

    assert result.changed and result.paths == ["config/chip.yaml", "config/system.yaml"]
    remote_chip = _remote_file(origin, "config/chip.yaml")
    assert "chip-2: # second instance" in remote_chip and "chip-3" in remote_chip
    assert (
        yaml.safe_load(_remote_file(origin, "config/system.yaml"))["chip-3"]["backend"] == "quel3"
    )
    # The local root was pulled to the pushed state.
    assert "chip-2" in (root / "config/chip.yaml").read_text()
    assert Repo(root).head.commit.hexsha[:8] == result.commit
    assert sink.records[-1]["summary"].startswith("upsert")


def test_propose_opens_a_pull_request_with_only_the_given_paths(
    tmp_path: Path, origin: Path
) -> None:
    root = tmp_path / "root"
    _clone_root(origin, root)
    repo, sink = _github_repo(origin, root)
    (root / "config/wiring.yaml").write_text("chip-1: []\n")
    (root / "config/chip.yaml").write_text("chip-1:\n  n_qubits: 1\n")  # not proposed
    (root / "config/wiring.yaml.lock").write_text("")

    result = repo.propose(
        [root / "config/wiring.yaml", root / "config/wiring.yaml.lock"],
        "wire chip-1",
        "Wire chip-1",
    )

    assert result.pr_url == f"https://example.test/pr/{result.branch}" and result.pr_number == 7
    assert result.branch is not None and result.branch.startswith("config-update/")
    bare = Repo(origin)
    assert bare.git.show(f"{result.branch}:config/wiring.yaml").strip() == "chip-1: []"
    assert "n_qubits: 16" in bare.git.show(f"{result.branch}:config/chip.yaml")
    assert "n_qubits: 16" in _remote_file(origin, "config/chip.yaml")  # main untouched
    assert sink.records[-1]["message"] == "Wire chip-1"


def test_review_required_turns_publish_into_a_proposal(tmp_path: Path, origin: Path) -> None:
    root = tmp_path / "root"
    _clone_root(origin, root)
    repo, _ = _github_repo(origin, root, review_required=True)
    (root / "params/chip-1/readout_frequency.yaml").write_text("data:\n  Q00: 3.3\n")

    result = repo.publish_owned([root / "params/chip-1/readout_frequency.yaml"], "Q00")

    assert result.pr_url is not None
    assert "7.0" in _remote_file(origin, "params/chip-1/readout_frequency.yaml")  # main unchanged


def test_status_reports_remote_state_and_hides_lock_files(tmp_path: Path, origin: Path) -> None:
    root = tmp_path / "root"
    _clone_root(origin, root)
    repo, _ = _github_repo(origin, root)
    (root / ".qdash-repository.lock").write_text("")
    (root / "params/chip-1/readout_frequency.yaml").write_text("data: {}\n")
    other = tmp_path / "other"
    _clone_root(origin, other)
    (other / "calibration/chip-1/calib_note.json").write_text('{"a": 1}')
    other_repo = Repo(other)
    other_repo.git.add("-A")
    other_repo.index.commit("note")
    other_repo.remotes.origin.push(refspec="main:main")

    status = repo.status()

    assert status.mode is RepoMode.GITHUB and status.branch == "main" and status.is_git_repo
    assert status.changed_paths == ["params/chip-1/readout_frequency.yaml"]
    assert status.untracked_paths == []
    assert status.has_remote_updates is True
    assert status.unpushed_commits == 0
    assert status.to_dict()["dirty_paths"] == ["params/chip-1/readout_frequency.yaml"]
    assert status.layout_version == "2.0"
    assert status.manifest_present is False
    assert status.schemas_status == "absent"


def test_plain_root_without_layout_blocks_pull_on_any_dirty_file(
    tmp_path: Path, origin: Path
) -> None:
    root = tmp_path / "root"
    _clone_root(origin, root)
    repo = ConfigRepository(root, _settings(origin), label="knowledge")
    (root / "params/chip-1/readout_frequency.yaml").write_text("data: {}\n")

    with pytest.raises(DirtySharedFiles):
        repo.pull()
    with pytest.raises(ValueError, match="System-owned"):
        repo.publish_owned([root / "params/chip-1/readout_frequency.yaml"], "x")


def test_git_errors_never_leak_the_token(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _seed_tree(root)
    repo = ConfigRepository(
        QubexLayout.detect(root),
        GitHubSettings(repo_url=str(tmp_path / "missing.git"), user="bot", token="s3cret"),
    )
    with pytest.raises(ConfigRepositoryError) as exc_info:
        repo.pull()
    assert "s3cret" not in str(exc_info.value)
