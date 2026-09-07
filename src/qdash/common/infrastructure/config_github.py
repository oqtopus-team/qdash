"""Publish verified configuration files without modifying the live working tree."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote, urlsplit, urlunsplit

from git import Repo

from qdash.common.utils.commit_message import format_machine_commit_message
from qdash.common.utils.datetime import now_iso


def config_github_credentials_available() -> bool:
    """Match the workflow's configuration repository credential requirements."""
    return all(os.getenv(key) for key in ("GITHUB_USER", "GITHUB_TOKEN", "CONFIG_REPO_URL"))


def push_config_files(files: dict[str, bytes], message: str, branch: str = "main") -> str:
    """Publish an immutable file snapshot in one commit and check remote acceptance."""
    if not files:
        raise ValueError("No configuration files to push")
    for name in files:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Invalid configuration repository path")
    if not config_github_credentials_available():
        raise RuntimeError("Configuration repository credentials are incomplete")
    parsed = urlsplit(os.environ["CONFIG_REPO_URL"])
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("CONFIG_REPO_URL must be an HTTPS repository URL")
    user = quote(os.environ["GITHUB_USER"], safe="")
    token = quote(os.environ["GITHUB_TOKEN"], safe="")
    auth_url = urlunsplit((parsed.scheme, f"{user}:{token}@{parsed.netloc}", parsed.path, "", ""))
    try:
        with (
            TemporaryDirectory(prefix="qdash-config-push-") as directory,
            Repo.clone_from(
                auth_url, directory, branch=branch, depth=1, kill_after_timeout=30
            ) as repo,
        ):
            for name, content in files.items():
                target = Path(directory) / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            repo.index.add(list(files))
            if not repo.index.diff("HEAD"):
                return str(repo.head.commit.hexsha)
            repo.git.config("user.name", "github-actions[bot]")
            repo.git.config("user.email", "github-actions[bot]@users.noreply.github.com")
            repo.index.commit(format_machine_commit_message(message, now_iso()))
            results = repo.remotes.origin.push(kill_after_timeout=30)
            if not results:
                raise RuntimeError("No push result returned")
            results.raise_if_error()
            return str(repo.head.commit.hexsha)
    except Exception:
        # Git errors can contain the authenticated URL; never expose credentials.
        raise RuntimeError(
            "GitHub synchronization failed; check repository access and retry"
        ) from None
