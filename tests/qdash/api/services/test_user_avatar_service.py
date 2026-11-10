"""Tests for generated user avatars."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from qdash.api.services.user_avatar_service import (
    GLYPH_AVATAR_GENERATOR,
    GLYPH_AVATAR_RENDER_OPTIONS,
    GLYPH_AVATAR_VERSION,
    AvatarGenerationError,
    GeneratedAvatar,
    InvalidAvatarSpecError,
    UserAvatarService,
    UserNotFoundError,
    automatic_avatar_spec,
    parse_avatar_spec,
    svg_etag,
    validate_avatar_svg,
)
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.user import UserDocument
from qdash.dbmodel.user_avatar import UserAvatarDocument
from qdash.repository.user_avatar import MongoUserAvatarRepository

if TYPE_CHECKING:
    from qdash.datamodel.user_avatar import UserAvatarModel

# Real glyph-avatar 0.1.0 output: createAvatar(spec, {size: 64, shape: "circle"}).
ALICE_SPEC = "v1:alice::solid:c"
ALICE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="64" height="64" '
    'aria-hidden="true"><circle cx="50" cy="50" r="50" fill="#1F6B4A"/>'
    '<g transform="rotate(90 50 50)"><path d="M24 63A26 26 0 0 1 76 63Z" fill="#9BE3C9"/>'
    '<path d="M32 63A18 18 0 0 1 68 63Z" fill="#1F6B4A"/>'
    '<path d="M40 63A10 10 0 0 1 60 63Z" fill="#9BE3C9"/></g></svg>'
)
CUSTOM_SPEC = "v1:k3x9q2a-1.-2:p0w7zz:stripes:c"
CUSTOM_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="64" height="64" '
    'aria-hidden="true"><circle cx="50" cy="50" r="50" fill="#F6CD5E"/>'
    '<path d="M64.32 2.09A50 50 0 0 1 97.91 35.68L64.32 2.09Z" fill="#f2b960"/>'
    '<g transform="rotate(90 50 50)"><path d="M45 28A22 22 0 0 0 45 72Z" fill="#D9416F"/>'
    '<path d="M55 28A22 22 0 0 1 55 72Z" fill="#D9416F"/></g></svg>'
)


def fake_svg(spec: str) -> str:
    """Return a deterministic allowlisted SVG that depends only on ``spec``."""
    known = {ALICE_SPEC: ALICE_SVG, CUSTOM_SPEC: CUSTOM_SVG}
    if spec in known:
        return known[spec]
    radius = 10 + int(svg_etag(spec)[:4], 16) % 40
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="64" height="64">'
        f'<circle cx="50" cy="50" r="{radius}" fill="#3D7FE6"/></svg>'
    )


@dataclass
class FakeGenerator:
    """Generator double that follows the UI generator contract."""

    calls: list[str] = field(default_factory=list)
    version: str = GLYPH_AVATAR_VERSION
    svg_override: str | None = None
    fail: bool = False
    before_return: Any = None

    def generate(self, spec: str) -> GeneratedAvatar:
        self.calls.append(spec)
        if self.fail:
            msg = "generator down"
            raise AvatarGenerationError(msg)
        if self.before_return is not None:
            self.before_return()
        return GeneratedAvatar(
            spec=spec,
            svg=self.svg_override if self.svg_override is not None else fake_svg(spec),
            generator=GLYPH_AVATAR_GENERATOR,
            generator_version=self.version,
            options=dict(GLYPH_AVATAR_RENDER_OPTIONS),
        )


class InMemoryAvatarStore:
    """Thread-safe store double with first-writer-wins inserts."""

    def __init__(self, users: dict[str, str]) -> None:
        self.users = users
        self.avatars: dict[str, UserAvatarModel] = {}
        self._lock = threading.Lock()

    def find_user_id(self, username: str) -> str | None:
        return self.users.get(username)

    def find_avatar(self, user_id: str) -> UserAvatarModel | None:
        with self._lock:
            return self.avatars.get(user_id)

    def insert_if_absent(self, avatar: UserAvatarModel) -> UserAvatarModel:
        with self._lock:
            return self.avatars.setdefault(avatar.user_id, avatar)

    def replace(self, avatar: UserAvatarModel) -> UserAvatarModel:
        with self._lock:
            self.avatars[avatar.user_id] = avatar
            return avatar


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
            "v1:" + "a" * 65,
        ],
    )
    def test_rejects_non_canonical_or_unsupported_specs(self, spec: str) -> None:
        with pytest.raises(InvalidAvatarSpecError):
            parse_avatar_spec(spec)


class TestValidateAvatarSvg:
    """SVG allowlist validation."""

    @pytest.mark.parametrize("svg", [ALICE_SVG, CUSTOM_SVG])
    def test_accepts_real_generator_output(self, svg: str) -> None:
        validate_avatar_svg(svg)

    @pytest.mark.parametrize(
        "svg",
        [
            '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>',
            '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:x="http://www.w3.org/1999/xlink">'
            '<path x:href="javascript:alert(1)"/></svg>',
            '<svg xmlns="http://www.w3.org/2000/svg"><rect fill="url(#a)"/></svg>',
            '<svg xmlns="http://www.w3.org/2000/svg"><rect fill="javascript:x"/></svg>',
            '<svg xmlns="http://www.w3.org/2000/svg"><g>text</g></svg>',
            '<!DOCTYPE svg [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg"/>',
            '<?xml-stylesheet href="x"?><svg xmlns="http://www.w3.org/2000/svg"/>',
            "<svg><rect/></svg>",
            '<html xmlns="http://www.w3.org/1999/xhtml"/>',
            "<svg",
            '<svg xmlns="http://www.w3.org/2000/svg">' + "<g></g>" * 3000 + "</svg>",
        ],
    )
    def test_rejects_markup_the_generator_never_emits(self, svg: str) -> None:
        with pytest.raises(AvatarGenerationError):
            validate_avatar_svg(svg)


class TestUserAvatarService:
    """Lazy creation, persistence, and custom selections."""

    def test_same_username_gives_identical_avatar_across_independent_stores(self) -> None:
        first_store = InMemoryAvatarStore({"alice": "usr_11111111"})
        second_store = InMemoryAvatarStore({"alice": "usr_22222222"})
        first_generator, second_generator = FakeGenerator(), FakeGenerator()

        first = UserAvatarService(first_store, first_generator).get_or_create("alice")
        second = UserAvatarService(second_store, second_generator).get_or_create("alice")

        assert first is not None and second is not None
        assert first_generator.calls == second_generator.calls == [ALICE_SPEC]
        assert first.svg == second.svg == ALICE_SVG
        assert first.etag == second.etag == svg_etag(ALICE_SVG)
        assert (first.spec, first.seed, first.source) == (ALICE_SPEC, "alice", "automatic")
        assert (first.generator, first.generator_version) == ("glyph-avatar", "0.1.0")
        assert first.options == {"size": 64, "shape": "circle"}
        assert first.user_id != second.user_id

    def test_unknown_username_returns_none_without_generating(self) -> None:
        generator = FakeGenerator()
        service = UserAvatarService(InMemoryAvatarStore({}), generator)
        assert service.get_or_create("ghost") is None
        assert generator.calls == []

    def test_saved_avatar_is_served_without_generating_again(self) -> None:
        store = InMemoryAvatarStore({"alice": "usr_1"})
        generator = FakeGenerator()
        service = UserAvatarService(store, generator)

        first = service.get_or_create("alice")
        second = service.get_or_create("alice")

        assert first is second
        assert generator.calls == [ALICE_SPEC]

    def test_saved_avatar_from_older_generator_is_not_regenerated(self) -> None:
        store = InMemoryAvatarStore({"alice": "usr_1"})
        old = UserAvatarService(store, FakeGenerator()).get_or_create("alice")
        assert old is not None
        store.avatars["usr_1"] = old.model_copy(update={"generator_version": "0.0.9"})
        generator = FakeGenerator()

        served = UserAvatarService(store, generator).get_or_create("alice")

        assert served is not None and served.generator_version == "0.0.9"
        assert generator.calls == []

    def test_concurrent_first_requests_store_and_return_one_avatar(self) -> None:
        store = InMemoryAvatarStore({"alice": "usr_1"})
        barrier = threading.Barrier(4)
        generator = FakeGenerator(before_return=lambda: barrier.wait(timeout=5))
        service = UserAvatarService(store, generator)
        results: list[UserAvatarModel | None] = []

        threads = [
            threading.Thread(target=lambda: results.append(service.get_or_create("alice")))
            for _ in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(generator.calls) == 4  # every request missed the cache
        assert len(store.avatars) == 1
        assert all(result is store.avatars["usr_1"] for result in results)

    @pytest.mark.parametrize(
        "generator",
        [
            FakeGenerator(version="0.2.0"),
            FakeGenerator(svg_override='<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>'),
            FakeGenerator(fail=True),
        ],
    )
    def test_rejected_generator_output_is_not_saved(self, generator: FakeGenerator) -> None:
        store = InMemoryAvatarStore({"alice": "usr_1"})
        with pytest.raises(AvatarGenerationError):
            UserAvatarService(store, generator).get_or_create("alice")
        assert store.avatars == {}

    def test_custom_spec_replaces_and_reset_restores_the_automatic_avatar(self) -> None:
        store = InMemoryAvatarStore({"alice": "usr_1"})
        generator = FakeGenerator()
        service = UserAvatarService(store, generator)
        service.get_or_create("alice")

        custom = service.set_avatar("alice", CUSTOM_SPEC)
        assert (custom.source, custom.spec, custom.seed) == ("custom", CUSTOM_SPEC, "k3x9q2a-1.-2")
        assert service.get_or_create("alice") is custom

        reset = service.set_avatar("alice", None)
        assert (reset.source, reset.spec, reset.svg) == ("automatic", ALICE_SPEC, ALICE_SVG)
        assert generator.calls == [ALICE_SPEC, CUSTOM_SPEC, ALICE_SPEC]

    def test_invalid_spec_or_generator_failure_keeps_the_saved_avatar(self) -> None:
        store = InMemoryAvatarStore({"alice": "usr_1"})
        saved = UserAvatarService(store, FakeGenerator()).get_or_create("alice")
        failing = FakeGenerator(fail=True)
        service = UserAvatarService(store, failing)

        with pytest.raises(InvalidAvatarSpecError):
            service.set_avatar("alice", "v1:alice::solid:")
        with pytest.raises(AvatarGenerationError):
            service.set_avatar("alice", CUSTOM_SPEC)

        assert failing.calls == [CUSTOM_SPEC]
        assert store.avatars["usr_1"] is saved

    def test_set_avatar_for_unknown_user_raises(self) -> None:
        service = UserAvatarService(InMemoryAvatarStore({}), FakeGenerator())
        with pytest.raises(UserNotFoundError):
            service.set_avatar("ghost", None)


class TestMongoUserAvatarRepository:
    """Race-safe persistence in MongoDB."""

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

    def test_lost_insert_race_returns_the_record_saved_first(self, alice: UserDocument) -> None:
        repo = MongoUserAvatarRepository()
        service = UserAvatarService(repo, FakeGenerator())

        def custom_saved_meanwhile() -> None:
            UserAvatarService(repo, FakeGenerator()).set_avatar("alice", CUSTOM_SPEC)

        racing = UserAvatarService(repo, FakeGenerator(before_return=custom_saved_meanwhile))
        result = racing.get_or_create("alice")

        assert result is not None and result.spec == CUSTOM_SPEC
        stored = service.get_or_create("alice")
        assert stored is not None and stored.source == "custom"
        assert UserAvatarDocument.find({"user_id": alice.user_id}).count() == 1

    def test_replace_keeps_created_at_and_updates_the_record(self, alice: UserDocument) -> None:
        repo = MongoUserAvatarRepository()
        service = UserAvatarService(repo, FakeGenerator())
        first = service.get_or_create("alice")
        updated = service.set_avatar("alice", CUSTOM_SPEC)

        assert first is not None
        assert updated.created_at == first.created_at
        assert updated.spec == CUSTOM_SPEC
        assert UserAvatarDocument.find({"user_id": alice.user_id}).count() == 1


def test_backend_version_pin_matches_ui_package() -> None:
    """The API rejects generator output whose version differs from ui/package.json."""
    package_json = Path(__file__).resolve().parents[4] / "ui" / "package.json"
    if not package_json.exists():
        pytest.skip("ui/package.json is not available in this environment")
    dependencies = json.loads(package_json.read_text())["dependencies"]
    assert dependencies["glyph-avatar"] == GLYPH_AVATAR_VERSION
