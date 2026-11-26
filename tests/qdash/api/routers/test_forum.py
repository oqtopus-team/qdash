"""Tests for forum router endpoints."""

import re
import secrets
from typing import Any

import pytest
from bson import ObjectId
from pymongo.errors import AutoReconnect, DuplicateKeyError, WriteError
from starlette.exceptions import HTTPException

from qdash.api.services import forum_service
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.forum import ForumLabelDocument, ForumPostDocument
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
    _create_named_labels(test_client, headers, "Review", "Anomaly")

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

    multi = _create_post(test_client, headers, title="multi label", labels=["review", "anomaly"])
    assert multi.status_code == 201, multi.text
    assert multi.json()["labels"] == ["review", "anomaly"]

    rejected = _create_post(test_client, headers, title="unknown label", labels=["not-a-label"])
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


DEFAULT_LABEL_KEYS = ["agent", "calibration", "hardware", "software", "question"]


def _label_keys(test_client, headers) -> list[str]:
    """Return the label keys listed for the request's project, in display order."""
    response = test_client.get("/forum/labels", headers=headers)
    assert response.status_code == 200, response.text
    return [item["key"] for item in response.json()["labels"]]


def test_new_project_lists_default_forum_labels(test_client, init_db):
    """A new project starts with the default labels as ordinary hex-colored labels."""
    headers = _setup_owner()

    response = test_client.get("/forum/labels", headers=headers)

    assert response.status_code == 200
    labels = response.json()["labels"]
    assert [item["key"] for item in labels] == DEFAULT_LABEL_KEYS
    # Default names are lowercase classification terms.
    assert [item["name"] for item in labels] == [
        "agent",
        "calibration",
        "hardware",
        "software",
        "question",
    ]
    assert all(re.fullmatch(r"#[0-9a-f]{6}", item["color"]) for item in labels)
    # Listing again does not duplicate them.
    assert _label_keys(test_client, headers) == DEFAULT_LABEL_KEYS


def test_default_forum_labels_are_usable_on_threads_without_listing(test_client, init_db):
    """Defaults exist for a project even when its first label use is a thread create."""
    headers = _setup_owner()

    root = _create_post(test_client, headers, labels=["question", "hardware"])

    assert root.status_code == 201, root.text
    assert root.json()["labels"] == ["question", "hardware"]


def test_default_forum_labels_are_editable(test_client, init_db):
    """A default label can be renamed and recolored, and the edit is kept."""
    headers = _setup_owner()
    assert "question" in _label_keys(test_client, headers)

    updated = test_client.patch(
        "/forum/labels/question",
        headers=headers,
        json={"name": "Help wanted", "color": "#123ABC", "description": "Needs input"},
    )
    assert updated.status_code == 200, updated.text

    listed = test_client.get("/forum/labels", headers=headers).json()["labels"]
    question = next(item for item in listed if item["key"] == "question")
    assert question == {
        "key": "question",
        "name": "Help wanted",
        "description": "Needs input",
        "color": "#123abc",
    }
    # The old default name is free again and does not bring the default back.
    assert [item["name"] for item in listed].count("question") == 0


def test_deleted_default_forum_labels_are_not_recreated(test_client, init_db):
    """Deleting defaults is permanent across reads, label writes, and new service instances."""
    headers = _setup_owner()
    root = _create_post(test_client, headers, labels=["agent"])
    assert root.status_code == 201, root.text

    for key in DEFAULT_LABEL_KEYS:
        assert test_client.delete(f"/forum/labels/{key}", headers=headers).status_code == 200

    assert _label_keys(test_client, headers) == []
    [custom] = _create_named_labels(test_client, headers, "Review")
    assert _label_keys(test_client, headers) == [custom]
    # A fresh service instance (as after an API restart) does not reseed either.
    assert [
        label.key
        for label in forum_service.ForumService().list_labels(project_id="test_project").labels
    ] == [custom]
    rejected = _create_post(test_client, headers, title="old default", labels=["agent"])
    assert rejected.status_code == 422
    fetched = test_client.get(f"/forum/posts/{root.json()['id']}", headers=headers)
    assert fetched.json()["labels"] == []


def test_default_label_rejected_insert_is_retried_by_a_later_request(
    test_client, init_db, monkeypatch
):
    """A default whose insert the server rejected is created by the next request instead."""
    headers = _setup_owner()
    real_insert = ForumLabelDocument.insert

    def reject_question(self, *args, **kwargs):
        if self.key == "question":
            raise WriteError("rejected", code=121)
        return real_insert(self, *args, **kwargs)

    monkeypatch.setattr(ForumLabelDocument, "insert", reject_question)
    with pytest.raises(WriteError):
        forum_service.ForumService._ensure_default_labels("test_project")
    monkeypatch.undo()

    assert _label_keys(test_client, headers) == DEFAULT_LABEL_KEYS
    assert ForumLabelDocument.find({"project_id": "test_project"}).count() == len(
        DEFAULT_LABEL_KEYS
    )


