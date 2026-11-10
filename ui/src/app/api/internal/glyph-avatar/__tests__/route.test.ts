import { describe, expect, it } from "vitest";

import { GET } from "@/app/api/internal/glyph-avatar/route";

describe("glyph avatar generator route", () => {
  it("renders a canonical spec with the pinned generator metadata", async () => {
    const response = GET(
      new Request("http://ui/api/internal/glyph-avatar?spec=v1%3Aalice%3A%3Asolid%3Ac"),
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    const body = await response.json();
    expect(body).toMatchObject({
      spec: "v1:alice::solid:c",
      generator: "glyph-avatar",
      generator_version: "0.1.0",
      options: { size: 64, shape: "circle" },
    });
    expect(body.svg).toMatch(/^<svg xmlns="http:\/\/www.w3.org\/2000\/svg"/);
  });

  it.each(["", "?spec=alice", "?spec=v1%3Aalice%3A%3Asolid%3A", "?spec=%3Csvg%3E"])(
    "rejects an invalid spec (%s)",
    (query) => {
      expect(GET(new Request(`http://ui/api/internal/glyph-avatar${query}`)).status).toBe(400);
    },
  );
});
