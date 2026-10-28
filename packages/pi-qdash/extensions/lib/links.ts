import type { QDashClient } from "@oqtopus-team/qdash-client";

function firstString(object: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = object[key];
    if (typeof value === "string" && value.length > 0) return value;
    if (typeof value === "number" && Number.isFinite(value)) return String(value);
  }
  return undefined;
}

/**
 * Where the QDash web UI lives, for links in tool output.
 *
 * `QDASH_WEB_URL` wins when set: inside a deployment the API base URL is an
 * internal address (`http://api:5715`) that no browser can open. Without it,
 * the UI is assumed to sit next to the API with the `/api` prefix stripped,
 * which holds for a local checkout.
 */
export function qdashWebBaseUrl(client: QDashClient, env: NodeJS.ProcessEnv = process.env): string {
  const configured = env.QDASH_WEB_URL?.trim();
  if (configured) return configured.replace(/\/+$/, "");
  return client.config.baseUrl.replace(/\/api\/?$/, "").replace(/\/$/, "");
}

export function qdashWebUrl(client: QDashClient, path: string): string {
  return `${qdashWebBaseUrl(client)}${path.startsWith("/") ? path : `/${path}`}`;
}

/** Path of an execution page: under its chip when known, else the id-only route that redirects. */
export function executionPagePath(executionId: string, chipId?: string | null): string {
  return chipId
    ? `/execution/${encodeURIComponent(chipId)}/${encodeURIComponent(executionId)}`
    : `/executions/${encodeURIComponent(executionId)}`;
}

export function forumPostPagePath(postId: string): string {
  return `/forum/${encodeURIComponent(postId)}`;
}

export function qdashObjectLinks(client: QDashClient, object: Record<string, unknown>): Record<string, string> {
  const links: Record<string, string> = {};
  const taskId = firstString(object, ["task_id", "taskId"]);
  const executionId = firstString(object, ["execution_id", "executionId"]);
  const chipId = firstString(object, ["chip_id", "chipId"]);
  const postId = firstString(object, ["post_id", "forum_post_id", "id"]);
  const sessionId = firstString(object, ["session_id", "sessionId"]);
  if (taskId) links.task_result = qdashWebUrl(client, `/task-results/${encodeURIComponent(taskId)}`);
  if (executionId) links.execution = qdashWebUrl(client, executionPagePath(executionId, chipId));
  if (postId) links.forum_post = qdashWebUrl(client, forumPostPagePath(postId));
  if (sessionId) links.agent_session = qdashWebUrl(client, `/agent-sessions/${encodeURIComponent(sessionId)}`);
  return links;
}

export function withQDashLinks(client: QDashClient, data: unknown): unknown {
  if (!data || typeof data !== "object" || Array.isArray(data)) return data;
  const object = data as Record<string, unknown>;
  const links = qdashObjectLinks(client, object);
  if (Object.keys(links).length === 0) return data;
  return { ...object, _links: links };
}

export function safeConfig(client: QDashClient, source: string) {
  const config = client.config;
  return {
    source,
    baseUrl: config.baseUrl,
    projectId: config.projectId ?? null,
    timeoutSeconds: config.timeoutSeconds,
    verifyTls: config.verifyTls,
    proxyConfigured: Boolean(config.proxy),
    apiTokenConfigured: Boolean(config.apiToken),
    cloudflareAccessConfigured: Boolean(config.cfAccessClientId || config.cfAccessClientSecret),
    userAgent: config.userAgent,
    retry: config.retry,
  };
}