def test_default_label_ambiguous_insert_failure_is_retried_without_duplicates(
    test_client, init_db, monkeypatch
):
    """A default whose insert outcome is unknown is retried, and the retry cannot duplicate it."""
    headers = _setup_owner()
    real_insert = ForumLabelDocument.insert

    def write_then_lose_connection(self, *args, **kwargs):
        result = real_insert(self, *args, **kwargs)
        if self.key == "question":
            raise AutoReconnect("connection lost after the write")
        return result

    monkeypatch.setattr(ForumLabelDocument, "insert", write_then_lose_connection)
    with pytest.raises(AutoReconnect):
        forum_service.ForumService._ensure_default_labels("test_project")
    monkeypatch.undo()

    assert _label_keys(test_client, headers) == DEFAULT_LABEL_KEYS
    assert ForumLabelDocument.find({"project_id": "test_project"}).count() == len(
        DEFAULT_LABEL_KEYS
    )


def _label_rows(key: str) -> list[dict[str, Any]]:
    """Return every stored row for a label key in the test project, deleted ones included."""
    return list(
        ForumLabelDocument.get_motor_collection().find({"project_id": "test_project", "key": key})
    )


def _pause_default_insert(monkeypatch, key, on_pause):
    """Run ``on_pause`` once when a seeder is about to insert the default ``key``.

    This replays a seeder that read the project's labels, found ``key`` missing, and
    then stalled before its insert while other requests ran.
    """
    real_insert = ForumLabelDocument.insert
    paused = False

    def insert(self, *args, **kwargs):
        nonlocal paused
        if not paused and self.key == key:
            paused = True
            on_pause()
        return real_insert(self, *args, **kwargs)

    monkeypatch.setattr(ForumLabelDocument, "insert", insert)


def _fail_reads(monkeypatch):
    """Make every later find or find_one on any collection raise a connection error."""
    collection_type = type(ForumLabelDocument.get_motor_collection())

    def lost(*args, **kwargs):
        raise AutoReconnect("connection lost")

    monkeypatch.setattr(collection_type, "find", lost)
    monkeypatch.setattr(collection_type, "find_one", lost)


def _set_thread_labels(test_client, headers, post, labels):
    """Replace a root thread's labels and return the HTTP response."""
    return test_client.patch(
        f"/forum/posts/{post['id']}",
        headers=headers,
        json={
            "category": post["category"],
            "title": post["title"],
            "content": post["content"],
            "labels": labels,
        },
    )


def test_delayed_seeder_cannot_undo_default_delete_even_when_reads_fail(
    test_client, init_db, monkeypatch
):
    """A delete that succeeded stays in effect against a seeder that stalled before inserting.

    Seeder B reads an empty project and stalls. Meanwhile request A creates the defaults,
    a thread is tagged ``agent``, and a user deletes ``agent``. From then on every
    database read fails. B resumes; its insert hits the deleted row's key, so nothing it
    does, and nothing it fails to read, can bring the default back.
    """
    headers = _setup_owner()
    thread: dict[str, Any] = {}

    def other_requests_run() -> None:
        assert _label_keys(test_client, headers) == DEFAULT_LABEL_KEYS
        created = _create_post(test_client, headers, labels=["agent"])
        assert created.status_code == 201, created.text
        thread.update(created.json())
        assert test_client.delete("/forum/labels/agent", headers=headers).status_code == 200
        _fail_reads(monkeypatch)

    _pause_default_insert(monkeypatch, "agent", other_requests_run)

    forum_service.ForumService._ensure_default_labels("test_project")
    monkeypatch.undo()

    [row] = _label_rows("agent")
    assert row["is_deleted"] is True
    assert "agent" not in _label_keys(test_client, headers)
    fetched = test_client.get(f"/forum/posts/{thread['id']}", headers=headers)
    assert fetched.json()["labels"] == []
    assert _create_post(test_client, headers, title="stale", labels=["agent"]).status_code == 422


