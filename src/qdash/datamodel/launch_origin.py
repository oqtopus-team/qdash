"""How a caller says it started a run: a client report, never an authority.

QDash authenticates the user behind a request, not the program that sent it. An agent host
runs its tools with the signed-in user's own token, so the API cannot tell a pipeline started
by an agent tool from one the user started with the same token. A caller may therefore report
its origin with the request. QDash stores the report as given and shows it as reported: it
never verifies it, never treats it as an agent session link, and it grants nothing. The user
the request authenticated stays the one responsible for the run.

A run without a report is shown as before, with no origin claim.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class LaunchSource(StrEnum):
    """What a caller reports started a run.

    ``agent_tool``: a tool of an agent host, such as pi-qdash's ``qdash_run_pipeline``, made
    the request with the user's sign-in after the user approved it.
    """

    AGENT_TOOL = "agent_tool"


class ReportedLaunchOrigin(BaseModel):
    """A caller's own account of how a run was started; client reported, not verified."""

    model_config = ConfigDict(extra="forbid")

    source: LaunchSource
    tool: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_.:-]+$",
        description="The tool that made the request, such as qdash_run_pipeline",
    )
    client: str = Field(
        default="",
        max_length=100,
        pattern=r"^[A-Za-z0-9_.:@/ -]*$",
        description="The host or package that reports it, such as pi-qdash; empty when unnamed",
    )
