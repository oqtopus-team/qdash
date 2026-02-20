"""Tests for issue router endpoints."""

import pytest
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument


@pytest.fixture
def test_project(init_db):
    """Create a test project with owner membership."""
    user = UserDocument(
        username="test_user",
        hashed_password="hashed",
        access_token="test_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()

    project = ProjectDocument(
        project_id="test_project",
        name="Test Project",
        owner_username="test_user",
    )
    project.insert()

    membership = ProjectMembershipDocument(
        project_id="test_project",
        username="test_user",
        role=ProjectRole.OWNER,
        invited_by="test_user",
    )
    membership.insert()

    return project


@pytest.fixture
def auth_headers():
    """Get authentication headers with project context."""
    return {
        "Authorization": "Bearer test_token",
        "X-Project-Id": "test_project",
    }


@pytest.fixture
def other_user(init_db):
    """Create another user for permission tests."""
    user = UserDocument(
        username="other_user",
        hashed_password="hashed",
        access_token="other_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()

    membership = ProjectMembershipDocument(
        project_id="test_project",
        username="other_user",
        role=ProjectRole.VIEWER,
        invited_by="test_user",
    )
    membership.insert()

    return user


@pytest.fixture
def other_auth_headers():
    """Get authentication headers for the other user."""
    return {
        "Authorization": "Bearer other_token",
        "X-Project-Id": "test_project",
    }


def _create_issue(
    test_client,
    auth_headers,
    task_id="task_001",
    title="Test Issue",
    content="Test content",
    parent_id=None,
):
    """Helper to create an issue via the API."""
    body = {"content": content}
    if title is not None:
        body["title"] = title
    if parent_id is not None:
        body["parent_id"] = parent_id
    return test_client.post(
        f"/task-results/{task_id}/issues",
        headers=auth_headers,
        json=body,
    )


class TestCreateIssue:
    """Tests for creating issues."""

    def test_create_root_issue(self, test_client, test_project, auth_headers):
        """Test creating a root issue returns 201 with correct fields."""
        response = _create_issue(test_client, auth_headers)

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Issue"
        assert data["content"] == "Test content"
        assert data["task_id"] == "task_001"
        assert data["username"] == "test_user"
        assert data["parent_id"] is None
        assert data["is_closed"] is False
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_reply(self, test_client, test_project, auth_headers):
        """Test creating a reply sets parent_id."""
        # Create root issue first
        root = _create_issue(test_client, auth_headers)
        root_id = root.json()["id"]

        # Create reply
        response = _create_issue(
            test_client,
            auth_headers,
            title=None,
            content="Reply content",
            parent_id=root_id,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["parent_id"] == root_id
        assert data["content"] == "Reply content"

    def test_create_root_issue_without_title(self, test_client, test_project, auth_headers):
        """Test creating a root issue without title returns 422."""
        response = test_client.post(
            "/task-results/task_001/issues",
            headers=auth_headers,
            json={"content": "No title"},
        )

        assert response.status_code == 422


class TestListIssues:
    """Tests for listing issues."""

    def test_list_empty(self, test_client, test_project, auth_headers):
        """Test listing issues when none exist."""
        response = test_client.get("/issues", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["issues"] == []
        assert data["total"] == 0

    def test_list_with_data(self, test_client, test_project, auth_headers):
        """Test listing issues returns data with reply_count."""
        # Create a root issue
        root = _create_issue(test_client, auth_headers)
        root_id = root.json()["id"]

        # Create two replies
        _create_issue(test_client, auth_headers, title=None, content="Reply 1", parent_id=root_id)
        _create_issue(test_client, auth_headers, title=None, content="Reply 2", parent_id=root_id)

        # List root issues
        response = test_client.get("/issues", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["issues"]) == 1
        assert data["issues"][0]["reply_count"] == 2
        assert data["total"] == 1

    def test_filter_by_task_id(self, test_client, test_project, auth_headers):
        """Test filtering issues by task_id."""
        _create_issue(test_client, auth_headers, task_id="task_A", title="Issue A", content="A")
        _create_issue(test_client, auth_headers, task_id="task_B", title="Issue B", content="B")

        response = test_client.get("/issues?task_id=task_A", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["issues"]) == 1
        assert data["issues"][0]["task_id"] == "task_A"


class TestGetIssue:
    """Tests for getting a single issue."""

    def test_get_issue(self, test_client, test_project, auth_headers):
        """Test getting an existing issue."""
        created = _create_issue(test_client, auth_headers)
        issue_id = created.json()["id"]

        response = test_client.get(f"/issues/{issue_id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == issue_id
        assert data["title"] == "Test Issue"

    def test_get_issue_not_found(self, test_client, test_project, auth_headers):
        """Test getting a non-existent issue returns 404."""
        response = test_client.get("/issues/000000000000000000000000", headers=auth_headers)

        assert response.status_code == 404


class TestGetIssueReplies:
    """Tests for getting replies to an issue."""

    def test_get_replies(self, test_client, test_project, auth_headers):
        """Test getting replies in chronological order."""
        root = _create_issue(test_client, auth_headers)
        root_id = root.json()["id"]

        _create_issue(
            test_client, auth_headers, title=None, content="First reply", parent_id=root_id
        )
        _create_issue(
            test_client, auth_headers, title=None, content="Second reply", parent_id=root_id
        )

        response = test_client.get(f"/issues/{root_id}/replies", headers=auth_headers)

        assert response.status_code == 200
        replies = response.json()
        assert len(replies) == 2
        assert replies[0]["content"] == "First reply"
        assert replies[1]["content"] == "Second reply"


class TestUpdateIssue:
    """Tests for updating issues."""

    def test_update_own_issue(self, test_client, test_project, auth_headers):
        """Test updating own issue succeeds."""
        created = _create_issue(test_client, auth_headers)
        issue_id = created.json()["id"]

        response = test_client.patch(
            f"/issues/{issue_id}",
            headers=auth_headers,
            json={"title": "Updated Title", "content": "Updated content"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["content"] == "Updated content"
        # updated_at should be different from created_at
        assert data["updated_at"] >= data["created_at"]

    def test_update_other_user_issue(
        self, test_client, test_project, auth_headers, other_user, other_auth_headers
    ):
        """Test updating another user's issue returns 403."""
        created = _create_issue(test_client, auth_headers)
        issue_id = created.json()["id"]

        response = test_client.patch(
            f"/issues/{issue_id}",
            headers=other_auth_headers,
            json={"content": "Hacked content"},
        )

        assert response.status_code == 403

    def test_update_not_found(self, test_client, test_project, auth_headers):
        """Test updating a non-existent issue returns 404."""
        response = test_client.patch(
            "/issues/000000000000000000000000",
            headers=auth_headers,
            json={"content": "Does not matter"},
        )

        assert response.status_code == 404


class TestDeleteIssue:
    """Tests for deleting issues."""

    def test_delete_own_issue(self, test_client, test_project, auth_headers):
        """Test deleting own issue succeeds."""
        created = _create_issue(test_client, auth_headers)
        issue_id = created.json()["id"]

        response = test_client.delete(f"/issues/{issue_id}", headers=auth_headers)

        assert response.status_code == 200

        # Verify it's gone
        get_resp = test_client.get(f"/issues/{issue_id}", headers=auth_headers)
        assert get_resp.status_code == 404

    def test_delete_other_user_issue(
        self, test_client, test_project, auth_headers, other_user, other_auth_headers
    ):
        """Test deleting another user's issue returns 403."""
        created = _create_issue(test_client, auth_headers)
        issue_id = created.json()["id"]

        response = test_client.delete(f"/issues/{issue_id}", headers=other_auth_headers)

        assert response.status_code == 403


class TestCloseReopenIssue:
    """Tests for closing and reopening issues."""

    def test_close_issue(self, test_client, test_project, auth_headers):
        """Test closing an issue sets is_closed=true."""
        created = _create_issue(test_client, auth_headers)
        issue_id = created.json()["id"]

        response = test_client.patch(f"/issues/{issue_id}/close", headers=auth_headers)

        assert response.status_code == 200

        # Verify it's closed
        get_resp = test_client.get(f"/issues/{issue_id}", headers=auth_headers)
        assert get_resp.json()["is_closed"] is True

    def test_reopen_issue(self, test_client, test_project, auth_headers):
        """Test reopening a closed issue sets is_closed=false."""
        created = _create_issue(test_client, auth_headers)
        issue_id = created.json()["id"]

        # Close first
        test_client.patch(f"/issues/{issue_id}/close", headers=auth_headers)

        # Reopen
        response = test_client.patch(f"/issues/{issue_id}/reopen", headers=auth_headers)

        assert response.status_code == 200

        # Verify it's open again
        get_resp = test_client.get(f"/issues/{issue_id}", headers=auth_headers)
        assert get_resp.json()["is_closed"] is False
