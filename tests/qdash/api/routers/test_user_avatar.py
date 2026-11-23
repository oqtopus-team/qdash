"""Tests for glyph avatar settings endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.user import UserDocument
from qdash.dbmodel.user_avatar import UserAvatarDocument
from tests.qdash.api.services.test_user_avatar_service import CUSTOM_SPEC

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer viewer-token"}
ALICE_AUTH = {"Authorization": "Bearer alice-token"}


@pytest.fixture
def users(init_db: Any) -> dict[str, UserDocument]:
    """A legacy user with only an emoji avatar key, and a viewer."""
    created: dict[str, UserDocument] = {}
    for username, token, avatar_key in [
        ("alice", "alice-token", "fox"),
        ("viewer", "viewer-token", None),
    ]:
        user = UserDocument(
            username=username,
            avatar_key=avatar_key,
            hashed_password="hashed",
            access_token=token,
            system_info=SystemInfoModel(),
        )
        user.insert()
        created[username] = user
    return created


def test_avatar_routes_require_authentication(test_client: TestClient) -> None:
    assert test_client.get("/auth/me/avatar").status_code == 401
    assert test_client.put("/auth/me/avatar", json={"spec": None}).status_code == 401
    assert test_client.get("/users/avatars", params={"username": "alice"}).status_code == 401


def test_image_routes_no_longer_exist(
    test_client: TestClient, users: dict[str, UserDocument]
) -> None:
    assert test_client.get("/users/alice/avatar", headers=AUTH).status_code == 404


def test_current_user_can_choose_and_reset_a_picker_avatar(
    test_client: TestClient, users: dict[str, UserDocument]
) -> None:
    current = test_client.get("/auth/me/avatar", headers=AUTH)
    assert current.status_code == 200
    assert current.json() == {
        "source": "automatic",
        "spec": "v1:viewer::solid:c",
        "generator": "glyph-avatar",
        "generator_version": "0.1.0",
    }
    assert UserAvatarDocument.find_all().count() == 0

    chosen = test_client.put("/auth/me/avatar", json={"spec": CUSTOM_SPEC}, headers=AUTH)
    assert chosen.status_code == 200
    assert chosen.json()["source"] == "custom"
    assert chosen.json()["spec"] == CUSTOM_SPEC
    assert test_client.get("/auth/me/avatar", headers=AUTH).json()["spec"] == CUSTOM_SPEC
    saved = UserAvatarDocument.find_one({"user_id": users["viewer"].user_id}).run()
    assert saved is not None and saved.spec == CUSTOM_SPEC

    reset = test_client.put("/auth/me/avatar", json={"spec": None}, headers=AUTH)
    assert reset.status_code == 200
    assert reset.json()["source"] == "automatic"
    assert reset.json()["spec"] == "v1:viewer::solid:c"
    assert UserAvatarDocument.find_all().count() == 0


def test_custom_specs_are_listed_in_one_batch(
    test_client: TestClient, users: dict[str, UserDocument]
) -> None:
    test_client.put("/auth/me/avatar", json={"spec": CUSTOM_SPEC}, headers=ALICE_AUTH)

    response = test_client.get(
        "/users/avatars",
        params={"username": ["alice", "viewer", "ghost", "Bad Name"]},
        headers=AUTH,
    )

    assert response.status_code == 200
    assert response.json() == {"avatars": [{"username": "alice", "spec": CUSTOM_SPEC}]}


def test_batch_lookup_is_bounded(test_client: TestClient, users: dict[str, UserDocument]) -> None:
    assert test_client.get("/users/avatars", headers=AUTH).status_code == 422
    too_many = {"username": [f"user{index}" for index in range(101)]}
    assert test_client.get("/users/avatars", params=too_many, headers=AUTH).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"spec": "v1:viewer::solid:"},
        {"spec": "v1:x::unknown:c"},
        {"svg": "<svg/>", "spec": "<svg xmlns='http://www.w3.org/2000/svg'/>"},
    ],
)
def test_invalid_spec_is_rejected_and_svg_is_never_accepted(
    test_client: TestClient, users: dict[str, UserDocument], body: dict[str, Any]
) -> None:
    response = test_client.put("/auth/me/avatar", json=body, headers=AUTH)
    assert response.status_code == 422
    assert UserAvatarDocument.find_all().count() == 0
