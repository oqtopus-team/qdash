"""Chat snapshots shared with a project: who may read, update and revoke, and what is copied."""

from __future__ import annotations

import json
from typing import Any

import pytest

from qdash.api.services.agent_chat_session_service import AgentChatSessionService
from qdash.api.services.agent_chat_share_service import AgentChatShareService
from qdash.common.utils.datetime import now
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.agent_chat_session import (
    AgentChatMessage,
    AgentChatServerTurn,
    AgentChatSessionDocument,
)
from qdash.dbmodel.agent_chat_share import AgentChatShareDocument
from qdash.dbmodel.agent_chat_turn import AgentChatTurnDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument

PROJECT = "share_project"
OTHER_PROJECT = "other_project"


def _user(username: str, project_id: str = PROJECT) -> UserDocument:
    user = UserDocument(
        username=username,
        hashed_password="hashed",
        access_token=f"{username}_token",
        default_project_id=project_id,
        system_info=SystemInfoModel(),
    )
    user.insert()
    return user


def _member(user: UserDocument, project_id: str, role: ProjectRole) -> None:
    ProjectMembershipDocument(
        project_id=project_id,
        user_id=user.user_id,
        username=user.username,
        role=role,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by=user.username,
    ).insert()


def _project(project_id: str, owner: UserDocument) -> None:
    ProjectDocument(
        project_id=project_id,
        name=project_id,
        owner_user_id=owner.user_id,
        owner_username=owner.username,
    ).insert()
    _member(owner, project_id, ProjectRole.OWNER)


def _headers(username: str, project_id: str = PROJECT) -> dict[str, str]:
    return {"Authorization": f"Bearer {username}_token", "X-Project-Id": project_id}


@pytest.fixture
def people(init_db: Any) -> dict[str, UserDocument]:
    """A project owner, two editors (alice owns the chat), a viewer, and an outsider."""
    users = {name: _user(name) for name in ("lead", "alice", "bob", "vera", "outsider")}
    _project(PROJECT, users["lead"])
    _member(users["alice"], PROJECT, ProjectRole.EDITOR)
    _member(users["bob"], PROJECT, ProjectRole.EDITOR)
    _member(users["vera"], PROJECT, ProjectRole.VIEWER)
    _project(OTHER_PROJECT, users["outsider"])
    _member(users["alice"], OTHER_PROJECT, ProjectRole.EDITOR)
    return users


ANSWER = {
    "blocks": [
        {"type": "text", "content": "Q5 looks **stable**.", "chart": None},
        {
            "type": "chart",
            "content": None,
            "chart": {"data": [{"x": [1, 2], "y": [3, 4]}], "layout": {"title": "T1"}},
        },
        {"type": "ask", "content": None, "chart": None, "ask": {"question": "Run it?"}},
        {"type": "ui", "content": "Summary table", "chart": None, "ui": {"version": 1}},
    ],
    "assessment": None,
    "images_sent": {
        "experiment_figure": True,
        "experiment_figure_paths": ["/calib/secret/fig.png"],
        "expected_images": [],
        "task_name": "CheckT1",
    },
    "trace": {
        "steps": [
            {
                "kind": "tool",
                "id": "t1",
                "tool": "bash",
                "label": "cat /workspace/notes.md",
                "status": "done",
                "output": "WORKSPACE SECRET",
                "figures": ["/calib/secret/fig.png"],
            }
        ],
        "durationMs": 10,
    },
    "feedback": "up",
}


def _chat(
    *,
    username: str = "alice",
    session_id: str = "s1",
    messages: list[AgentChatMessage] | None = None,
    turn: AgentChatServerTurn | None = None,
) -> AgentChatSessionDocument:
    doc = AgentChatSessionDocument(
        username=username,
        session_id=session_id,
        title="Calibrate Q5",
        store_session_id="store-xyz",
        conversation_id="conv-123",
        messages=messages
        if messages is not None
        else [
            AgentChatMessage(
                role="user",
                content="How is Q5?",
                attached_image="1",
                turn_request_id="req-1",
            ),
            AgentChatMessage(
                role="assistant",
                content=json.dumps(ANSWER),
                entry_id="42",
                turn_request_id="req-1",
            ),
        ],
        turn=turn,
    )
    doc.insert()
    AgentChatTurnDocument(
        username=username,
        session_id=session_id,
        request_id="req-1",
        project_id=PROJECT,
        planner_model="test/model",
    ).insert()
    return doc


