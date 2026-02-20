/**
 * Streaming SSE proxy helper for Copilot endpoints.
 *
 * Next.js rewrites buffer the entire response, which breaks SSE streaming.
 * These route handlers bypass rewrites and stream chunk-by-chunk from the
 * FastAPI backend to the browser.
 */

const INTERNAL_API_URL =
  process.env.INTERNAL_API_URL || "http://localhost:5715";

/**
 * Forward relevant headers from the incoming request to the backend.
 */
function forwardHeaders(request: Request): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  const auth = request.headers.get("authorization");
  if (auth) {
    headers["Authorization"] = auth;
  }

  const username = request.headers.get("x-username");
  if (username) {
    headers["X-Username"] = username;
  }

  const projectId = request.headers.get("x-project-id");
  if (projectId) {
    headers["X-Project-Id"] = projectId;
  }

  return headers;
}

/**
 * Proxy a POST request to the backend and stream the SSE response back.
 *
 * The backend response body (a ReadableStream) is passed directly to the
 * Next.js Response, ensuring chunks are forwarded as they arrive without
 * buffering.
 */
export async function proxySSEStream(
  request: Request,
  backendPath: string,
): Promise<Response> {
  const body = await request.text();

  const upstream = await fetch(`${INTERNAL_API_URL}${backendPath}`, {
    method: "POST",
    headers: forwardHeaders(request),
    body,
  });

  if (!upstream.ok) {
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
