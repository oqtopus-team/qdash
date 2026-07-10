"""Tests for forum router endpoints."""

from qdash.api.services import forum_service
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.notification import NotificationDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument


def _create_user(username: str, token: str, role: ProjectRole) -> UserDocument:
    """Create a user with an active membership in the test project."""
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
    """Insert the shared test project owned by the ``owner`` user."""
    owner = UserDocument.find_one({"username": "owner"}).run()
    assert owner is not None
    ProjectDocument(
        project_id="test_project",
        name="Test Project",
        owner_user_id=owner.user_id,
        owner_username="owner",
    ).insert()


def _headers(token: str) -> dict[str, str]:
    """Build auth and project headers for the given access token."""
    return {"Authorization": f"Bearer {token}", "X-Project-Id": "test_project"}


def _create_post(
    test_client,
    headers,
    *,
    category="qubit",
    title="T1 drift on Q12",
    content="Tracking today's calibration notes",
    parent_id=None,
    labels=None,
    chip_id=None,
    target_type=None,
    target_id=None,
    cooldown_id=None,
    assignee_username=None,
):
    """Post a forum thread or reply and return the raw HTTP response."""
    body = {
        "category": category,
        "title": title,
        "content": content,
        "parent_id": parent_id,
    }
    if labels is not None:
        body["labels"] = labels
    if chip_id is not None:
        body["chip_id"] = chip_id
    if target_type is not None:
        body["target_type"] = target_type
    if target_id is not None:
        body["target_id"] = target_id
    if cooldown_id is not None:
        body["cooldown_id"] = cooldown_id
    if assignee_username is not None:
        body["assignee_username"] = assignee_username
    return test_client.post("/forum/posts", headers=headers, json=body)


