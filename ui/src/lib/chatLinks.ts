/**
 * What a link in a chat answer points at, so the chat can preview QDash
 * records in a dialog instead of navigating away from the conversation.
 *
 * pi-qdash builds these URLs from the deployment's web address, so they
 * arrive absolute (`https://qdash.example/task-results/abc`) or, in older
 * answers, with the legacy `/executions/{id}` and `/forum/posts/{id}` shapes;
 * both are accepted. The origin is not checked for QDash record routes: a
 * misconfigured deployment can name the wrong host, and the preview and
 * "Open page" link resolve the record on this one. Links that match no record
 * route keep their origin: same-origin ones are internal, others external.
 */

export type ChatLink =
  | { kind: "task-result"; taskId: string; href: string }
  | { kind: "execution"; executionId: string; chipId: string | null; href: string }
  | { kind: "forum-post"; postId: string; href: string }
  | { kind: "figure"; path: string; href: string }
  | { kind: "internal"; href: string }
  | { kind: "external"; href: string };

function segment(value: string | undefined): string | null {
  if (!value) return null;
  try {
    const decoded = decodeURIComponent(value);
    return decoded.trim() ? decoded : null;
  } catch {
    return value;
  }
}

/** Classify `href` relative to the page at `origin` (defaults to the current one). */
export function classifyChatLink(href: string, origin?: string): ChatLink {
  const base =
    origin ?? (typeof window !== "undefined" ? window.location.origin : "http://localhost");
  let url: URL;
  try {
    url = new URL(href, base);
  } catch {
    return { kind: "external", href };
  }
  const parts = url.pathname.split("/").filter(Boolean);
  const [first, second, third] = parts;

  if (first === "task-results" && parts.length === 2) {
    const taskId = segment(second);
    if (taskId) return { kind: "task-result", taskId, href };
  }
  if (first === "executions" && parts.length === 2) {
    const executionId = segment(second);
    if (executionId) return { kind: "execution", executionId, chipId: null, href };
  }
  if (first === "execution" && parts.length === 3) {
    const chipId = segment(second);
    const executionId = segment(third);
    if (chipId && executionId) return { kind: "execution", executionId, chipId, href };
  }
  if (first === "forum" && parts.length === 2 && second !== "new") {
    const postId = segment(second);
    if (postId) return { kind: "forum-post", postId, href };
  }
  if (first === "forum" && second === "posts" && parts.length === 3) {
    const postId = segment(third);
    if (postId) return { kind: "forum-post", postId, href };
  }
  if (first === "api" && second === "executions" && third === "figure") {
    const path = url.searchParams.get("path");
    if (path) return { kind: "figure", path, href };
  }
  if (url.origin !== new URL(base).origin) return { kind: "external", href };
  return { kind: "internal", href };
}

/** The page a chat link should open in full, with legacy shapes mapped to real routes. */
export function chatLinkPagePath(link: ChatLink): string | null {
  switch (link.kind) {
    case "task-result":
      return `/task-results/${encodeURIComponent(link.taskId)}`;
    case "execution":
      return link.chipId
        ? `/execution/${encodeURIComponent(link.chipId)}/${encodeURIComponent(link.executionId)}`
        : `/executions/${encodeURIComponent(link.executionId)}`;
    case "forum-post":
      return `/forum/${encodeURIComponent(link.postId)}`;
    default:
      return null;
  }
}
