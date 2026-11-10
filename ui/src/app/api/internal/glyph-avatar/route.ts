import { canonicalAvatarSpec, renderGlyphAvatar } from "@/lib/avatar/glyphAvatar";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Render a canonical glyph-avatar spec for the QDash API.
 *
 * This is a pure function of the spec with no data access, so it needs no authentication. The
 * API calls it to create avatars and validates the SVG before saving it; browsers never send
 * avatar markup to the API.
 */
export function GET(request: Request): Response {
  const spec = canonicalAvatarSpec(new URL(request.url).searchParams.get("spec") ?? "");
  if (!spec) {
    return Response.json({ detail: "Invalid avatar spec" }, { status: 400 });
  }
  return Response.json(renderGlyphAvatar(spec), { headers: { "Cache-Control": "no-store" } });
}
