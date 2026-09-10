import { BlockNoteEditor, type PartialBlock } from "@blocknote/core";
import { strToU8, zip, type AsyncZippable } from "fflate";
import { stringify } from "yaml";

import { formatDateTime } from "@/lib/utils/datetime";
import type { ForumPostResponse } from "@/schemas";

export type ForumThreadExport = {
  /** ZIP file name, including the `.zip` extension. */
  filename: string;
  blob: Blob;
};

type BlockRecord = Record<string, unknown>;

const MIME_EXTENSIONS: Record<string, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/gif": "gif",
  "image/webp": "webp",
  "video/mp4": "mp4",
  "audio/mpeg": "mp3",
};

interface CollectedAsset {
  url: string;
  kind: "data" | "relative";
  refs: BlockRecord[];
  bytes: Uint8Array | null;
  filename: string | null;
  zipPath: string | null;
}

function cloneBlocks(blocks: BlockRecord[]): BlockRecord[] {
  if (typeof structuredClone === "function") {
    return structuredClone(blocks);
  }
  return JSON.parse(JSON.stringify(blocks)) as BlockRecord[];
}

function slugify(input: string): string {
  return input
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}

function buildRootFolderName(post: ForumPostResponse): string {
  if (post.number !== null && post.number !== undefined) {
    const numberPart = String(post.number).padStart(4, "0");
    const slug = slugify(post.title ?? "");
    return slug ? `forum-${numberPart}-${slug}` : `forum-${numberPart}`;
  }
  const idSlug = slugify(post.id);
  return `forum-${idSlug || post.id}`;
}

function setIfPresent(target: Record<string, unknown>, key: string, value: unknown): void {
  if (value === null || value === undefined || value === "") return;
  target[key] = value;
}

function resolveThreadTitle(post: ForumPostResponse): string {
  return post.title?.trim() ? post.title : "Untitled topic";
}

function resourceUrl(path: string): string {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return origin ? `${origin}${path}` : path;
}

/** Mirrors `dashboardTargetHref` in ForumDetailPage.tsx without importing it. */
function targetResourcePath(chipId: string, targetType: string, targetId: string): string {
  if (targetType === "qubit") return `/chip/${chipId}/qubit/${targetId}`;
  return `/dashboard?chip=${encodeURIComponent(chipId)}&type=coupling`;
}

const BARE_ISO_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/;

/** Normalizes a possibly timezone-less API timestamp to ISO8601; returns the raw value if it can't be parsed. */
function toIsoTimestamp(raw: string): string {
  const normalized = BARE_ISO_DATETIME.test(raw) ? `${raw}Z` : raw;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? raw : date.toISOString();
}

const HEADING_LINE = /^#{1,6}\s/;
const IMAGE_OR_EMBED_LINE = /^!\[[^\]]*\]\([^)]*\)/;
const DESCRIPTION_MAX_LENGTH = 200;

