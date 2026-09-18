/**
 * Pi session events -> NDJSON lines.
 *
 * Pure functions only, so they can be tested without a running agent.
 * See .agent/sessions/2026-09-18-copilot-pi-agent-runtime/adr/0005-*.md
 */

export type NdjsonEvent =
  | { type: "tool_start"; name: string }
  | { type: "tool_end"; name: string; isError: boolean }
  | { type: "chart"; chart: { data: unknown[]; layout: unknown } }
  | { type: "done"; text: string; messages: unknown[] }
  | { type: "error"; message: string };

/** Minimal shape of the Pi events we care about. */
type SessionEventLike = {
  type: string;
  toolName?: string;
  isError?: boolean;
  result?: { details?: { chart?: { data: unknown[]; layout: unknown } } };
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
    const chart = event.result?.details?.chart;
    if (chart) out.push({ type: "chart", chart });
    out.push({
      type: "tool_end",
      name: event.toolName ?? "unknown",
      isError: event.isError === true,
    });
    return out;
  }
  return [];
}

export function encodeLine(event: NdjsonEvent): string {
  return `${JSON.stringify(event)}\n`;
}
