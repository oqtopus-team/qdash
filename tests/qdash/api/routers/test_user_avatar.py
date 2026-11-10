"""Tests for generated user avatar endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from qdash.api.dependencies import get_user_avatar_service
from qdash.api.main import app
from qdash.api.services.user_avatar_service import UserAvatarService
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.user import UserDocument
from qdash.dbmodel.user_avatar import UserAvatarDocument
from qdash.repository.user_avatar import MongoUserAvatarRepository
from tests.qdash.api.services.test_user_avatar_service import (
    ALICE_SPEC,
    ALICE_SVG,
    CUSTOM_SPEC,
    CUSTOM_SVG,
    FakeGenerator,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer viewer-token"}


@pytest.fixture
def generator(init_db: Any) -> Generator[FakeGenerator, None, None]:
    fake = FakeGenerator()
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_user_avatar_service] = lambda: UserAvatarService(
        MongoUserAvatarRepository(), fake
    )
    try:
        yield fake
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


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


def test_avatar_requires_authentication(test_client: TestClient, generator: FakeGenerator) -> None:
    assert test_client.get("/users/alice/avatar").status_code == 401
    assert test_client.put("/auth/me/avatar", json={"spec": None}).status_code == 401
    assert generator.calls == []


def test_legacy_user_avatar_is_generated_once_and_served_safely(
    test_client: TestClient, generator: FakeGenerator, users: dict[str, UserDocument]
) -> None:
    response = test_client.get("/users/alice/avatar", headers=AUTH)

    assert response.status_code == 200
    assert response.text == ALICE_SVG
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert "sandbox" in response.headers["content-security-policy"]
    assert response.headers["cache-control"].startswith("private")
    etag = response.headers["etag"]

    cached = test_client.get("/users/alice/avatar", headers={**AUTH, "If-None-Match": etag})
    assert cached.status_code == 304
    assert cached.content == b""
    assert test_client.get("/users/alice/avatar", headers=AUTH).text == ALICE_SVG
    assert generator.calls == [ALICE_SPEC]

    saved = UserAvatarDocument.find_one({"user_id": users["alice"].user_id}).run()
    assert saved is not None and saved.seed == "alice"
    alice = UserDocument.find_one({"username": "alice"}).run()
    assert alice is not None and alice.avatar_key == "fox"
    assert alice.user_id == users["alice"].user_id


def test_unknown_or_invalid_username_returns_404_or_422(
    test_client: TestClient, generator: FakeGenerator, users: dict[str, UserDocument]
) -> None:
    assert test_client.get("/users/ghost/avatar", headers=AUTH).status_code == 404
    assert test_client.get("/users/Bad%20Name/avatar", headers=AUTH).status_code == 422
    assert generator.calls == []


def test_generator_failure_returns_503_without_saving(
    test_client: TestClient, generator: FakeGenerator, users: dict[str, UserDocument]
) -> None:
    generator.fail = True
    assert test_client.get("/users/alice/avatar", headers=AUTH).status_code == 503
    assert UserAvatarDocument.find_all().count() == 0


def test_current_user_can_choose_and_reset_a_picker_avatar(
    test_client: TestClient, generator: FakeGenerator, users: dict[str, UserDocument]
) -> None:
    current = test_client.get("/auth/me/avatar", headers=AUTH)
    assert current.status_code == 200
    assert current.json()["source"] == "automatic"
    assert current.json()["spec"] == "v1:viewer::solid:c"

    chosen = test_client.put("/auth/me/avatar", json={"spec": CUSTOM_SPEC}, headers=AUTH)
    assert chosen.status_code == 200
    assert chosen.json()["source"] == "custom"
    assert chosen.json()["spec"] == CUSTOM_SPEC
    assert test_client.get("/users/viewer/avatar", headers=AUTH).text == CUSTOM_SVG

    reset = test_client.put("/auth/me/avatar", json={"spec": None}, headers=AUTH)
    assert reset.status_code == 200
    assert reset.json()["source"] == "automatic"
    assert reset.json()["spec"] == "v1:viewer::solid:c"


@pytest.mark.parametrize(
    "body",
    [
        {"spec": "v1:viewer::solid:"},
        {"spec": "v1:x::unknown:c"},
        {"svg": "<svg/>", "spec": "<svg xmlns='http://www.w3.org/2000/svg'/>"},
    ],
)
def test_invalid_spec_is_rejected_and_svg_is_never_accepted(
    test_client: TestClient,
    generator: FakeGenerator,
    users: dict[str, UserDocument],
    body: dict[str, Any],
) -> None:
    response = test_client.put("/auth/me/avatar", json=body, headers=AUTH)
    assert response.status_code == 422
    assert generator.calls == []
    assert UserAvatarDocument.find_all().count() == 0
