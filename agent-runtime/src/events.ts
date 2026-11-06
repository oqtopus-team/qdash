/**
 * Pi session events -> NDJSON lines.
 *
 * Pure functions only, so they can be tested without a running agent.
 */

import { recordFromDetails, type EvaluateResult } from "./evaluate.ts";

export type NdjsonEvent =
  | { type: "tool_start"; name: string; id?: string; args?: unknown }
  | {
      type: "tool_end";
      name: string;
      isError: boolean;
      id?: string;
      /** QDash figure paths the tool fetched, for the chat to show inline. */
      figures?: string[];
      /** What an evaluation tool sent its model, for the chat to show on request. */
      evaluation?: EvaluationSummary;
      /** What a workspace tool printed or answered, for the chat to show under the step; bounded. */
      output?: string;
      /** A command's exit status (`bash`). */
      exitCode?: number;
    }
  | { type: "text_delta"; delta: string }
  | { type: "thinking_delta"; delta: string }
  /** The model started writing a tool call; its arguments follow as `tool_args_delta` until `tool_start`. */
  | { type: "tool_draft"; name: string; index: number; id?: string }
  /** Text appended to one argument (`path`, such as `["content"]`) of the call being written. */
  | { type: "tool_args_delta"; index: number; path: Array<string | number>; delta: string }
  | { type: "chart"; chart: { data: unknown[]; layout: unknown } }
  | { type: "ask"; ask: unknown }
  | { type: "approval"; approval: unknown }
  /** A change the model proposes to the editor the user has open (propose_code_edit). */
  | { type: "edit"; edit: unknown }
  | { type: "done"; text: string }
  | { type: "error"; message: string }
  /** Keepalive while a turn is quiet (long tool calls); carries no content. */
  | { type: "ping" };

/**
 * Suffix for an unanswered submission's `detail`, which carries the provider's
 * error text (HTTP status and body) behind reasons such as `model_error`.
 */
export function formatSettledDetail(detail: unknown): string {
  if (detail === undefined || detail === null || detail === "") return "";
  return `: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`;
}

/**
 * What an evaluation tool (`qcal_evaluate`) sent its model: the exact prompt,
 * so the user can see which reference and context the verdict rests on, and
 * the model that judged.
 */
export interface EvaluationSummary {
  prompt: string;
  /** `provider/modelId` of the judging model. */
  model?: string;
  /** True when no calibration VLM was configured and the conversation's model judged. */
  fallback?: boolean;
  /**
   * The evaluation as a record (what the model saw and answered, the task the
   * figures came from), when the durable wrapper stamped the result. The API
   * stores it as a chat-triggered evaluation.
   */
  record?: EvaluateResult;
}

/** Minimal shape of the Pi events we care about. */
type SessionEventLike = {
  type: string;
  toolName?: string;
  toolCallId?: string;
  args?: unknown;
  isError?: boolean;
  changes?: ReadonlyArray<{
    type: string;
    delta?: string;
    contentIndex?: number;
    path?: readonly (string | number)[];
    block?: unknown;
  }>;
  result?: { details?: unknown; structuredOutput?: unknown };
  entry?: {
    model?: ReadonlyArray<{
      role?: string;
      isError?: boolean;
      details?: unknown;
      content?: unknown;
    }>;
  };
};

/** Tools whose answer the chat shows under the step: the workspace's. QDash tools answer the model only. */
const OUTPUT_TOOLS = new Set(["bash", "read", "write", "edit"]);
/** Longest output a tool_end line carries; the tail, as the model's own window keeps the tail. */
export const MAX_TOOL_OUTPUT_CHARS = 4000;

/**
 * What a workspace tool answered: `bash` reports `{ output, exitCode }` as its
 * structured output, `read`/`write`/`edit` their bounded text. A result the
 * harness wrote itself (blocked, interrupted) has no structured output; its
 * entry's text is shown instead.
 */