def _share(client: Any, username: str = "alice", session_id: str = "s1") -> dict[str, Any]:
    response = client.put(f"/agent/chat/sessions/{session_id}/share", headers=_headers(username))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_owner_shares_and_members_read_a_sanitized_snapshot(test_client, people):
    _chat()
    assert test_client.get("/agent/chat/sessions/s1/share", headers=_headers("alice")).json() == {
        "share": None
    }

    summary = _share(test_client)
    assert summary["share_id"].startswith("chatshare_")
    assert summary["project_id"] == PROJECT
    assert summary["message_count"] == 2
    status = test_client.get("/agent/chat/sessions/s1/share", headers=_headers("alice")).json()
    assert status["share"]["share_id"] == summary["share_id"]

    for reader in ("bob", "vera", "lead"):
        got = test_client.get(f"/agent/chat/shares/{summary['share_id']}", headers=_headers(reader))
        assert got.status_code == 200, (reader, got.text)
        assert got.headers["cache-control"] == "private, no-store"
    body = got.json()
    assert body["title"] == "Calibrate Q5"
    assert body["owner_username"] == "alice"
    assert body["is_owner"] is False
    user, answer = body["messages"]
    assert user["role"] == "user"
    assert user["blocks"] == [{"type": "text", "content": "How is Q5?", "chart": None, "ui": None}]
    assert user["figures_attached"] is True
    assert [b["type"] for b in answer["blocks"]] == ["text", "chart", "ui"]
    assert answer["blocks"][1]["chart"]["layout"] == {"title": "T1"}
    assert answer["omitted_content"] is True

    raw = json.dumps(body)
    # Nothing of the owner's runtime, workspace or figure paths, nor the private chat ID.
    for leaked in (
        "WORKSPACE SECRET",
        "/calib/secret",
        "store-xyz",
        "conv-123",
        "req-1",
        '"42"',
        "Run it?",
        '"s1"',
        "feedback",
    ):
        assert leaked not in raw, leaked


def test_non_members_and_other_projects_cannot_read_a_share(test_client, people):
    _chat()
    share_id = _share(test_client)["share_id"]
    # Not a member of the share's project.
    response = test_client.get(f"/agent/chat/shares/{share_id}", headers=_headers("outsider"))
    assert response.status_code == 403
    # A member of the share's project asking in another project sees nothing.
    response = test_client.get(
        f"/agent/chat/shares/{share_id}", headers=_headers("outsider", OTHER_PROJECT)
    )
    assert response.status_code == 404
    response = test_client.get(
        f"/agent/chat/shares/{share_id}", headers=_headers("alice", OTHER_PROJECT)
    )
    assert response.status_code == 404
    # The original chat stays private to its owner.
    assert test_client.get("/agent/chat/sessions/s1", headers=_headers("bob")).status_code == 404


def test_only_the_owner_can_share_or_update_their_chat(test_client, people):
    _chat()
    # Another member cannot share, update or see the sharing state of alice's chat.
    for method in ("put", "get"):
        response = getattr(test_client, method)(
            "/agent/chat/sessions/s1/share", headers=_headers("bob")
        )
        assert response.status_code == 404
    # A viewer cannot share their own chat with the project.
    _chat(username="vera", session_id="v1")
    response = test_client.put("/agent/chat/sessions/v1/share", headers=_headers("vera"))
    assert response.status_code == 403
    assert AgentChatShareDocument.find_all().to_list() == []


