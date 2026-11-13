import type { Theme } from "@earendil-works/pi-coding-agent";

import { firstNumber, firstString, payloadTotal } from "./payload.js";
import { ansi, boxed, boxLinesToWidth } from "./render.js";

function shortId(value: string, length = 10): string {
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

export function forumPostsFromPayload(payload: unknown): Record<string, unknown>[] {
  if (Array.isArray(payload)) return payload.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object");
  if (payload && typeof payload === "object") {
    const object = payload as Record<string, unknown>;
    for (const key of ["posts", "items", "results", "data"]) {
      if (Array.isArray(object[key])) return object[key].filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object");
    }
  }
  return [];
}

function forumPostId(post: Record<string, unknown>): string {
  return firstString(post, ["post_id", "id", "forum_post_id"]) ?? "unknown";
}

export function forumPostTitle(post: Record<string, unknown>): string {
  return firstString(post, ["title", "subject", "summary"]) ?? firstString(post, ["content", "body", "text"])?.slice(0, 60) ?? "(untitled)";
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.length > 0) : [];
}

function forumPostLine(post: Record<string, unknown>): string {
  const number = firstNumber(post, ["number"]);
  const id = shortId(forumPostId(post), 10);
  const title = forumPostTitle(post);
  const status = firstString(post, ["status"]);
  const category = firstString(post, ["category"]);
  const targetType = firstString(post, ["target_type"]);
  const target = firstString(post, ["target_id", "chip_id", "task_id", "qid"]);
  const replies = firstNumber(post, ["reply_count"]);
  const assignee = firstString(post, ["assignee_username", "username"]);
  return [
    "•",
    number ? `#${number}` : id,
    title,
    category ? `[${category}]` : undefined,
    status ? `[${status}]` : undefined,
    target ? `(${targetType ? `${targetType}:` : ""}${target})` : undefined,
    replies && replies > 0 ? `↩${replies}` : undefined,
    assignee ? `@${assignee}` : undefined,
  ].filter(Boolean).join(" ");
}

function inlineContentText(value: unknown): string {
  if (typeof value === "string") return value;
  if (!Array.isArray(value)) return "";
  return value.map((item) => {
    if (typeof item === "string") return item;
    if (!item || typeof item !== "object") return "";
    const object = item as Record<string, unknown>;
    if (typeof object.text === "string") return object.text;
    if (object.type === "link") return inlineContentText(object.content);
    return "";
  }).join("");
}

function forumBlockLines(blocks: unknown): string[] {
  if (!Array.isArray(blocks)) return [];
  const lines: string[] = [];
  for (const item of blocks) {
    if (!item || typeof item !== "object") continue;
    const block = item as Record<string, unknown>;
    const type = firstString(block, ["type"]) ?? "block";
    const props = block.props && typeof block.props === "object" ? block.props as Record<string, unknown> : {};
    const text = inlineContentText(block.content).trimEnd();
    if (type === "heading") {
      const level = firstNumber(props, ["level"]) ?? 2;
      lines.push(`${"#".repeat(Math.max(1, Math.min(6, level)))} ${text}`.trimEnd());
    } else if (type === "image") {
      const name = firstString(props, ["name", "caption"]) ?? "image";
      const url = firstString(props, ["url"]);
      lines.push(`🖼 ${name}${url ? `  ${url}` : ""}`);
    } else if (type === "bulletListItem") {
      lines.push(`- ${text}`);
    } else if (type === "numberedListItem") {
      lines.push(`1. ${text}`);
    } else if (text) {
      lines.push(...text.split("\n"));
    }
    const childLines = forumBlockLines(block.children);
    if (childLines.length > 0) lines.push(...childLines.map((line) => `  ${line}`));
  }
  return lines;
}

function forumContentLines(object: Record<string, unknown>): string[] {
  const blockLines = forumBlockLines(object.content_blocks);
  if (blockLines.length > 0) return blockLines;
  const content = firstString(object, ["content", "body", "text", "message", "description"]);
  return content ? content.split("\n") : ["(no content)"];
}

export function forumListLines(payload: unknown, title = "QDash Forum", color = false): string[] {
  const posts = forumPostsFromPayload(payload);
  const total = payloadTotal(payload);
  const accent = (text: string) => color ? ansi("1;36", text) : text;
  const dim = (text: string) => color ? ansi("2", text) : text;
  return boxed(title, [
    `posts ${accent(`${posts.length}/${total}`)}`,
    "",
    ...(posts.length > 0 ? posts.map((post) => `  ${forumPostLine(post)}`) : [`  ${dim("none")}`]),
  ], color);
}

export function forumDetailBodyLines(post: unknown, color = false): string[] {
  const object = post && typeof post === "object" ? post as Record<string, unknown> : {};
  const accent = (text: string) => color ? ansi("1;36", text) : text;
  const muted = (text: string) => color ? ansi("90", text) : text;
  const labels = stringList(object.labels);
  const replyCount = firstNumber(object, ["reply_count"]);
  const meta = [
    firstString(object, ["category"]) ? `${muted("category")} ${firstString(object, ["category"])}` : undefined,
    firstString(object, ["status"]) ? `${muted("status")} ${firstString(object, ["status"])}` : undefined,
    firstString(object, ["target_type"]) || firstString(object, ["target_id"]) ? `${muted("target")} ${[firstString(object, ["target_type"]), firstString(object, ["target_id"])].filter(Boolean).join(":")}` : undefined,
    firstString(object, ["chip_id"]) ? `${muted("chip")} ${firstString(object, ["chip_id"])}` : undefined,
    replyCount !== undefined ? `${muted("replies")} ${replyCount}` : undefined,
  ].filter((line): line is string => typeof line === "string");
  return [
    `${muted("id")} ${accent(forumPostId(object))}${firstNumber(object, ["number"]) ? `  ${muted("#")} ${firstNumber(object, ["number"])}` : ""}`,
    `${muted("title")} ${forumPostTitle(object)}`,
    `${muted("author")} ${firstString(object, ["username", "user_id"]) ?? "unknown"}${firstString(object, ["assignee_username"]) ? `  ${muted("assignee")} ${firstString(object, ["assignee_username"])}` : ""}`,
    meta.join("  "),
    labels.length > 0 ? `${muted("labels")} ${labels.map((label) => `#${label}`).join(" ")}` : undefined,
    firstString(object, ["created_at"]) ? `${muted("created")} ${firstString(object, ["created_at"])}${firstString(object, ["updated_at"]) ? `  ${muted("updated")} ${firstString(object, ["updated_at"])}` : ""}` : undefined,
    "",
    ...forumContentLines(object).map((line) => `  ${line}`),
  ].filter((line): line is string => typeof line === "string");
}

export function forumDetailLines(post: unknown, title = "QDash Forum Post", color = false): string[] {
  return boxed(title, forumDetailBodyLines(post, color), color);
}

export function forumDetailComponent(post: unknown, theme: Theme) {
  return {
    render(width: number) {
      return boxLinesToWidth("QDash Forum Post", forumDetailBodyLines(post), width, theme);
    },
    invalidate() {},
  };
}
