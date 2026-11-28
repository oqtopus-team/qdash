/**
 * The events of one running chat turn, kept so a dropped stream can attach again.
 *
 * A turn outlives the HTTP stream that started it: closing the browser stream
 * does not cancel durable work, so a proxy that drops a quiet connection (a
 * tool parked on an expert's answer for many minutes) leaves the turn running
 * with nobody watching. `TurnFeed` keeps every event the turn wrote, in order,
 * and hands them to each subscriber: the turn's own response first, and any
 * request that reattaches to the same turn (`reattach: true` with the turn's
 * request ID). A subscriber that attaches late gets the whole turn replayed,
 * then the live events, then the terminal event, so it sees exactly what the
 * original stream would have shown. Nothing is resubmitted: an attach only
 * reads this feed, so no tool runs and no model is asked again.
 *
 * Consecutive appends to the same text, thinking, or tool-argument block are
 * merged in the log, so the log stays about the size of the turn's transcript
 * however finely the model streamed it. Pings go to live subscribers only.
 */

import type { NdjsonEvent } from "./events.ts";

type Subscriber = (event: NdjsonEvent) => void;

/** Events that end a turn's stream. */
const TERMINAL = new Set<NdjsonEvent["type"]>(["done", "noop", "error"]);

/** `next` merged into `last` when both append to the same block, else undefined. */
function merged(last: NdjsonEvent | undefined, next: NdjsonEvent): NdjsonEvent | undefined {
  if (last === undefined) return undefined;
  if (
    (last.type === "text_delta" && next.type === "text_delta") ||
    (last.type === "thinking_delta" && next.type === "thinking_delta")
  ) {
    return { type: last.type, delta: last.delta + next.delta };
  }
  if (
    last.type === "tool_args_delta" &&
    next.type === "tool_args_delta" &&
    last.index === next.index &&
    JSON.stringify(last.path) === JSON.stringify(next.path)
  ) {
    return { ...last, delta: last.delta + next.delta };
  }
  return undefined;
}

export class TurnFeed {
  readonly #log: NdjsonEvent[] = [];
  readonly #subscribers = new Set<Subscriber>();
  #ended = false;
  #terminal = false;
  #close!: () => void;
  /** Settles once the turn wrote its last event and freed its conversation. */
  readonly closed: Promise<void> = new Promise((resolve) => (this.#close = resolve));

  /** Whether the turn wrote a terminal event (`done`, `noop`, or `error`). */
  get terminal(): boolean {
    return this.#terminal;
  }

  get ended(): boolean {
    return this.#ended;
  }

  /** The events a subscriber attaching now is replayed, merged as described above. */
  get log(): readonly NdjsonEvent[] {
    return this.#log;
  }

  /** Record `event` and pass it to every subscriber; a ping is passed on only. */
  write(event: NdjsonEvent): void {
    if (this.#ended) return;
    if (event.type !== "ping") {
      const last = this.#log.at(-1);
      const both = merged(last, event);
      if (both !== undefined) this.#log[this.#log.length - 1] = both;
      else this.#log.push({ ...event });
      if (TERMINAL.has(event.type)) this.#terminal = true;
    }
    for (const subscriber of [...this.#subscribers]) {
      try {
        subscriber(event);
      } catch (error) {
        // One broken subscriber must not keep the event from the others.
        console.warn("[agent-runtime] turn feed subscriber failed:", error);
        this.#subscribers.delete(subscriber);
      }
    }
  }

  /**
   * Replay the turn so far to `subscriber`, then pass it every later event
   * until the turn ends or the returned function detaches it.
   */
  subscribe(subscriber: Subscriber): () => void {
    for (const event of this.#log) subscriber(event);
    if (this.#ended) return () => undefined;
    this.#subscribers.add(subscriber);
    return () => this.#subscribers.delete(subscriber);
  }

  /** The turn is over: no event follows, and `closed` settles. */
  end(): void {
    if (this.#ended) return;
    this.#ended = true;
    this.#subscribers.clear();
    this.#close();
  }
}
