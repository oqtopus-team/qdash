/**
 * Conversation view revisions -> the session events `toNdjsonEvents()` maps.
 *
 * pi-durable 1.5 removed `watchEvents()`: a client now watches the conversation
 * view (`Conversation.watch()`) and renders state. The chat stream keeps its
 * NDJSON protocol, so this translator diffs successive view revisions into the
 * events the stream already understands: text, thinking and tool-call argument
 * appends of the answer being written, and the start and end of each tool call.
 *
 * The watch folds the revisions that arrive while its listener runs, so a
 * revision may skip states. The translator therefore works from what a later
 * revision still shows: an answer's tail that no partial showed is taken from
 * its entry, and a tool call that started and finished between two revisions
 * is started and ended from its result entry.
 *
 * A revision's `entries` are only a window (the newest 50 to 100 by default).
 * When the window has moved past the newest entry the stream accounted for,
 * `gap()` names the committed entries in between; the caller reads them with
 * `Conversation.entries()` and hands them to `advance()`, so every entry is
 * translated once, in order, and history before the stream is never replayed.
 *
 * `ViewEventTranslator` is pure apart from its own state, so it can be tested
 * without a running agent. `ViewEventStream` feeds it from a watch, one
 * revision at a time, and drains the final state when the turn settles.
 */

import type { Context, WatchHandle } from "@earendil-works/chord";
import type {
  Conversation,
  ConversationView,
  Cursor,
  EntryId,
  EntryRecord,
  LiveState,
} from "@earendil-works/pi-durable";

import type { SessionEventLike } from "./events.ts";

type Block = { type?: unknown; [key: string]: unknown };
type MessageChange = NonNullable<SessionEventLike["changes"]>[number];

/** What has been streamed of one content block of the answer being written. */
type Streamed =
  | { type: "text"; text: string }
  | { type: "thinking"; text: string }
  | { type: "toolCall"; args: Map<string, string> };

/** Revision of the view a translator reads; only these fields are used. */
export type ViewRevision = Pick<ConversationView, "entries" | "docs" | "before">;

/** Committed entries a revision's window no longer shows: IDs after `after`, through `through`. */
export type EntryGap = { after: number; through: EntryId };

function liveOf(view: ViewRevision): LiveState {
  return (view.docs["pi.live"] ?? {}) as LiveState;
}

/** The newest entry a revision accounts for: its window's last, or the entry before an empty window. */
function newestEntryId(view: ViewRevision): number {
  const last = view.entries.at(-1);
  if (last) return Number(last.id);
  return view.before === undefined ? 0 : Number(view.before);
}

function blocksOf(message: unknown): Block[] {
  const content = (message as { content?: unknown } | undefined)?.content;
  return Array.isArray(content) ? (content as Block[]) : [];
}

/** Every string leaf of a tool call's arguments, keyed by its JSON path. */
function stringLeaves(
  value: unknown,
  path: Array<string | number> = [],
  out: Array<[Array<string | number>, string]> = [],
): Array<[Array<string | number>, string]> {
  if (typeof value === "string") {
    out.push([path, value]);
  } else if (Array.isArray(value)) {
    value.forEach((item, index) => stringLeaves(item, [...path, index], out));
  } else if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) stringLeaves(item, [...path, key], out);
  }
  return out;
}

export class ViewEventTranslator {
  /** Newest entry the stream has accounted for; earlier entries are history. */
  #lastEntryId: number;

  get lastEntryId(): number {
    return this.#lastEntryId;
  }
  /** Generation task and attempt whose answer `#streamed` describes. */
  #messageKey: string | undefined;
  /** Answers (generation task and attempt) whose entry was already consumed. */
  readonly #consumed = new Set<string>();
  #streamed = new Map<number, Streamed>();
  readonly #started = new Set<string>();
  readonly #ended = new Set<string>();
  /** Arguments of each tool call the model made, by call ID, for `tool_start`. */
  readonly #callArgs = new Map<string, unknown>();
  /** Calls of the current run's tool rounds that have not ended, with their tool names. */
  readonly #open = new Map<string, string>();

  /** Start from the watch's first value: everything in it is history. */
  constructor(initial: ViewRevision) {
    this.#lastEntryId = newestEntryId(initial);
    const live = liveOf(initial);
    // A run already in progress (a retried request) continues from here.
    for (const slot of live.tools ?? []) {
      if (slot.status !== "pending") this.#started.add(slot.callId);
      if (slot.status === "done" && slot.entry !== undefined) this.#ended.add(slot.callId);
      else this.#open.set(slot.callId, slot.name);
    }
    for (const entry of initial.entries) this.#recordCalls(entry.model?.[0]);
    const partial = live.generation?.message;
    if (partial !== undefined && live.run !== undefined) {
      this.#messageKey = `${live.run.taskId}/${live.generation?.attempt ?? 0}`;
      this.#diffMessage(partial);
    }
  }