def test_the_snapshot_does_not_follow_the_chat_until_updated(test_client, people):
    chat = _chat()
    first = _share(test_client)
    share_id = first["share_id"]

    chat.messages.append(AgentChatMessage(role="user", content="And Q6?"))
    chat.messages.append(AgentChatMessage(role="assistant", content="Q6 drifts."))
    chat.title = "Calibrate Q5 and Q6"
    chat.save()

    got = test_client.get(f"/agent/chat/shares/{share_id}", headers=_headers("bob")).json()
    assert len(got["messages"]) == 2
    assert got["title"] == "Calibrate Q5"

    updated = _share(test_client)
    assert updated["share_id"] == share_id
    assert updated["created_at"] == first["created_at"]
    assert updated["message_count"] == 4
    got = test_client.get(f"/agent/chat/shares/{share_id}", headers=_headers("bob")).json()
    assert got["title"] == "Calibrate Q5 and Q6"
    assert got["messages"][-1]["blocks"][0]["content"] == "Q6 drifts."
    assert AgentChatShareDocument.find_all().count() == 1


def test_revoke_by_owner_or_project_owner_only(test_client, people):
    _chat()
    share_id = _share(test_client)["share_id"]
    as_bob = test_client.get(f"/agent/chat/shares/{share_id}", headers=_headers("bob")).json()
    assert as_bob["can_revoke"] is False
    as_lead = test_client.get(f"/agent/chat/shares/{share_id}", headers=_headers("lead")).json()
    assert as_lead["can_revoke"] is True

    for other in ("bob", "vera"):
        response = test_client.delete(f"/agent/chat/shares/{share_id}", headers=_headers(other))
        assert response.status_code == 403
    response = test_client.delete(
        f"/agent/chat/shares/{share_id}", headers=_headers("alice", OTHER_PROJECT)
    )
    assert response.status_code == 404

    response = test_client.delete(f"/agent/chat/shares/{share_id}", headers=_headers("lead"))
    assert response.status_code == 200
    assert (
        test_client.get(f"/agent/chat/shares/{share_id}", headers=_headers("bob")).status_code
        == 404
    )
    # The original chat is untouched.
    assert test_client.get("/agent/chat/sessions/s1", headers=_headers("alice")).status_code == 200

    share_id = _share(test_client)["share_id"]
    response = test_client.delete(f"/agent/chat/shares/{share_id}", headers=_headers("alice"))
    assert response.status_code == 200
    assert test_client.get("/agent/chat/sessions/s1/share", headers=_headers("alice")).json() == {
        "share": None
    }


def test_a_chat_with_answers_from_another_project_is_not_shared(test_client, people):
    _chat()
    response = test_client.put(
        "/agent/chat/sessions/s1/share", headers=_headers("alice", OTHER_PROJECT)
    )
    assert response.status_code == 409
    assert "another project" in response.json()["detail"]
    assert AgentChatShareDocument.find_all().to_list() == []


def test_a_running_or_empty_chat_is_not_shared(test_client, people):
    _chat(turn=AgentChatServerTurn(request_id="req-1", project_id=PROJECT, status="running"))
    response = test_client.put("/agent/chat/sessions/s1/share", headers=_headers("alice"))
    assert response.status_code == 409
    _chat(session_id="empty", messages=[])
    response = test_client.put("/agent/chat/sessions/empty/share", headers=_headers("alice"))
    assert response.status_code == 422


def test_deleting_the_chat_removes_its_shares(test_client, people, monkeypatch):
    async def fake_delete(self: Any, *, username: str, session_id: str, **_: Any) -> None:
        AgentChatSessionDocument.find_one(
            {"username": username, "session_id": session_id}
        ).delete().run()

    monkeypatch.setattr(AgentChatSessionService, "delete_session", fake_delete)
    _chat()
    share_id = _share(test_client)["share_id"]
    response = test_client.delete("/agent/chat/sessions/s1", headers=_headers("alice"))
    assert response.status_code == 200, response.text
    assert (
        test_client.get(f"/agent/chat/shares/{share_id}", headers=_headers("bob")).status_code
        == 404
    )
    assert AgentChatShareDocument.find_all().to_list() == []


