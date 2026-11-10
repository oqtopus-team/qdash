export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://127.0.0.1:5715";
const ACCESS_TOKEN_COOKIE = "access_token";
const PASSTHROUGH_HEADERS = [
  "cache-control",
  "content-security-policy",
  "content-type",
  "etag",
  "x-content-type-options",
];

function accessToken(request: Request): string | null {
  const cookie = request.headers
    .get("cookie")
    ?.split(/;\s*/)
    .find((row) => row.startsWith(`${ACCESS_TOKEN_COOKIE}=`))
    ?.slice(ACCESS_TOKEN_COOKIE.length + 1);
  if (!cookie) return null;
  try {
    return decodeURIComponent(cookie);
  } catch {
    return null;
  }
}

/**
 * Proxy a user's avatar image to the API.
 *
 * An `<img>` request carries the session cookie but no Authorization header, so this handler
 * converts the cookie into the bearer token the API expects and forwards `If-None-Match` for
 * ETag revalidation.
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ username: string }> },
): Promise<Response> {
  const { username } = await params;
  const headers: Record<string, string> = {};
  const authorization = request.headers.get("authorization");
  const token = accessToken(request);
  if (authorization) {
    headers.Authorization = authorization;
  } else if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const ifNoneMatch = request.headers.get("if-none-match");
  if (ifNoneMatch) {
    headers["If-None-Match"] = ifNoneMatch;
  }

  const upstream = await fetch(`${INTERNAL_API_URL}/users/${encodeURIComponent(username)}/avatar`, {
    headers,
    cache: "no-store",
    signal: request.signal,
  });
  const responseHeaders = new Headers();
  for (const name of PASSTHROUGH_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  if (!upstream.ok && upstream.status !== 304) {
    responseHeaders.set("Cache-Control", "no-store");
  }
  const body = upstream.status === 304 ? null : await upstream.arrayBuffer();
  return new Response(body, { status: upstream.status, headers: responseHeaders });
}
