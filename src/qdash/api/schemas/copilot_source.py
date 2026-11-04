"""Schemas for the Copilot's read-only source access."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SourceRootResponse(BaseModel):
    """One source tree the Copilot can search and read."""

    name: str = Field(description="Root name used by search and read, such as qdash or qubex")
    kind: str = Field(description="qdash or dependency")
    version: str | None = Field(default=None, description="Installed package version, if known")
    revision: str | None = Field(
        default=None, description="Commit of the served source, when it can be established"
    )
    revision_source: str | None = Field(
        default=None,
        description="Where the revision came from: git, direct_url.json or QDASH_SOURCE_REVISION",
    )
    dirty: bool | None = Field(
        default=None, description="The git checkout has uncommitted changes (git revisions only)"
    )


class ListSourceRootsResponse(BaseModel):
    """The source trees available to this QDash API."""

    roots: list[SourceRootResponse]
    missing_dependencies: list[str] = Field(
        default_factory=list,
        description="Allowlisted dependencies whose source is not installed here",
    )
    execution_revision_recorded: bool = Field(
        default=False,
        description=(
            "Whether executions record the source revision they ran with. QDash does not "
            "record it, so a match between served source and an execution cannot be established."
        ),
    )


class SourceSearchMatch(BaseModel):
    """One search hit; ``line`` and ``text`` are null for a path search."""

    root: str
    path: str
    line: int | None = None
    text: str | None = None


class SearchSourceResponse(BaseModel):
    """Matches of a literal source search."""

    query: str
    mode: str
    matches: list[SourceSearchMatch]
    truncated: bool = Field(description="The search stopped at the result or file limit")


class SourceFileResponse(BaseModel):
    """A line range of one source file, each line prefixed with its number."""

    root: str
    path: str
    start_line: int
    end_line: int
    total_lines: int
    content: str
    truncated: bool = Field(description="More lines follow the returned range")
    revision: str | None = None
