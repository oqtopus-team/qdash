"""Shared pytest gate for tests that execute code in the OS-isolated sandbox.

The Copilot Python sandbox is fail-closed: it needs bubblewrap plus working user and
network namespaces. Some CI runners allow the namespaces but deny configuring loopback
("bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted"), so availability is
probed by actually running a trivial analysis rather than only checking for the binary.
"""

from __future__ import annotations

import asyncio
import functools

import pytest


@functools.lru_cache(maxsize=1)
def sandbox_available() -> bool:
    """Whether the OS sandbox can actually run in this environment."""
    from qdash.copilot.tooling import sandbox
    from qdash.copilot.tooling.sandbox import execute_python_analysis

    if sandbox._bwrap_path() is None:
        return False
    result = asyncio.run(execute_python_analysis('result = {"output": "ok"}'))
    return result.get("output") == "ok"


requires_sandbox = pytest.mark.skipif(
    not sandbox_available(),
    reason="OS sandbox (bubblewrap + user/network namespaces) is unavailable here",
)
