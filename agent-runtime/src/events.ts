/**
 * Pi session events -> NDJSON lines.
 *
 * Pure functions only, so they can be tested without a running agent.
 */

export type NdjsonEvent =
  | { type: "tool_start"; name: string; id?: string; args?: unknown }
  | {
      type: "tool_end";
      name: string;
      isError: boolean;
      id?: string;
      /** QDash figure paths the tool fetched, for the chat to show inline. */
      figures?: string[];
    }
  | { type: "text_delta"; delta: string }
  | { type: "thinking_delta"; delta: string }
  | { type: "chart"; chart: { data: unknown[]; layout: unknown } }
  | { type: "ask"; ask: unknown }
  | { type: "approval"; approval: unknown }
  | { type: "done"; text: string }
  | { type: "error"; message: string }
  /** Keepalive while a turn is quiet (long tool calls); carries no content. */
  | { type: "ping" };

/** Minimal shape of the Pi events we care about. */
type SessionEventLike = {
  type: string;
  toolName?: string;
  toolCallId?: string;
  args?: unknown;
  isError?: boolean;
  changes?: ReadonlyArray<{ type: string; delta?: string }>;
  result?: { details?: Record<string, unknown> & { chart?: { data: unknown[]; layout: unknown } } };
  entry?: {
    model?: ReadonlyArray<{
      role?: string;
      isError?: boolean;
      details?: unknown;
    }>;
  };
};

/**
 * Map one Pi session event to zero or more NDJSON events.
 *
 * `done` and `error` are built by the server after `prompt()` settles, not here.
 */
export function toNdjsonEvents(event: SessionEventLike): NdjsonEvent[] {
  if (event.type === "message_update") {
    // Text and thinking appends drive the live answer in the chat UI. Tool-call
    // argument deltas are skipped: the complete args arrive with tool_start.
    const out: NdjsonEvent[] = [];
    for (const change of event.changes ?? []) {
      if (!change.delta) continue;
      if (change.type === "text_delta") out.push({ type: "text_delta", delta: change.delta });
      if (change.type === "thinking_delta") {
        out.push({ type: "thinking_delta", delta: change.delta });
      }
    }
    return out;
  }
  if (event.type === "tool_execution_start") {
    return [
      {
        type: "tool_start",
        name: event.toolName ?? "unknown",
        ...(event.toolCallId ? { id: event.toolCallId } : {}),
        ...(event.args !== undefined ? { args: event.args } : {}),
      },
    ];
  }
  if (event.type === "tool_execution_end") {
    const out: NdjsonEvent[] = [];
    const durableResult = event.entry?.model?.[0];
    const chart = event.result?.details?.chart ?? chartFromDetails(durableResult?.details);
    if (chart) out.push({ type: "chart", chart });
    // Interactive requests end the turn; the UI renders them as cards.
    const details = (event.result?.details ?? durableResult?.details) as
      | Record<string, unknown>
      | undefined;
    if (details && typeof details === "object") {
      if (details.ask) out.push({ type: "ask", ask: details.ask });
      if (details.approval) out.push({ type: "approval", approval: details.approval });
    }
    const figures = figuresFromDetails(details);
    out.push({
      type: "tool_end",
      name: event.toolName ?? "unknown",
      ...(figures.length ? { figures } : {}),
      isError: event.isError === true || durableResult?.isError === true,
      ...(event.toolCallId ? { id: event.toolCallId } : {}),
    });
    return out;
  }
  return [];
}

/**
 * Figure paths in a pi-qdash figure tool's details: the figure it rendered
 * (`path` with an image media type) and the task's other figures
 * (`figurePaths`). Paths only; the chat fetches them through the QDash API.
 */
function figuresFromDetails(details: Record<string, unknown> | undefined): string[] {
  if (!details) return [];
  const out: string[] = [];
  const mediaType = typeof details.mediaType === "string" ? details.mediaType : "";
  if (typeof details.path === "string" && details.path && mediaType.startsWith("image/")) {
    out.push(details.path);
  }
  if (Array.isArray(details.figurePaths)) {
    for (const path of details.figurePaths) {
      if (typeof path === "string" && path && !out.includes(path)) out.push(path);
    }
  }
  return out;
}

function chartFromDetails(details: unknown): { data: unknown[]; layout: unknown } | undefined {
  if (!details || typeof details !== "object" || !("chart" in details)) return undefined;
  const chart = details.chart;
  if (!chart || typeof chart !== "object" || !("data" in chart) || !("layout" in chart)) {
    return undefined;
  }
  return chart as { data: unknown[]; layout: unknown };
}

export function encodeLine(event: NdjsonEvent): string {
  return `${JSON.stringify(event)}\n`;
}