def test_create_and_list_forum_threads(test_client, init_db):
    """Forum threads are project-scoped and return reply counts."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    root = _create_post(test_client, headers)
    root_body = root.json()
    root_id = root_body["id"]
    reply = _create_post(
        test_client,
        headers,
        title=None,
        content="Adding a follow-up observation",
        parent_id=root_id,
    )
    second_root = _create_post(test_client, headers, title="Readout outlier on Q03")

    assert root_body["number"] == 1
    assert reply.json()["number"] == 1
    assert second_root.json()["number"] == 2

    response = test_client.get("/forum/posts?category=qubit&number=1", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["posts"][0]["number"] == 1
    assert data["posts"][0]["title"] == "T1 drift on Q12"
    assert data["posts"][0]["category"] == "qubit"
    assert data["posts"][0]["reply_count"] == 1


def test_forum_thread_labels_round_trip_filter_and_update(test_client, init_db):
    """Root thread labels are returned, filterable, and editable by the author."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    root = _create_post(test_client, headers, labels=["review"])

    assert root.status_code == 201
    root_body = root.json()
    assert root_body["labels"] == ["review"]

    listed = test_client.get("/forum/posts?label=review", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["posts"][0]["labels"] == ["review"]

    hidden = test_client.get("/forum/posts?label=anomaly", headers=headers)
    assert hidden.status_code == 200
    assert hidden.json()["total"] == 0

    rejected = _create_post(test_client, headers, title="multi label", labels=["review", "anomaly"])
    assert rejected.status_code == 422

    updated = test_client.patch(
        f"/forum/posts/{root_body['id']}",
        headers=headers,
        json={
            "category": "qubit",
            "title": root_body["title"],
            "content": root_body["content"],
            "labels": ["anomaly"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["labels"] == ["anomaly"]

    fetched = test_client.get(f"/forum/posts/{root_body['id']}", headers=headers)
    assert fetched.json()["labels"] == ["anomaly"]

    rejected_status_label = test_client.patch(
        f"/forum/posts/{root_body['id']}",
        headers=headers,
        json={
            "category": "qubit",
            "title": root_body["title"],
            "content": root_body["content"],
            "labels": ["resolved"],
        },
    )
    assert rejected_status_label.status_code == 422


def test_forum_thread_assignee_round_trip_update_and_reply_inherit(test_client, init_db):
    """Root thread assignees are validated, editable, clearable, and inherited by replies."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_user("alice", "alice_token", ProjectRole.EDITOR)
    _create_project()
    headers = _headers("owner_token")

    root = _create_post(test_client, headers, assignee_username="alice")

    assert root.status_code == 201, root.text
    root_body = root.json()
    assert root_body["assignee_username"] == "alice"

    reply = _create_post(
        test_client,
        headers,
        title=None,
        content="reply",
        parent_id=root_body["id"],
    )
    assert reply.status_code == 201, reply.text
    assert reply.json()["assignee_username"] == "alice"

    updated = test_client.patch(
        f"/forum/posts/{root_body['id']}",
        headers=headers,
        json={
            "category": root_body["category"],
            "title": root_body["title"],
            "content": root_body["content"],
            "assignee_username": "owner",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["assignee_username"] == "owner"

    cleared = test_client.patch(
        f"/forum/posts/{root_body['id']}",
        headers=headers,
        json={
            "category": root_body["category"],
            "title": root_body["title"],
            "content": root_body["content"],
            "assignee_username": None,
        },
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["assignee_username"] is None

    rejected = test_client.patch(
        f"/forum/posts/{root_body['id']}",
        headers=headers,
        json={
            "category": root_body["category"],
            "title": root_body["title"],
            "content": root_body["content"],
            "assignee_username": "missing",
        },
    )
    assert rejected.status_code == 422


def test_forum_thread_target_metadata_round_trip_filter_and_update(test_client, init_db):
    """Root thread target metadata is stored, filterable, inherited by replies, and editable."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    root = _create_post(
        test_client,
        headers,
        chip_id="chip-1",
        target_type="qubit",
        target_id="12",
        cooldown_id="cd-1",
    )

    assert root.status_code == 201, root.text
    root_body = root.json()
    assert root_body["chip_id"] == "chip-1"
    assert root_body["target_type"] == "qubit"
    assert root_body["target_id"] == "12"
    assert root_body["cooldown_id"] == "cd-1"

    listed = test_client.get(
        "/forum/posts?chip_id=chip-1&target_type=qubit&target_id=12&cooldown_id=cd-1",
        headers=headers,
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    hidden = test_client.get(
        "/forum/posts?chip_id=chip-1&target_type=coupling&target_id=0-1",
        headers=headers,
    )
    assert hidden.status_code == 200
    assert hidden.json()["total"] == 0

    reply = _create_post(
        test_client,
        headers,
        title=None,
        content="reply",
        parent_id=root_body["id"],
    )
    assert reply.status_code == 201, reply.text
    assert reply.json()["chip_id"] == "chip-1"
    assert reply.json()["target_type"] == "qubit"
    assert reply.json()["target_id"] == "12"
    assert reply.json()["cooldown_id"] == "cd-1"

    partial_target_update = test_client.patch(
        f"/forum/posts/{root_body['id']}",
        headers=headers,
        json={
            "category": root_body["category"],
            "title": root_body["title"],
            "content": root_body["content"],
            "target_id": "13",
        },
    )
    assert partial_target_update.status_code == 200, partial_target_update.text
    assert partial_target_update.json()["chip_id"] == "chip-1"
    assert partial_target_update.json()["target_type"] == "qubit"
    assert partial_target_update.json()["target_id"] == "13"

    updated = test_client.patch(
        f"/forum/posts/{root_body['id']}",
        headers=headers,
        json={
            "category": "coupling",
            "title": root_body["title"],
            "content": root_body["content"],
            "chip_id": "chip-1",
            "target_type": "coupling",
            "target_id": "12-13",
            "cooldown_id": "cd-2",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["target_type"] == "coupling"
    assert updated.json()["target_id"] == "12-13"
    assert updated.json()["cooldown_id"] == "cd-2"


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


def test_close_and_reopen_forum_thread_updates_status(test_client, init_db):
    """Close/reopen compatibility endpoints map to resolved/open status."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    root = _create_post(test_client, headers)
    root_id = root.json()["id"]

    closed = test_client.patch(f"/forum/posts/{root_id}/close", headers=headers)
    assert closed.status_code == 200
    fetched = test_client.get(f"/forum/posts/{root_id}", headers=headers)
    assert fetched.json()["status"] == "resolved"

    blocked_reply = _create_post(
        test_client, headers, title=None, content="reply", parent_id=root_id
    )
    assert blocked_reply.status_code == 409

    reopened = test_client.patch(f"/forum/posts/{root_id}/reopen", headers=headers)
    assert reopened.status_code == 200
    fetched = test_client.get(f"/forum/posts/{root_id}", headers=headers)
    assert fetched.json()["status"] == "open"


def test_author_can_update_forum_thread_category(test_client, init_db):
    """The author can change a root thread's category along with title and content."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    root = _create_post(test_client, headers)
    root_id = root.json()["id"]

    response = test_client.patch(
        f"/forum/posts/{root_id}",
        headers=headers,
        json={
            "category": "coupling",
            "title": "Updated title",
            "content": "Updated content",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "coupling"
    assert body["title"] == "Updated title"
    assert body["content"] == "Updated content"

    fetched = test_client.get(f"/forum/posts/{root_id}", headers=headers)
    assert fetched.json()["category"] == "coupling"


def test_update_forum_thread_rejects_unknown_category(test_client, init_db):
    """Updating to a non-existent category is rejected and leaves the thread unchanged."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    root = _create_post(test_client, headers)
    root_id = root.json()["id"]

    response = test_client.patch(
        f"/forum/posts/{root_id}",
        headers=headers,
        json={"category": "does-not-exist", "content": "Updated content"},
    )

    assert response.status_code == 422
    assert test_client.get(f"/forum/posts/{root_id}", headers=headers).json()["category"] == "qubit"


def test_update_forum_reply_ignores_category(test_client, init_db):
    """Replies inherit the root category; editing a reply never changes its category."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    root = _create_post(test_client, headers)
    root_id = root.json()["id"]
    reply = _create_post(
        test_client,
        headers,
        title=None,
        content="A reply",
        parent_id=root_id,
    )
    reply_id = reply.json()["id"]

    response = test_client.patch(
        f"/forum/posts/{reply_id}",
        headers=headers,
        json={"category": "coupling", "content": "Edited reply"},
    )

    assert response.status_code == 200
    assert response.json()["category"] == "qubit"
    assert response.json()["content"] == "Edited reply"


def test_forum_post_round_trips_content_blocks(test_client, init_db):
    """BlockNote JSON is stored alongside the markdown projection and is updatable."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    blocks = [
        {
            "id": "b1",
            "type": "paragraph",
            "props": {},
            "content": [{"type": "text", "text": "rich body", "styles": {}}],
            "children": [],
        }
    ]
    created = test_client.post(
        "/forum/posts",
        headers=headers,
        json={
            "category": "qubit",
            "title": "Rich post",
            "content": "rich body",
            "content_blocks": blocks,
            "parent_id": None,
        },
    )
    assert created.status_code == 201, created.text
    post_id = created.json()["id"]
    assert created.json()["content_blocks"] == blocks

    fetched = test_client.get(f"/forum/posts/{post_id}", headers=headers)
    assert fetched.json()["content_blocks"] == blocks

    new_blocks = [
        {
            "id": "b1",
            "type": "heading",
            "props": {"level": 2},
            "content": [{"type": "text", "text": "updated", "styles": {}}],
            "children": [],
        }
    ]
    updated = test_client.patch(
        f"/forum/posts/{post_id}",
        headers=headers,
        json={"title": "Rich post", "content": "updated", "content_blocks": new_blocks},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["content_blocks"] == new_blocks


def test_forum_update_preserves_content_blocks_when_omitted(test_client, init_db):
    """Omitting content_blocks on update leaves existing rich content untouched."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    blocks = [
        {
            "id": "b1",
            "type": "paragraph",
            "props": {},
            "content": [{"type": "text", "text": "rich body", "styles": {}}],
            "children": [],
        }
    ]
    created = test_client.post(
        "/forum/posts",
        headers=headers,
        json={
            "category": "qubit",
            "title": "Rich post",
            "content": "rich body",
            "content_blocks": blocks,
            "parent_id": None,
        },
    )
    assert created.status_code == 201, created.text
    post_id = created.json()["id"]

    # Update without content_blocks: existing blocks must be preserved.
    updated = test_client.patch(
        f"/forum/posts/{post_id}",
        headers=headers,
        json={"title": "Rich post", "content": "edited body"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["content"] == "edited body"
    assert updated.json()["content_blocks"] == blocks

    # An explicit empty list clears the blocks.
    cleared = test_client.patch(
        f"/forum/posts/{post_id}",
        headers=headers,
        json={"title": "Rich post", "content": "plain body", "content_blocks": []},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["content_blocks"] == []


def test_forum_post_defaults_content_blocks_to_empty(test_client, init_db):
    """Posting plain markdown without blocks yields an empty content_blocks list."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    created = _create_post(test_client, headers)

    assert created.status_code == 201, created.text
    assert created.json()["content_blocks"] == []


def test_upload_and_serve_forum_image(test_client, init_db, tmp_path, monkeypatch):
    """Forum images can be uploaded by members and served for markdown rendering."""
    monkeypatch.setattr(forum_service, "FORUM_IMAGE_DIR", tmp_path / "forum")
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()

    upload = test_client.post(
        "/forum/upload-image",
        headers=_headers("owner_token"),
        files={"file": ("image.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )

    assert upload.status_code == 200
    url = upload.json()["url"]
    assert url.startswith("/api/forum/images/")

    image = test_client.get(url.removeprefix("/api"))
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
