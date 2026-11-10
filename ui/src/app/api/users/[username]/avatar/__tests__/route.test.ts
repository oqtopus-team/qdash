import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "@/app/api/users/[username]/avatar/route";

const params = (username: string) => ({ params: Promise.resolve({ username }) });

function upstream(status: number, body: string | null, headers: Record<string, string> = {}) {
  return vi.fn().mockResolvedValue(new Response(body, { status, headers }));
}

describe("user avatar proxy route", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("forwards the session cookie as a bearer token and passes image headers through", async () => {
    const fetchMock = upstream(200, "<svg/>", {
      "content-type": "image/svg+xml",
      etag: '"abc"',
      "cache-control": "private, no-cache",
      "content-security-policy": "default-src 'none'; sandbox",
      "x-content-type-options": "nosniff",
      "set-cookie": "leak=1",
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(
      new Request("http://ui/api/users/alice/avatar?v=abc", {
        headers: { cookie: "theme=dark; access_token=tok%2Ben", "if-none-match": '"old"' },
      }),
      params("alice"),
    );

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:5715/users/alice/avatar");
    expect(init.headers).toEqual({ Authorization: "Bearer tok+en", "If-None-Match": '"old"' });
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("<svg/>");
    expect(response.headers.get("content-type")).toBe("image/svg+xml");
    expect(response.headers.get("etag")).toBe('"abc"');
    expect(response.headers.get("content-security-policy")).toContain("sandbox");
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("returns 304 with the cache headers intact", async () => {
    vi.stubGlobal(
      "fetch",
      upstream(304, null, { etag: '"abc"', "cache-control": "private, no-cache" }),
    );
    const response = await GET(new Request("http://ui/api/users/alice/avatar"), params("alice"));
    expect(response.status).toBe(304);
    expect(response.headers.get("cache-control")).toBe("private, no-cache");
  });

  it("does not cache an error and encodes the username into the path", async () => {
    const fetchMock = upstream(404, '{"detail":"User not found"}', {
      "content-type": "application/json",
    });
    vi.stubGlobal("fetch", fetchMock);
    const response = await GET(new Request("http://ui/api/users/x/avatar"), params("../admin"));
    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:5715/users/..%2Fadmin/avatar");
    expect(fetchMock.mock.calls[0][1].headers).toEqual({});
    expect(response.status).toBe(404);
    expect(response.headers.get("cache-control")).toBe("no-store");
  });
});
