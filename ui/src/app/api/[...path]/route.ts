import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://127.0.0.1:5715";
const ACCESS_TOKEN_COOKIE = "access_token";
const SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;

type RouteContext = {
  params: Promise<{
    path?: string[];
  }>;
};

function backendUrl(path: string[], search: string): string {
  const pathname = path.join("/");
  return `${INTERNAL_API_URL}/${pathname}${search}`;
}

function buildForwardHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const accept = request.headers.get("accept");
  const projectId = request.headers.get("x-project-id");
  const token = request.cookies.get(ACCESS_TOKEN_COOKIE)?.value;

  if (contentType) {
    headers.set("Content-Type", contentType);
  }
  if (accept) {
    headers.set("Accept", accept);
  }
  if (projectId) {
    headers.set("X-Project-Id", projectId);
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  return headers;
}

function copyResponseHeaders(upstream: Response): Headers {
  const headers = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType) {
    headers.set("Content-Type", contentType);
  }
  return headers;
}

function setSessionCookie(response: NextResponse, token: string): void {
  response.cookies.set({
    name: ACCESS_TOKEN_COOKIE,
    value: token,
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_MAX_AGE_SECONDS,
  });
}

function clearSessionCookie(response: NextResponse): void {
  response.cookies.set({
    name: ACCESS_TOKEN_COOKIE,
    value: "",
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
  response.headers.append(
    "Set-Cookie",
    `${ACCESS_TOKEN_COOKIE}=; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax`,
  );
}

async function proxyRequest(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path = [] } = await context.params;
  const backendPath = path.join("/");

  if (backendPath === "auth/logout") {
    const response = NextResponse.json({ message: "Successfully logged out" });
    clearSessionCookie(response);
    return response;
  }

  const url = backendUrl(path, request.nextUrl.search);
  const method = request.method.toUpperCase();
  const hasBody = method !== "GET" && method !== "HEAD";

  const upstream = await fetch(url, {
    method,
    headers: buildForwardHeaders(request),
    body: hasBody ? await request.arrayBuffer() : undefined,
    cache: "no-store",
  });

  if (backendPath === "auth/login") {
    const payload = await upstream.json();
    const responsePayload = { ...payload };
    const token =
      typeof responsePayload.access_token === "string" ? responsePayload.access_token : null;
    delete responsePayload.access_token;

    const response = NextResponse.json(responsePayload, {
      status: upstream.status,
      statusText: upstream.statusText,
    });
    if (upstream.ok && token) {
      setSessionCookie(response, token);
    }
    return response;
  }

  const response = new NextResponse(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: copyResponseHeaders(upstream),
  });

  return response;
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