function firstDescriptionLine(markdown: string): string | undefined {
  let inFence = false;
  for (const rawLine of markdown.split("\n")) {
    const line = rawLine.trim();
    if (/^```/.test(line)) {
      inFence = !inFence;
      continue;
    }
    if (inFence || line === "") continue;
    if (IMAGE_OR_EMBED_LINE.test(line) || HEADING_LINE.test(line)) continue;
    return line;
  }
  return undefined;
}

function stripInlineMarkdown(text: string): string {
  return text
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/~~([^~]+)~~/g, "$1")
    .replace(/(^|[^A-Za-z0-9_])__([^_]+)__(?![A-Za-z0-9_])/g, "$1$2")
    .replace(/(^|[^A-Za-z0-9_])_([^_]+)_(?![A-Za-z0-9_])/g, "$1$2")
    .replace(/^#{1,6}\s*/, "")
    .replace(/\s+/g, " ")
    .trim();
}

function deriveDescription(rootMarkdown: string): string | undefined {
  const line = firstDescriptionLine(rootMarkdown);
  if (!line) return undefined;
  const text = stripInlineMarkdown(line);
  if (!text) return undefined;
  if (text.length <= DESCRIPTION_MAX_LENGTH) return text;
  return `${text.slice(0, DESCRIPTION_MAX_LENGTH)}…`;
}

/** Partial Open Knowledge Format v0.2 front matter; QDash-only fields live under `qdash`. */
function buildFrontMatter(
  post: ForumPostResponse,
  replies: ForumPostResponse[],
  rootMarkdown: string,
): Record<string, unknown> {
  const frontMatter: Record<string, unknown> = {};

  frontMatter.type = "Forum Thread";
  frontMatter.title = resolveThreadTitle(post);
  setIfPresent(frontMatter, "description", deriveDescription(rootMarkdown));
  frontMatter.resource = resourceUrl(`/forum/${post.id}`);
  if (post.labels && post.labels.length > 0) {
    frontMatter.tags = post.labels;
  }
  frontMatter.status = post.status === "resolved" ? "stable" : "draft";
  frontMatter.generated = {
    by: post.is_ai_reply ? "process:qdash-ai-reply" : `human:${post.username}`,
    at: toIsoTimestamp(post.created_at),
  };
  if (post.status === "resolved" && post.assignee_username) {
    frontMatter.verified = [
      { by: `human:${post.assignee_username}`, at: toIsoTimestamp(post.updated_at) },
    ];
  }
  if (post.chip_id && post.target_type && post.target_id) {
    frontMatter.sources = [
      {
        id: "target",
        resource: resourceUrl(targetResourcePath(post.chip_id, post.target_type, post.target_id)),
        title: `${post.target_id} · ${post.chip_id}`,
      },
    ];
  }

  const qdash: Record<string, unknown> = {};
  setIfPresent(qdash, "number", post.number);
  setIfPresent(qdash, "category", post.category);
  setIfPresent(qdash, "thread_status", post.status);
  setIfPresent(qdash, "author", post.username);
  setIfPresent(qdash, "assignee", post.assignee_username);
  setIfPresent(qdash, "chip_id", post.chip_id);
  setIfPresent(qdash, "target_type", post.target_type);
  setIfPresent(qdash, "target_id", post.target_id);
  setIfPresent(qdash, "cooldown_id", post.cooldown_id);
  qdash.reply_count = replies.length;
  setIfPresent(qdash, "created_at", post.created_at);
  setIfPresent(qdash, "updated_at", post.updated_at);
  qdash.exported_at = new Date().toISOString();
  qdash.exported_by = "process:qdash-forum-export";
  frontMatter.qdash = qdash;

  return frontMatter;
}

function buildThreadMarkdown(
  post: ForumPostResponse,
  replies: ForumPostResponse[],
  rootMarkdown: string,
  replyMarkdowns: string[],
): string {
  const frontMatter = buildFrontMatter(post, replies, rootMarkdown);
  const yamlBlock = ["---", stringify(frontMatter, { lineWidth: 0 }).trimEnd(), "---"].join("\n");
  const title = resolveThreadTitle(post);

  const sections = [yamlBlock, `# ${title}`, rootMarkdown.trim()];

  replies.forEach((reply, index) => {
    const aiSuffix = reply.is_ai_reply ? " (AI)" : "";
    const date = formatDateTime(reply.created_at, "yyyy-MM-dd HH:mm");
    const heading = `## Reply by @${reply.username}${aiSuffix} — ${date}`;
    sections.push(["---", heading, replyMarkdowns[index].trim()].join("\n\n"));
  });

  return `${sections.join("\n\n")}\n`;
}

function renderMarkdown(content: string, blocks: BlockRecord[]): string {
  if (blocks.length === 0) {
    return content;
  }
  const editor = BlockNoteEditor.create({
    initialContent: blocks as unknown as PartialBlock[],
  });
  return editor.blocksToMarkdownLossy();
}

/**
 * Recursively walk a BlockNote document (blocks, their `content` and
 * `children`) and invoke `register` for every `props` object that carries a
 * string `url` (image / video / audio / file blocks).
 */
function collectAssetRefs(
  node: unknown,
  register: (url: string, props: BlockRecord) => void,
): void {
  if (Array.isArray(node)) {
    for (const item of node) collectAssetRefs(item, register);
    return;
  }
  if (node !== null && typeof node === "object") {
    const obj = node as BlockRecord;
    const props = obj.props;
    if (
      props !== null &&
      typeof props === "object" &&
      typeof (props as BlockRecord).url === "string"
    ) {
      register((props as BlockRecord).url as string, props as BlockRecord);
    }
    for (const value of Object.values(obj)) {
      collectAssetRefs(value, register);
    }
  }
}

function collectAllAssets(blocksList: BlockRecord[][]): Map<string, CollectedAsset> {
  const assets = new Map<string, CollectedAsset>();
  const register = (url: string, props: BlockRecord) => {
    let kind: "data" | "relative";
    if (url.startsWith("data:")) {
      kind = "data";
    } else if (/^https?:\/\//i.test(url)) {
      // External hosts are never fetched (CORS, third-party content); leave as-is.
      return;
    } else {
      kind = "relative";
    }
    let asset = assets.get(url);
    if (!asset) {
      asset = { url, kind, refs: [], bytes: null, filename: null, zipPath: null };
      assets.set(url, asset);
    }
    asset.refs.push(props);
  };
  for (const blocks of blocksList) {
    collectAssetRefs(blocks, register);
  }
  return assets;
}

function extensionForMime(mime: string): string {
  const known = MIME_EXTENSIONS[mime];
  if (known) return known;
  const subtype = mime.split("/")[1] ?? "";
  const cleaned = subtype.replace(/[^a-z0-9]/gi, "").toLowerCase();
  return cleaned || "bin";
}

function decodeBase64(base64: string): Uint8Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function parseDataUrl(url: string): { mime: string; base64: string } | null {
  const match = /^data:([^,]*),(.*)$/s.exec(url);
  if (!match) return null;
  const [, meta, payload] = match;
  const mime = meta.replace(/;base64$/, "") || "application/octet-stream";
  return { mime, base64: payload };
}

function basenameFromUrl(url: string): string {
  const withoutHash = url.split("#")[0];
  const withoutQuery = withoutHash.split("?")[0];
  const segments = withoutQuery.split("/").filter(Boolean);
  const last = segments[segments.length - 1] ?? "asset";
  const sanitized = last.replace(/[^A-Za-z0-9._-]/g, "_").slice(0, 48);
  return sanitized || "asset";
}

async function resolveAsset(asset: CollectedAsset): Promise<boolean> {
  try {
    if (asset.kind === "data") {
      const parsed = parseDataUrl(asset.url);
      if (!parsed) return false;
      asset.bytes = decodeBase64(parsed.base64);
      asset.filename = `inline.${extensionForMime(parsed.mime)}`;
      return true;
    }
    const response = await fetch(asset.url);
    if (!response.ok) return false;
    asset.bytes = new Uint8Array(await response.arrayBuffer());
    asset.filename = basenameFromUrl(asset.url);
    return true;
  } catch {
    return false;
  }
}

/** Fetch/decode every collected asset and rewrite `props.url` in place for the ones that succeed. */
async function resolveAndRewriteAssets(assets: Map<string, CollectedAsset>): Promise<void> {
  const ordered = [...assets.values()];
  const ok = await Promise.all(ordered.map((asset) => resolveAsset(asset)));

  let sequence = 0;
  ordered.forEach((asset, index) => {
    if (!ok[index] || !asset.filename) return;
    sequence += 1;
    const zipPath = `assets/${String(sequence).padStart(3, "0")}-${asset.filename}`;
    asset.zipPath = zipPath;
    for (const props of asset.refs) {
      props.url = zipPath;
    }
  });
}

function zipAsync(files: AsyncZippable): Promise<Uint8Array<ArrayBuffer>> {
  return new Promise((resolve, reject) => {
    zip(files, (err, data) => {
      if (err) reject(err);
      else resolve(data);
    });
  });
}

/**
 * Build a downloadable ZIP export of a forum thread: `thread.md` (front
 * matter + markdown for the root post and every reply) plus an `assets/`
 * folder with the inline and same-origin media referenced by the thread.
 */
export async function buildForumThreadZip(
  post: ForumPostResponse,
  replies: ForumPostResponse[],
): Promise<ForumThreadExport> {
  const rootBlocks = cloneBlocks((post.content_blocks as BlockRecord[] | undefined) ?? []);
  const replyBlocksList = replies.map((reply) =>
    cloneBlocks((reply.content_blocks as BlockRecord[] | undefined) ?? []),
  );

  const assets = collectAllAssets([rootBlocks, ...replyBlocksList]);
  await resolveAndRewriteAssets(assets);

  const rootMarkdown = renderMarkdown(post.content, rootBlocks);
  const replyMarkdowns = replies.map((reply, index) =>
    renderMarkdown(reply.content, replyBlocksList[index]),
  );

  const threadMd = buildThreadMarkdown(post, replies, rootMarkdown, replyMarkdowns);
  const rootName = buildRootFolderName(post);

  const files: AsyncZippable = {
    [`${rootName}/thread.md`]: strToU8(threadMd),
  };
  for (const asset of assets.values()) {
    if (asset.zipPath && asset.bytes) {
      files[`${rootName}/${asset.zipPath}`] = asset.bytes;
    }
  }

  const zipped = await zipAsync(files);
  return {
    filename: `${rootName}.zip`,
    blob: new Blob([zipped], { type: "application/zip" }),
  };
}
