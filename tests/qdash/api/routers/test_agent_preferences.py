"""A user's own Agent instructions: stored per user, sent with chat turns only."""

from qdash.agent.config import AgentConfig, ModelConfig
from qdash.agent.contracts.models import ChatRequest
from qdash.api.services import pi_chat_service
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.user import UserDocument


def _user(username: str, token: str) -> dict[str, str]:
    UserDocument(
        username=username,
        hashed_password="hashed",
        access_token=token,
        system_info=SystemInfoModel(),
    ).insert()
    return {"Authorization": f"Bearer {token}"}


def test_instructions_are_stored_per_user_and_cleared_by_empty_text(test_client):
    alice = _user("alice", "alice-token")
    bob = _user("bob", "bob-token")

    assert test_client.get("/agent/preferences", headers=alice).json()["instructions"] == ""

    saved = test_client.put(
        "/agent/preferences",
        headers=alice,
        json={"instructions": "  Answer in Japanese, conclusion first.  "},
    )
    assert saved.status_code == 200
    assert saved.json()["instructions"] == "Answer in Japanese, conclusion first."
    assert test_client.get("/agent/preferences", headers=alice).json()["instructions"] == (
        "Answer in Japanese, conclusion first."
    )
    # Another user's preferences are untouched.
    assert test_client.get("/agent/preferences", headers=bob).json()["instructions"] == ""

    cleared = test_client.put("/agent/preferences", headers=alice, json={"instructions": ""})
    assert cleared.json()["instructions"] == ""
    user = UserDocument.find_one({"username": "alice"}).run()
    assert user is not None
    assert user.agent_instructions is None


def test_instructions_keep_their_legacy_stored_field_name(test_client):
    """Instructions saved before the Agent rename stay readable, and new saves keep the name."""
    UserDocument.get_motor_collection().insert_one(
        {
            "username": "legacy",
            "hashed_password": "hashed",
            "access_token": "legacy-token",
            "copilot_instructions": "Saved before the rename.",
            "system_info": SystemInfoModel().model_dump(),
        }
    )
    headers = {"Authorization": "Bearer legacy-token"}

    assert test_client.get("/agent/preferences", headers=headers).json()["instructions"] == (
        "Saved before the rename."
    )
    test_client.put("/agent/preferences", headers=headers, json={"instructions": "Updated."})
    raw = UserDocument.get_motor_collection().find_one({"username": "legacy"})
    assert raw is not None
    assert raw["copilot_instructions"] == "Updated."
    assert "agent_instructions" not in raw


def test_instructions_have_a_length_limit(test_client):
    alice = _user("alice", "alice-token")
    limit = test_client.get("/agent/preferences", headers=alice).json()["max_instructions_chars"]

    response = test_client.put(
        "/agent/preferences", headers=alice, json={"instructions": "x" * (limit + 1)}
    )

    assert response.status_code == 422


def test_preferences_require_a_signed_in_user(test_client):
    assert test_client.get("/agent/preferences").status_code in {401, 403}


def test_a_chat_turn_carries_the_users_instructions_and_only_theirs(test_client):
    _user("alice", "alice-token")
    _user("bob", "bob-token")
    alice = UserDocument.find_one({"username": "alice"}).run()
    assert alice is not None
    alice.agent_instructions = "Use tables for numbers."
    alice.save()
    config = AgentConfig(model=ModelConfig(provider="vllm", name="m"))
    request = ChatRequest.model_validate({"message": "hi", "session_id": "s1"})

    assert pi_chat_service._request_payload(request, config, "alice")["user_instructions"] == (
        "Use tables for numbers."
    )
    assert "user_instructions" not in pi_chat_service._request_payload(request, config, "bob")


def test_system_prompt_shows_the_runtime_text_and_the_users_part(test_client, monkeypatch):
    alice = _user("alice", "alice-token")
    seen: dict[str, str] = {}

    async def fake_system_prompt(username: str):
        seen["username"] = username
        return {
            "system_prompt": "You are QDash Agent.",
            "user_preferences": "<user-preferences>\nUse tables.\n</user-preferences>",
            "tools": ["ask_user"],
        }

    monkeypatch.setattr(pi_chat_service, "system_prompt", fake_system_prompt)

    shown = test_client.get("/agent/system-prompt", headers=alice).json()

    assert seen["username"] == "alice"
    assert shown["system_prompt"] == "You are QDash Agent."
    assert "Use tables." in shown["user_preferences"]
    assert shown["tools"] == ["ask_user"]


def test_system_prompt_reports_an_unreachable_runtime(test_client, monkeypatch):
    alice = _user("alice", "alice-token")

    async def down(username: str):
        raise ConnectionError("runtime down")

    monkeypatch.setattr(pi_chat_service, "system_prompt", down)

    assert test_client.get("/agent/system-prompt", headers=alice).status_code == 503


def test_skills_list_what_the_runtime_loaded(test_client, monkeypatch):
    alice = _user("alice", "alice-token")

    async def fake_skills():
        return {"skills": [{"name": "qdash-characterization", "description": "Remeasure T1."}]}

    monkeypatch.setattr(pi_chat_service, "skills", fake_skills)

    shown = test_client.get("/agent/skills", headers=alice)

    assert shown.status_code == 200
    assert shown.json() == {
        "skills": [{"name": "qdash-characterization", "description": "Remeasure T1."}]
    }


def test_skills_report_an_unreachable_runtime(test_client, monkeypatch):
    alice = _user("alice", "alice-token")

    async def down():
        raise ConnectionError("runtime down")

    monkeypatch.setattr(pi_chat_service, "skills", down)

    assert test_client.get("/agent/skills", headers=alice).status_code == 503
    assert test_client.get("/agent/skills").status_code in {401, 403}