def test_delayed_seeder_preserves_explicitly_recreated_default_and_its_threads(
    test_client, init_db, monkeypatch
):
    """A user's recreation of a deleted default survives a seeder that stalled before it."""
    headers = _setup_owner()
    thread: dict[str, Any] = {}

    def other_requests_run() -> None:
        assert _label_keys(test_client, headers) == DEFAULT_LABEL_KEYS
        assert test_client.delete("/forum/labels/agent", headers=headers).status_code == 200
        recreated = test_client.post(
            "/forum/labels", headers=headers, json={"name": "Agent", "color": "#AA0011"}
        )
        assert recreated.status_code == 201, recreated.text
        assert recreated.json()["key"] == "agent"
        created = _create_post(test_client, headers, labels=["agent", "question"])
        assert created.status_code == 201, created.text
        thread.update(created.json())

    _pause_default_insert(monkeypatch, "agent", other_requests_run)

    forum_service.ForumService._ensure_default_labels("test_project")
    monkeypatch.undo()

    [row] = _label_rows("agent")
    assert (row["is_deleted"], row["color"]) == (False, "#aa0011")
    fetched = test_client.get(f"/forum/posts/{thread['id']}", headers=headers)
    assert fetched.json()["labels"] == ["agent", "question"]
    stored = ForumPostDocument.get_motor_collection().find_one({"title": thread["title"]})
    assert stored is not None
    assert stored["labels"] == ["agent", "question"]


def test_delayed_seeder_keeps_default_renamed_during_stall(test_client, init_db, monkeypatch):
    """A seeder stalled before its insert leaves a default that a user edited meanwhile."""
    headers = _setup_owner()

    def other_requests_run() -> None:
        assert _label_keys(test_client, headers) == DEFAULT_LABEL_KEYS
        renamed = test_client.patch(
            "/forum/labels/agent", headers=headers, json={"name": "Renamed", "color": "#040506"}
        )
        assert renamed.status_code == 200, renamed.text

    _pause_default_insert(monkeypatch, "agent", other_requests_run)
    forum_service.ForumService._ensure_default_labels("test_project")
    monkeypatch.undo()

    [row] = _label_rows("agent")
    assert (row["name"], row["color"], row["is_deleted"]) == ("Renamed", "#040506", False)


def test_label_update_racing_a_delete_does_not_restore_the_label(test_client, init_db, monkeypatch):
    """An update that read the label before a delete cannot write the deleted label back."""
    headers = _setup_owner()
    assert _label_keys(test_client, headers) == DEFAULT_LABEL_KEYS
    real_find = ForumLabelDocument.find
    deleted = False

    def find(*args, **kwargs):
        # The update's duplicate-name check runs after it read the label.
        nonlocal deleted
        if not deleted:
            deleted = True
            assert test_client.delete("/forum/labels/agent", headers=headers).status_code == 200
        return real_find(*args, **kwargs)

    monkeypatch.setattr(ForumLabelDocument, "find", find)
    response = test_client.patch("/forum/labels/agent", headers=headers, json={"name": "Later"})
    monkeypatch.undo()

    assert deleted
    assert response.status_code == 404
    [row] = _label_rows("agent")
    assert (row["name"], row["is_deleted"]) == ("agent", True)


def test_recreating_deleted_default_restores_its_key(test_client, init_db):
    """Creating a label named like a deleted default reuses the deleted row and its key."""
    headers = _setup_owner()
    root = _create_post(test_client, headers, labels=["agent"])
    assert root.status_code == 201, root.text
    assert test_client.delete("/forum/labels/agent", headers=headers).status_code == 200

    recreated = test_client.post(
        "/forum/labels",
        headers=headers,
        json={"name": "AGENT", "color": "#ABCDEF", "description": "Ours"},
    )

    assert recreated.status_code == 201, recreated.text
    assert recreated.json() == {
        "key": "agent",
        "name": "AGENT",
        "description": "Ours",
        "color": "#abcdef",
    }
    assert len(_label_rows("agent")) == 1
    assert _label_keys(test_client, headers)[-1] == "agent"
    # The delete removed the old tag; the restored label starts with no threads.
    assert (
        test_client.get(f"/forum/posts/{root.json()['id']}", headers=headers).json()["labels"] == []
    )
    tagged = _set_thread_labels(test_client, headers, root.json(), ["agent"])
    assert tagged.status_code == 200, tagged.text
    assert tagged.json()["labels"] == ["agent"]
    duplicate = test_client.post(
        "/forum/labels", headers=headers, json={"name": "agent", "color": "#111111"}
    )
    assert duplicate.status_code == 409
    # Deleting the restored label hides it again without losing the reserved key.
    assert test_client.delete("/forum/labels/agent", headers=headers).status_code == 200
    assert "agent" not in _label_keys(test_client, headers)
    assert [row["is_deleted"] for row in _label_rows("agent")] == [True]


