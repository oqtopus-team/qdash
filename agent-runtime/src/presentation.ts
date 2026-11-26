/**
 * The runtime-owned presentation contract: maps a chat turn's events
 * (`NdjsonEvent`) to the envelopes the API validates
 * (`qdash.agent.contracts.presentation`) and relays to the chat as SSE. An
 * envelope's `data` is the SSE payload; its `internal` is for the API's own side
 * effects and is never relayed. See docs/developer-guide/agent/chat-streaming.md.
 *
 * A request opts in with `Accept: PRESENTATION_MEDIA_TYPE`; otherwise it gets
 * the raw NDJSON events. Each subscriber of a turn (its own response, and every
 * reattached replay) maps with its own `PresentationStream`.
 */

import type { NdjsonEvent } from "./events.ts";

export const PRESENTATION_VERSION = 1;
export const PRESENTATION_MEDIA_TYPE = "application/vnd.qdash.agent-presentation+x-ndjson";
export const PRESENTATION_CONTENT_TYPE = `${PRESENTATION_MEDIA_TYPE}; version=${PRESENTATION_VERSION}`;
/** Bound on one stored `ui` block (its JSON); the runtime caps the spec itself well below it. */
export const MAX_UI_BLOCK_CHARS = 200_000;

/** The SSE events the chat reads, plus `keepalive`, which the API relays as an SSE comment. */
export type PresentationEventName =
  | "keepalive"
  | "delta"
  | "thinking"
  | "tool_draft"
  | "tool_args_delta"
  | "tool_start"
  | "status"
  | "tool_end"
  | "ui"
  | "steer"
  | "turn_start"
  | "noop"
  | "error"
  | "result";

/** An evaluation tool's record, for the API to store (`tool_end` only). */
export interface InternalEvaluationRecord {
  record: Record<string, unknown>;
  /** The result's durable entry, which names the call the same way in every stream of the turn. */
  entry_id?: string;
  /** The result belongs to an earlier turn: the API does not file it with this one. */
  before_turn?: true;
}

/** What the API uses for its own side effects; never shown. */
export interface PresentationInternal {
  evaluation_record?: InternalEvaluationRecord;
  /** The turn's final answer text (`result`, or the `error` of an empty answer). */
  answer?: string;
}

export interface PresentationEnvelope {
  v: typeof PRESENTATION_VERSION;
  event: PresentationEventName;
  data: Record<string, unknown>;
  internal?: PresentationInternal;
}

/** One block of an answer as the chat renders and stores it. */
export type PresentationBlock = Record<string, unknown> & { type: string; content: string | null };

/** Whether an `Accept` header asks for this contract (any version parameter must be ours). */
export function acceptsPresentation(accept: string | string[] | undefined): boolean {
  const value = Array.isArray(accept) ? accept.join(",") : (accept ?? "");
  return value.split(",").some((range) => {
    const [type, ...params] = range.split(";").map((part) => part.trim().toLowerCase());
    if (type !== PRESENTATION_MEDIA_TYPE) return false;
    const quality = params.find((param) => param.startsWith("q="));
    if (quality !== undefined && Number(quality.slice(2)) === 0) return false;
    const version = params.find((param) => param.startsWith("version="));
    return version === undefined || version === `version=${PRESENTATION_VERSION}`;
  });
}

/** Runtime tools whose derived label would not say what they do. */
const TOOL_LABELS: Record<string, string> = { codemode: "Code mode script", tool_search: "Search tools" };

/**
 * A tool name rendered for display. Derived rather than looked up: pi-qdash
 * ships many tools and the set changes with the package, so only the
 * runtime's own tools in `TOOL_LABELS` are looked up.
 */
