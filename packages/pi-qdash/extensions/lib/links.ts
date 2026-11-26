import { firstString } from "./payload.js";
import type { QDashConnection } from "./qdash-connection.js";

/**
 * Where the QDash web UI lives, for links in tool output.
 *
 * `QDASH_WEB_URL` wins when set: inside a deployment the API base URL is an
 * internal address (`http://api:5715`) that no browser can open. Without it,
 * the UI is assumed to sit next to the API with the `/api` prefix stripped,
 * which holds for a local checkout.
 */
export function qdashWebBaseUrl(client: QDashConnection, env: NodeJS.ProcessEnv = process.env): string {
  const configured = env.QDASH_WEB_URL?.trim();
  if (configured) return configured.replace(/\/+$/, "");
  return client.config.baseUrl.replace(/\/api\/?$/, "").replace(/\/$/, "");
}

export function qdashWebUrl(client: QDashConnection, path: string): string {
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

/** Path of a metric script's editor page. */
export function metricScriptPagePath(scriptId: string): string {
  return `/dashboards/scripts/${encodeURIComponent(scriptId)}`;
}

/** Path of a dashboard's page. */
export function dashboardPagePath(dashboardId: string): string {
  return `/dashboards/${encodeURIComponent(dashboardId)}`;
}

export function qdashObjectLinks(client: QDashConnection, object: Record<string, unknown>): Record<string, string> {
  const links: Record<string, string> = {};
  const taskId = firstString(object, ["task_id", "taskId"]);
  const executionId = firstString(object, ["execution_id", "executionId"]);
  const chipId = firstString(object, ["chip_id", "chipId"]);
  const postId = firstString(object, ["post_id", "forum_post_id", "id"]);
  const sessionId = firstString(object, ["session_id", "sessionId"]);
  const scriptId = firstString(object, ["script_id", "scriptId"]);
  const dashboardId = firstString(object, ["dashboard_id", "dashboardId"]);
  if (taskId) links.task_result = qdashWebUrl(client, `/task-results/${encodeURIComponent(taskId)}`);
  if (executionId) links.execution = qdashWebUrl(client, executionPagePath(executionId, chipId));
  if (postId) links.forum_post = qdashWebUrl(client, forumPostPagePath(postId));
  if (scriptId) links.metric_script = qdashWebUrl(client, metricScriptPagePath(scriptId));
  if (dashboardId) links.dashboard = qdashWebUrl(client, dashboardPagePath(dashboardId));
  if (sessionId) links.agent_session = qdashWebUrl(client, `/agent-sessions/${encodeURIComponent(sessionId)}`);
  return links;
}

export function withQDashLinks(client: QDashConnection, data: unknown): unknown {
  if (!data || typeof data !== "object" || Array.isArray(data)) return data;
  const object = data as Record<string, unknown>;
  const links = qdashObjectLinks(client, object);
  if (Object.keys(links).length === 0) return data;
  return { ...object, _links: links };
}

export function safeConfig(client: QDashConnection, source: string) {
  const config = client.config;
  return {
    source,
    baseUrl: config.baseUrl,
    projectId: config.projectId ?? null,
    timeoutSeconds: config.timeoutSec,
    verifyTls: config.verifyTls,
    proxyConfigured: Boolean(config.proxy),
    apiTokenConfigured: Boolean(config.apiToken),
    cloudflareAccessConfigured: Boolean(config.cfAccessClientId || config.cfAccessClientSecret),
    // Null when the SDK's own user agent is sent.
    userAgent: config.userAgent ?? null,
    readAttempts: config.readAttempts,
  };
}
