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

    def test_reload_config_caches_as_admin(self, test_client, admin_user, admin_headers):
        """Admin can reload cached configuration."""
        response = test_client.post("/admin/config/reload", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "cleared" in data
        assert "policy.yaml" in data["cleared"]

    def test_reload_config_caches_requires_admin(
        self, test_client, admin_user, regular_user, user_headers
    ):
        """Regular users cannot reload cached configuration."""
        response = test_client.post("/admin/config/reload", headers=user_headers)
        assert response.status_code == 403

    def test_reload_config_caches_requires_auth(self, test_client, admin_user):
        """Unauthenticated requests are rejected."""
        response = test_client.post("/admin/config/reload")
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

    def test_bulk_import_users_returns_generated_passwords(
        self, test_client, admin_user, admin_headers
    ):
        """Admin can bulk import users and download generated passwords from response."""
        csv_content = (
            "username,full_name,system_role\n"
            "bulkviewer,Bulk Viewer,user\n"
            "bulkadmin,Bulk Admin,admin\n"
        )
        response = test_client.post(
            "/admin/users/bulk-import",
            headers=admin_headers,
            files={"file": ("users.csv", csv_content, "text/csv")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 2
        assert data["skipped"] == 0
        assert data["failed"] == 0
        assert data["total"] == 2

        first = data["results"][0]
        assert first["username"] == "bulkviewer"
        assert first["status"] == "created"
        assert first["initial_password"]
        assert "project_id" not in first

        login_response = test_client.post(
            "/auth/login",
            data={"username": "bulkviewer", "password": first["initial_password"]},
        )
        assert login_response.status_code == 200
        assert login_response.json()["must_change_password"] is True

        created_admin = UserDocument.find_one({"username": "bulkadmin"}).run()
        assert created_admin is not None
        assert created_admin.system_role == SystemRole.ADMIN

    def test_bulk_import_users_skips_existing_user_without_password(
        self, test_client, admin_user, regular_user, admin_headers
    ):
        """Existing users are skipped and do not return password information."""
        csv_content = "username,full_name\nregularuser,Regular Duplicate\n"
        response = test_client.post(
            "/admin/users/bulk-import",
            headers=admin_headers,
            files={"file": ("users.csv", csv_content, "text/csv")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 0
        assert data["skipped"] == 1
        assert data["results"][0]["status"] == "skipped"
        assert data["results"][0]["initial_password"] is None

    def test_bulk_import_users_rejects_invalid_username(
        self, test_client, admin_user, admin_headers
    ):
        """Bulk import rejects usernames outside the canonical format."""
        csv_content = "username,full_name\ntaka fumi,Invalid Username\n"
        response = test_client.post(
            "/admin/users/bulk-import",
            headers=admin_headers,
            files={"file": ("users.csv", csv_content, "text/csv")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 0
        assert data["failed"] == 1
        assert data["results"][0]["status"] == "failed"
        assert "lowercase letters" in data["results"][0]["message"]

    def test_bulk_import_users_rejects_project_columns(
        self, test_client, admin_user, admin_headers
    ):
        """Bulk import only creates accounts; project membership is managed separately."""
        csv_content = "username,full_name,project_id\nprojectuser,Project User,proj-001\n"
        response = test_client.post(
            "/admin/users/bulk-import",
            headers=admin_headers,
            files={"file": ("users.csv", csv_content, "text/csv")},
        )

        assert response.status_code == 400
        data = response.json()
        assert "Unsupported columns" in data["detail"]


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
            owner_user_id=project_owner.user_id,
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
            owner_user_id=admin_user.user_id,
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
            owner_user_id=project_owner.user_id,
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
            user_id=member_user.user_id,
            username="memberuser",
            role=ProjectRole.VIEWER,
            status="active",
            invited_by_user_id=test_project.owner_user_id,
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
        assert membership is not None
        assert membership.status == "revoked"

    def test_cannot_remove_project_owner(
        self, test_client, admin_user, project_owner, test_project, admin_headers, init_db
    ):
        """Cannot remove the project owner."""
        # Create owner membership
        owner_membership = ProjectMembershipDocument(
            project_id="proj-owner",
            user_id=project_owner.user_id,
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


class TestAdminRegisterUser:
    """Tests for admin-managed user registration."""

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
    def admin_headers(self):
        """Admin authentication headers."""
        return {"Authorization": "Bearer admin-token"}

    def test_register_user_generates_temporary_password(
        self, test_client, admin_user, admin_headers
    ):
        """Admin can create a user without choosing a password."""
        response = test_client.post(
            "/auth/register",
            headers=admin_headers,
            json={
                "username": "generateduser",
                "full_name": "Generated User",
                "create_default_project": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "generateduser"
        assert data["must_change_password"] is True
        assert data["initial_password"]
        assert data["access_token"]
        assert data["default_project_id"]

        login_response = test_client.post(
            "/auth/login",
            data={"username": "generateduser", "password": data["initial_password"]},
        )
        assert login_response.status_code == 200
        assert login_response.json()["must_change_password"] is True

    def test_register_user_without_default_project(self, test_client, admin_user, admin_headers):
        """Admin can create an account without provisioning a default project."""
        response = test_client.post(
            "/auth/register",
            headers=admin_headers,
            json={"username": "accountonly"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "accountonly"
        assert data["default_project_id"] is None
        assert data["initial_password"]

    def test_register_user_rejects_invalid_username(self, test_client, admin_user, admin_headers):
        """Admin user registration rejects usernames with spaces."""
        response = test_client.post(
            "/auth/register",
            headers=admin_headers,
            json={"username": "taka fumi"},
        )

        assert response.status_code == 422

    def test_change_password_clears_must_change_password(
        self, test_client, admin_user, admin_headers
    ):
        """Changing password clears the first-login password-change flag."""
        register_response = test_client.post(
            "/auth/register",
            headers=admin_headers,
            json={"username": "changeme"},
        )
        assert register_response.status_code == 200
        initial_password = register_response.json()["initial_password"]
        token = register_response.json()["access_token"]

        change_response = test_client.post(
            "/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": initial_password, "new_password": "changed-password"},
        )
        assert change_response.status_code == 200

        user = UserDocument.find_one({"username": "changeme"}).run()
        assert user is not None
        assert user.must_change_password is False