def _tombstone(username: str, session_id: str) -> None:
    """Hide a chat as the delete route does first, keeping it as a tombstone."""
    AgentChatSessionDocument.get_motor_collection().update_one(
        {"username": username, "session_id": session_id}, {"$set": {"deleted_at": now()}}
    )


def _hard_delete(username: str, session_id: str) -> None:
    AgentChatSessionDocument.find_one(
        {"username": username, "session_id": session_id}
    ).delete().run()


@pytest.mark.parametrize("remove", [_tombstone, _hard_delete], ids=["tombstone", "removed"])
@pytest.mark.parametrize("already_shared", [False, True], ids=["create", "update"])
def test_a_chat_deleted_while_it_is_shared_leaves_no_snapshot(
    test_client, people, monkeypatch, remove, already_shared
):
    """A deletion that finishes between reading the chat and writing its snapshot."""
    _chat()
    if already_shared:
        share_id = _share(test_client)["share_id"]
    check = AgentChatShareService._check_shareable

    def delete_after_read(chat: AgentChatSessionDocument, project_id: str) -> None:
        check(chat, project_id)
        # The whole delete route runs here: hide the chat, then remove its snapshots.
        remove(chat.username, chat.session_id)
        AgentChatShareService.delete_for_chat(username=chat.username, session_id=chat.session_id)

    monkeypatch.setattr(AgentChatShareService, "_check_shareable", staticmethod(delete_after_read))
    response = test_client.put("/agent/chat/sessions/s1/share", headers=_headers("alice"))
    assert response.status_code == 404, response.text
    assert AgentChatShareDocument.find_all().to_list() == []
    if already_shared:
        got = test_client.get(f"/agent/chat/shares/{share_id}", headers=_headers("bob"))
        assert got.status_code == 404


def test_a_new_chat_reusing_the_session_id_does_not_keep_a_deleted_chats_snapshot(
    test_client, people, monkeypatch
):
    """The recheck follows the chat that was read, not whatever holds its session ID now."""
    _chat()
    check = AgentChatShareService._check_shareable

    def replace_after_read(chat: AgentChatSessionDocument, project_id: str) -> None:
        check(chat, project_id)
        _hard_delete(chat.username, chat.session_id)
        AgentChatShareService.delete_for_chat(username=chat.username, session_id=chat.session_id)
        AgentChatSessionDocument(username=chat.username, session_id=chat.session_id).insert()

    monkeypatch.setattr(AgentChatShareService, "_check_shareable", staticmethod(replace_after_read))
    response = test_client.put("/agent/chat/sessions/s1/share", headers=_headers("alice"))
    assert response.status_code == 404, response.text
    assert AgentChatShareDocument.find_all().to_list() == []


def test_a_chat_deleted_after_its_snapshot_is_written_is_cleaned_by_the_deletion(
    test_client, people
):
    """The other order: the recheck sees the chat, so the later deletion removes the share."""
    _chat()
    share_id = _share(test_client)["share_id"]
    _tombstone("alice", "s1")
    AgentChatShareService.delete_for_chat(username="alice", session_id="s1")
    got = test_client.get(f"/agent/chat/shares/{share_id}", headers=_headers("bob"))
    assert got.status_code == 404


def test_snapshot_message_handles_plain_malformed_and_unfinished_answers():
    from qdash.api.services.agent_chat_share_service import snapshot_message

    plain = snapshot_message(AgentChatMessage(role="assistant", content="{not json"))
    assert plain is not None
    assert plain.blocks[0].content == "{not json"
    error = snapshot_message(AgentChatMessage(role="assistant", content="Error: boom"))
    assert error is not None
    assert error.is_error
    assert error.blocks[0].content == "boom"
    unfinished = snapshot_message(
        AgentChatMessage(
            role="assistant",
            content=json.dumps(
                {"blocks": [{"type": "text", "content": "so far"}, "junk"], "in_progress": True}
            ),
        )
    )
    assert unfinished is not None
    assert unfinished.incomplete == "interrupted"
    assert [b.content for b in unfinished.blocks] == ["so far"]
    assert unfinished.omitted_content is True
    assert snapshot_message(AgentChatMessage(role="system", content="x")) is None
