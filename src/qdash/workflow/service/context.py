"""Validated execution context for calibration workflows.

A calibration runs as one user, on one chip, inside one project, on one
backend. QDash checks them once, authorizing the user the same way the API
does, and every session of the run inherits the checked result:

- ``CalibService(username, chip_id, project_id=...)`` resolves the context from
  the parameters the API injects into a Prefect flow.
- :func:`resolve_calib_context` resolves it for direct Python use; pass the
  result to ``CalibService.from_context``.

A context cannot be built from arbitrary strings: :class:`CalibContext` only
comes out of the resolver, which requires an active user with write permission
on the project (an editor or owner membership, or project ownership).
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)

# Only the resolver holds this token, so a context is never built unchecked.
_RESOLVED = object()


class CalibContextError(PermissionError):
    """The user, project or permission of a calibration context is not valid."""


@dataclass(frozen=True)
class CalibContext:
    """The user, chip, project and backend a calibration runs as.

    Obtain one from :func:`resolve_calib_context`; direct construction is
    rejected so an unchecked project cannot reach the workflow.
    """

    username: str
    chip_id: str
    project_id: str
    backend_name: str
    _token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _RESOLVED:
            raise TypeError(
                "CalibContext is created by resolve_calib_context(username, chip_id, "
                "project_id=...), which checks the user's project permission"
            )


class AccessDecision(enum.Enum):
    """Outcome of a write-permission check."""

    GRANTED = "granted"
    UNKNOWN_USER = "unknown_user"
    DISABLED_USER = "disabled_user"
    UNKNOWN_PROJECT = "unknown_project"
    DENIED = "denied"


class ProjectAccessDirectory(Protocol):
    """Lookups the resolver needs; the Mongo implementation is the default."""

    def default_project_id(self, username: str) -> str | None:
        """Return the user's default project, if one is set."""
        ...

    def write_access(self, username: str, project_id: str) -> AccessDecision:
        """Decide whether the user may run calibrations in the project."""
        ...


class MongoProjectAccessDirectory:
    """Apply the API's project permission rule to MongoDB documents."""

    def default_project_id(self, username: str) -> str | None:
        from qdash.repository import MongoUserRepository

        return MongoUserRepository().get_default_project_id(username)

    def write_access(self, username: str, project_id: str) -> AccessDecision:
        from qdash.datamodel.project import ProjectPermission, role_has_permission
        from qdash.repository.project import MongoProjectRepository
        from qdash.repository.project_membership import MongoProjectMembershipRepository
        from qdash.repository.user import MongoUserRepository

        user = MongoUserRepository().find_by_username(username)
        if user is None:
            return AccessDecision.UNKNOWN_USER
        if user.disabled:
            return AccessDecision.DISABLED_USER
        project = MongoProjectRepository().find_by_id(project_id)
        if project is None:
            return AccessDecision.UNKNOWN_PROJECT
        membership = MongoProjectMembershipRepository().get_active_membership(
            project_id, username, user.user_id
        )
        if membership is not None:
            allowed = role_has_permission(membership.role, ProjectPermission.WRITE)
        else:
            allowed = bool(user.user_id) and project.owner_user_id == user.user_id
        return AccessDecision.GRANTED if allowed else AccessDecision.DENIED


class CalibContextResolver:
    """Resolve and check a calibration context against a project directory."""

    def __init__(self, directory: ProjectAccessDirectory | None = None) -> None:
        self._directory = directory or MongoProjectAccessDirectory()

    def resolve(
        self,
        username: str,
        chip_id: str,
        *,
        project_id: str | None = None,
        backend: str | None = None,
    ) -> CalibContext:
        """Return the checked context or raise :class:`CalibContextError`."""
        from qdash.common.config.backend import get_available_backends, get_default_backend

        backend_name = backend or get_default_backend()
        available = get_available_backends()
        if available and backend_name not in available:
            raise CalibContextError(
                f"Backend '{backend_name}' is not configured; available: {', '.join(available)}"
            )
        if not isinstance(username, str) or not username.strip():
            raise CalibContextError("username is required")
        if not isinstance(chip_id, str) or not chip_id.strip():
            raise CalibContextError("chip_id is required")
        if project_id is None:
            project_id = self._directory.default_project_id(username)
            if not project_id:
                raise CalibContextError(
                    f"Could not resolve project_id for user={username}. "
                    "default_project_id is not set. Either provide project_id explicitly "
                    "or ensure user has default_project_id set."
                )
            logger.info("Auto-resolved project_id=%s from user=%s", project_id, username)
        decision = self._directory.write_access(username, project_id)
        if decision is not AccessDecision.GRANTED:
            raise CalibContextError(_access_message(decision, username, project_id))
        return CalibContext(username, chip_id, project_id, backend_name, _RESOLVED)


def _access_message(decision: AccessDecision, username: str, project_id: str) -> str:
    if decision is AccessDecision.UNKNOWN_USER:
        return f"User '{username}' does not exist"
    if decision is AccessDecision.DISABLED_USER:
        return f"User '{username}' is disabled"
    if decision is AccessDecision.UNKNOWN_PROJECT:
        return f"Project '{project_id}' not found"
    return (
        f"User '{username}' cannot run calibrations in project '{project_id}'; "
        "an editor or owner role is required"
    )


def resolve_calib_context(
    username: str,
    chip_id: str,
    *,
    project_id: str | None = None,
    backend: str | None = None,
) -> CalibContext:
    """Resolve the context of a calibration run from QDash's user and project records.

    Args:
        username: User the run is attributed to.
        chip_id: Chip to calibrate.
        project_id: Project of the run. Defaults to the user's default project.
        backend: Backend to run on, such as ``"fake"``. Defaults to the
            configured default backend.

    Raises:
        CalibContextError: The user or project does not exist, the user is
            disabled, the user lacks editor or owner permission on the project,
            or the backend is not configured.

    Example:
        ```python
        from qdash.workflow import CalibService, resolve_calib_context

        context = resolve_calib_context("alice", "64Qv3")
        CalibService.from_context(context).run(targets, steps=[...])
        ```
    """
    return CalibContextResolver().resolve(username, chip_id, project_id=project_id, backend=backend)
