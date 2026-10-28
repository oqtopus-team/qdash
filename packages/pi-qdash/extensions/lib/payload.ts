function shortId(value: string, length = 10): string {
  if (value.length <= length) return value;
  return `${value.slice(0, length)}…`;
}

export function arrayFromPayload(payload: unknown): unknown[] {
  if (Array.isArray(payload)) return payload;
  if (payload && typeof payload === "object") {
    const object = payload as Record<string, unknown>;
    for (const key of ["items", "results", "data", "issues", "executions", "chips", "tasks", "insights"]) {
      if (Array.isArray(object[key])) return object[key];
    }
  }
  return [];
}

export function compactItems(payload: unknown, keys: string[], limit: number): Record<string, unknown>[] {
  return arrayFromPayload(payload).slice(0, limit).map((item) => {
    if (!item || typeof item !== "object") return { value: item };
    const object = item as Record<string, unknown>;
    return Object.fromEntries(keys.filter((key) => key in object).map((key) => [key, object[key]]));
  });
}

export function payloadTotal(payload: unknown): number {
  const fallback = arrayFromPayload(payload).length;
  if (!payload || typeof payload !== "object") return fallback;
  const object = payload as Record<string, unknown>;
  for (const key of ["total", "total_count", "count", "total_items"]) {
    const value = object[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return fallback;
}

export function firstString(object: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = object[key];
    if (typeof value === "string" && value.length > 0) return value;
    if (typeof value === "number" && Number.isFinite(value)) return String(value);
  }
  return undefined;
}

export function firstNumber(object: Record<string, unknown>, keys: string[]): number | undefined {
  for (const key of keys) {
    const value = object[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return undefined;
}

export function statusIcon(status: string | undefined): string {
  const normalized = status?.toLowerCase() ?? "";
  if (["completed", "success", "succeeded", "active", "applied"].includes(normalized)) return "✓";
  if (["failed", "error", "crashed"].includes(normalized)) return "✗";
  if (["running", "pending", "queued", "in_progress"].includes(normalized)) return "…";
  if (["cancelled", "canceled"].includes(normalized)) return "-";
  return "•";
}

export function formatItem(item: Record<string, unknown>, fallbackId: string): string {
  const id = firstString(item, ["issue_id", "execution_id", "flow_run_id", "task_id", "id"]) ?? fallbackId;
  const title = firstString(item, ["title", "task_name", "flow_name", "name"]);
  const status = firstString(item, ["status", "execution_status", "activity_status"]);
  const target = firstString(item, ["qid", "coupling_id"]);
  return [statusIcon(status), shortId(id, 14), title, target ? `(${target})` : undefined, status ? `[${status}]` : undefined]
    .filter(Boolean)
    .join(" ");
}
