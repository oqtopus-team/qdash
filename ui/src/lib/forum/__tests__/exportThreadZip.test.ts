import { strFromU8, unzipSync, type Unzipped } from "fflate";
import { afterEach, describe, expect, it, vi } from "vitest";

import { formatDateTime } from "@/lib/utils/datetime";
import type { ForumPostResponse } from "@/schemas";

import { buildForumThreadZip } from "../exportThreadZip";

function makePost(overrides: Partial<ForumPostResponse> = {}): ForumPostResponse {
  return {
    id: "post-1",
    project_id: "proj-1",
    category: "general",
    username: "alice",
    content: "Hello from the plain content field.",
    created_at: "2026-08-01T01:03:00+00:00",
    updated_at: "2026-08-01T01:03:00+00:00",
    ...overrides,
  };
}

async function unzipBlob(blob: Blob): Promise<Unzipped> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  return unzipSync(bytes);
}

const originalFetch = globalThis.fetch;

describe("buildForumThreadZip", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("writes the expected front matter keys and omits null/empty ones, while always writing labels", async () => {
    const post = makePost({
      number: 42,
      title: "Readout error spike",
      category: "bug",
      status: "open",
      labels: [],
      assignee_username: null,
      chip_id: "chip-64",
      target_type: null,
      target_id: null,
      cooldown_id: undefined,
    });

    const { blob, filename } = await buildForumThreadZip(post, []);
    expect(filename).toBe("forum-0042-readout-error-spike.zip");

    const files = await unzipBlob(blob);
    const md = strFromU8(files["forum-0042-readout-error-spike/thread.md"]);

    expect(md).toContain("number: 42");
    expect(md).toContain("title: Readout error spike");
    expect(md).toContain("category: bug");
    expect(md).toContain("status: open");
    expect(md).toContain("labels: []");
    expect(md).toContain("author: alice");
    expect(md).toContain("chip_id: chip-64");
    expect(md).not.toMatch(/^assignee:/m);
    expect(md).not.toMatch(/^target_type:/m);
    expect(md).not.toMatch(/^target_id:/m);
    expect(md).not.toMatch(/^cooldown_id:/m);
    expect(md).toMatch(/exported_at: ['"]?\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
  });

  it("concatenates replies as headings, marks AI replies, and omits the section when there are no replies", async () => {
    const post = makePost({ number: 7, title: "No replies yet" });

    const { blob: soloBlob } = await buildForumThreadZip(post, []);
    const soloFiles = await unzipBlob(soloBlob);
    const soloMd = strFromU8(soloFiles["forum-0007-no-replies-yet/thread.md"]);
    expect(soloMd).not.toContain("## Reply by");

    const reply1 = makePost({
      id: "reply-1",
      username: "bob",
      content: "Thanks, looking into it.",
      created_at: "2026-08-01T01:03:00+00:00",
      is_ai_reply: false,
    });
    const reply2 = makePost({
      id: "reply-2",
      username: "qdash-bot",
      content: "Automated triage suggests a wiring issue.",
      created_at: "2026-08-01T02:20:00+00:00",
      is_ai_reply: true,
    });

    const { blob } = await buildForumThreadZip(post, [reply1, reply2]);
    const files = await unzipBlob(blob);
    const md = strFromU8(files["forum-0007-no-replies-yet/thread.md"]);

    const date1 = formatDateTime(reply1.created_at, "yyyy-MM-dd HH:mm");
    const date2 = formatDateTime(reply2.created_at, "yyyy-MM-dd HH:mm");

    expect(md).toContain(`## Reply by @bob — ${date1}`);
    expect(md).toContain(`## Reply by @qdash-bot (AI) — ${date2}`);
    expect(md).toContain("Thanks, looking into it.");
    expect(md).toContain("Automated triage suggests a wiring issue.");
    expect(md.indexOf(`## Reply by @bob`)).toBeLessThan(md.indexOf(`## Reply by @qdash-bot`));
  });

  it("fetches same-origin images, stores them under assets/, and rewrites the reference in thread.md", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      expect(url).toBe("/api/forum/images/photo.png");
      return {
        ok: true,
        arrayBuffer: async () => new TextEncoder().encode("PNGBYTES").buffer,
      } as Response;
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const post = makePost({
      number: 5,
      title: "Photo attached",
      content_blocks: [{ type: "image", props: { url: "/api/forum/images/photo.png" } }],
    });

    const { blob } = await buildForumThreadZip(post, []);
    const files = await unzipBlob(blob);
    const rootName = "forum-0005-photo-attached";

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(files[`${rootName}/assets/001-photo.png`]).toBeDefined();
    expect(strFromU8(files[`${rootName}/assets/001-photo.png`])).toBe("PNGBYTES");

    const md = strFromU8(files[`${rootName}/thread.md`]);
    expect(md).toContain("assets/001-photo.png");
    expect(md).not.toContain("/api/forum/images/photo.png");
  });

  it("decodes inline data: URLs into assets/ without leaving base64 in thread.md", async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const base64 = Buffer.from("VIDEOBYTES").toString("base64");
    const post = makePost({
      number: 6,
      title: "Inline clip",
      content_blocks: [{ type: "video", props: { url: `data:video/mp4;base64,${base64}` } }],
    });

    const { blob } = await buildForumThreadZip(post, []);
    const files = await unzipBlob(blob);
    const rootName = "forum-0006-inline-clip";

    expect(fetchMock).not.toHaveBeenCalled();
    expect(files[`${rootName}/assets/001-inline.mp4`]).toBeDefined();
    expect(strFromU8(files[`${rootName}/assets/001-inline.mp4`])).toBe("VIDEOBYTES");

    const md = strFromU8(files[`${rootName}/thread.md`]);
    expect(md).not.toContain("base64");
    expect(md).not.toContain(base64);
    expect(md).toContain("assets/001-inline.mp4");
  });

  it("leaves external https URLs untouched and never fetches them", async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const post = makePost({
      number: 8,
      title: "External image",
      content_blocks: [{ type: "image", props: { url: "https://example.com/cat.png" } }],
    });

    const { blob } = await buildForumThreadZip(post, []);
    const files = await unzipBlob(blob);
    const rootName = "forum-0008-external-image";

    expect(fetchMock).not.toHaveBeenCalled();
    const md = strFromU8(files[`${rootName}/thread.md`]);
    expect(md).toContain("https://example.com/cat.png");
    expect(Object.keys(files).some((path) => path.includes("/assets/"))).toBe(false);
  });

  it("falls back to post.content when content_blocks is empty", async () => {
    const post = makePost({
      number: 9,
      title: "Legacy post",
      content: "Legacy **markdown** content.",
      content_blocks: [],
    });

    const { blob } = await buildForumThreadZip(post, []);
    const files = await unzipBlob(blob);
    const md = strFromU8(files["forum-0009-legacy-post/thread.md"]);

    expect(md).toContain("Legacy **markdown** content.");
  });

  it("keeps the original URL when fetch rejects or responds with ok: false", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/forum/images/rejects.png") {
        throw new Error("network down");
      }
      return { ok: false, arrayBuffer: async () => new ArrayBuffer(0) } as Response;
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const post = makePost({
      number: 10,
      title: "Broken assets",
      content_blocks: [
        { type: "image", props: { url: "/api/forum/images/rejects.png" } },
        { type: "image", props: { url: "/api/forum/images/not-ok.png" } },
      ],
    });

    const { blob } = await buildForumThreadZip(post, []);
    const files = await unzipBlob(blob);

    const rootName = "forum-0010-broken-assets";
    const md = strFromU8(files[`${rootName}/thread.md`]);
    expect(md).toContain("/api/forum/images/rejects.png");
    expect(md).toContain("/api/forum/images/not-ok.png");
    expect(Object.keys(files).some((path) => path.includes("/assets/"))).toBe(false);
  });

  it("builds the ZIP filename from the post number and an English title slug, or just the number for a non-ASCII title", async () => {
    const englishPost = makePost({ number: 42, title: "Readout error spike on Q12" });
    const { filename: englishFilename } = await buildForumThreadZip(englishPost, []);
    expect(englishFilename).toBe("forum-0042-readout-error-spike-on-q12.zip");

    const japanesePost = makePost({ number: 42, title: "読み出しエラーの急増" });
    const { filename: japaneseFilename } = await buildForumThreadZip(japanesePost, []);
    expect(japaneseFilename).toBe("forum-0042.zip");
  });

  it("does not mutate the input post.content_blocks", async () => {
    const contentBlocks = [{ type: "image", props: { url: "/api/forum/images/keep.png" } }];
    const post = makePost({
      number: 11,
      title: "Immutable input",
      content_blocks: contentBlocks,
    });
    const before = JSON.stringify(post.content_blocks);

    const fetchMock = vi.fn(async () => ({
      ok: true,
      arrayBuffer: async () => new TextEncoder().encode("BYTES").buffer,
    })) as unknown as typeof fetch;
    globalThis.fetch = fetchMock;

    await buildForumThreadZip(post, []);

    expect(JSON.stringify(post.content_blocks)).toBe(before);
    expect(post.content_blocks![0].props).toEqual({ url: "/api/forum/images/keep.png" });
  });
});
