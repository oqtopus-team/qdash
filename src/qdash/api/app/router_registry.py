"""Router registration for the QDash API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI

if TYPE_CHECKING:
    from fastapi.routing import APIRouter

from qdash.api.lib.auth import get_current_active_user
from qdash.api.routers import (
    admin,
    agent_session,
    auth,
    backend,
    calibration,
    chip,
    config,
    cooldown,
    cooldown_wiring_event,
    copilot,
    cryostat,
    dashboard,
    device_topology,
    execution,
    file,
    flow,
    forum,
    issue,
    issue_knowledge,
    metrics,
    note,
    notification,
    project,
    provenance,
    settings,
    tag,
    task,
    task_file,
    task_result,
    topology,
)


@dataclass(frozen=True, slots=True)
class RouterRegistration:
    """Configuration for a router mounted on the API app."""

    router: APIRouter
    tags: tuple[str, ...]
    prefix: str | None = None
    requires_auth: bool = True


PUBLIC_ROUTERS: tuple[RouterRegistration, ...] = (
    RouterRegistration(auth.router, tags=("auth",), requires_auth=False),
    RouterRegistration(admin.router, tags=("admin",), requires_auth=False),
    RouterRegistration(project.router, tags=("projects",), requires_auth=False),
    RouterRegistration(execution.router, tags=("execution",), requires_auth=False),
    RouterRegistration(file.router, tags=("file",), requires_auth=False),
    RouterRegistration(
        copilot.public_router,
        prefix="/copilot",
        tags=("copilot",),
        requires_auth=False,
    ),
    RouterRegistration(issue.public_router, tags=("issue",), requires_auth=False),
    RouterRegistration(forum.public_router, tags=("forum",), requires_auth=False),
)

PROTECTED_ROUTERS: tuple[RouterRegistration, ...] = (
    RouterRegistration(agent_session.router, tags=("agent-session",)),
    RouterRegistration(calibration.router, tags=("calibration",)),
    RouterRegistration(copilot.router, prefix="/copilot", tags=("copilot",)),
    RouterRegistration(settings.router, tags=("settings",)),
    RouterRegistration(chip.router, tags=("chip",)),
    RouterRegistration(task.router, tags=("task",)),
    RouterRegistration(task_file.router, tags=("task-file",)),
    RouterRegistration(task_result.router, tags=("task-result",)),
    RouterRegistration(forum.router, tags=("forum",)),
    RouterRegistration(issue.router, tags=("issue",)),
    RouterRegistration(issue_knowledge.router, tags=("issue-knowledge",)),
    RouterRegistration(tag.router, tags=("tag",)),
    RouterRegistration(device_topology.router, tags=("device-topology",)),
    RouterRegistration(backend.router, tags=("backend",)),
    RouterRegistration(flow.router, tags=("flow",)),
    RouterRegistration(metrics.router, prefix="/metrics", tags=("metrics",)),
    RouterRegistration(note.router, tags=("note",)),
    RouterRegistration(notification.router, tags=("notification",)),
    RouterRegistration(cryostat.router, tags=("cryostat",)),
    RouterRegistration(cooldown.router, tags=("cooldown",)),
    RouterRegistration(cooldown_wiring_event.router, tags=("cooldown-wiring",)),
    RouterRegistration(topology.router, prefix="/topology", tags=("topology",)),
    RouterRegistration(config.router, tags=("config",)),
    RouterRegistration(dashboard.router, prefix="/dashboard", tags=("dashboard",)),
    RouterRegistration(provenance.router, prefix="/provenance", tags=("provenance",)),
)


def register_routers(app: FastAPI) -> None:
    """Register all API routers on the FastAPI app."""
    auth_dependency = [Depends(get_current_active_user)]

    for registration in (*PUBLIC_ROUTERS, *PROTECTED_ROUTERS):
        dependencies = auth_dependency if registration.requires_auth else None
        app.include_router(
            registration.router,
            prefix=registration.prefix or "",
            tags=list(registration.tags),
            dependencies=dependencies,
        )
