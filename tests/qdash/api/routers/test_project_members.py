"""Tests for project member management endpoints."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pymongo.database import Database as PyMongoDatabase
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument


@pytest.fixture
def project_with_members(init_db: PyMongoDatabase[Any]) -> ProjectDocument:
    """Create a project with owner, editor, viewer, and candidate users."""
    users = [
        ("owner", "owner-token"),
        ("editor", "editor-token"),
        ("viewer", "viewer-token"),
        ("candidate", "candidate-token"),
    ]
    user_ids: dict[str, str] = {}
    for username, token in users:
        user = UserDocument(
            username=username,
            display_name=username.title(),
            organization="Project Org",
            avatar_key="planet",
            hashed_password="hashed",
            access_token=token,
            default_project_id="project-1",
            system_info=SystemInfoModel(),
        )
        user.insert()
        assert user.user_id is not None
        user_ids[username] = user.user_id

    project = ProjectDocument(
        project_id="project-1",
        name="Project 1",
        owner_user_id=user_ids["owner"],
        owner_username="owner",
    )
    project.insert()

    for username, role in [
        ("owner", ProjectRole.OWNER),
        ("editor", ProjectRole.EDITOR),
        ("viewer", ProjectRole.VIEWER),
    ]:
        ProjectMembershipDocument(
            project_id="project-1",
            user_id=user_ids[username],
            username=username,
            role=role,
            status="active",
            invited_by_user_id=user_ids["owner"],
            invited_by="owner",
        ).insert()

    return project


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_owner_can_invite_project_member_as_editor(
    test_client: TestClient,
    project_with_members: ProjectDocument,
) -> None:
    """Project owners can add editors to their project."""
    response = test_client.post(
        "/projects/project-1/members",
        headers=_headers("owner-token"),
        json={"username": "candidate", "role": "editor"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "candidate"
    assert data["role"] == "editor"


def test_list_project_members_includes_display_metadata(
    test_client: TestClient,
    project_with_members: ProjectDocument,
) -> None:
    """Project member listings include display metadata for mentions."""
    response = test_client.get(
        "/projects/project-1/members",
        headers=_headers("owner-token"),
    )

    assert response.status_code == 200
    data = response.json()
    owner = next(member for member in data["members"] if member["username"] == "owner")
    assert owner["display_name"] == "Owner"
    assert owner["organization"] == "Project Org"
    assert owner["avatar_key"] == "planet"


def test_owner_cannot_invite_member_as_owner(
    test_client: TestClient,
    project_with_members: ProjectDocument,
) -> None:
    """Owner role assignment must use ownership transfer."""
    response = test_client.post(
        "/projects/project-1/members",
        headers=_headers("owner-token"),
        json={"username": "candidate", "role": "owner"},
    )

    assert response.status_code == 400
    assert "ownership transfer" in response.json()["detail"]


def test_owner_can_update_viewer_to_editor(
    test_client: TestClient,
    project_with_members: ProjectDocument,
) -> None:
    """Project owners can change non-owner members between viewer and editor."""
    response = test_client.patch(
        "/projects/project-1/members/viewer",
        headers=_headers("owner-token"),
        json={"role": "editor"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "editor"


def test_editor_cannot_update_project_member_role(
    test_client: TestClient,
    project_with_members: ProjectDocument,
) -> None:
    """Editors cannot manage project membership."""
    response = test_client.patch(
        "/projects/project-1/members/viewer",
        headers=_headers("editor-token"),
        json={"role": "editor"},
    )

    assert response.status_code == 403


def test_owner_can_remove_project_member(
    test_client: TestClient,
    project_with_members: ProjectDocument,
) -> None:
    """Project owners can remove non-owner members."""
    response = test_client.delete(
        "/projects/project-1/members/viewer",
        headers=_headers("owner-token"),
    )

    assert response.status_code == 204
