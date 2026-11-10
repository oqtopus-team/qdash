"""Generated user avatars: spec validation, lazy creation, and persistence.

Avatars are rendered by the ``glyph-avatar`` npm package, which runs in the QDash UI server.
An avatar is described by a canonical ``glyph-avatar`` spec string such as
``v1:alice::solid:c``. The API never accepts avatar markup from a browser: it validates a spec,
calls the UI server's generator endpoint itself, checks the returned SVG against the elements
the generator emits, and saves the SVG together with the spec, generator version, and options.
Later requests serve the saved SVG, so a generator upgrade never changes an existing avatar.

A user without a saved avatar gets the automatic spec ``v1:<username>::solid:c`` on first
request. Its seed is the username, not the random internal user ID, so instances that share a
username and generator version produce the same SVG bytes. A custom spec chosen in the picker is
saved on the instance where it was chosen; instances do not synchronize custom choices.
"""

from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Final, Protocol
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ValidationError

from qdash.common.utils.datetime import now
from qdash.datamodel.user_avatar import UserAvatarModel, UserAvatarSource

logger = logging.getLogger(__name__)

GLYPH_AVATAR_GENERATOR: Final = "glyph-avatar"
# Must match the exact version pinned in ui/package.json. Changing either is a deliberate
# avatar style change; saved avatars keep the version that rendered them.
GLYPH_AVATAR_VERSION: Final = "0.1.0"
GLYPH_AVATAR_RENDER_OPTIONS: Final[dict[str, str | int]] = {"size": 64, "shape": "circle"}
GENERATOR_PATH: Final = "/api/internal/glyph-avatar"
MAX_SVG_BYTES: Final = 16 * 1024

SPEC_PREFIX: Final = "v1:"
GLYPH_AVATAR_BACKGROUNDS: Final = frozenset(
    {"solid", "split", "quarter", "ring", "halo", "stripes", "horizon", "polka"}
)
AUTOMATIC_BACKGROUND: Final = "solid"
# Characters that encodeURIComponent leaves unchanged, minus the ones the picker never emits.
_SPEC_TOKEN: Final = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MAX_SPEC_LENGTH: Final = 160

_SVG_NS: Final = "http://www.w3.org/2000/svg"
_ALLOWED_ELEMENTS: Final = frozenset({"svg", "g", "circle", "rect", "path", "polygon"})
_ALLOWED_ATTRIBUTES: Final = frozenset(
    {
        "viewBox",
        "width",
        "height",
        "aria-hidden",
        "cx",
        "cy",
        "r",
        "rx",
        "x",
        "y",
        "d",
        "points",
        "transform",
        "fill",
        "stroke",
        "stroke-width",
        "stroke-linecap",
        "stroke-linejoin",
        "opacity",
    }
)
# Geometry, hex colors, keywords, and transform functions; no URLs, entities, or scripts.
_SAFE_ATTRIBUTE_VALUE: Final = re.compile(r"^[A-Za-z0-9#.,() -]*$")


class AvatarGenerationError(Exception):
    """The generator could not produce an avatar that QDash accepts."""


class InvalidAvatarSpecError(ValueError):
    """A spec string is not a canonical ``glyph-avatar`` v1 spec that QDash accepts."""


class UserNotFoundError(LookupError):
    """No user has the requested username."""


class GeneratedAvatar(BaseModel):
    """Response contract of the UI server's generator endpoint."""

    spec: str
    svg: str
    generator: str
    generator_version: str
    options: dict[str, str | int]


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


class AvatarGenerator(Protocol):
    """Renders an avatar SVG for a spec."""

    def generate(self, spec: str) -> GeneratedAvatar:
        """Return the generated avatar for ``spec``.

        Raises
        ------
        AvatarGenerationError
            If the generator is unavailable or returns an invalid response.

        """
        ...


class UserAvatarStore(Protocol):
    """Persistence used by :class:`UserAvatarService`."""

    def find_user_id(self, username: str) -> str | None:
        """Return the internal user ID for ``username``."""
        ...

    def find_avatar(self, user_id: str) -> UserAvatarModel | None:
        """Return the saved avatar for ``user_id``."""
        ...

    def insert_if_absent(self, avatar: UserAvatarModel) -> UserAvatarModel:
        """Save ``avatar`` unless one exists and return the stored record."""
        ...

    def replace(self, avatar: UserAvatarModel) -> UserAvatarModel:
        """Save ``avatar``, replacing any existing record, and return it."""
        ...


@dataclass(frozen=True, slots=True)
class HttpGlyphAvatarGenerator:
    """Call the QDash UI server, which runs the pinned ``glyph-avatar`` package."""

    base_url: str
    timeout_seconds: float = 5.0

    def generate(self, spec: str) -> GeneratedAvatar:
        """Request the avatar for ``spec`` from the UI server."""
        url = f"{self.base_url.rstrip('/')}{GENERATOR_PATH}?spec={quote(spec, safe='')}"
        try:
            response = httpx.get(url, timeout=self.timeout_seconds, follow_redirects=False)
            response.raise_for_status()
            return GeneratedAvatar.model_validate_json(response.content)
        except (httpx.HTTPError, ValidationError) as exc:
            msg = f"Avatar generator request failed: {exc}"
            raise AvatarGenerationError(msg) from exc