function toolOutput(event: SessionEventLike): { output?: string; exitCode?: number } {
  if (!event.toolName || !OUTPUT_TOOLS.has(event.toolName)) return {};
  const structured = event.result?.structuredOutput;
  let text: string | undefined;
  let exitCode: number | undefined;
  if (typeof structured === "string") {
    text = structured;
  } else if (structured && typeof structured === "object" && !Array.isArray(structured)) {
    const record = structured as Record<string, unknown>;
    if (typeof record.output === "string") text = record.output;
    if (typeof record.exitCode === "number") exitCode = record.exitCode;
  }
  if (text === undefined) {
    const content = event.entry?.model?.[0]?.content;
    if (Array.isArray(content)) {
      text = content
        .map((block) =>
          block && typeof block === "object" && (block as { type?: unknown }).type === "text"
            ? String((block as { text?: unknown }).text ?? "")
            : "",
        )
        .join("");
    }
  }
  text = text?.trim();
  if (text && text.length > MAX_TOOL_OUTPUT_CHARS) text = `…${text.slice(-MAX_TOOL_OUTPUT_CHARS)}`;
  return { ...(text ? { output: text } : {}), ...(exitCode !== undefined ? { exitCode } : {}) };
}

/**
 * Map one Pi session event to zero or more NDJSON events.
 *
 * `done` and `error` are built by the server after `prompt()` settles, not here.
 */
export function toNdjsonEvents(event: SessionEventLike): NdjsonEvent[] {
  if (event.type === "message_update") {
    // Text and thinking appends drive the live answer in the chat UI. A tool
    // call being written streams too, so the chat can show code as it is
    // typed; the complete, validated args still arrive with tool_start.
    const out: NdjsonEvent[] = [];
    for (const change of event.changes ?? []) {
      if (change.type === "toolcall_start") {
        const block = change.block as { name?: unknown; id?: unknown } | undefined;
        if (typeof block?.name === "string" && typeof change.contentIndex === "number") {
          out.push({
            type: "tool_draft",
            name: block.name,
            index: change.contentIndex,
            ...(typeof block.id === "string" && block.id ? { id: block.id } : {}),
          });
        }
        continue;
      }
      if (change.type === "toolcall_delta") {
        if (change.delta && typeof change.contentIndex === "number" && Array.isArray(change.path)) {
          out.push({
            type: "tool_args_delta",
            index: change.contentIndex,
            path: [...change.path],
            delta: change.delta,
          });
        }
        continue;
      }
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
    const chart = chartFromDetails(event.result?.details) ?? chartFromDetails(durableResult?.details);
    if (chart) out.push({ type: "chart", chart });
    // Interactive requests end the turn; the UI renders them as cards.
    const details = (event.result?.details ?? durableResult?.details) as
      | Record<string, unknown>
      | undefined;
    if (details && typeof details === "object") {
      if (details.ask) out.push({ type: "ask", ask: details.ask });
      if (details.approval) out.push({ type: "approval", approval: details.approval });
      if (details.edit) out.push({ type: "edit", edit: details.edit });
    }
    const figures = figuresFromDetails(details);
    const evaluation = evaluationFromDetails(details);
    out.push({
      type: "tool_end",
      name: event.toolName ?? "unknown",
      ...(figures.length ? { figures } : {}),
      ...(evaluation ? { evaluation } : {}),
      ...toolOutput(event),
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

/** The prompt and model an evaluation tool recorded in its details, when it did. */
function evaluationFromDetails(
  details: Record<string, unknown> | undefined,
): EvaluationSummary | undefined {
  if (!details || typeof details.prompt !== "string" || !details.prompt) return undefined;
  const spec = details.model as { provider?: unknown; modelId?: unknown } | undefined;
  const model =
    spec && typeof spec.provider === "string" && typeof spec.modelId === "string"
      ? `${spec.provider}/${spec.modelId}`
      : undefined;
  const host = details.host;
  const record =
    typeof host === "object" && host !== null
      ? recordFromDetails("", details, { mode: "planner" })
      : undefined;
  return {
    prompt: details.prompt,
    ...(model ? { model } : {}),
    ...(details.fallback === true ? { fallback: true } : {}),
    ...(record ? { record } : {}),
  };
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
