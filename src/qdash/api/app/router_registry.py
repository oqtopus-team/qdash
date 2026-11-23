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
    agent,
    agent_session,
    auth,
    backend,
    calibration,
    calibration_pipeline,
    calibration_session,
    chip,
    config,
    cooldown,
    cooldown_wiring_event,
    cryostat,
    dashboard,
    device_topology,
    evaluation,
    execution,
    file,
    flow,
    forum,
    metric_script,
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
    user_avatar,
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
    RouterRegistration(file.router, tags=("file",)),
    RouterRegistration(
        agent.public_router,
        prefix="/agent",
        tags=("agent",),
        requires_auth=False,
    ),
    RouterRegistration(forum.public_router, tags=("forum",), requires_auth=False),
)

PROTECTED_ROUTERS: tuple[RouterRegistration, ...] = (
    RouterRegistration(agent_session.router, tags=("agent-session",)),
    RouterRegistration(calibration.router, tags=("calibration",)),
    RouterRegistration(calibration_pipeline.router, tags=("calibration-pipeline",)),
    RouterRegistration(calibration_session.router, tags=("calibration-session",)),
    RouterRegistration(agent.router, prefix="/agent", tags=("agent",)),
    RouterRegistration(settings.router, tags=("settings",)),
    RouterRegistration(chip.router, tags=("chip",)),
    RouterRegistration(task.router, tags=("task",)),
    RouterRegistration(task_file.router, tags=("task-file",)),
    RouterRegistration(task_result.router, tags=("task-result",)),
    RouterRegistration(evaluation.router, tags=("evaluation",)),
    RouterRegistration(forum.router, tags=("forum",)),
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
    RouterRegistration(dashboard.router, prefix="/dashboards", tags=("dashboard",)),
    RouterRegistration(metric_script.router, prefix="/metric-scripts", tags=("metric-script",)),
    RouterRegistration(topology.router, prefix="/topology", tags=("topology",)),
    RouterRegistration(config.router, tags=("config",)),
    RouterRegistration(provenance.router, prefix="/provenance", tags=("provenance",)),
    RouterRegistration(user_avatar.router, tags=("user-avatar",)),
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
