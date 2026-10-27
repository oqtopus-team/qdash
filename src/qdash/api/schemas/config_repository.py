"""Schemas for the configuration repository endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConfigRepositoryStatus(BaseModel):
    """State of the Qubex configuration root and its repository."""

    mode: str = Field(..., description="github, local-git or plain")
    layout: str | None = Field(default=None, description="shared or legacy Qubex layout")
    layout_version: str | None = Field(
        default=None, description="qubex-config layout version: 1.0 (legacy) or 2.0 (shared)"
    )
    manifest_present: bool = Field(
        default=False, description="Whether <root>/qubex-config.json declares the version"
    )
    schemas_status: str | None = Field(
        default=None,
        description="match, differs or absent: the tree's schemas/ copy versus the schemas QDash ships",
    )
    root: str = Field(..., description="Configuration root on the API host")
    is_git_repo: bool = False
    branch: str | None = None
    head: str | None = Field(default=None, description="Short SHA of the local head")
    head_message: str | None = None
    changed_paths: list[str] = Field(default_factory=list)
    untracked_paths: list[str] = Field(default_factory=list)
    unpushed_commits: int = 0
    has_remote_updates: bool = False
    review_required: bool = False


class ConfigRepositorySyncRequest(BaseModel):
    """Options for a synchronization."""

    force: bool = Field(
        default=False, description="Discard local edits to shared files instead of refusing"
    )


class ConfigRepositorySyncResult(BaseModel):
    """What a synchronization published and pulled."""

    mode: str
    commit: str | None = Field(default=None, description="Head after the pull")
    published: list[str] = Field(default_factory=list, description="Owned files pushed first")
    published_commit: str | None = None
    changed: bool = Field(default=False, description="Whether the pull moved the head")
    message: str = ""
