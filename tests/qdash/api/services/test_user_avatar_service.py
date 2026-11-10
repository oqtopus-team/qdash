"""Tests for glyph avatar settings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qdash.api.services.user_avatar_service import (
    GLYPH_AVATAR_GENERATOR,
    GLYPH_AVATAR_VERSION,
    InvalidAvatarSpecError,
    UserAvatarService,
    UserNotFoundError,
    automatic_avatar_spec,
    parse_avatar_spec,
)
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.user_avatar import UserAvatarModel
from qdash.dbmodel.user import UserDocument
from qdash.dbmodel.user_avatar import UserAvatarDocument
from qdash.repository.user_avatar import MongoUserAvatarRepository

ALICE_SPEC = "v1:alice::solid:c"
CUSTOM_SPEC = "v1:k3x9q2a-1.-2:p0w7zz:stripes:c"


class InMemoryAvatarStore:
    """Store double keyed by user ID."""

    def __init__(self, users: dict[str, str]) -> None:
        self.users = users
        self.avatars: dict[str, UserAvatarModel] = {}

    def find_user_id(self, username: str) -> str | None:
        return self.users.get(username)

    def find_custom(self, user_id: str) -> UserAvatarModel | None:
        avatar = self.avatars.get(user_id)
        return avatar if avatar is not None and avatar.source == "custom" else None

    def find_custom_by_usernames(self, usernames: list[str]) -> list[UserAvatarModel]:
        found = (
            self.find_custom(user_id) for name, user_id in self.users.items() if name in usernames
        )
        return [avatar for avatar in found if avatar is not None]

    def save(self, avatar: UserAvatarModel) -> UserAvatarModel:
        self.avatars[avatar.user_id] = avatar
        return avatar

    def delete(self, user_id: str) -> None:
        self.avatars.pop(user_id, None)


class TestAvatarSpec:
    """Canonical spec parsing."""

    def test_automatic_spec_uses_the_exact_username_as_seed(self) -> None:
        assert automatic_avatar_spec("alice") == ALICE_SPEC
        assert parse_avatar_spec(automatic_avatar_spec("a.b-c_d")).seed == "a.b-c_d"

    @pytest.mark.parametrize(
        "spec",
        [ALICE_SPEC, CUSTOM_SPEC, "v1:abc", "v1:abc:def", "v1:abc::ring", "v1:abc:::c"],
    )
    def test_accepts_canonical_specs(self, spec: str) -> None:
        assert parse_avatar_spec(spec).stringify() == spec

    @pytest.mark.parametrize(
        "spec",
        [
            "alice",
            "v2:alice",
            "v1:",
            "v1:alice:",
            "v1:alice::solid:",
            "v1:alice::unknown:c",
            "v1:alice::solid:x",
            "v1:alice::solid:c:extra",
            "v1:al%20ice",
            "v1:<script>",
            "<svg xmlns='http://www.w3.org/2000/svg'/>",
            "v1:" + "a" * 65,
        ],
    )
    def test_rejects_non_canonical_or_unsupported_specs(self, spec: str) -> None:
        with pytest.raises(InvalidAvatarSpecError):
            parse_avatar_spec(spec)


class TestUserAvatarService:
    """Reading and saving specs."""

    @pytest.fixture
    def store(self) -> InMemoryAvatarStore:
        return InMemoryAvatarStore({"alice": "usr_a", "bob": "usr_b"})

    def test_user_without_a_record_shows_the_automatic_avatar(
        self, store: InMemoryAvatarStore
    ) -> None:
        avatar = UserAvatarService(store).get("alice")

        assert (avatar.source, avatar.spec) == ("automatic", ALICE_SPEC)
        assert store.avatars == {}

    def test_same_username_gets_the_same_automatic_avatar_on_any_instance(self) -> None:
        first = UserAvatarService(InMemoryAvatarStore({"alice": "usr_1"})).get("alice")
        second = UserAvatarService(InMemoryAvatarStore({"alice": "usr_2"})).get("alice")
        assert first == second

    def test_custom_spec_is_saved_with_seed_and_version_then_reset(
        self, store: InMemoryAvatarStore
    ) -> None:
        service = UserAvatarService(store)

        chosen = service.set_avatar("alice", CUSTOM_SPEC)
        saved = store.avatars["usr_a"]
        assert (chosen.source, chosen.spec) == ("custom", CUSTOM_SPEC)
        assert saved.seed == "k3x9q2a-1.-2"
        assert (saved.generator, saved.generator_version) == (
            GLYPH_AVATAR_GENERATOR,
            GLYPH_AVATAR_VERSION,
        )
        assert service.get("alice").spec == CUSTOM_SPEC
        assert service.custom_specs(["alice", "bob", "ghost"]) == {"alice": CUSTOM_SPEC}

        reset = service.set_avatar("alice", None)
        assert (reset.source, reset.spec) == ("automatic", ALICE_SPEC)
        assert store.avatars == {}

    def test_choosing_the_automatic_spec_stores_nothing(self, store: InMemoryAvatarStore) -> None:
        avatar = UserAvatarService(store).set_avatar("alice", ALICE_SPEC)
        assert avatar.source == "automatic"
        assert store.avatars == {}

    def test_invalid_spec_or_unknown_user_is_rejected_without_saving(
        self, store: InMemoryAvatarStore
    ) -> None:
        service = UserAvatarService(store)
        with pytest.raises(InvalidAvatarSpecError):
            service.set_avatar("alice", "<svg/>")
        with pytest.raises(UserNotFoundError):
            service.set_avatar("ghost", CUSTOM_SPEC)
        with pytest.raises(UserNotFoundError):
            service.get("ghost")
        assert store.avatars == {}

    def test_invalid_saved_spec_falls_back_to_the_automatic_avatar(
        self, store: InMemoryAvatarStore
    ) -> None:
        store.avatars["usr_a"] = UserAvatarModel(
            user_id="usr_a",
            username="alice",
            spec="v1:alice::bogus",
            seed="alice",
            generator=GLYPH_AVATAR_GENERATOR,
            generator_version=GLYPH_AVATAR_VERSION,
        )
        service = UserAvatarService(store)
        assert service.get("alice").spec == ALICE_SPEC
        assert service.custom_specs(["alice"]) == {}


class TestMongoUserAvatarRepository:
    """Persistence in MongoDB."""

    @pytest.fixture
    def alice(self, init_db: Any) -> UserDocument:
        user = UserDocument(
            username="alice",
            avatar_key="fox",
            hashed_password="hashed",
            access_token="alice-token",
            system_info=SystemInfoModel(),
        )
        user.insert()
        return user

    def test_save_replaces_the_record_and_keeps_created_at(self, alice: UserDocument) -> None:
        service = UserAvatarService(MongoUserAvatarRepository())
        service.set_avatar("alice", "v1:first")
        first = UserAvatarDocument.find_one({"user_id": alice.user_id}).run()
        service.set_avatar("alice", CUSTOM_SPEC)
        updated = UserAvatarDocument.find_one({"user_id": alice.user_id}).run()

        assert first is not None and updated is not None
        assert updated.created_at == first.created_at
        assert updated.spec == CUSTOM_SPEC
        assert UserAvatarDocument.find({"user_id": alice.user_id}).count() == 1
        user = UserDocument.find_one({"username": "alice"}).run()
        assert user is not None and user.avatar_key == "fox"

    def test_records_from_the_svg_storing_version_stay_readable(self, alice: UserDocument) -> None:
        """An earlier version stored rendered SVG and automatic records; neither is used now."""
        collection = UserAvatarDocument.get_motor_collection()
        legacy = {
            "user_id": alice.user_id,
            "username": "alice",
            "seed": "alice",
            "svg": "<svg/>",
            "etag": "abc",
            "generator": GLYPH_AVATAR_GENERATOR,
            "generator_version": GLYPH_AVATAR_VERSION,
            "options": {"size": 64, "shape": "circle"},
        }
        collection.insert_one({**legacy, "source": "automatic", "spec": ALICE_SPEC})
        service = UserAvatarService(MongoUserAvatarRepository())
        assert service.get("alice").source == "automatic"
        assert service.custom_specs(["alice"]) == {}

        collection.update_one(
            {"user_id": alice.user_id}, {"$set": {"source": "custom", "spec": CUSTOM_SPEC}}
        )
        assert service.get("alice").spec == CUSTOM_SPEC
        assert service.custom_specs(["alice"]) == {"alice": CUSTOM_SPEC}

        service.set_avatar("alice", "v1:next")
        rewritten = collection.find_one({"user_id": alice.user_id})
        assert rewritten is not None
        assert "svg" not in rewritten and "etag" not in rewritten and "options" not in rewritten

    def test_reset_deletes_the_record(self, alice: UserDocument) -> None:
        service = UserAvatarService(MongoUserAvatarRepository())
        service.set_avatar("alice", CUSTOM_SPEC)
        service.set_avatar("alice", None)
        assert UserAvatarDocument.find({"user_id": alice.user_id}).count() == 0


def test_backend_version_pin_matches_ui_package() -> None:
    """Saved specs record the version the UI bundles; both must stay pinned together."""
    package_json = Path(__file__).resolve().parents[4] / "ui" / "package.json"
    if not package_json.exists():
        pytest.skip("ui/package.json is not available in this environment")
    dependencies = json.loads(package_json.read_text())["dependencies"]
    assert dependencies["glyph-avatar"] == GLYPH_AVATAR_VERSION
