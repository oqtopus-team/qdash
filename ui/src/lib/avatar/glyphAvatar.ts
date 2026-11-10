import { BACKGROUNDS, avatarDataUri, parseSpec, stringifySpec } from "glyph-avatar";

/**
 * User avatars rendered in the browser by the glyph-avatar package bundled with the UI.
 *
 * The API stores only canonical spec strings chosen in the picker; it never renders avatars.
 * These constants must match `src/qdash/api/services/user_avatar_service.py` and the exact
 * version in `ui/package.json`.
 */
export const GLYPH_AVATAR_VERSION = "0.1.0";
const AUTOMATIC_AVATAR_BACKGROUND = "solid";

// Characters encodeURIComponent leaves unchanged, minus the ones the picker never emits.
const SPEC_TOKEN = /^[A-Za-z0-9._-]{1,64}$/;
const MAX_SPEC_LENGTH = 160;

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

/** The spec a user shows: a valid custom spec, otherwise the automatic one. */
export function resolveAvatarSpec(username: string, customSpec?: string | null): string {
  return (customSpec && canonicalAvatarSpec(customSpec)) || automaticAvatarSpec(username);
}

const dataUris = new Map<string, string>();

/**
 * A `data:` URI of the circular SVG for a canonical spec.
 *
 * The SVG is generated locally and shown through `<img>`, so it needs no network request and
 * cannot run script. Results are memoized because lists render the same users repeatedly.
 */
export function glyphAvatarDataUri(spec: string): string {
  let uri = dataUris.get(spec);
  if (!uri) {
    uri = avatarDataUri(spec, { shape: "circle" });
    dataUris.set(spec, uri);
  }
  return uri;
}
