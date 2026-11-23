import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

import { createAvatar } from "glyph-avatar";
import { describe, expect, it } from "vitest";

import {
  GLYPH_AVATAR_VERSION,
  automaticAvatarSpec,
  canonicalAvatarSpec,
  glyphAvatarDataUri,
  resolveAvatarSpec,
} from "@/lib/avatar/glyphAvatar";

// Golden glyph-avatar 0.1.0 output; a change here changes every user's avatar.
const ALICE_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="64" height="64" ' +
  'aria-hidden="true"><circle cx="50" cy="50" r="50" fill="#1F6B4A"/>' +
  '<g transform="rotate(90 50 50)"><path d="M24 63A26 26 0 0 1 76 63Z" fill="#9BE3C9"/>' +
  '<path d="M32 63A18 18 0 0 1 68 63Z" fill="#1F6B4A"/>' +
  '<path d="M40 63A10 10 0 0 1 60 63Z" fill="#9BE3C9"/></g></svg>';

const require = createRequire(import.meta.url);

describe("glyph avatar generation", () => {
  it("pins the exact installed glyph-avatar version", () => {
    const uiPackage = JSON.parse(readFileSync(join(process.cwd(), "package.json"), "utf8"));
    const installed = JSON.parse(
      readFileSync(join(dirname(require.resolve("glyph-avatar")), "..", "package.json"), "utf8"),
    );
    expect(uiPackage.dependencies["glyph-avatar"]).toBe(GLYPH_AVATAR_VERSION);
    expect(installed.version).toBe(GLYPH_AVATAR_VERSION);
  });

  it("seeds the automatic avatar with the exact username", () => {
    expect(automaticAvatarSpec("alice")).toBe("v1:alice::solid:c");
    expect(automaticAvatarSpec("a.b-c_d")).toBe("v1:a.b-c_d::solid:c");
  });

  it("renders fixed bytes for a username locally as a data URI", () => {
    const uri = glyphAvatarDataUri(automaticAvatarSpec("alice"));
    expect(uri.startsWith("data:image/svg+xml;utf8,")).toBe(true);
    expect(decodeURIComponent(uri.slice(uri.indexOf(",") + 1))).toBe(ALICE_SVG);
    expect(
      createAvatar(
        { seed: "alice" },
        { size: 64, colors: "curated", background: "solid", shape: "circle" },
      ),
    ).toBe(ALICE_SVG);
    expect(glyphAvatarDataUri("v1:alice::solid:c")).toBe(uri);
  });

  it("uses a valid custom spec and falls back to the automatic spec otherwise", () => {
    const custom = "v1:k3x9q2a-1.-2:p0w7zz:stripes:c";
    expect(resolveAvatarSpec("alice", custom)).toBe(custom);
    expect(resolveAvatarSpec("alice", null)).toBe("v1:alice::solid:c");
    expect(resolveAvatarSpec("alice", "<svg onload=alert(1)>")).toBe("v1:alice::solid:c");
  });

  it.each(["v1:alice::solid:c", "v1:k3x9q2a-1.-2:p0w7zz:stripes:c", "v1:abc", "v1:abc:::c"])(
    "accepts canonical spec %s",
    (spec) => {
      expect(canonicalAvatarSpec(spec)).toBe(spec);
    },
  );

  it.each([
    "alice",
    "v1:",
    "v1:alice:",
    "v1:alice::solid:",
    "v1:alice::unknown:c",
    "v1:alice::solid:x",
    "v1:alice::solid:c:extra",
    "v1:al%20ice",
    `v1:${"a".repeat(65)}`,
  ])("rejects non-canonical or unsupported spec %s", (spec) => {
    expect(canonicalAvatarSpec(spec)).toBeNull();
  });
});