def test_recreate_falls_back_to_new_key_when_deleted_row_was_restored_first(
    test_client, init_db, monkeypatch
):
    """If another request restores the deleted row first, the create gets a fresh key."""
    headers = _setup_owner()
    assert test_client.delete("/forum/labels/agent", headers=headers).status_code == 200
    monkeypatch.setattr(
        forum_service.ForumService,
        "_restore_deleted_label",
        staticmethod(lambda doc, key: False),
    )

    created = test_client.post(
        "/forum/labels", headers=headers, json={"name": "Agent", "color": "#111111"}
    )

    assert created.status_code == 201, created.text
    assert created.json()["key"] == "agent-2"
    [row] = _label_rows("agent")
    assert row["is_deleted"] is True


def test_deleting_custom_label_removes_its_row(test_client, init_db):
    """Only default keys are kept as deleted rows; other labels are removed outright."""
    headers = _setup_owner()
    [key] = _create_named_labels(test_client, headers, "Review")

    assert test_client.delete(f"/forum/labels/{key}", headers=headers).status_code == 200

    assert _label_rows(key) == []
    assert test_client.delete(f"/forum/labels/{key}", headers=headers).status_code == 404
    assert test_client.delete("/forum/labels/agent", headers=headers).status_code == 200
    assert test_client.delete("/forum/labels/agent", headers=headers).status_code == 404
    assert (
        test_client.patch("/forum/labels/agent", headers=headers, json={"name": "Back"}).status_code
        == 404
    )


def test_default_forum_labels_preserve_existing_project_labels(test_client, init_db):
    """Seeding an existing project keeps its labels and skips defaults whose key or name is taken."""
    headers = _setup_owner()
    for key, name, color in (
        ("hardware", "Cryo hardware", "#010203"),
        ("triage", "Question", "#040506"),
        ("review", "Review", "#070809"),
    ):
        ForumLabelDocument(project_id="test_project", key=key, name=name, color=color).insert()

    listed = test_client.get("/forum/labels", headers=headers).json()["labels"]

    by_key = {item["key"]: item for item in listed}
    assert set(by_key) == {"hardware", "triage", "review", "agent", "calibration", "software"}
    assert (by_key["hardware"]["name"], by_key["hardware"]["color"]) == (
        "Cryo hardware",
        "#010203",
    )
    assert (by_key["triage"]["name"], by_key["triage"]["color"]) == ("Question", "#040506")
    assert (by_key["review"]["name"], by_key["review"]["color"]) == ("Review", "#070809")
    # The default "question" is reserved as deleted because its name is taken.
    [question] = _label_rows("question")
    assert question["is_deleted"] is True
    assert _label_keys(test_client, headers) == [item["key"] for item in listed]


def test_default_forum_labels_are_project_scoped(test_client, init_db):
    """Each project gets its own defaults; deleting one in a project leaves others alone."""
    headers = _setup_owner()
    owner = UserDocument.find_one({"username": "owner"}).run()
    assert owner is not None
    ProjectDocument(
        project_id="other_project",
        name="Other Project",
        owner_user_id=owner.user_id,
        owner_username="owner",
    ).insert()
    ProjectMembershipDocument(
        project_id="other_project",
        user_id=owner.user_id,
        username="owner",
        role=ProjectRole.OWNER,
        status="active",
        invited_by_user_id=owner.user_id,
        invited_by="owner",
    ).insert()
    other_headers = {**headers, "X-Project-Id": "other_project"}

    assert _label_keys(test_client, headers) == DEFAULT_LABEL_KEYS
    assert test_client.delete("/forum/labels/agent", headers=headers).status_code == 200
    updated = test_client.patch("/forum/labels/hardware", headers=headers, json={"name": "Fridge"})
    assert updated.status_code == 200, updated.text

    other = test_client.get("/forum/labels", headers=other_headers).json()["labels"]
    assert [item["key"] for item in other] == DEFAULT_LABEL_KEYS
    assert next(item for item in other if item["key"] == "hardware")["name"] == "hardware"
    assert _label_keys(test_client, headers) == [
        key for key in DEFAULT_LABEL_KEYS if key != "agent"
    ]


