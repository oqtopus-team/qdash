"""Glyph avatar settings: spec validation and persistence.

Avatars are rendered in the browser by the ``glyph-avatar`` npm package bundled with the QDash
UI. An avatar is described by a canonical ``glyph-avatar`` spec string such as
``v1:alice::solid:c``. The API stores only validated spec strings chosen in the picker; it
never renders, accepts, or stores avatar markup.

A user without a custom avatar shows the automatic spec ``v1:<username>::solid:c``, which the
UI derives from the username without asking the API. Its seed is the username, not the random
internal user ID, so instances that share a username show the same automatic avatar. A custom
spec is saved on the instance where it was chosen; instances do not synchronize custom choices.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Final, Protocol

from qdash.common.utils.datetime import now
from qdash.datamodel.user_avatar import UserAvatarModel, UserAvatarSource

logger = logging.getLogger(__name__)

GLYPH_AVATAR_GENERATOR: Final = "glyph-avatar"
# Must match the exact version pinned in ui/package.json and ui/src/lib/avatar/glyphAvatar.ts.
# Changing it is a deliberate avatar style change for every user.
GLYPH_AVATAR_VERSION: Final = "0.1.0"

SPEC_PREFIX: Final = "v1:"
GLYPH_AVATAR_BACKGROUNDS: Final = frozenset(
    {"solid", "split", "quarter", "ring", "halo", "stripes", "horizon", "polka"}
)
AUTOMATIC_BACKGROUND: Final = "solid"
# Characters that encodeURIComponent leaves unchanged, minus the ones the picker never emits.
_SPEC_TOKEN: Final = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MAX_SPEC_LENGTH: Final = 160


class InvalidAvatarSpecError(ValueError):
    """A spec string is not a canonical ``glyph-avatar`` v1 spec that QDash accepts."""


class UserNotFoundError(LookupError):
    """No user has the requested username."""


@dataclass(frozen=True, slots=True)
class AvatarSpec:
    """Parsed parts of a canonical ``glyph-avatar`` v1 spec string."""

    seed: str
    color_seed: str = ""
    background: str = ""
    curated: bool = False

    def stringify(self) -> str:
        """Return the spec string in the format of ``glyph-avatar``'s ``stringifySpec``."""
        parts = [self.seed, self.color_seed, self.background, "c" if self.curated else ""]
        while len(parts) > 1 and parts[-1] == "":
            parts.pop()
        return SPEC_PREFIX + ":".join(parts)


def parse_avatar_spec(value: str) -> AvatarSpec:
    """Parse a canonical spec string, rejecting anything the picker would not produce.

    Raises
    ------
    InvalidAvatarSpecError
        If ``value`` is not a canonical v1 spec with a supported seed, color seed, and
        background.

    """
    if len(value) > MAX_SPEC_LENGTH or not value.startswith(SPEC_PREFIX):
        msg = "Avatar spec must be a glyph-avatar v1 spec"
        raise InvalidAvatarSpecError(msg)
    parts = value[len(SPEC_PREFIX) :].split(":")
    if len(parts) > 4:
        msg = "Avatar spec has too many parts"
        raise InvalidAvatarSpecError(msg)
    seed, color_seed, background, colors = [*parts, "", "", ""][:4]
    if not _SPEC_TOKEN.fullmatch(seed):
        msg = "Avatar spec seed is invalid"
        raise InvalidAvatarSpecError(msg)
    if color_seed and not _SPEC_TOKEN.fullmatch(color_seed):
        msg = "Avatar spec color seed is invalid"
        raise InvalidAvatarSpecError(msg)
    if background and background not in GLYPH_AVATAR_BACKGROUNDS:
        msg = "Avatar spec background is invalid"
        raise InvalidAvatarSpecError(msg)
    if colors not in {"", "c"}:
        msg = "Avatar spec color mode is invalid"
        raise InvalidAvatarSpecError(msg)
    spec = AvatarSpec(seed, color_seed, background, curated=colors == "c")
    if spec.stringify() != value:
        msg = "Avatar spec is not in canonical form"
        raise InvalidAvatarSpecError(msg)
    return spec


