"""Typed event payloads emitted by workflow authoring agents."""

from __future__ import annotations

from typing import Literal, TypedDict


class SummaryDeltaEvent(TypedDict):
    """Incremental assistant summary text."""

    type: Literal["summary_delta"]
    delta: str


class DiffEvent(TypedDict):
    """Latest unified diff produced by the agent runtime."""

    type: Literal["diff"]
    diff: str


class StatusEvent(TypedDict):
    """Progress status emitted by the agent runtime."""

    type: Literal["status"]
    stage: str
    message: str


class CompleteEvent(TypedDict):
    """Final event emitted after the edited workflow has been validated."""

    type: Literal["complete"]
    code: str
    summary: str
    diff: str
    command: list[str]


AgentEvent = StatusEvent | SummaryDeltaEvent | DiffEvent | CompleteEvent
