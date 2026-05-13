/**
 * Shared SSE (Server-Sent Events) utilities used by copilot chat and issue AI reply.
 */

import { buildAuthHeaders } from "@/lib/auth/session";

/**
 * Build request headers including auth tokens and project context.
 */
export function buildHeaders(): Record<string, string> {
  return buildAuthHeaders();
}

interface SSEEvent {
  event: string;
  data: string;
}

/**
 * Parse complete SSE event blocks from a text buffer.
 * Returns parsed events and the unprocessed remainder.
 */
export function consumeSSEEvents(text: string): {
  events: SSEEvent[];
  remainder: string;
} {
  const events: SSEEvent[] = [];
  const lastDoubleNewline = text.lastIndexOf("\n\n");
  if (lastDoubleNewline === -1) {
    return { events, remainder: text };
  }

  const completePart = text.slice(0, lastDoubleNewline);
  const remainder = text.slice(lastDoubleNewline + 2);

  const blocks = completePart.split("\n\n");
  for (const block of blocks) {
    if (!block.trim()) continue;
    let event = "";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) {
        event = line.slice(7);
      } else if (line.startsWith("data: ")) {
        dataLines.push(line.slice(6));
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5));
      }
    }
    const data = dataLines.join("\n");
    if (event && data) {
      events.push({ event, data });
    }
  }
  return { events, remainder };
}