def test_owner_can_create_update_and_delete_forum_label(test_client, init_db):
    """Project owners can manage custom forum labels."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    created = test_client.post(
        "/forum/labels",
        headers=headers,
        json={"name": "Cryostat", "color": "#ABCDEF"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["key"] == "cryostat"
    assert body["color"] == "#abcdef"
    assert "is_system" not in body

    duplicate = test_client.post(
        "/forum/labels",
        headers=headers,
        json={"name": "cryostat", "color": "#111111"},
    )
    assert duplicate.status_code == 409

    updated = test_client.patch(
        "/forum/labels/cryostat",
        headers=headers,
        json={"name": "Cryostat Issue", "color": "#222222"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Cryostat Issue"
    assert updated.json()["color"] == "#222222"

    deleted = test_client.delete("/forum/labels/cryostat", headers=headers)
    assert deleted.status_code == 200

    listed = test_client.get("/forum/labels", headers=headers)
    assert "cryostat" not in {item["key"] for item in listed.json()["labels"]}


def test_update_forum_label_rejects_case_insensitive_duplicate_name(test_client, init_db):
    """Renaming a label to another label's name, ignoring case, is rejected with 409."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")
    _create_named_labels(test_client, headers, "Review")

    created = test_client.post(
        "/forum/labels", headers=headers, json={"name": "Cryostat", "color": "#111111"}
    )
    assert created.status_code == 201, created.text

    response = test_client.patch("/forum/labels/cryostat", headers=headers, json={"name": "REVIEW"})
    assert response.status_code == 409


def test_update_forum_label_allows_case_variant_of_own_name(test_client, init_db):
    """Renaming a label to a different casing of its own name succeeds."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    created = test_client.post(
        "/forum/labels", headers=headers, json={"name": "Cryostat", "color": "#111111"}
    )
    assert created.status_code == 201, created.text

    response = test_client.patch(
        "/forum/labels/cryostat", headers=headers, json={"name": "CRYOSTAT"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "CRYOSTAT"


def test_forum_label_rejects_whitespace_only_name(test_client, init_db):
    """Whitespace-only label names are rejected on create and update."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    blank = test_client.post(
        "/forum/labels", headers=headers, json={"name": "   ", "color": "#111111"}
    )
    assert blank.status_code == 422

    created = test_client.post(
        "/forum/labels", headers=headers, json={"name": "  Cryostat  ", "color": "#111111"}
    )
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "Cryostat"

    renamed = test_client.patch("/forum/labels/cryostat", headers=headers, json={"name": "   "})
    assert renamed.status_code == 422


def test_create_forum_label_with_japanese_only_name_gets_random_key(test_client, init_db):
    """A name with no usable ASCII characters falls back to a random ``label-`` key."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    created = test_client.post(
        "/forum/labels",
        headers=headers,
        json={"name": "異常", "color": "#123456"},
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "異常"
    assert re.fullmatch(r"label-[a-z0-9]{6}", body["key"])


def test_create_forum_label_ignores_client_supplied_key(test_client, init_db):
    """A ``key`` sent in the request body is ignored; it is always derived from the name."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    created = test_client.post(
        "/forum/labels",
        headers=headers,
        json={"key": "totally-custom", "name": "Firmware", "color": "#123456"},
    )

    assert created.status_code == 201, created.text
    assert created.json()["key"] == "firmware"