  /** Committed entries between the stream and `view`'s window, which `advance()` needs as `missing`. */
  gap(view: ViewRevision): EntryGap | undefined {
    if (view.before === undefined || Number(view.before) <= this.#lastEntryId) return undefined;
    return { after: this.#lastEntryId, through: view.before };
  }

  /**
   * The events between the previous revision and `view`, in stream order. `missing` holds the entries `gap(view)`
   * named, in ID order; without them, entries the window dropped are lost.
   */
  advance(view: ViewRevision, missing: readonly EntryRecord[] = []): SessionEventLike[] {
    const events: SessionEventLike[] = [];
    const live = liveOf(view);
    const appended = [...missing, ...view.entries].filter((entry) => {
      const id = Number(entry.id);
      if (id <= this.#lastEntryId) return false;
      this.#lastEntryId = id;
      return true;
    });

    // Entries first: they finish the answer that was streaming and end tools.
    for (const entry of appended) events.push(...this.#entryEvents(entry));

    // The answer being written.
    const partial = live.generation?.message;
    if (partial !== undefined && live.run !== undefined) {
      const key = `${live.run.taskId}/${live.generation?.attempt ?? 0}`;
      if (!this.#consumed.has(key)) {
        if (key !== this.#messageKey) {
          this.#messageKey = key;
          this.#streamed = new Map();
        }
        const changes = this.#diffMessage(partial);
        if (changes.length > 0) events.push({ type: "message_update", changes });
      }
    }

    // Tool calls that started; ends come with their result entries.
    const slots = live.tools ?? [];
    for (const slot of slots) {
      if (slot.status === "pending" || this.#started.has(slot.callId)) continue;
      events.push(this.#start(slot.name, slot.callId));
    }
    for (const slot of slots) {
      if (!this.#ended.has(slot.callId)) this.#open.set(slot.callId, slot.name);
      // A call that finished without a result entry: its tool task faulted or was orphaned.
      if (slot.status === "done" && slot.entry === undefined) events.push(...this.#failed(slot.callId, slot.name));
    }
    // A call whose slot left with its round or run without a result entry, seen or not: a
    // result entry is committed before its slot leaves, so every result is accounted for here.
    const current = new Set(slots.map((slot) => slot.callId));
    for (const [id, name] of [...this.#open]) {
      if (!current.has(id)) events.push(...this.#failed(id, name));
    }
    return events;
  }

  #entryEvents(entry: EntryRecord): SessionEventLike[] {
    const message = entry.model?.[0] as
      | { role?: unknown; toolCallId?: unknown; toolName?: unknown; isError?: unknown }
      | undefined;
    if (message?.role === "assistant") {
      this.#recordCalls(message);
      // Only a tool-calling answer starts a tool round; its slots arrive in the same commit.
      if ((message as { stopReason?: unknown }).stopReason === "toolUse") {
        for (const block of blocksOf(message)) {
          if (block.type === "toolCall" && typeof block.id === "string" && !this.#ended.has(block.id)) {
            this.#open.set(block.id, typeof block.name === "string" ? block.name : "unknown");
          }
        }
      }
      const taskId = entry.byTaskId === undefined ? undefined : String(entry.byTaskId);
      const key = this.#messageKey;
      const streamingThis = key !== undefined && taskId !== undefined && key.startsWith(`${taskId}/`);
      if (!streamingThis) this.#streamed = new Map();
      // An attempt that failed or was aborted keeps what it showed; its retry streams anew.
      const stop = (message as { stopReason?: unknown }).stopReason;
      const changes = stop === "error" || stop === "aborted" ? [] : this.#diffMessage(message);
      if (streamingThis) this.#consumed.add(key);
      this.#streamed = new Map();
      this.#messageKey = undefined;
      return changes.length > 0 ? [{ type: "message_update", changes }] : [];
    }
    if (message?.role === "toolResult" && typeof message.toolCallId === "string") {
      const id = message.toolCallId;
      if (this.#ended.has(id)) return [];
      const name = typeof message.toolName === "string" ? message.toolName : "unknown";
      const out: SessionEventLike[] = [];
      if (!this.#started.has(id)) out.push(this.#start(name, id));
      this.#ended.add(id);
      this.#open.delete(id);
      out.push({
        type: "tool_execution_end",
        toolName: name,
        toolCallId: id,
        isError: message.isError === true,
        entry: entry as SessionEventLike["entry"],
      });
      return out;
    }
    return [];
  }

  #recordCalls(message: unknown): void {
    if ((message as { role?: unknown } | undefined)?.role !== "assistant") return;
    for (const block of blocksOf(message)) {
      if (block.type === "toolCall" && typeof block.id === "string") {
        this.#callArgs.set(block.id, block.arguments);
      }
    }
  }

  #start(name: string, id: string): SessionEventLike {
    this.#started.add(id);
    const args = this.#callArgs.get(id);
    return {
      type: "tool_execution_start",
      toolName: name,
      toolCallId: id,
      ...(args !== undefined ? { args } : {}),
    };
  }

  #failed(id: string, name: string): SessionEventLike[] {
    this.#open.delete(id);
    if (this.#ended.has(id)) return [];
    this.#ended.add(id);
    const out: SessionEventLike[] = [];
    if (!this.#started.has(id)) out.push(this.#start(name, id));
    out.push({ type: "tool_execution_end", toolName: name, toolCallId: id, isError: true });
    return out;
  }

  /** Appends `message` makes to what was streamed of the answer, recording them as streamed. */
  #diffMessage(message: unknown): MessageChange[] {
    const changes: MessageChange[] = [];
    blocksOf(message).forEach((block, contentIndex) => {
      const seen = this.#streamed.get(contentIndex);
      if (block.type === "text" || block.type === "thinking") {
        const field = block.type === "text" ? "text" : "thinking";
        const text = typeof block[field] === "string" ? (block[field] as string) : "";
        const before = seen?.type === block.type ? seen.text : "";
        // A block that does not extend what was streamed was replaced; keep its new text silent.
        if (text.length > before.length && text.startsWith(before)) {
          changes.push({ type: `${field}_delta`, contentIndex, delta: text.slice(before.length) });
        }
        this.#streamed.set(contentIndex, { type: block.type, text });
        return;
      }
      if (block.type === "toolCall") {
        let args = seen?.type === "toolCall" ? seen.args : undefined;
        if (!args) {
          args = new Map();
          this.#streamed.set(contentIndex, { type: "toolCall", args });
          changes.push({
            type: "toolcall_start",
            contentIndex,
            block: { name: block.name, id: block.id },
          });
        }
        for (const [path, value] of stringLeaves(block.arguments)) {
          const key = JSON.stringify(path);
          const before = args.get(key) ?? "";
          if (value.length > before.length && value.startsWith(before)) {
            changes.push({
              type: "toolcall_delta",
              contentIndex,
              path,
              delta: value.slice(before.length),
            });
          }
          args.set(key, value);
        }
      }
    });
    return changes;
  }
}

/** What `ViewEventStream` reads of the watched conversation. */
export type WatchedConversation = Pick<Conversation, "entries" | "watch">;

/** Page size for reading entries a revision's window skipped. */
const GAP_PAGE = 100;

/**
 * Feeds a conversation watch through a `ViewEventTranslator`, one revision at a time.
 *
 * Revisions are translated in the order they arrive, each after the previous one, including its gap read, so events
 * go out once and in order. `finish()` stops the watch, waits for a revision still being translated, and translates
 * an authoritative revision read after the turn settled, so commits the watch had not delivered yet still stream.
 */
export class ViewEventStream {
  readonly #translator: ViewEventTranslator;
  readonly #conversation: WatchedConversation;
  readonly #emit: (event: SessionEventLike) => void;
  readonly #context: Context;
  #queue: Promise<void> = Promise.resolve();
  #closed = false;

  constructor(
    conversation: WatchedConversation,
    initial: ViewRevision,
    emit: (event: SessionEventLike) => void,
    context: Context,
  ) {
    this.#conversation = conversation;
    this.#translator = new ViewEventTranslator(initial);
    this.#emit = emit;
    this.#context = context;
  }

  /**
   * Translate `view` after every revision before it; resolves once its events are emitted. Ignored once `finish()`
   * stopped the watch: a listener call still on its way holds a revision older than the one `finish()` reads.
   */
  push(view: ViewRevision): Promise<void> {
    if (this.#closed) return Promise.resolve();
    return this.#enqueue(view);
  }

  /**
   * Stop `watch`, the watch this stream was started from, then translate the conversation view as of now: the first
   * value of a new watch includes every commit before it, which `watch` may not have delivered yet. Call it once the
   * turn settled, so that view holds its last commit.
   */
  async finish(watch: WatchHandle<ConversationView>): Promise<void> {
    await watch.stop();
    this.#closed = true;
    // `stop()` does not wait for a listener call already running; its revision is in the queue.
    await this.#queue;
    const from = (this.#translator.lastEntryId + 1) as EntryId;
    const now = await this.#conversation.watch(this.#context, { from });
    let view: ViewRevision;
    try {
      view = now.value;
    } finally {
      await now.stop();
    }
    await this.#enqueue(view);
  }

  #enqueue(view: ViewRevision): Promise<void> {
    const next = this.#queue.then(() => this.#translate(view));
    // A failed revision is reported to its caller; the next one still runs.
    this.#queue = next.catch(() => undefined);
    return next;
  }

  async #translate(view: ViewRevision): Promise<void> {
    const gap = this.#translator.gap(view);
    const missing: EntryRecord[] = [];
    if (gap !== undefined) {
      let cursor: Cursor | undefined;
      do {
        const page = await this.#conversation.entries(
          { minEntryId: (gap.after + 1) as EntryId, maxEntryId: gap.through, order: "ascending" },
          GAP_PAGE,
          cursor,
          this.#context,
        );
        missing.push(...page.items);
        cursor = page.next;
      } while (cursor !== undefined);
    }
    for (const event of this.#translator.advance(view, missing)) this.#emit(event);
  }
}