export function toolLabel(name: string): string {
  if (Object.hasOwn(TOOL_LABELS, name)) return TOOL_LABELS[name];
  const derived = name.replace(/^qdash_/, "").replaceAll("_", " ");
  return derived ? derived.charAt(0).toUpperCase() + derived.slice(1).toLowerCase() : name;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * The chat block for a `ui` event (a `render_ui` result): a versioned block
 * within the size bound, else its plain-text fallback as a text block, else
 * nothing. The chat validates the spec again before rendering it.
 */
export function uiBlock(ui: unknown): PresentationBlock | undefined {
  if (!isRecord(ui)) return undefined;
  const fallback = typeof ui.fallback === "string" ? ui.fallback : "";
  const { version, spec } = ui;
  let size: number;
  try {
    size = JSON.stringify(ui).length;
  } catch {
    size = MAX_UI_BLOCK_CHARS + 1;
  }
  if (Number.isInteger(version) && isRecord(spec) && size <= MAX_UI_BLOCK_CHARS) {
    // The fallback doubles as the block's text for readers that only know text.
    return { type: "ui", content: fallback || null, chart: null, ui: { version, spec, fallback } };
  }
  console.warn("[agent-runtime] dropped a malformed ui block");
  return fallback ? { type: "text", content: fallback, chart: null } : undefined;
}

/**
 * The blocks payload of an answer segment: the visuals its tools produced, in
 * order, then the answer text, then the cards it ended on. `assessment` stays
 * null: the runtime answers in free-form text, not a structured verdict.
 */
export function blocksResult(
  text: string,
  visuals: readonly PresentationBlock[],
  interactions: readonly PresentationBlock[] = [],
): { blocks: PresentationBlock[]; assessment: null } {
  const blocks = [...visuals];
  if (text) blocks.push({ type: "text", content: text, chart: null });
  blocks.push(...interactions);
  return { blocks, assessment: null };
}

const TERMINAL = new Set<NdjsonEvent["type"]>(["done", "noop", "error"]);

type Emit = (name: PresentationEventName, data: Record<string, unknown>, internal?: PresentationInternal) => void;

/** Maps one stream's turn events to presentation envelopes; see the module comment. */
export class PresentationStream {
  /** Charts and composed UIs of the current segment, in the order their tools finished. */
  #visuals: PresentationBlock[] = [];
  /** Questions, approvals, and proposed edits the current segment ended on. */
  #interactions: PresentationBlock[] = [];
  readonly #completedTools: string[] = [];
  #ended = false;

  map(event: NdjsonEvent): PresentationEnvelope[] {
    if (this.#ended) return [];
    if (TERMINAL.has(event.type)) this.#ended = true;
    const out: PresentationEnvelope[] = [];
    const emit: Emit = (name, data, internal) => {
      const envelope: PresentationEnvelope = { v: PRESENTATION_VERSION, event: name, data };
      if (internal) envelope.internal = internal;
      out.push(envelope);
    };

    switch (event.type) {
      case "ping":
        // Keepalive from a quiet turn; the API keeps every proxy on the way from timing out.
        emit("keepalive", {});
        break;
      case "text_delta":
        emit("delta", { text: event.delta });
        break;
      case "thinking_delta":
        emit("thinking", { text: event.delta });
        break;
      case "tool_draft":
        // The model is writing a tool call; the chat shows the code as it is typed.
        emit("tool_draft", { index: event.index, id: event.id ?? null, tool: event.name, label: toolLabel(event.name) });
        break;
      case "tool_args_delta":
        emit("tool_args_delta", { index: event.index, path: event.path ?? [], delta: event.delta });
        break;
      case "tool_start": {
        const label = toolLabel(event.name);
        emit("tool_start", { id: event.id ?? null, tool: event.name, label, args: event.args ?? null });
        emit("status", { step: "tool_call", tool: event.name, message: `${label}...` });
        break;
      }
      case "tool_end":
        this.#toolEnd(event, emit);
        break;
      case "chart":
        this.#visuals.push({ type: "chart", content: null, chart: event.chart });
        break;
      case "ui": {
        // Shown as soon as its tool finishes, and kept if the user stops the turn.
        const block = uiBlock(event.ui);
        if (block) {
          this.#visuals.push(block);
          emit("ui", block);
        }
        break;
      }
      case "ask":
        this.#interactions.push({ type: "ask", content: null, chart: null, ask: event.ask });
        break;
      case "approval":
        this.#interactions.push({ type: "approval", content: null, chart: null, approval: event.approval });
        break;
      case "edit":
        // A change proposed to the editor the user has open; the chat shows a diff.
        this.#interactions.push({ type: "edit", content: null, chart: null, edit: event.edit });
        break;
      case "steer":
        if (event.status === "applied") {
          // The user's message landed here in the transcript: what streamed before it is
          // the answer so far, with the answer it follows when it came after the last tool round.
          const applied: Record<string, unknown> = {
            request_id: event.request_id,
            status: "applied",
            entry_id: event.entry_id ?? null,
            text: event.text ?? "",
            result: this.#closeSegment(event.answer ?? ""),
          };
          // A run recovered after the runtime died placed it before this turn's message.
          if (event.before_turn) applied.before_turn = true;
          emit("steer", applied);
        } else {
          // Settled without being placed: the run failed or was stopped first.
          emit("steer", { request_id: event.request_id, status: "withdrawn", reason: event.reason ?? "" });
        }
        break;
      case "turn_start":
        // This turn's own message was placed: what streamed before it was a recovered run
        // answering a steer of an earlier turn, and the chat keeps it with that turn.
        emit("turn_start", { result: this.#closeSegment(event.answer ?? "") });
        break;
      case "noop":
        // A continue found the last answer complete: nothing was asked or added.
        emit("noop", { reason: event.reason || "nothing_to_answer" });
        break;
      case "error": {
        const error: Record<string, unknown> = { detail: event.message ?? "Agent failed" };
        if (typeof event.code === "string") error.code = event.code;
        emit("error", error);
        break;
      }
      case "done": {
        const answer = event.text ?? "";
        const result = this.#closeSegment(answer);
        // No text and no block: local models do this on a malformed tool call, and a
        // silent empty reply is indistinguishable from the chat hanging.
        if (result.blocks.length === 0) {
          emit("error", { detail: "The model returned an empty response" }, { answer });
          break;
        }
        const data: Record<string, unknown> = { ...result };
        if (typeof event.entry_id === "string" && event.entry_id) data.entry_id = event.entry_id;
        emit("status", { step: "complete", message: "Done" });
        emit("result", data, { answer });
        break;
      }
    }
    return out;
  }

  #closeSegment(answer: string): { blocks: PresentationBlock[]; assessment: null } {
    const segment = blocksResult(answer, this.#visuals, this.#interactions);
    this.#visuals = [];
    this.#interactions = [];
    return segment;
  }

  #toolEnd(event: Extract<NdjsonEvent, { type: "tool_end" }>, emit: Emit): void {
    const label = toolLabel(event.name);
    this.#completedTools.push(label);
    const data: Record<string, unknown> = {
      id: event.id ?? null,
      tool: event.name,
      label,
      is_error: event.isError === true,
    };
    // Optional fields follow, each present only when it has something to show.
    // Figure paths the tool fetched; the chat renders them inline.
    if (Array.isArray(event.figures) && event.figures.length) data.figures = event.figures;

    // What an evaluation tool sent its model; the chat shows it on request. Its record
    // is split off for the API to store and never reaches the chat.
    let internal: PresentationInternal | undefined;
    if (isRecord(event.evaluation)) {
      const { record, ...shown } = event.evaluation;
      data.evaluation = shown;
      if (isRecord(record)) {
        const evaluationRecord: InternalEvaluationRecord = { record };
        if (typeof event.entry_id === "string" && event.entry_id) evaluationRecord.entry_id = event.entry_id;
        if (event.before_turn) evaluationRecord.before_turn = true;
        internal = { evaluation_record: evaluationRecord };
      }
    }

    // What the classifier decided for a `classify` call (bounded by events.ts).
    if (event.classification) data.classification = event.classification;

    // The calibration session a successful create call made, for the chat to show.
    const created = event.calibrationSession;
    if (created && !event.isError) {
      const session: Record<string, unknown> = { calibration_session_id: created.calibrationSessionId };
      if (created.chipId) session.chip_id = created.chipId;
      data.calibration_session = session;
    }

    // What a workspace tool (bash, read, write, edit) answered.
    if (typeof event.output === "string" && event.output) data.output = event.output;
    if (Number.isInteger(event.exitCode)) data.exit_code = event.exitCode;

    emit("tool_end", data, internal);
    emit("status", { step: "thinking", message: "AI is thinking...", completed_tools: [...this.#completedTools] });
  }
}

/** One envelope as a line of the presentation stream. */
export function encodeEnvelope(envelope: PresentationEnvelope): string {
  return `${JSON.stringify(envelope)}\n`;
}

/**
 * How one subscriber writes the turn's events: raw NDJSON, or this contract
 * with its own mapping state.
 */
export function streamEncoder(presentation: boolean, encodeLine: (event: NdjsonEvent) => string) {
  if (!presentation) return encodeLine;
  const stream = new PresentationStream();
  return (event: NdjsonEvent): string => stream.map(event).map(encodeEnvelope).join("");
}
