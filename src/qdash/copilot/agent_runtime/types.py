"""Shared runtime type aliases for Copilot agent execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

ToolExecutor = Callable[[dict[str, Any]], Any]
ToolExecutors = dict[str, ToolExecutor]
StoredToolKey = str | Callable[[dict[str, Any]], str]
OnToolCallHook = Callable[[str, dict[str, Any]], Awaitable[None]] | None
OnStatusHook = Callable[[str], Awaitable[None]] | None