def test_create_forum_label_slug_collision_gets_numeric_suffix(test_client, init_db):
    """A name whose slug collides with an existing label's key gets a ``-2`` suffix."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    first = test_client.post(
        "/forum/labels", headers=headers, json={"name": "Bug?", "color": "#111111"}
    )
    assert first.status_code == 201, first.text
    assert first.json()["key"] == "bug"

    second = test_client.post(
        "/forum/labels", headers=headers, json={"name": "Bug!", "color": "#222222"}
    )
    assert second.status_code == 201, second.text
    assert second.json()["key"] == "bug-2"


def test_editor_can_create_update_and_delete_forum_label(test_client, init_db):
    """Project editors can create, update, and delete forum labels."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_user("editor", "editor_token", ProjectRole.EDITOR)
    _create_project()
    headers = _headers("editor_token")

    created = test_client.post(
        "/forum/labels", headers=headers, json={"name": "Cryostat", "color": "#123456"}
    )
    assert created.status_code == 201, created.text
    key = created.json()["key"]

    updated = test_client.patch(
        f"/forum/labels/{key}", headers=headers, json={"name": "Cryostat v2"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Cryostat v2"

    deleted = test_client.delete(f"/forum/labels/{key}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    [owner_key] = _create_named_labels(test_client, _headers("owner_token"), "Owner label")
    updated_owner_label = test_client.patch(
        f"/forum/labels/{owner_key}", headers=headers, json={"name": "Owner label v2"}
    )
    assert updated_owner_label.status_code == 200, updated_owner_label.text
    deleted_owner_label = test_client.delete(f"/forum/labels/{owner_key}", headers=headers)
    assert deleted_owner_label.status_code == 200, deleted_owner_label.text

    assert _label_keys(test_client, headers) == DEFAULT_LABEL_KEYS


def test_viewer_cannot_manage_forum_labels(test_client, init_db):
    """Project viewers get 403 when creating, updating, or deleting forum labels."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_user("viewer", "viewer_token", ProjectRole.VIEWER)
    _create_project()
    owner_headers = _headers("owner_token")
    viewer_headers = _headers("viewer_token")

    created = test_client.post(
        "/forum/labels", headers=owner_headers, json={"name": "Cryostat", "color": "#123456"}
    )
    assert created.status_code == 201, created.text
    key = created.json()["key"]

    assert (
        test_client.post(
            "/forum/labels", headers=viewer_headers, json={"name": "Other", "color": "#654321"}
        ).status_code
        == 403
    )
    assert (
        test_client.patch(
            f"/forum/labels/{key}", headers=viewer_headers, json={"name": "Changed"}
        ).status_code
        == 403
    )
    assert test_client.delete(f"/forum/labels/{key}", headers=viewer_headers).status_code == 403


def test_delete_forum_label_removes_it_from_posts(test_client, init_db):
    """Deleting a label pulls it from every thread that used it."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")

    created = test_client.post(
        "/forum/labels", headers=headers, json={"name": "Flaky", "color": "#654321"}
    )
    assert created.status_code == 201
    _create_named_labels(test_client, headers, "Review")

    root = _create_post(test_client, headers, labels=["flaky", "review"])
    assert root.status_code == 201, root.text
    root_id = root.json()["id"]

    deleted = test_client.delete("/forum/labels/flaky", headers=headers)
    assert deleted.status_code == 200

    fetched = test_client.get(f"/forum/posts/{root_id}", headers=headers)
    assert fetched.json()["labels"] == ["review"]


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


def test_editor_can_update_forum_thread_metadata(test_client, init_db):
    """Project editors can manage metadata on a thread created by another user."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_user("editor", "editor_token", ProjectRole.EDITOR)
    _create_project()
    _create_named_labels(test_client, _headers("owner_token"), "Anomaly")

    root = _create_post(test_client, _headers("owner_token"))
    root_id = root.json()["id"]
    response = test_client.patch(
        f"/forum/posts/{root_id}",
        headers=_headers("editor_token"),
        json={
            "category": "coupling",
            "content": root.json()["content"],
            "labels": ["anomaly"],
            "status": "investigating",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["category"] == "coupling"
    assert response.json()["labels"] == ["anomaly"]
    assert response.json()["status"] == "investigating"


def test_editor_can_update_another_users_forum_thread_title(test_client, init_db):
    """Project editors can update the title without permission to rewrite the content."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_user("editor", "editor_token", ProjectRole.EDITOR)
    _create_project()

    root = _create_post(test_client, _headers("owner_token"))
    response = test_client.patch(
        f"/forum/posts/{root.json()['id']}",
        headers=_headers("editor_token"),
        json={"title": "Clarified title", "content": root.json()["content"]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Clarified title"
    assert response.json()["content"] == root.json()["content"]


def test_editor_cannot_update_another_users_forum_content(test_client, init_db):
    """Metadata moderation does not grant editors permission to rewrite post content."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_user("editor", "editor_token", ProjectRole.EDITOR)
    _create_project()

    root = _create_post(test_client, _headers("owner_token"))
    response = test_client.patch(
        f"/forum/posts/{root.json()['id']}",
        headers=_headers("editor_token"),
        json={"content": "Rewritten by editor", "status": "investigating"},
    )

    assert response.status_code == 403


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


def test_upload_forum_image_openapi_contract(test_client):
    """Forum image upload is a documented multipart API operation."""
    operation = test_client.app.openapi()["paths"]["/forum/upload-image"]["post"]

    assert operation["operationId"] == "uploadForumImage"
    assert operation["requestBody"]["content"]["multipart/form-data"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ForumImageUploadResponse"
    }
    assert operation["responses"]["400"]["description"]

    upload_schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    component = upload_schema["$ref"].rsplit("/", 1)[-1]
    assert (
        test_client.app.openapi()["components"]["schemas"][component]["properties"]["file"][
            "format"
        ]
        == "binary"
    )

    bulk_import = test_client.app.openapi()["paths"]["/admin/users/bulk-import"]["post"]
    bulk_schema = bulk_import["requestBody"]["content"]["multipart/form-data"]["schema"]
    bulk_component = bulk_schema["$ref"].rsplit("/", 1)[-1]
    assert (
        test_client.app.openapi()["components"]["schemas"][bulk_component]["properties"]["file"][
            "format"
        ]
        == "binary"
    )


def test_upload_forum_image_rejects_unsupported_content_type(test_client, init_db):
    """Forum image upload reports unsupported multipart files as a client error."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()

    upload = test_client.post(
        "/forum/upload-image",
        headers=_headers("owner_token"),
        files={"file": ("analysis.svg", b"<svg />", "image/svg+xml")},
    )

    assert upload.status_code == 400
    assert "Unsupported image type" in upload.json()["detail"]


def _create_task_result(task_id: str, qid: str = "12", chip_id: str = "chip-1") -> None:
    from datetime import UTC, datetime

    from qdash.datamodel.note import NoteModel
    from qdash.datamodel.system_info import SystemInfoModel
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    TaskResultHistoryDocument(
        project_id="test_project",
        username="owner",
        task_id=task_id,
        name="CheckT1",
        upstream_id="",
        status="completed",
        message="",
        input_parameters={},
        output_parameters={},
        output_parameter_names=[],
        note={},
        user_note=NoteModel(),
        figure_path=[],
        json_figure_path=[],
        raw_data_path=[],
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 1, 1, tzinfo=UTC),
        elapsed_time=1.0,
        task_type="qubit",
        system_info=SystemInfoModel(),
        qid=qid,
        execution_id="exec-1",
        tags=[],
        chip_id=chip_id,
    ).insert()


def test_forum_thread_about_a_task_result(test_client, init_db):
    """A thread may be about one task result: linked, filterable, inherited by replies."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    headers = _headers("owner_token")
    _create_task_result("task-1", qid="4-6")

    body = {
        "category": "qubit",
        "title": "ZX90 fidelity looks off",
        "content": "The interleaved curve decays too fast.",
        "parent_id": None,
        "task_id": "task-1",
    }
    created = test_client.post("/forum/posts", headers=headers, json=body)
    assert created.status_code == 201, created.text
    root = created.json()
    assert root["task_id"] == "task-1"
    assert root["task_result"]["task_name"] == "CheckT1"
    # Chip and target come from the task result when not given.
    assert (root["chip_id"], root["target_type"], root["target_id"]) == (
        "chip-1",
        "coupling",
        "4-6",
    )

    reply = _create_post(test_client, headers, title=None, content="Agreed", parent_id=root["id"])
    assert reply.status_code == 201, reply.text
    assert reply.json()["task_id"] == "task-1"

    listed = test_client.get("/forum/posts", headers=headers, params={"task_id": "task-1"})
    assert [post["id"] for post in listed.json()["posts"]] == [root["id"]]
    # Listings and the thread carry the result's summary, so the forum shows its state.
    summary = listed.json()["posts"][0]["task_result"]
    assert (summary["task_name"], summary["qid"], summary["status"]) == (
        "CheckT1",
        "4-6",
        "completed",
    )
    fetched = test_client.get(f"/forum/posts/{root['id']}", headers=headers).json()
    assert fetched["task_result"]["task_id"] == "task-1"
    assert (
        test_client.get("/forum/posts", headers=headers, params={"task_id": "other"}).json()[
            "posts"
        ]
        == []
    )

    # A closed thread about the result still shows up with status=all.
    closed = test_client.patch(f"/forum/posts/{root['id']}/close", headers=headers)
    assert closed.status_code == 200, closed.text
    assert (
        test_client.get("/forum/posts", headers=headers, params={"task_id": "task-1"}).json()[
            "posts"
        ]
        == []
    )
    everything = test_client.get(
        "/forum/posts", headers=headers, params={"task_id": "task-1", "status": "all"}
    ).json()["posts"]
    assert [post["id"] for post in everything] == [root["id"]]

    unknown = test_client.post("/forum/posts", headers=headers, json={**body, "task_id": "nope"})
    assert unknown.status_code == 404

    explicit = test_client.post(
        "/forum/posts",
        headers=headers,
        json={**body, "chip_id": "chip-9", "target_type": "qubit", "target_id": "0"},
    )
    assert explicit.status_code == 201, explicit.text
    assert (explicit.json()["chip_id"], explicit.json()["target_id"]) == ("chip-9", "0")


def _setup_owner():
    """Create the owner and project, returning the owner's headers."""
    _create_user("owner", "owner_token", ProjectRole.OWNER)
    _create_project()
    return _headers("owner_token")


def _create_named_labels(test_client, headers, *names):
    """Create one label per name as the owner and return their keys."""
    keys = []
    for name in names:
        response = test_client.post(
            "/forum/labels", headers=headers, json={"name": name, "color": "#123456"}
        )
        assert response.status_code == 201, response.text
        keys.append(response.json()["key"])
    return keys


def test_make_label_key_random_exhaustion_raises(monkeypatch):
    """A non-ASCII name whose random keys always collide fails with a 500."""
    monkeypatch.setattr(secrets, "token_hex", lambda _n: "abcdef")
    with pytest.raises(HTTPException) as exc_info:
        forum_service.ForumService._make_label_key("日本語", {"label-abcdef"})
    assert exc_info.value.status_code == 500


def test_make_label_key_suffix_exhaustion_raises():
    """A slug whose numeric suffixes are all taken fails with a 500."""
    existing = {"dup", *(f"dup-{n}" for n in range(2, 1000))}
    with pytest.raises(HTTPException) as exc_info:
        forum_service.ForumService._make_label_key("dup", existing)
    assert exc_info.value.status_code == 500


def test_create_forum_label_insert_race_returns_conflict(test_client, init_db, monkeypatch):
    """A duplicate-key error on insert is reported as a 409."""
    headers = _setup_owner()

    def _raise(*_args, **_kwargs):
        """Simulate a concurrent insert of the same label."""
        raise DuplicateKeyError("dup")

    monkeypatch.setattr(ForumLabelDocument, "insert", _raise)
    response = test_client.post(
        "/forum/labels", headers=headers, json={"name": "Racy", "color": "#111111"}
    )
    assert response.status_code == 409


def test_update_and_delete_unknown_forum_label_return_404(test_client, init_db):
    """Updating or deleting a missing label returns 404."""
    headers = _setup_owner()

    patched = test_client.patch("/forum/labels/missing", headers=headers, json={"name": "X"})
    assert patched.status_code == 404
    deleted = test_client.delete("/forum/labels/missing", headers=headers)
    assert deleted.status_code == 404


def test_update_forum_label_description_round_trips(test_client, init_db):
    """Label descriptions can be updated."""
    headers = _setup_owner()
    _create_named_labels(test_client, headers, "Review")

    updated = test_client.patch(
        "/forum/labels/review", headers=headers, json={"description": "Needs a look"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["description"] == "Needs a look"
    listed = test_client.get("/forum/labels", headers=headers)
    review = next(item for item in listed.json()["labels"] if item["key"] == "review")
    assert review["description"] == "Needs a look"


def test_undefined_stored_label_is_omitted_and_dropped_on_update(test_client, init_db):
    """A stored label key without a definition is hidden and replaced on the next update."""
    headers = _setup_owner()
    root = _create_post(test_client, headers)
    assert root.status_code == 201, root.text
    root_id = root.json()["id"]
    ForumPostDocument.find_one({"_id": ObjectId(root_id)}).update(
        {"$set": {"labels": ["review"]}}
    ).run()

    fetched = test_client.get(f"/forum/posts/{root_id}", headers=headers)
    assert fetched.json()["labels"] == []

    (key,) = _create_named_labels(test_client, headers, "Anomaly")
    updated = test_client.patch(
        f"/forum/posts/{root_id}",
        headers=headers,
        json={
            "category": "qubit",
            "title": root.json()["title"],
            "content": root.json()["content"],
            "labels": [key],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["labels"] == [key]


def test_list_posts_and_replies_omit_undefined_stored_labels(test_client, init_db):
    """Listing posts and replies keeps defined label keys and omits undefined ones."""
    headers = _setup_owner()
    (key,) = _create_named_labels(test_client, headers, "Anomaly")
    root = _create_post(test_client, headers)
    root_id = root.json()["id"]
    reply = _create_post(test_client, headers, title=None, content="Reply", parent_id=root_id)
    for post_id in (root_id, reply.json()["id"]):
        ForumPostDocument.find_one({"_id": ObjectId(post_id)}).update(
            {"$set": {"labels": ["review", key]}}
        ).run()

    posts = test_client.get("/forum/posts", headers=headers)
    assert [post["labels"] for post in posts.json()["posts"]] == [[key]]
    replies = test_client.get(f"/forum/posts/{root_id}/replies", headers=headers)
    assert [post["labels"] for post in replies.json()] == [[key]]


def test_thread_with_labels_can_be_updated_unchanged(test_client, init_db):
    """A thread carrying labels accepts its own labels back in an update."""
    headers = _setup_owner()
    _create_named_labels(test_client, headers, "Review", "Anomaly")
    root = _create_post(test_client, headers, labels=["review", "anomaly"])
    assert root.status_code == 201, root.text

    updated = test_client.patch(
        f"/forum/posts/{root.json()['id']}",
        headers=headers,
        json={
            "category": "qubit",
            "title": root.json()["title"],
            "content": root.json()["content"],
            "labels": ["review", "anomaly"],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["labels"] == ["review", "anomaly"]
