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

  it("writes the OKF front matter keys in order, with the qdash block omitting absent fields", async () => {
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
    const topLevelKeys = [...md.matchAll(/^([a-z_]+):/gm)].map((m) => m[1]);

    expect(topLevelKeys).toEqual([
      "type",
      "title",
      "description",
      "resource",
      "status",
      "generated",
      "qdash",
    ]);
    expect(md).toContain("type: Forum Thread");
    expect(md).toContain("title: Readout error spike");
    expect(md).toContain("description: Hello from the plain content field.");
    expect(md).toMatch(/^resource: .+\/forum\/post-1$/m);
    expect(md).toContain("status: draft");
    expect(md).toContain(`by: human:alice`);
    expect(md).toMatch(/at: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z/);
    expect(md).not.toMatch(/^tags:/m);
    expect(md).not.toMatch(/^verified:/m);
    expect(md).not.toMatch(/^sources:/m);
    expect(md).toContain("number: 42");
    expect(md).toContain("category: bug");
    expect(md).toContain("thread_status: open");
    expect(md).toContain("author: alice");
    expect(md).toContain("chip_id: chip-64");
    expect(md).not.toMatch(/^\s+assignee:/m);
    expect(md).not.toMatch(/^\s+target_type:/m);
    expect(md).not.toMatch(/^\s+target_id:/m);
    expect(md).not.toMatch(/^\s+cooldown_id:/m);
    expect(md).toContain("reply_count: 0");
    expect(md).toContain("exported_by: process:qdash-forum-export");
    expect(md).toMatch(/exported_at: ['"]?\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
  });

  it("maps a resolved thread to status: stable and an open thread to status: draft", async () => {
    const resolvedPost = makePost({ number: 1, status: "resolved" });
    const { blob: resolvedBlob } = await buildForumThreadZip(resolvedPost, []);
    const resolvedMd = strFromU8((await unzipBlob(resolvedBlob))["forum-0001/thread.md"]);
    expect(resolvedMd).toContain("status: stable");
    expect(resolvedMd).toContain("thread_status: resolved");

    const openPost = makePost({ number: 2, status: "open" });
    const { blob: openBlob } = await buildForumThreadZip(openPost, []);
    const openMd = strFromU8((await unzipBlob(openBlob))["forum-0002/thread.md"]);
    expect(openMd).toContain("status: draft");
    expect(openMd).toContain("thread_status: open");
  });

  it("emits verified only for a resolved thread with an assignee", async () => {
    const resolvedWithAssignee = makePost({
      number: 1,
      status: "resolved",
      assignee_username: "carol",
      updated_at: "2026-08-02T04:00:00+00:00",
    });
    const { blob: verifiedBlob } = await buildForumThreadZip(resolvedWithAssignee, []);
    const verifiedMd = strFromU8((await unzipBlob(verifiedBlob))["forum-0001/thread.md"]);
    expect(verifiedMd).toMatch(/^verified:/m);
    expect(verifiedMd).toContain("by: human:carol");
    expect(verifiedMd).toContain("at: 2026-08-02T04:00:00.000Z");

    const resolvedWithoutAssignee = makePost({ number: 2, status: "resolved" });
    const { blob: noAssigneeBlob } = await buildForumThreadZip(resolvedWithoutAssignee, []);
    const noAssigneeMd = strFromU8((await unzipBlob(noAssigneeBlob))["forum-0002/thread.md"]);
    expect(noAssigneeMd).not.toMatch(/^verified:/m);

    const openWithAssignee = makePost({
      number: 3,
      status: "open",
      assignee_username: "carol",
    });
    const { blob: openBlob } = await buildForumThreadZip(openWithAssignee, []);
    const openMd = strFromU8((await unzipBlob(openBlob))["forum-0003/thread.md"]);
    expect(openMd).not.toMatch(/^verified:/m);
  });

  it("credits generated.by to the AI reply process identifier when the root post is an AI reply", async () => {
    const humanPost = makePost({ number: 1, username: "alice" });
    const { blob: humanBlob } = await buildForumThreadZip(humanPost, []);
    const humanMd = strFromU8((await unzipBlob(humanBlob))["forum-0001/thread.md"]);
    expect(humanMd).toContain("by: human:alice");

    const aiPost = makePost({ number: 2, username: "qdash-bot", is_ai_reply: true });
    const { blob: aiBlob } = await buildForumThreadZip(aiPost, []);
    const aiMd = strFromU8((await unzipBlob(aiBlob))["forum-0002/thread.md"]);
    expect(aiMd).toContain("by: process:qdash-ai-reply");
  });

  it("emits sources only when chip_id, target_type and target_id are all set, in the qubit and coupling URL forms", async () => {
    const noTarget = makePost({ number: 1 });
    const { blob: noTargetBlob } = await buildForumThreadZip(noTarget, []);
    const noTargetMd = strFromU8((await unzipBlob(noTargetBlob))["forum-0001/thread.md"]);
    expect(noTargetMd).not.toMatch(/^sources:/m);

    const qubitPost = makePost({
      number: 2,
      chip_id: "chip-64",
      target_type: "qubit",
      target_id: "12",
    });
    const { blob: qubitBlob } = await buildForumThreadZip(qubitPost, []);
    const qubitMd = strFromU8((await unzipBlob(qubitBlob))["forum-0002/thread.md"]);
    expect(qubitMd).toMatch(/^sources:/m);
    expect(qubitMd).toContain("id: target");
    expect(qubitMd).toContain(`resource: ${window.location.origin}/chip/chip-64/qubit/12`);
    expect(qubitMd).toContain("title: 12 · chip-64");

    const couplingPost = makePost({
      number: 3,
      chip_id: "chip-64",
      target_type: "coupling",
      target_id: "12-13",
    });
    const { blob: couplingBlob } = await buildForumThreadZip(couplingPost, []);
    const couplingMd = strFromU8((await unzipBlob(couplingBlob))["forum-0003/thread.md"]);
    expect(couplingMd).toContain(
      `resource: ${window.location.origin}/dashboard?chip=chip-64&type=coupling`,
    );
    expect(couplingMd).toContain("title: 12-13 · chip-64");
  });

  it("derives description from the first plain-text line of the rendered root markdown, skipping code/image/heading lines", async () => {
    const post = makePost({
      number: 1,
      content: [
        "```js",
        "const skipped = true;",
        "```",
        "![alt](image.png)",
        "# Heading not counted",
        "",
        "Some **bold** and ~~struck~~ and _italic_ and `code` and [link text](https://example.com) keeps target_id and chip_id intact.",
      ].join("\n"),
    });

    const { blob } = await buildForumThreadZip(post, []);
    const md = strFromU8((await unzipBlob(blob))["forum-0001/thread.md"]);
    expect(md).toContain(
      "description: Some bold and struck and italic and code and link text keeps target_id and chip_id intact.",
    );
  });

  it("keeps literal markdown characters in the description and flattens styled runs", async () => {
    const post = makePost({
      number: 12,
      content_blocks: [
        { type: "heading", content: [{ type: "text", text: "Not the description", styles: {} }] },
        {
          type: "paragraph",
          content: [
            { type: "text", text: "5 * 3 * 2 shots in _raw_ mode, ", styles: {} },
            { type: "text", text: "retried", styles: { bold: true } },
            { type: "text", text: " via ", styles: {} },
            {
              type: "link",
              href: "https://example.com",
              content: [{ type: "text", text: "the runbook", styles: {} }],
            },
          ],
        },
      ],
    });

    const { blob } = await buildForumThreadZip(post, []);
    const md = strFromU8((await unzipBlob(blob))["forum-0012/thread.md"]);
    expect(md).toContain("description: 5 * 3 * 2 shots in _raw_ mode, retried via the runbook");
  });

  it("truncates a long description to 200 characters with a trailing ellipsis", async () => {
    const longLine = "A".repeat(250);
    const post = makePost({ number: 1, content: longLine });

    const { blob } = await buildForumThreadZip(post, []);
    const md = strFromU8((await unzipBlob(blob))["forum-0001/thread.md"]);
    expect(md).toContain(`description: ${"A".repeat(200)}…`);
  });

  it("omits description when the root markdown has no plain-text content", async () => {
    const post = makePost({ number: 1, content: "![alt](image.png)" });

    const { blob } = await buildForumThreadZip(post, []);
    const md = strFromU8((await unzipBlob(blob))["forum-0001/thread.md"]);
    expect(md).not.toMatch(/^description:/m);
  });

  it("omits tags when the thread has no labels, and emits them otherwise", async () => {
    const withoutLabels = makePost({ number: 1, labels: [] });
    const { blob: withoutBlob } = await buildForumThreadZip(withoutLabels, []);
    const withoutMd = strFromU8((await unzipBlob(withoutBlob))["forum-0001/thread.md"]);
    expect(withoutMd).not.toMatch(/^tags:/m);

    const withLabels = makePost({ number: 2, labels: ["hardware", "readout"] });
    const { blob: withBlob } = await buildForumThreadZip(withLabels, []);
    const withMd = strFromU8((await unzipBlob(withBlob))["forum-0002/thread.md"]);
    expect(withMd).toMatch(/^tags:/m);
    expect(withMd).toContain("- hardware");
    expect(withMd).toContain("- readout");
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

  it("leaves protocol-relative and blob URLs untouched and never fetches them", async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const post = makePost({
      number: 11,
      title: "Off origin image",
      content_blocks: [
        { type: "image", props: { url: "//example.com/cat.png" } },
        { type: "image", props: { url: "blob:http://localhost:3000/9f8e" } },
      ],
    });

    const { blob } = await buildForumThreadZip(post, []);
    const files = await unzipBlob(blob);
    const rootName = "forum-0011-off-origin-image";

    expect(fetchMock).not.toHaveBeenCalled();
    const md = strFromU8(files[`${rootName}/thread.md`]);
    expect(md).toContain("//example.com/cat.png");
    expect(md).toContain("blob:http://localhost:3000/9f8e");
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

  it("parses data URLs whose mime carries extra parameters", async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const base64 = Buffer.from("PNGBYTES").toString("base64");
    const post = makePost({
      number: 20,
      title: "Charset param",
      content_blocks: [
        { type: "image", props: { url: `data:image/png;charset=utf-8;base64,${base64}` } },
      ],
    });

    const { blob } = await buildForumThreadZip(post, []);
    const files = await unzipBlob(blob);
    const rootName = "forum-0020-charset-param";

    expect(fetchMock).not.toHaveBeenCalled();
    expect(files[`${rootName}/assets/001-inline.png`]).toBeDefined();
    expect(strFromU8(files[`${rootName}/assets/001-inline.png`])).toBe("PNGBYTES");
  });

  it("decodes percent-encoded (non-base64) data URLs", async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const post = makePost({
      number: 21,
      title: "Percent encoded",
      content_blocks: [{ type: "image", props: { url: "data:text/plain,Hello%20World" } }],
    });

    const { blob } = await buildForumThreadZip(post, []);
    const files = await unzipBlob(blob);
    const rootName = "forum-0021-percent-encoded";

    expect(fetchMock).not.toHaveBeenCalled();
    expect(strFromU8(files[`${rootName}/assets/001-inline.plain`])).toBe("Hello World");
  });

  it("maps image/svg+xml to a .svg extension", async () => {
    const base64 = Buffer.from("<svg/>").toString("base64");
    const post = makePost({
      number: 22,
      title: "Svg asset",
      content_blocks: [{ type: "image", props: { url: `data:image/svg+xml;base64,${base64}` } }],
    });

    const { blob } = await buildForumThreadZip(post, []);
    const files = await unzipBlob(blob);
    const rootName = "forum-0022-svg-asset";

    expect(files[`${rootName}/assets/001-inline.svg`]).toBeDefined();
    expect(strFromU8(files[`${rootName}/assets/001-inline.svg`])).toBe("<svg/>");
  });

  it("treats backslash URLs as external and never fetches them", async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const post = makePost({
      number: 23,
      title: "Backslash url",
      content_blocks: [{ type: "image", props: { url: "\\\\example.com\\cat.png" } }],
    });

    const { blob } = await buildForumThreadZip(post, []);
    const files = await unzipBlob(blob);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(Object.keys(files).some((path) => path.includes("/assets/"))).toBe(false);
  });

  it("truncates the description on code point boundaries", async () => {
    const post = makePost({ number: 24, content: "A" + "🐙".repeat(200) });

    const { blob } = await buildForumThreadZip(post, []);
    const md = strFromU8((await unzipBlob(blob))["forum-0024/thread.md"]);
    expect(md).toContain(`description: A${"🐙".repeat(199)}…`);
  });
});
