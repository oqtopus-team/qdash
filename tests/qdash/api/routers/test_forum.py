"""Tests for forum router endpoints."""

from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.notification import NotificationDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument


def _create_user(username: str, token: str, role: ProjectRole) -> UserDocument:
    user = UserDocument(
        username=username,
        hashed_password="hashed",
        access_token=token,
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()
    inviter = UserDocument.find_one({"username": "owner"}).run()
    ProjectMembershipDocument(
        project_id="test_project",
        user_id=user.user_id,
        username=username,
        role=role,
        status="active",
        invited_by_user_id=inviter.user_id if inviter else user.user_id,
        invited_by="owner",
    ).insert()
    return user


def _create_project() -> None:
    owner = UserDocument.find_one({"username": "owner"}).run()
    assert owner is not None
    ProjectDocument(
        project_id="test_project",
        name="Test Project",
        owner_user_id=owner.user_id,
        owner_username="owner",
    ).insert()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Project-Id": "test_project"}


def _create_post(
    test_client,
    headers,
    *,
    category="qubit",
    title="T1 drift on Q12",
    content="Tracking today's calibration notes",
    parent_id=None,
):
    body = {
        "category": category,
        "title": title,
        "content": content,
        "parent_id": parent_id,
    }
    return test_client.post("/forum/posts", headers=headers, json=body)


def test_create_and_list_forum_threads(test_client, init_db):
    """Forum threads are project-scoped and return reply counts."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    root = _create_post(test_client, headers)
    root_id = root.json()["id"]
    _create_post(
        test_client,
        headers,
        title=None,
        content="Adding a follow-up observation",
        parent_id=root_id,
    )

    response = test_client.get("/forum/posts?category=qubit", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["posts"][0]["title"] == "T1 drift on Q12"
    assert data["posts"][0]["category"] == "qubit"
    assert data["posts"][0]["reply_count"] == 1


def test_owner_can_create_and_archive_forum_category(test_client, init_db):
    """Project owners can add and archive forum categories."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    created = test_client.post(
        "/forum/categories",
        headers=headers,
        json={
            "key": "software",
            "name": "Software",
            "description": "Software and dashboard behavior",
            "color": "accent",
            "icon": "settings",
        },
    )
    assert created.status_code == 201
    assert created.json()["key"] == "software"

    listed = test_client.get("/forum/categories", headers=headers)
    assert listed.status_code == 200
    assert "software" in {item["key"] for item in listed.json()["categories"]}

    deleted = test_client.delete("/forum/categories/software", headers=headers)
    assert deleted.status_code == 200

    listed_active = test_client.get("/forum/categories", headers=headers)
    assert "software" not in {item["key"] for item in listed_active.json()["categories"]}


def test_cannot_archive_last_active_forum_category(test_client, init_db):
    """At least one active forum category must remain."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    listed = test_client.get("/forum/categories", headers=headers)
    assert listed.status_code == 200
    keys = [item["key"] for item in listed.json()["categories"]]

    for key in keys[:-1]:
        response = test_client.delete(f"/forum/categories/{key}", headers=headers)
        assert response.status_code == 200

    response = test_client.delete(f"/forum/categories/{keys[-1]}", headers=headers)

    assert response.status_code == 409


def test_viewer_cannot_create_forum_category(test_client, init_db):
    """Only owners can manage forum categories."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_user("member", "member_token", ProjectRole.VIEWER)
    _create_project()

    response = test_client.post(
        "/forum/categories",
        headers=_headers("member_token"),
        json={"key": "software", "name": "Software"},
    )

    assert response.status_code == 403


def test_delete_root_thread_archives_replies_from_normal_listing(test_client, init_db):
    """Deleting a root thread hides the thread and its replies from normal reads."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    root = _create_post(test_client, headers)
    root_id = root.json()["id"]
    _create_post(test_client, headers, title=None, content="Reply", parent_id=root_id)

    deleted = test_client.delete(f"/forum/posts/{root_id}", headers=headers)
    assert deleted.status_code == 200

    listed = test_client.get("/forum/posts", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 0

    fetched = test_client.get(f"/forum/posts/{root_id}", headers=headers)
    assert fetched.status_code == 404

    replies = test_client.get(f"/forum/posts/{root_id}/replies", headers=headers)
    assert replies.status_code == 200
    assert replies.json() == []


def test_owner_can_delete_member_forum_thread(test_client, init_db):
    """Project owners can moderate another member's forum thread."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_user("member", "member_token", ProjectRole.VIEWER)
    _create_project()

    root = _create_post(test_client, _headers("member_token"))
    root_id = root.json()["id"]

    response = test_client.delete(f"/forum/posts/{root_id}", headers=_headers("owner_token"))

    assert response.status_code == 200
    assert (
        test_client.get(f"/forum/posts/{root_id}", headers=_headers("owner_token")).status_code
        == 404
    )


def test_get_forum_replies_is_paginated(test_client, init_db):
    """Reply listing accepts skip and limit parameters."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")
    root = _create_post(test_client, headers)
    root_id = root.json()["id"]
    for index in range(3):
        _create_post(test_client, headers, title=None, content=f"Reply {index}", parent_id=root_id)

    response = test_client.get(f"/forum/posts/{root_id}/replies?skip=1&limit=1", headers=headers)

    assert response.status_code == 200
    replies = response.json()
    assert len(replies) == 1
    assert replies[0]["content"] == "Reply 1"


def test_reply_creates_forum_reply_notification(test_client, init_db):
    """Replying to another user's thread creates an in-app notification."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_user("member", "member_token", ProjectRole.VIEWER)
    _create_project()

    root = _create_post(test_client, _headers("owner_token"))
    root_id = root.json()["id"]

    reply = _create_post(
        test_client,
        _headers("member_token"),
        title=None,
        content="I see the same readout trend.",
        parent_id=root_id,
    )

    assert reply.status_code == 201, reply.text
    notification = NotificationDocument.find_one(
        {
            "recipient_username": "owner",
            "actor_username": "member",
            "kind": "forum_reply",
        }
    ).run()
    assert notification is not None
    assert notification.target_url == f"/forum/{root_id}"


def test_close_forum_thread_requires_author_or_owner(test_client, init_db):
    """A viewer cannot close another user's forum thread."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_user("member", "member_token", ProjectRole.VIEWER)
    _create_project()

    root = _create_post(test_client, _headers("owner_token"))
    root_id = root.json()["id"]

    response = test_client.patch(f"/forum/posts/{root_id}/close", headers=_headers("member_token"))

    assert response.status_code == 403