def automatic_avatar_spec(username: str) -> str:
    """Return the automatic spec for ``username``: its seed is the exact username."""
    return AvatarSpec(seed=username, background=AUTOMATIC_BACKGROUND, curated=True).stringify()


@dataclass(frozen=True, slots=True)
class ResolvedAvatar:
    """The avatar a user shows: a saved custom spec or the automatic one."""

    source: UserAvatarSource
    spec: str
    generator_version: str


class UserAvatarStore(Protocol):
    """Persistence used by :class:`UserAvatarService`."""

    def find_user_id(self, username: str) -> str | None:
        """Return the internal user ID for ``username``."""
        ...

    def find_custom(self, user_id: str) -> UserAvatarModel | None:
        """Return the custom avatar saved for ``user_id``."""
        ...

    def find_custom_by_usernames(self, usernames: list[str]) -> list[UserAvatarModel]:
        """Return the custom avatars of the given users."""
        ...

    def save(self, avatar: UserAvatarModel) -> UserAvatarModel:
        """Save ``avatar``, replacing any existing record, and return it."""
        ...

    def delete(self, user_id: str) -> None:
        """Remove the user's avatar record."""
        ...


def _custom(avatar: UserAvatarModel) -> ResolvedAvatar | None:
    """Return a saved record as a custom avatar, or ``None`` if its spec is no longer valid."""
    try:
        parse_avatar_spec(avatar.spec)
    except InvalidAvatarSpecError:
        logger.warning("Ignoring invalid saved avatar spec for user %s", avatar.username)
        return None
    return ResolvedAvatar("custom", avatar.spec, avatar.generator_version)


def _automatic(username: str) -> ResolvedAvatar:
    return ResolvedAvatar("automatic", automatic_avatar_spec(username), GLYPH_AVATAR_VERSION)


class UserAvatarService:
    """Read and save users' avatar specs."""

    def __init__(self, store: UserAvatarStore) -> None:
        """Create the service with its store."""
        self._store = store

    def get(self, username: str) -> ResolvedAvatar:
        """Return the avatar ``username`` shows.

        Raises
        ------
        UserNotFoundError
            If no user has ``username``.

        """
        user_id = self._store.find_user_id(username)
        if user_id is None:
            msg = f"User {username!r} not found"
            raise UserNotFoundError(msg)
        saved = self._store.find_custom(user_id)
        resolved = _custom(saved) if saved is not None else None
        return resolved or _automatic(username)

    def custom_specs(self, usernames: list[str]) -> dict[str, str]:
        """Return the custom spec of each listed user that has one, keyed by username.

        Users without a custom avatar and unknown usernames are omitted; the UI shows the
        automatic avatar for them.
        """
        specs: dict[str, str] = {}
        for avatar in self._store.find_custom_by_usernames(sorted(set(usernames))):
            resolved = _custom(avatar)
            if resolved is not None:
                specs[avatar.username] = resolved.spec
        return specs

    def set_avatar(self, username: str, spec: str | None) -> ResolvedAvatar:
        """Save a custom avatar ``spec``, or return to the automatic avatar when it is None.

        Raises
        ------
        UserNotFoundError
            If no user has ``username``.
        InvalidAvatarSpecError
            If ``spec`` is not a canonical v1 spec.

        """
        parsed = parse_avatar_spec(spec) if spec is not None else None
        user_id = self._store.find_user_id(username)
        if user_id is None:
            msg = f"User {username!r} not found"
            raise UserNotFoundError(msg)
        if spec is None or parsed is None or spec == automatic_avatar_spec(username):
            self._store.delete(user_id)
            logger.info("Reset avatar of user %s to automatic", username)
            return _automatic(username)
        timestamp = now()
        saved = self._store.save(
            UserAvatarModel(
                user_id=user_id,
                username=username,
                source="custom",
                spec=spec,
                seed=parsed.seed,
                generator=GLYPH_AVATAR_GENERATOR,
                generator_version=GLYPH_AVATAR_VERSION,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        logger.info("Saved custom avatar for user %s", username)
        return ResolvedAvatar("custom", saved.spec, saved.generator_version)
