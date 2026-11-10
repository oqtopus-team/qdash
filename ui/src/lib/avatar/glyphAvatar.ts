import { BACKGROUNDS, createAvatar, parseSpec, stringifySpec } from "glyph-avatar";

/**
 * Generated user avatars rendered by the pinned glyph-avatar package.
 *
 * The API owns persistence: it asks this UI server to render a canonical spec string and saves
 * the resulting SVG. These constants must match `src/qdash/api/services/user_avatar_service.py`
 * and the exact version in `ui/package.json`.
 */
const GLYPH_AVATAR_GENERATOR = "glyph-avatar";
export const GLYPH_AVATAR_VERSION = "0.1.0";
const GLYPH_AVATAR_RENDER_OPTIONS = { size: 64, shape: "circle" } as const;
const AUTOMATIC_AVATAR_BACKGROUND = "solid";

// Characters encodeURIComponent leaves unchanged, minus the ones the picker never emits.
const SPEC_TOKEN = /^[A-Za-z0-9._-]{1,64}$/;
const MAX_SPEC_LENGTH = 160;

export type GeneratedGlyphAvatar = {
  spec: string;
  svg: string;
  generator: typeof GLYPH_AVATAR_GENERATOR;
  generator_version: typeof GLYPH_AVATAR_VERSION;
  options: typeof GLYPH_AVATAR_RENDER_OPTIONS;
};

/** Returns the spec if it is a canonical v1 spec QDash accepts, otherwise null. */
export function canonicalAvatarSpec(value: string): string | null {
  if (value.length > MAX_SPEC_LENGTH) return null;
  const parts = value.startsWith("v1:") ? value.slice(3).split(":") : [];
  if (parts.length === 0 || parts.length > 4) return null;
  const [seed, colorSeed = "", background = "", colors = ""] = parts;
  if (!SPEC_TOKEN.test(seed)) return null;
  if (colorSeed && !SPEC_TOKEN.test(colorSeed)) return null;
  if (background && !(BACKGROUNDS as readonly string[]).includes(background)) return null;
  if (colors !== "" && colors !== "c") return null;
  const parsed = parseSpec(value);
  return parsed && stringifySpec(parsed) === value ? value : null;
}

/** The automatic spec for a user: the seed is the exact username. */
export function automaticAvatarSpec(username: string): string {
  return stringifySpec({
    seed: username,
    background: AUTOMATIC_AVATAR_BACKGROUND,
    colors: "curated",
  });
}

/** Renders a canonical spec with the fixed QDash options. */
export function renderGlyphAvatar(spec: string): GeneratedGlyphAvatar {
  return {
    spec,
    svg: createAvatar(spec, { ...GLYPH_AVATAR_RENDER_OPTIONS }),
    generator: GLYPH_AVATAR_GENERATOR,
    generator_version: GLYPH_AVATAR_VERSION,
    options: GLYPH_AVATAR_RENDER_OPTIONS,
  };
}

/** Same-origin URL of a user's saved avatar image; `version` busts the browser cache. */
export function userAvatarUrl(username: string, version?: string | null): string {
  const path = `/api/users/${encodeURIComponent(username)}/avatar`;
  return version ? `${path}?v=${encodeURIComponent(version)}` : path;
}
