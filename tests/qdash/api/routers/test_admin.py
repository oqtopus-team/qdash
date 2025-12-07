"""Tests for admin API endpoints."""

import pytest

from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.user import SystemRole
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument


class TestAdminUsersEndpoints:
    """Tests for admin user management endpoints."""

    @pytest.fixture
    def admin_user(self, init_db):
        """Create admin user."""
        user = UserDocument(
            username="admin",
            full_name="Admin User",
            hashed_password="hashed",
            access_token="admin-token",
            disabled=False,
            system_role=SystemRole.ADMIN,
            default_project_id="proj-admin",
            system_info=SystemInfoModel(),
        )
        user.insert()
        yield user

    @pytest.fixture
    def regular_user(self, init_db):
        """Create regular user."""
        user = UserDocument(
            username="regularuser",
            full_name="Regular User",
            hashed_password="hashed",
            access_token="regular-token",
            disabled=False,
            system_role=SystemRole.USER,
            default_project_id=None,
            system_info=SystemInfoModel(),
        )
        user.insert()
        yield user

    @pytest.fixture
    def admin_headers(self):
        """Admin authentication headers."""
        return {"Authorization": "Bearer admin-token"}

    @pytest.fixture
    def user_headers(self):
        """Regular user authentication headers."""
        return {"Authorization": "Bearer regular-token"}

    def test_list_all_users_as_admin(self, test_client, admin_user, regular_user, admin_headers):
        """Admin can list all users."""
        response = test_client.get("/admin/users", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert "total" in data
        assert data["total"] >= 2

    def test_list_all_users_requires_admin(
        self, test_client, admin_user, regular_user, user_headers
    ):
        """Regular users cannot list all users."""
        response = test_client.get("/admin/users", headers=user_headers)
        assert response.status_code == 403

    def test_list_all_users_requires_auth(self, test_client, admin_user):
        """Unauthenticated requests are rejected."""
        response = test_client.get("/admin/users")
        assert response.status_code == 401

    def test_get_user_details(self, test_client, admin_user, regular_user, admin_headers):
        """Admin can get user details."""
        response = test_client.get("/admin/users/regularuser", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "regularuser"
        assert data["full_name"] == "Regular User"
        assert data["system_role"] == "user"

    def test_get_user_details_not_found(self, test_client, admin_user, admin_headers):
        """Returns 404 for non-existent user."""
        response = test_client.get("/admin/users/nonexistent", headers=admin_headers)
        assert response.status_code == 404

    def test_update_user_settings(self, test_client, admin_user, regular_user, admin_headers):
        """Admin can update user settings."""
        response = test_client.put(
            "/admin/users/regularuser",
            headers=admin_headers,
            json={"full_name": "Updated Name"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Updated Name"

    def test_update_user_disable(self, test_client, admin_user, regular_user, admin_headers):
        """Admin can disable a user."""
        response = test_client.put(
            "/admin/users/regularuser",
            headers=admin_headers,
            json={"disabled": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["disabled"] is True

    def test_cannot_demote_last_admin(self, test_client, admin_user, admin_headers):
        """Cannot demote the last admin."""
        response = test_client.put(
            "/admin/users/admin",
            headers=admin_headers,
            json={"system_role": "user"},
        )
        assert response.status_code == 400
        assert "last admin" in response.json()["detail"].lower()

    def test_delete_user(self, test_client, admin_user, regular_user, admin_headers):
        """Admin can delete a user."""
        response = test_client.delete("/admin/users/regularuser", headers=admin_headers)
        assert response.status_code == 200

        # Verify user is deleted
        deleted_user = UserDocument.find_one({"username": "regularuser"}).run()
        assert deleted_user is None

    def test_cannot_delete_self(self, test_client, admin_user, admin_headers):
        """Admin cannot delete themselves."""
        response = test_client.delete("/admin/users/admin", headers=admin_headers)
        assert response.status_code == 400
        assert "own account" in response.json()["detail"].lower()

    def test_cannot_delete_last_admin(self, test_client, admin_user, admin_headers):
        """Cannot delete the last admin."""
        response = test_client.delete("/admin/users/admin", headers=admin_headers)
        assert response.status_code == 400


class TestAdminProjectsEndpoints:
    """Tests for admin project management endpoints."""

    @pytest.fixture
    def admin_user(self, init_db):
        """Create admin user."""
        user = UserDocument(
            username="admin",
            full_name="Admin User",
            hashed_password="hashed",
            access_token="admin-token",
            disabled=False,
            system_role=SystemRole.ADMIN,
            default_project_id="proj-admin",
            system_info=SystemInfoModel(),
        )
        user.insert()
        yield user

    @pytest.fixture
    def project_owner(self, init_db):
        """Create project owner user."""
        user = UserDocument(
            username="projectowner",
            full_name="Project Owner",
            hashed_password="hashed",
            access_token="owner-token",
            disabled=False,
            system_role=SystemRole.USER,
            default_project_id="proj-owner",
            system_info=SystemInfoModel(),
        )
        user.insert()
        yield user

    @pytest.fixture
    def test_project(self, init_db, project_owner):
        """Create test project."""
        project = ProjectDocument(
            project_id="proj-owner",
            name="Owner's Project",
            owner_username="projectowner",
            description="Test project",
            system_info=SystemInfoModel(),
        )
        project.insert()
        yield project

    @pytest.fixture
    def admin_headers(self):
        """Admin authentication headers."""
        return {"Authorization": "Bearer admin-token"}

    @pytest.fixture
    def user_headers(self):
        """Regular user authentication headers."""
        return {"Authorization": "Bearer owner-token"}

    def test_list_all_projects(self, test_client, admin_user, test_project, admin_headers):
        """Admin can list all projects."""
        response = test_client.get("/admin/projects", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_list_projects_requires_admin(
        self, test_client, admin_user, project_owner, test_project, user_headers
    ):
        """Regular users cannot list all projects."""
        response = test_client.get("/admin/projects", headers=user_headers)
        assert response.status_code == 403

    def test_delete_project(
        self, test_client, admin_user, project_owner, test_project, admin_headers
    ):
        """Admin can delete a project."""
        response = test_client.delete(
            f"/admin/projects/{test_project.project_id}", headers=admin_headers
        )
        assert response.status_code == 200

        # Verify project is deleted
        deleted = ProjectDocument.find_one({"project_id": test_project.project_id}).run()
        assert deleted is None

    def test_cannot_delete_own_project(self, test_client, admin_user, admin_headers, init_db):
        """Admin cannot delete their own project."""
        # Create admin's project
        admin_project = ProjectDocument(
            project_id="proj-admin",
            name="Admin's Project",
            owner_username="admin",
            description="Admin project",
            system_info=SystemInfoModel(),
        )
        admin_project.insert()

        response = test_client.delete("/admin/projects/proj-admin", headers=admin_headers)
        assert response.status_code == 400
        assert "own project" in response.json()["detail"].lower()


class TestAdminMembersEndpoints:
    """Tests for admin member management endpoints."""

    @pytest.fixture
    def admin_user(self, init_db):
        """Create admin user."""
        user = UserDocument(
            username="admin",
            full_name="Admin User",
            hashed_password="hashed",
            access_token="admin-token",
            disabled=False,
            system_role=SystemRole.ADMIN,
            default_project_id="proj-admin",
            system_info=SystemInfoModel(),
        )
        user.insert()
        yield user

    @pytest.fixture
    def project_owner(self, init_db):
        """Create project owner user."""
        user = UserDocument(
            username="projectowner",
            full_name="Project Owner",
            hashed_password="hashed",
            access_token="owner-token",
            disabled=False,
            system_role=SystemRole.USER,
            default_project_id="proj-owner",
            system_info=SystemInfoModel(),
        )
        user.insert()
        yield user

    @pytest.fixture
    def member_user(self, init_db):
        """Create member user."""
        user = UserDocument(
            username="memberuser",
            full_name="Member User",
            hashed_password="hashed",
            access_token="member-token",
            disabled=False,
            system_role=SystemRole.USER,
            system_info=SystemInfoModel(),
        )
        user.insert()
        yield user

    @pytest.fixture
    def test_project(self, init_db, project_owner):
        """Create test project."""
        project = ProjectDocument(
            project_id="proj-owner",
            name="Owner's Project",
            owner_username="projectowner",
            description="Test project",
            system_info=SystemInfoModel(),
        )
        project.insert()
        yield project

    @pytest.fixture
    def test_membership(self, init_db, test_project, member_user):
        """Create test membership."""
        membership = ProjectMembershipDocument(
            project_id="proj-owner",
            username="memberuser",
            role=ProjectRole.VIEWER,
            status="active",
            invited_by="projectowner",
            system_info=SystemInfoModel(),
        )
        membership.insert()
        yield membership

    @pytest.fixture
    def admin_headers(self):
        """Admin authentication headers."""
        return {"Authorization": "Bearer admin-token"}

    def test_list_project_members(
        self, test_client, admin_user, test_project, test_membership, admin_headers
    ):
        """Admin can list project members."""
        response = test_client.get(
            f"/admin/projects/{test_project.project_id}/members", headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert len(data["members"]) >= 1

    def test_add_project_member(
        self, test_client, admin_user, project_owner, test_project, member_user, admin_headers
    ):
        """Admin can add a member to a project."""
        response = test_client.post(
            f"/admin/projects/{test_project.project_id}/members",
            headers=admin_headers,
            json={"username": "memberuser"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "memberuser"
        assert data["role"] == "viewer"

        # Cleanup
        ProjectMembershipDocument.find_one(
            {"project_id": test_project.project_id, "username": "memberuser"}
        ).delete()

    def test_remove_project_member(
        self, test_client, admin_user, test_project, test_membership, member_user, admin_headers
    ):
        """Admin can remove a member from a project."""
        response = test_client.delete(
            f"/admin/projects/{test_project.project_id}/members/memberuser", headers=admin_headers
        )
        assert response.status_code == 200

        # Verify membership is revoked
        membership = ProjectMembershipDocument.find_one(
            {"project_id": test_project.project_id, "username": "memberuser"}
        ).run()
        assert membership.status == "revoked"

    def test_cannot_remove_project_owner(
        self, test_client, admin_user, project_owner, test_project, admin_headers, init_db
    ):
        """Cannot remove the project owner."""
        # Create owner membership
        owner_membership = ProjectMembershipDocument(
            project_id="proj-owner",
            username="projectowner",
            role=ProjectRole.OWNER,
            status="active",
            invited_by="system",
            system_info=SystemInfoModel(),
        )
        owner_membership.insert()

        response = test_client.delete(
            f"/admin/projects/{test_project.project_id}/members/projectowner", headers=admin_headers
        )
        assert response.status_code == 400
        assert "owner" in response.json()["detail"].lower()


class TestAdminCreateProjectForUser:
    """Tests for creating project for user endpoint."""

    @pytest.fixture
    def admin_user(self, init_db):
        """Create admin user."""
        user = UserDocument(
            username="admin",
            full_name="Admin User",
            hashed_password="hashed",
            access_token="admin-token",
            disabled=False,
            system_role=SystemRole.ADMIN,
            default_project_id="proj-admin",
            system_info=SystemInfoModel(),
        )
        user.insert()
        yield user

    @pytest.fixture
    def user_without_project(self, init_db):
        """Create user without project."""
        user = UserDocument(
            username="noprojectuser",
            full_name="No Project User",
            hashed_password="hashed",
            access_token="noproject-token",
            disabled=False,
            system_role=SystemRole.USER,
            default_project_id=None,
            system_info=SystemInfoModel(),
        )
        user.insert()
        yield user

    @pytest.fixture
    def admin_headers(self):
        """Admin authentication headers."""
        return {"Authorization": "Bearer admin-token"}

    def test_create_project_for_user(
        self, test_client, admin_user, user_without_project, admin_headers
    ):
        """Admin can create project for user."""
        response = test_client.post("/admin/users/noprojectuser/project", headers=admin_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["default_project_id"] is not None

    def test_create_project_user_not_found(self, test_client, admin_user, admin_headers):
        """Returns 404 for non-existent user."""
        response = test_client.post("/admin/users/nonexistent/project", headers=admin_headers)
        assert response.status_code == 404
