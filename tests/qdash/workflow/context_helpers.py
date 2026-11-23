"""Grant calibration contexts in tests without MongoDB user and project records."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qdash.workflow.service.context import (
    AccessDecision,
    CalibContext,
    CalibContextResolver,
)

if TYPE_CHECKING:
    import pytest


class GrantingDirectory:
    """Every user may write to every project; the default project is ``test_project``."""

    def __init__(self, default_project_id: str | None = "test_project") -> None:
        self.default = default_project_id
        self.checked: list[tuple[str, str]] = []

    def default_project_id(self, username: str) -> str | None:
        return self.default

    def write_access(self, username: str, project_id: str) -> AccessDecision:
        self.checked.append((username, project_id))
        return AccessDecision.GRANTED


def granted_context(
    username: str = "alice", chip_id: str = "chip-1", project_id: str = "project-1"
) -> CalibContext:
    """A context resolved against a directory that grants access."""
    return CalibContextResolver(GrantingDirectory()).resolve(
        username, chip_id, project_id=project_id
    )


def grant_all_contexts(monkeypatch: pytest.MonkeyPatch) -> GrantingDirectory:
    """Make ``resolve_calib_context`` grant every request; returns the directory."""
    directory = GrantingDirectory()
    monkeypatch.setattr(
        "qdash.workflow.service.context.MongoProjectAccessDirectory", lambda: directory
    )
    return directory