def validate_avatar_svg(svg: str) -> None:
    """Reject markup outside the subset of SVG that ``glyph-avatar`` emits.

    Raises
    ------
    AvatarGenerationError
        If the SVG is too large, uses a declaration, processing instruction, or entity, or
        contains an element, attribute, text, or value that the generator never produces.

    """
    if len(svg.encode("utf-8")) > MAX_SVG_BYTES:
        msg = "Generated avatar SVG is too large"
        raise AvatarGenerationError(msg)
    if "<!" in svg or "<?" in svg or "&" in svg:
        msg = "Generated avatar SVG contains a declaration or entity"
        raise AvatarGenerationError(msg)
    try:
        root = ET.fromstring(svg)  # noqa: S314 - declarations and entities are rejected above
    except ET.ParseError as exc:
        msg = f"Generated avatar SVG is not well-formed: {exc}"
        raise AvatarGenerationError(msg) from exc
    if root.tag != f"{{{_SVG_NS}}}svg":
        msg = "Generated avatar root is not an SVG element"
        raise AvatarGenerationError(msg)
    for element in root.iter():
        namespace, _, local_name = element.tag.partition("}")
        if namespace != f"{{{_SVG_NS}" or local_name not in _ALLOWED_ELEMENTS:
            msg = f"Generated avatar contains unsupported element {element.tag!r}"
            raise AvatarGenerationError(msg)
        if (element.text or "").strip() or (element.tail or "").strip():
            msg = "Generated avatar contains text content"
            raise AvatarGenerationError(msg)
        for name, value in element.attrib.items():
            if name not in _ALLOWED_ATTRIBUTES:
                msg = f"Generated avatar contains unsupported attribute {name!r}"
                raise AvatarGenerationError(msg)
            if not _SAFE_ATTRIBUTE_VALUE.fullmatch(value) or "url(" in value.lower():
                msg = f"Generated avatar attribute {name!r} has an unsupported value"
                raise AvatarGenerationError(msg)


def _validate_generated(avatar: GeneratedAvatar, spec: str) -> None:
    """Check that the generator rendered ``spec`` with the pinned package and options."""
    if avatar.spec != spec:
        msg = "Avatar generator returned a different spec"
        raise AvatarGenerationError(msg)
    if avatar.generator != GLYPH_AVATAR_GENERATOR:
        msg = f"Unexpected avatar generator {avatar.generator!r}"
        raise AvatarGenerationError(msg)
    if avatar.generator_version != GLYPH_AVATAR_VERSION:
        msg = (
            f"Avatar generator version {avatar.generator_version!r} does not match "
            f"the pinned version {GLYPH_AVATAR_VERSION!r}"
        )
        raise AvatarGenerationError(msg)
    if avatar.options != GLYPH_AVATAR_RENDER_OPTIONS:
        msg = "Avatar generator used unexpected options"
        raise AvatarGenerationError(msg)
    validate_avatar_svg(avatar.svg)


def svg_etag(svg: str) -> str:
    """Return the strong ETag value (without quotes) for ``svg``."""
    return hashlib.sha256(svg.encode("utf-8")).hexdigest()


class UserAvatarService:
    """Serve each user's saved avatar, generating and saving it when needed."""

    def __init__(self, store: UserAvatarStore, generator: AvatarGenerator) -> None:
        """Create the service with its store and generator."""
        self._store = store
        self._generator = generator

    def get_or_create(self, username: str) -> UserAvatarModel | None:
        """Return the saved avatar for ``username``, generating the automatic one on first use.

        Returns ``None`` when no user has ``username``. A saved avatar is returned as stored,
        even if an older generator version rendered it.

        Raises
        ------
        AvatarGenerationError
            If no avatar is saved and the generator cannot produce a valid one.

        """
        user_id = self._store.find_user_id(username)
        if user_id is None:
            return None
        existing = self._store.find_avatar(user_id)
        if existing is not None:
            return existing
        avatar = self._render(user_id, username, automatic_avatar_spec(username), "automatic")
        logger.info("Generated automatic avatar for user %s", username)
        return self._store.insert_if_absent(avatar)

    def set_avatar(self, username: str, spec: str | None) -> UserAvatarModel:
        """Save a custom avatar from ``spec``, or the automatic avatar when ``spec`` is None.

        Raises
        ------
        UserNotFoundError
            If no user has ``username``.
        InvalidAvatarSpecError
            If ``spec`` is not a canonical v1 spec.
        AvatarGenerationError
            If the generator cannot produce a valid avatar; the saved avatar is unchanged.

        """
        if spec is not None:
            parse_avatar_spec(spec)
        user_id = self._store.find_user_id(username)
        if user_id is None:
            msg = f"User {username!r} not found"
            raise UserNotFoundError(msg)
        source: UserAvatarSource = "custom" if spec is not None else "automatic"
        resolved = spec if spec is not None else automatic_avatar_spec(username)
        avatar = self._render(user_id, username, resolved, source)
        logger.info("Saved %s avatar for user %s", source, username)
        return self._store.replace(avatar)

    def _render(
        self, user_id: str, username: str, spec: str, source: UserAvatarSource
    ) -> UserAvatarModel:
        parsed = parse_avatar_spec(spec)
        generated = self._generator.generate(spec)
        _validate_generated(generated, spec)
        timestamp = now()
        return UserAvatarModel(
            user_id=user_id,
            username=username,
            source=source,
            spec=spec,
            seed=parsed.seed,
            svg=generated.svg,
            etag=svg_etag(generated.svg),
            generator=generated.generator,
            generator_version=generated.generator_version,
            options=dict(generated.options),
            created_at=timestamp,
            updated_at=timestamp,
        )
