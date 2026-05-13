"""Tests for project role permission helpers."""

import pytest
from fastapi import HTTPException

from qdash.api.lib.project import _check_permission
from qdash.api.schemas.auth import User
from qdash.datamodel.project import ProjectPermission, ProjectRole, role_has_permission
from qdash.datamodel.user import SystemRole
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument


@pytest.fixture
def project_members(init_db) -> None:
    """Create a project with owner/editor/viewer memberships."""
    project = ProjectDocument(
        project_id="permission-project",
        name="Permission Project",
        owner_user_id="usr_owner",
        owner_username="owner",
    )
    project.insert()

    for username, user_id, role in [
        ("owner", "usr_owner", ProjectRole.OWNER),
        ("editor", "usr_editor", ProjectRole.EDITOR),
        ("viewer", "usr_viewer", ProjectRole.VIEWER),
    ]:
        ProjectMembershipDocument(
            project_id="permission-project",
            user_id=user_id,
            username=username,
            role=role,
            status="active",
            invited_by_user_id="usr_owner",
            invited_by="owner",
        ).insert()


def test_role_has_permission_matrix() -> None:
    """Project roles map to read/write/admin permissions."""
    assert role_has_permission(ProjectRole.VIEWER, ProjectPermission.READ)
    assert not role_has_permission(ProjectRole.VIEWER, ProjectPermission.WRITE)
    assert role_has_permission(ProjectRole.EDITOR, ProjectPermission.WRITE)
    assert not role_has_permission(ProjectRole.EDITOR, ProjectPermission.ADMIN)
    assert role_has_permission(ProjectRole.OWNER, ProjectPermission.ADMIN)


def test_editor_can_write_but_viewer_cannot(project_members) -> None:
    """Operational write permission starts at editor."""
    _, editor_role = _check_permission(
        "permission-project",
        User(username="editor", user_id="usr_editor", default_project_id="permission-project"),
        required_permission=ProjectPermission.WRITE,
    )

    assert editor_role == ProjectRole.EDITOR

    with pytest.raises(HTTPException) as exc_info:
        _check_permission(
            "permission-project",
            User(username="viewer", user_id="usr_viewer", default_project_id="permission-project"),
            required_permission=ProjectPermission.WRITE,
        )

    assert exc_info.value.status_code == 403


def test_owner_can_admin_but_editor_cannot(project_members) -> None:
    """Administrative permission is owner-only."""
    _, owner_role = _check_permission(
        "permission-project",
        User(username="owner", user_id="usr_owner", default_project_id="permission-project"),
        required_permission=ProjectPermission.ADMIN,
    )

    assert owner_role == ProjectRole.OWNER

    with pytest.raises(HTTPException) as exc_info:
        _check_permission(
            "permission-project",
            User(username="editor", user_id="usr_editor", default_project_id="permission-project"),
            required_permission=ProjectPermission.ADMIN,
        )

    assert exc_info.value.status_code == 403


def test_system_admin_cannot_access_project_without_membership(project_members) -> None:
    """System admins need membership for normal project-scoped APIs."""
    with pytest.raises(HTTPException) as exc_info:
        _check_permission(
            "permission-project",
            User(username="admin", user_id="usr_admin", system_role=SystemRole.ADMIN),
            required_permission=ProjectPermission.ADMIN,
        )

    assert exc_info.value.status_code == 403
