/**
 * Pi session events -> NDJSON lines.
 *
 * Pure functions only, so they can be tested without a running agent.
 */

export type NdjsonEvent =
  | { type: "tool_start"; name: string }
  | { type: "tool_end"; name: string; isError: boolean }
  | { type: "chart"; chart: { data: unknown[]; layout: unknown } }
  | { type: "done"; text: string }
  | { type: "error"; message: string };

/** Minimal shape of the Pi events we care about. */
type SessionEventLike = {
  type: string;
  toolName?: string;
  isError?: boolean;
  result?: { details?: { chart?: { data: unknown[]; layout: unknown } } };
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
  if (event.type === "tool_execution_start") {
    return [{ type: "tool_start", name: event.toolName ?? "unknown" }];
  }
  if (event.type === "tool_execution_end") {
    const out: NdjsonEvent[] = [];
    const durableResult = event.entry?.model?.[0];
    const chart = event.result?.details?.chart ?? chartFromDetails(durableResult?.details);
    if (chart) out.push({ type: "chart", chart });
    out.push({
      type: "tool_end",
      name: event.toolName ?? "unknown",
      isError: event.isError === true || durableResult?.isError === true,
    });
    return out;
  }
  return [];
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
