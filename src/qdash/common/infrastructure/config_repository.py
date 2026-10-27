"""One access layer for the Qubex configuration repository.

The repository is the directory that :class:`~qdash.common.config.qubex_layout.QubexLayout`
describes. It is operated in one of three modes, decided once per instance:

* ``github``: the root is the canonical clone of ``CONFIG_REPO_URL``; ``pull`` keeps it
  current and ``publish_owned`` commits and pushes from it. The working tree is never
  reset by a publish, so values another session wrote but has not published survive.
* ``local-git``: the root has a ``.git`` directory but no credentials; every write becomes
  a local commit and ``pull`` is a no-op.
* ``plain``: no git at all; writes land on disk with no history beyond the files.

Two kinds of files exist. Owned files (``params/<system_id>/*.yaml`` and
``calibration/<system_id>/calib_note.json``) belong to one System and are written by
calibration runs through :meth:`ConfigRepository.publish_owned`. Shared files
(``config/*.yaml``) are per-chip catalogs edited only by the chip provisioning services
through :meth:`ConfigRepository.upsert_shared`, which replaces whole top-level keys and
nothing else. Automated workflows cannot reach the shared files through this class.

The same class serves a plain directory (no :class:`QubexLayout`), for workspaces such
as the task knowledge repository; the owned/shared distinction then does not apply and
every dirty file blocks a ``pull``.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import shutil
import uuid
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, Protocol

from filelock import FileLock
from git import Actor, Repo
from git.exc import GitCommandError, InvalidGitRepositoryError

from qdash.common.config.qubex_config_schema import schemas_status
from qdash.common.config.qubex_layout import LayoutKind, QubexLayout
from qdash.common.utils.commit_message import format_machine_commit_message
from qdash.common.utils.datetime import now_iso

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

logger = logging.getLogger(__name__)

SHARED_FILES: tuple[str, ...] = ("chip.yaml", "system.yaml", "wiring.yaml", "box.yaml", "skew.yaml")
"""Shared catalog files that :meth:`ConfigRepository.upsert_shared` may edit."""

NEVER_PUBLISHED: tuple[str, ...] = (".git", "*.lock", "*.tmp")
"""Path patterns that never enter a commit."""

REPO_LOCK_FILE = ".qdash-repository.lock"
"""Lock file (inside the root) that serializes git operations of this host."""

BOT_ACTOR = Actor("github-actions[bot]", "github-actions[bot]@users.noreply.github.com")
PUSH_ATTEMPTS = 3
PUBLISH_LOCAL_MESSAGE = "Publish local calibration changes"


class RepoMode(StrEnum):
    """How the configuration root is synchronized."""

    GITHUB = "github"
    LOCAL_GIT = "local-git"
    PLAIN = "plain"


@dataclass(frozen=True)
class GitHubSettings:
    """Credentials and policy for the ``github`` mode."""

    repo_url: str | None = None
    user: str | None = None
    token: str | None = None
    branch: str = "main"
    review_required: bool = False
    repo_url_env: str = "CONFIG_REPO_URL"

    @property
    def credentials_available(self) -> bool:
        return bool(self.repo_url and self.user and self.token)

    @property
    def missing_variables(self) -> list[str]:
        """Environment variables that the ``github`` mode still needs."""
        missing = []
        if not self.user:
            missing.append("GITHUB_USER")
        if not self.token:
            missing.append("GITHUB_TOKEN")
        if not self.repo_url:
            missing.append(self.repo_url_env)
        return missing

    @classmethod
    def from_env(
        cls,
        workflow_settings: Mapping[str, Any] | None = None,
        *,
        repo_url_env: str = "CONFIG_REPO_URL",
    ) -> GitHubSettings:
        """Read ``<repo_url_env>`` / ``GITHUB_USER`` / ``GITHUB_TOKEN`` and ``workflow.github``."""
        github: Mapping[str, Any] = {}
        if workflow_settings is None:
            from qdash.common.config.loader import ConfigLoader

            workflow_settings = ConfigLoader.load_workflow()
        if isinstance(workflow_settings, Mapping):
            candidate = workflow_settings.get("github", {})
            if isinstance(candidate, Mapping):
                github = candidate
        return cls(
            repo_url=os.getenv(repo_url_env) or None,
            user=os.getenv("GITHUB_USER") or None,
            token=os.getenv("GITHUB_TOKEN") or None,
            branch=str(github.get("branch") or "main"),
            review_required=bool(github.get("review_required", False)),
            repo_url_env=repo_url_env,
        )


@dataclass
class RepoStatus:
    """What :meth:`ConfigRepository.status` reports."""

    mode: RepoMode
    layout: LayoutKind | None
    root: str
    layout_version: str | None = None
    """``1.0`` or ``2.0``, from the manifest when present, else inferred from the layout."""
    manifest_present: bool = False
    schemas_status: str | None = None
    """``match`` / ``differs`` / ``absent``: the tree's ``schemas/`` copy versus QDash's."""
    is_git_repo: bool = False
    branch: str | None = None
    head: str | None = None
    head_message: str | None = None
    changed_paths: list[str] = field(default_factory=list)
    untracked_paths: list[str] = field(default_factory=list)
    unpushed_commits: int = 0
    has_remote_updates: bool = False
    review_required: bool = False

    @property
    def dirty_paths(self) -> list[str]:
        return [*self.changed_paths, *self.untracked_paths]

    @property
    def is_dirty(self) -> bool:
        return bool(self.changed_paths or self.untracked_paths)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "layout": self.layout.value if self.layout is not None else None,
            "layout_version": self.layout_version,
            "manifest_present": self.manifest_present,
            "schemas_status": self.schemas_status,
            "root": self.root,
            "is_git_repo": self.is_git_repo,
            "branch": self.branch,
            "head": self.head,
            "head_message": self.head_message,
            "dirty_paths": self.dirty_paths,
            "changed_paths": list(self.changed_paths),
            "untracked_paths": list(self.untracked_paths),
            "unpushed_commits": self.unpushed_commits,
            "has_remote_updates": self.has_remote_updates,
            "review_required": self.review_required,
        }


@dataclass
class PublishResult:
    """Outcome of :meth:`ConfigRepository.publish_owned` or :meth:`upsert_shared`."""

    mode: RepoMode
    paths: list[str]
    message: str
    commit: str | None = None
    changed: bool = True
    pr_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "paths": list(self.paths),
            "message": self.message,
            "commit": self.commit,
            "changed": self.changed,
            "pr_url": self.pr_url,
        }


@dataclass
class ProposeResult:
    """Outcome of :meth:`ConfigRepository.propose`."""

    mode: RepoMode
    paths: list[str]
    message: str
    commit: str | None = None
    branch: str | None = None
    pr_url: str | None = None
    pr_number: int | None = None
    changed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "paths": list(self.paths),
            "message": self.message,
            "commit": self.commit,
            "branch": self.branch,
            "pr_url": self.pr_url,
            "pr_number": self.pr_number,
            "changed": self.changed,
        }


@dataclass
class SyncResult:
    """Outcome of :meth:`ConfigRepository.sync`: what was published, then pulled."""

    mode: RepoMode
    commit: str | None = None
    published: list[str] = field(default_factory=list)
    published_commit: str | None = None
    changed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "commit": self.commit,
            "published": list(self.published),
            "published_commit": self.published_commit,
            "changed": self.changed,
        }


class ChangeLogSink(Protocol):
    """Optional observer of every write (publish, upsert, propose).

    Nothing is recorded by default: git history is the record in the git modes.
    Tests pass a recording sink to assert which paths a write touched, and a
    deployment that wants a database history of ``plain``-mode writes can plug one in.
    """

    def record(
        self,
        *,
        chip_id: str | None,
        paths: list[str],
        message: str,
        actor: str,
        mode: str,
        commit: str | None,
        summary: str,
    ) -> object: ...


class NullChangeLog:
    """Sink that keeps nothing (the default)."""

    def record(self, **_: Any) -> object:
        return None


class ConfigRepositoryError(RuntimeError):
    """A repository operation could not complete; the message is safe to show."""


class DirtySharedFiles(ConfigRepositoryError):
    """``pull`` refused because shared files hold unpublished edits."""

    def __init__(self, paths: Iterable[str]) -> None:
        self.paths = sorted(paths)
        super().__init__(
            "Shared configuration files have unpublished changes: " + ", ".join(self.paths)
        )


class PullRequestCreator(Protocol):
    """Opens a pull request; swapped in tests."""

    def __call__(
        self, settings: GitHubSettings, *, head: str, base: str, title: str, body: str
    ) -> tuple[str, int]: ...


def create_github_pull_request(
    settings: GitHubSettings, *, head: str, base: str, title: str, body: str
) -> tuple[str, int]:
    """Create a pull request through the GitHub REST API; returns ``(html_url, number)``."""
    import httpx

    match = re.match(r"https?://[^/]+/([^/]+)/([^/]+?)(?:\.git)?/?$", settings.repo_url or "")
    if not match:
        raise ConfigRepositoryError(f"{settings.repo_url_env} is not a GitHub repository URL")
    owner, repo_name = match.group(1), match.group(2)
    response = httpx.post(
        f"https://api.github.com/repos/{owner}/{repo_name}/pulls",
        headers={
            "Authorization": f"token {settings.token}",
            "Accept": "application/vnd.github.v3+json",
        },
        json={"title": title, "head": head, "base": base, "body": body},
        timeout=30,
    )
    if response.status_code >= 400:
        raise ConfigRepositoryError(f"Failed to create pull request: {response.text}")
    data = response.json()
    return str(data["html_url"]), int(data["number"])


class ConfigRepository:
    """Pull, publish, upsert and propose against one configuration root."""

    def __init__(
        self,
        layout: QubexLayout | Path,
        settings: GitHubSettings | None = None,
        *,
        change_log: ChangeLogSink | None = None,
        actor: str = "system",
        label: str = "config",
        lock_timeout: float = 60.0,
        pull_request_creator: PullRequestCreator | None = None,
    ) -> None:
        if isinstance(layout, QubexLayout):
            self.layout: QubexLayout | None = layout
            self._root = layout.root
        else:
            self.layout = None
            self._root = Path(layout)
        self.settings = settings if settings is not None else GitHubSettings.from_env()
        self.change_log: ChangeLogSink = change_log if change_log is not None else NullChangeLog()
        self.actor = actor
        self.label = label
        self.lock_timeout = lock_timeout
        self._create_pull_request: PullRequestCreator = (
            pull_request_creator or create_github_pull_request
        )
        self._mode = self._detect_mode()

    # --- Mode -------------------------------------------------------------------------

    @property
    def root(self) -> Path:
        return self._root

    @property
    def mode(self) -> RepoMode:
        return self._mode

    @property
    def branch(self) -> str:
        return self.settings.branch

    def _detect_mode(self) -> RepoMode:
        if self.settings.credentials_available:
            return RepoMode.GITHUB
        if (self.root / ".git").exists():
            return RepoMode.LOCAL_GIT
        return RepoMode.PLAIN

    # --- Paths ------------------------------------------------------------------------

    def relpath(self, path: Path | str) -> str:
        """Repository-relative POSIX path of ``path``; raises when outside the root."""
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        try:
            rel = candidate.resolve().relative_to(self.root.resolve())
        except ValueError as exc:
            raise ValueError(f"Path is outside the configuration root: {path}") from exc
        return PurePosixPath(rel).as_posix()

    def _is_owned_rel(self, rel: str) -> bool:
        parts = PurePosixPath(rel).parts
        if self.layout is None:
            return False
        if self.layout.kind is LayoutKind.SHARED:
            return len(parts) >= 3 and parts[0] in {"params", "calibration"}
        return len(parts) >= 3 and parts[1] in {"params", "calibration"}

    def _is_shared_rel(self, rel: str) -> bool:
        parts = PurePosixPath(rel).parts
        if self.layout is None:
            return False
        if self.layout.kind is LayoutKind.SHARED:
            return len(parts) == 2 and parts[0] == "config" and parts[1] in SHARED_FILES
        return len(parts) == 3 and parts[1] == "config" and parts[2] in SHARED_FILES

    def is_owned_path(self, path: Path | str) -> bool:
        """True for files under a System's ``params`` or ``calibration`` directory."""
        return self._is_owned_rel(self.relpath(path))

    def is_shared_path(self, path: Path | str) -> bool:
        """True for the per-chip catalog files."""
        return self._is_shared_rel(self.relpath(path))

    def _owned_relpaths(self, paths: Iterable[Path | str]) -> list[str]:
        rels: list[str] = []
        for path in paths:
            rel = self.relpath(path)
            if not self._is_owned_rel(rel):
                raise ValueError(f"Not a System-owned configuration file: {path}")
            if rel not in rels:
                rels.append(rel)
        return rels

    @staticmethod
    def _is_never_published(rel: str) -> bool:
        parts = PurePosixPath(rel).parts
        return ".git" in parts or rel.endswith((".lock", ".tmp"))

    # --- Git plumbing -----------------------------------------------------------------

    def _git_env(self) -> dict[str, str]:
        """Environment for git on this root: safe.directory plus a credential helper.

        The directory may be a bind mount owned by another user, which git refuses as
        "dubious ownership". Credentials go through a one-shot helper so the token never
        lands in ``.git/config`` or in a URL that an error message could echo.
        """
        entries = [("safe.directory", str(self.root))]
        env = {"GIT_TERMINAL_PROMPT": "0"}
        if self.settings.user and self.settings.token:
            env["QDASH_GIT_USER"] = self.settings.user
            env["QDASH_GIT_TOKEN"] = self.settings.token
            entries.append(
                (
                    "credential.helper",
                    '!f() { echo "username=$QDASH_GIT_USER"; echo "password=$QDASH_GIT_TOKEN"; }; f',
                )
            )
        env["GIT_CONFIG_COUNT"] = str(len(entries))
        for index, (key, value) in enumerate(entries):
            env[f"GIT_CONFIG_KEY_{index}"] = key
            env[f"GIT_CONFIG_VALUE_{index}"] = value
        return env

    def _open_repo(self) -> Repo:
        try:
            repo = Repo(self.root)
        except InvalidGitRepositoryError as exc:
            raise ConfigRepositoryError(f"{self.root} is not a git repository") from exc
        repo.git.update_environment(**self._git_env())
        return repo

    def _lock(self) -> FileLock:
        """Host-wide lock for git operations; inside ``.git`` so it never shows as dirty."""
        self.root.mkdir(parents=True, exist_ok=True)
        git_dir = self.root / ".git"
        directory = git_dir if git_dir.is_dir() else self.root
        return FileLock(directory / REPO_LOCK_FILE, timeout=self.lock_timeout)

    def _mask(self, text: str) -> str:
        for secret in (self.settings.token, self.settings.user):
            if secret:
                text = text.replace(secret, "***")
        return text

    def _fail(self, action: str, exc: Exception) -> ConfigRepositoryError:
        detail = self._mask(str(getattr(exc, "stderr", None) or exc)).strip()
        logger.error("Configuration repository %s failed: %s", action, detail)
        return ConfigRepositoryError(f"Configuration repository {action} failed: {detail}")

    def _ensure_remote(self, repo: Repo) -> None:
        url = self.settings.repo_url
        assert url is not None
        if "origin" in [remote.name for remote in repo.remotes]:
            if repo.remotes.origin.url != url:
                repo.remotes.origin.set_url(url)
        else:
            repo.create_remote("origin", url)

    def _ensure_clone(self) -> Repo:
        """Make the root a clone of the remote, adopting files that are already there.

        A root without ``.git`` receives the remote's history; files already present
        stay as they are (they show up as local changes), files it lacks are checked out.
        """
        if (self.root / ".git").exists():
            repo = self._open_repo()
            self._ensure_remote(repo)
            return repo
        url = self.settings.repo_url
        assert url is not None
        with TemporaryDirectory(prefix="qdash-config-clone-") as directory:
            clone_dir = Path(directory) / "clone"
            try:
                Repo.clone_from(url, clone_dir, branch=self.branch, env=self._git_env()).close()
            except GitCommandError as exc:
                raise self._fail("clone", exc) from exc
            self.root.mkdir(parents=True, exist_ok=True)
            shutil.move(str(clone_dir / ".git"), str(self.root / ".git"))
        repo = self._open_repo()
        tracked = repo.git.ls_tree("-r", "--name-only", "HEAD").splitlines()
        missing = [rel for rel in tracked if rel and not (self.root / rel).exists()]
        if missing:
            repo.git.checkout("HEAD", "--", *missing)
        return repo

    def _dirty(self, repo: Repo) -> tuple[list[str], list[str]]:
        """Changed tracked paths and untracked paths, without lock files and git internals."""
        changed: set[str] = set()
        for diff in (
            repo.index.diff(None),
            repo.index.diff("HEAD") if repo.head.is_valid() else [],
        ):
            for item in diff:
                path = item.a_path or item.b_path
                if path:
                    changed.add(str(path))
        changed_paths = sorted(p for p in changed if not self._is_never_published(p))
        untracked = sorted(p for p in repo.untracked_files if not self._is_never_published(p))
        return changed_paths, untracked

    def _remote_ref_name(self, repo: Repo) -> str | None:
        name = f"origin/{self.branch}"
        try:
            repo.commit(name)
        except Exception:
            return None
        return name

    def _unpushed(self, repo: Repo) -> int:
        remote = self._remote_ref_name(repo)
        if remote is None or not repo.head.is_valid():
            return 0
        return sum(1 for _ in repo.iter_commits(f"{remote}..HEAD"))

    def _behind(self, repo: Repo) -> bool:
        remote = self._remote_ref_name(repo)
        if remote is None or not repo.head.is_valid():
            return False
        return any(True for _ in repo.iter_commits(f"HEAD..{remote}"))

    @staticmethod
    def _short(sha: str | None) -> str | None:
        return sha[:8] if sha else None

    def _stage(self, repo: Repo, root: Path, rels: list[str]) -> bool:
        """Stage exactly ``rels`` (additions, edits, deletions); True when something changed."""
        existing = [rel for rel in rels if (root / rel).exists()]
        if existing:
            repo.git.add("--", *existing)
        for rel in rels:
            if rel in existing:
                continue
            try:
                repo.git.rm("--cached", "--quiet", "--", rel)
            except GitCommandError:
                continue
        if repo.head.is_valid():
            return bool(repo.index.diff("HEAD"))
        return bool(repo.index.entries)

    def _commit_paths(self, repo: Repo, rels: list[str], message: str) -> str | None:
        """Stage exactly ``rels`` and commit; returns the new commit or None if unchanged."""
        if not self._stage(repo, self.root, rels):
            return None
        commit = repo.index.commit(
            format_machine_commit_message(message, now_iso()), author=BOT_ACTOR, committer=BOT_ACTOR
        )
        return commit.hexsha

    def _try_push(self, repo: Repo) -> Exception | None:
        try:
            results = repo.remotes.origin.push(refspec=f"HEAD:{self.branch}")
            results.raise_if_error()
        except Exception as exc:
            return exc
        return None

    def _rebase_onto_remote(self, repo: Repo) -> None:
        try:
            repo.remotes.origin.fetch()
            repo.git.rebase("--autostash", f"origin/{self.branch}")
        except GitCommandError as rebase_error:
            with contextlib.suppress(GitCommandError):
                repo.git.rebase("--abort")
            raise self._fail("rebase", rebase_error) from rebase_error

    def _push_with_rebase(self, repo: Repo) -> None:
        """Push HEAD; on rejection fetch and rebase the local commits over the remote.

        Owned paths are disjoint between sessions, so the rebase has nothing to merge.
        ``--autostash`` keeps unrelated unpublished edits in the working tree intact.
        """
        last: Exception | None = None
        for attempt in range(PUSH_ATTEMPTS):
            last = self._try_push(repo)
            if last is None:
                return
            logger.info(
                "Push rejected (attempt %d/%d); rebasing onto origin/%s",
                attempt + 1,
                PUSH_ATTEMPTS,
                self.branch,
            )
            self._rebase_onto_remote(repo)
        assert last is not None
        raise self._fail("push", last)

    # --- Operations -------------------------------------------------------------------

    def status(self) -> RepoStatus:
        """Describe the root: mode, layout, head, dirty paths and remote state."""
        status = RepoStatus(
            mode=self.mode,
            layout=self.layout.kind if self.layout is not None else None,
            root=str(self.root),
            layout_version=self.layout.version if self.layout is not None else None,
            manifest_present=self.layout is not None and self.layout.manifest_path.is_file(),
            schemas_status=schemas_status(self.layout) if self.layout is not None else None,
            review_required=self.settings.review_required,
        )
        if not (self.root / ".git").exists():
            return status
        status.is_git_repo = True
        try:
            repo = self._open_repo()
            if repo.head.is_valid():
                status.head = self._short(repo.head.commit.hexsha)
                message = repo.head.commit.message
                status.head_message = (
                    message if isinstance(message, str) else message.decode("utf-8")
                ).strip()
            try:
                status.branch = repo.active_branch.name
            except TypeError:
                status.branch = None
            status.changed_paths, status.untracked_paths = self._dirty(repo)
            # Status never mutates the repository: it fetches only an existing origin.
            if self.mode is RepoMode.GITHUB and "origin" in [r.name for r in repo.remotes]:
                try:
                    repo.remotes.origin.fetch()
                except Exception as exc:
                    logger.debug("Could not fetch remote for status: %s", self._mask(str(exc)))
            status.unpushed_commits = self._unpushed(repo)
            status.has_remote_updates = self._behind(repo)
        except Exception as exc:
            logger.warning("Could not read repository status: %s", self._mask(str(exc)))
        return status

    def pull(self, *, force: bool = False) -> str | None:
        """Bring the root up to date with the remote; returns the new head commit.

        ``github`` mode publishes unpushed owned changes first and refuses with
        :class:`DirtySharedFiles` when other files are dirty, unless ``force`` discards
        them. The other modes do nothing and return the current head.
        """
        return self.sync(force=force).commit

    def sync(self, *, force: bool = False) -> SyncResult:
        """Publish unpushed owned changes, then pull; the detailed form of :meth:`pull`."""
        result = SyncResult(mode=self.mode)
        if self.mode is not RepoMode.GITHUB:
            if (self.root / ".git").exists():
                repo = self._open_repo()
                if repo.head.is_valid():
                    result.commit = self._short(repo.head.commit.hexsha)
            return result
        with self._lock():
            repo = self._ensure_clone()
            try:
                repo.remotes.origin.fetch()
            except GitCommandError as exc:
                raise self._fail("fetch", exc) from exc
            changed, untracked = self._dirty(repo)
            dirty = [*changed, *untracked]
            owned = [rel for rel in dirty if self._is_owned_rel(rel)]
            blocking = [rel for rel in dirty if rel not in owned]
            if blocking and not force:
                raise DirtySharedFiles(blocking)
            if owned:
                try:
                    commit = self._commit_paths(repo, owned, PUBLISH_LOCAL_MESSAGE)
                except GitCommandError as exc:
                    raise self._fail("commit", exc) from exc
                if commit is not None:
                    result.published = owned
            if self._unpushed(repo):
                self._push_with_rebase(repo)
                if result.published:
                    result.published_commit = self._short(repo.head.commit.hexsha)
            before = repo.head.commit.hexsha if repo.head.is_valid() else None
            try:
                repo.git.reset("--hard", f"origin/{self.branch}")
                if force:
                    repo.git.clean("-fd", "-e", "*.lock")
            except GitCommandError as exc:
                raise self._fail("reset", exc) from exc
            result.commit = self._short(repo.head.commit.hexsha)
            result.changed = before != repo.head.commit.hexsha
        if result.published:
            self._record(
                None, result.published, PUBLISH_LOCAL_MESSAGE, result.published_commit, "publish"
            )
        return result

    def publish_owned(
        self, paths: Iterable[Path | str], message: str, *, chip_id: str | None = None
    ) -> PublishResult:
        """Record and, where the mode allows, commit and push owned files.

        With ``review_required`` the files go through :meth:`propose` instead of a direct
        push, so the result carries the pull request URL.
        """
        rels = self._owned_relpaths(paths)
        if not rels:
            raise ValueError("No configuration files to publish")
        if self.mode is RepoMode.GITHUB and self.settings.review_required:
            proposed = self.propose(rels, message, chip_id=chip_id)
            return PublishResult(
                mode=self.mode,
                paths=rels,
                message=message,
                commit=proposed.commit,
                changed=proposed.changed,
                pr_url=proposed.pr_url,
            )
        result = PublishResult(mode=self.mode, paths=rels, message=message)
        if self.mode is RepoMode.PLAIN:
            self._record(chip_id, rels, message, None, "publish")
            return result
        with self._lock():
            repo = self._ensure_clone() if self.mode is RepoMode.GITHUB else self._open_repo()
            try:
                commit = self._commit_paths(repo, rels, message)
            except GitCommandError as exc:
                raise self._fail("commit", exc) from exc
            if self.mode is RepoMode.GITHUB and (commit is not None or self._unpushed(repo)):
                self._push_with_rebase(repo)
            result.changed = commit is not None
            result.commit = self._short(repo.head.commit.hexsha) if repo.head.is_valid() else None
        if result.changed:
            self._record(chip_id, rels, message, result.commit, "publish")
        return result

    def upsert_shared(
        self,
        entries: Mapping[str, Mapping[str, Any]],
        message: str,
        *,
        chip_id: str | None = None,
    ) -> PublishResult:
        """Replace top-level keys of shared catalog files; ``None`` removes a key.

        ``entries`` maps a shared file name (``system.yaml``) to ``{key: value}``.
        Other keys of the file and its comments are preserved. In ``github`` mode the
        edit is applied to a fresh clone and pushed, so a stale local root cannot
        overwrite another instance's entries; the local root is then pulled.
        """
        if self.layout is None or self.layout.kind is not LayoutKind.SHARED:
            raise ConfigRepositoryError("Shared catalog files exist only in the shared layout")
        for name in entries:
            if name not in SHARED_FILES:
                raise ValueError(f"Not a shared configuration file: {name}")
        config_rel = self.relpath(self.layout.config_dir())
        rels = [f"{config_rel}/{name}" for name in entries]
        result = PublishResult(mode=self.mode, paths=rels, message=message)

        def apply(root: Path) -> None:
            for name, keys in entries.items():
                self._upsert_yaml_keys(root / config_rel / name, keys)

        if self.mode is RepoMode.PLAIN:
            apply(self.root)
        elif self.mode is RepoMode.LOCAL_GIT:
            with self._lock():
                repo = self._open_repo()
                apply(self.root)
                commit = self._commit_paths(repo, rels, message)
                result.changed = commit is not None
                result.commit = self._short(commit)
        else:
            result.commit, result.changed = self._push_from_fresh_clone(rels, message, apply)
            try:
                self.sync()
            except DirtySharedFiles as exc:
                logger.warning(
                    "Shared files are edited locally (%s); applying the upsert to the local copy",
                    ", ".join(exc.paths),
                )
                apply(self.root)
        if result.changed:
            self._record(chip_id, rels, message, result.commit, "upsert")
        return result

    def _push_from_fresh_clone(
        self,
        rels: list[str],
        message: str,
        apply: Callable[[Path], None],
        *,
        branch_name: str | None = None,
    ) -> tuple[str | None, bool]:
        """Apply ``apply`` in a fresh clone and push; retried from scratch on rejection."""
        url = self.settings.repo_url
        assert url is not None
        last: Exception | None = None
        for _attempt in range(PUSH_ATTEMPTS):
            with TemporaryDirectory(prefix="qdash-config-push-") as directory:
                clone = Path(directory) / "clone"
                try:
                    repo = Repo.clone_from(
                        url, clone, branch=self.branch, depth=1, env=self._git_env()
                    )
                except GitCommandError as exc:
                    raise self._fail("clone", exc) from exc
                with repo:
                    if branch_name:
                        repo.git.checkout("-b", branch_name)
                    apply(clone)
                    if not self._stage(repo, clone, rels):
                        return self._short(repo.head.commit.hexsha), False
                    commit = repo.index.commit(
                        format_machine_commit_message(message, now_iso()),
                        author=BOT_ACTOR,
                        committer=BOT_ACTOR,
                    )
                    target = branch_name or self.branch
                    try:
                        results = repo.remotes.origin.push(refspec=f"HEAD:{target}")
                        results.raise_if_error()
                        return self._short(commit.hexsha), True
                    except Exception as exc:
                        last = exc
                        if branch_name:
                            break
                        logger.info("Push of shared files rejected; retrying from a fresh clone")
        assert last is not None
        raise self._fail("push", last)

    def propose(
        self,
        paths: Iterable[Path | str],
        message: str,
        title: str | None = None,
        *,
        chip_id: str | None = None,
    ) -> ProposeResult:
        """Open a pull request holding only ``paths``; other modes commit or record."""
        rels: list[str] = []
        for path in paths:
            rel = self.relpath(path)
            if self._is_never_published(rel) or rel in rels:
                continue
            rels.append(rel)
        if not rels:
            raise ValueError("No configuration files to propose")
        title = title or message
        result = ProposeResult(mode=self.mode, paths=rels, message=message)
        if self.mode is RepoMode.PLAIN:
            self._record(chip_id, rels, title, None, "propose")
            return result
        if self.mode is RepoMode.LOCAL_GIT:
            with self._lock():
                repo = self._open_repo()
                try:
                    commit = self._commit_paths(repo, rels, message)
                except GitCommandError as exc:
                    raise self._fail("commit", exc) from exc
            result.changed = commit is not None
            result.commit = self._short(commit)
            if result.changed:
                self._record(chip_id, rels, title, result.commit, "propose")
            return result

        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
        branch_name = f"{self.label}-update/{stamp}-{uuid.uuid4().hex[:6]}"
        root = self.root

        def apply(clone: Path) -> None:
            for rel in rels:
                source = root / rel
                target = clone / rel
                if source.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                elif target.exists():
                    target.unlink()

        commit, changed = self._push_from_fresh_clone(rels, message, apply, branch_name=branch_name)
        result.commit, result.changed = commit, changed
        if not changed:
            return result
        result.branch = branch_name
        body = (
            f"{self.label.capitalize()} update from QDash\n\n"
            f"- Commit: `{commit}`\n- Timestamp: {now_iso()}\n- Files: {', '.join(rels)}\n"
        )
        result.pr_url, result.pr_number = self._create_pull_request(
            self.settings, head=branch_name, base=self.branch, title=title, body=body
        )
        self._record(chip_id, rels, title, commit, "propose")
        return result

    # --- Helpers ----------------------------------------------------------------------

    def _record(
        self, chip_id: str | None, rels: list[str], message: str, commit: str | None, kind: str
    ) -> None:
        try:
            self.change_log.record(
                chip_id=chip_id,
                paths=rels,
                message=message,
                actor=self.actor,
                mode=self.mode.value,
                commit=commit,
                summary=f"{kind}: {len(rels)} file(s)",
            )
        except Exception as exc:  # an observer must never undo a write
            logger.warning("Could not record configuration change: %s", exc)

    @staticmethod
    def _upsert_yaml_keys(path: Path, keys: Mapping[str, Any]) -> None:
        from ruamel.yaml import YAML

        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.width = 4096
        data: Any = None
        if path.exists():
            with path.open(encoding="utf-8") as f:
                data = yaml.load(f)
        if data is None:
            from ruamel.yaml.comments import CommentedMap

            data = CommentedMap()
        if not isinstance(data, MutableMapping):
            raise ConfigRepositoryError(f"{path.name} is not a mapping at the top level")
        for key, value in keys.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            yaml.dump(data, f)
        tmp.replace(path)


def get_config_repository(
    layout: QubexLayout | Path | None = None,
    *,
    actor: str = "system",
    settings: GitHubSettings | None = None,
    label: str = "config",
) -> ConfigRepository:
    """Build a repository over the detected layout (default: the resolved config root)."""
    if layout is None:
        layout = QubexLayout.detect()
    return ConfigRepository(layout, settings, actor=actor, label=label)
