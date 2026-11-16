/**
 * Steering a running chat and continuing a stopped one.
 *
 * A user may send a message while an answer is still being written. It is not
 * a second turn: the runtime submits it to the conversation the running turn
 * already has open (`ActiveChat`), as a steer the harness places after the
 * current tool round, so the model reads it before it decides on more tools.
 * Only that open harness writes the session's store; a steer never opens a
 * second one, and the turn keeps the QDash credentials it was opened with.
 *
 * A steer is placed as a `qdash.steer` entry (`STEER_ENTRY`) carrying its
 * request ID, so where it landed in the durable transcript is known exactly:
 * the chat stream reports it at that position (see view-events.ts), and the
 * same request ID submitted again finds the same submission.
 *
 * Continue starts a run on the conversation as it is, without a user message,
 * after a run that ended without an answer (stopped, or a model error). It is
 * refused while a question, an approval, or a proposed edit waits for the
 * user: those are answered, not continued.
 */

import { existsSync } from "node:fs";

import type { Context } from "@earendil-works/chord/context";
import {
  ConversationIdle,
  ROOT_CONVERSATION_ID,
  defineEntry,
  LiveDoc,
  ToolResultEntry,
  UserEntry,
  type Conversation,
  type ConversationId,
  type EntryId,
  type EntryRecord,
  type Harness,
  type RunFailureReason,
  type SettledSubmissionRecord,
  type Submission,
  type SubmissionId,
  type SubmissionRecord,
  type UserInput,
} from "@earendil-works/pi-durable";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";

/**
 * How the chat's harness handles queued messages. Every steer queued during a
 * tool round is placed at its end, in the order sent, not one per round. A
 * steer still queued when its run fails or is stopped settles unanswered, and
 * the chat says it was not delivered, instead of being kept to surface in
 * front of whatever the user sends next.
 *
 * That covers a run that ends while the runtime is up. A runtime that dies
 * mid-run (killed, out of memory) settles nothing: the steer stays queued in
 * the store, and the next request that opens the conversation recovers the
 * interrupted run, which places the steer and answers it before that request's
 * own input. The chat stream reports such a steer as `before_turn`.
 */
export const CHAT_QUEUE_SETTINGS = { steeringMode: "all", afterFailedRun: "withdraw" } as const;

/** Entry kind of a user's steer: its model message is the user message, its data the request ID. */
export const STEER_KIND = "qdash.steer";
export const STEER_ENTRY = defineEntry<{ requestId: string }>(STEER_KIND);

/**
 * The durable request key of a steer: its request ID within the QDash project
 * the steer was sent from. A retry from the same project finds the same
 * submission; the same request ID from another project names another request,
 * and is never admitted twice. The prefix keeps a steer apart from a turn's
 * own request IDs.
 */
export function steerKey(projectId: string | undefined, requestId: string): string {
  return `steer:${projectId ?? ""}:${requestId}`;
}

/** Tools whose result waits for the user: answered by the next message, never continued past. */
export const USER_WAIT_TOOLS: ReadonlySet<string> = new Set(["ask_user", "propose_code_edit"]);

/** A message the user wrote: a turn's input or a steer. */
export function isUserMessage(entry: EntryRecord | undefined): boolean {
  return UserEntry.is(entry) || STEER_ENTRY.is(entry);
}

/** The request ID of a steer entry, or undefined for any other entry. */
export function steerRequestId(entry: EntryRecord | undefined): string | undefined {
  if (!STEER_ENTRY.is(entry)) return undefined;
  const requestId = (entry.data as { requestId?: unknown } | undefined)?.requestId;
  return typeof requestId === "string" ? requestId : undefined;
}

/** What a steer request learned: where the steer stands, or why it was refused. */
export type SteerOutcome =
  | {
      /** Admitted, waiting for the end of the current tool round. */
      status: "queued";
      submissionId: SubmissionId;
    }
  | {
      /** Placed in the transcript as `entryId`; the model reads it. */
      status: "applied";
      submissionId: SubmissionId;
      entryId: EntryId;
    }
  | {
      /** Settled without being placed: the run failed or was stopped first. */
      status: "withdrawn";
      submissionId: SubmissionId;
      reason: string;
    }
  | {
      /**
       * The durable store has no steer with this request ID from this project:
       * it was never admitted, and the runtime will not admit it any more.
       */
      status: "not_found";
    }
  | {
      /** Nothing is running to steer: the answer finished first. Send it as a new message. */
      status: "rejected";
      reason: "idle";
    };

/** Where one steer's submission stands. */
export function steerOutcomeOf(record: SubmissionRecord): SteerOutcome {
  if (record.type === "input" && record.entry !== undefined) {
    return { status: "applied", submissionId: record.id, entryId: record.entry };
  }
  if (record.status === "unanswered") {
    return { status: "withdrawn", submissionId: record.id, reason: record.reason };
  }
  return { status: "queued", submissionId: record.id };
}

/**
 * The chat turn running for one owner and conversation: the harness its
 * request opened and the steers it accepted.
 *
 * The turn's request owns the harness; steers arrive on other requests and use
 * it through `steer()` only while the turn still accepts them. The turn stops
 * accepting once nothing runs (see `settleChat`), before it closes the harness,
 * so a late steer is refused instead of reaching a closed store.
 */
/**
 * Which chat a turn runs: the QDash session and the durable conversation of
 * its store (`root`, or a branch's ID). Every conversation of one store shares
 * the turn's open harness, so a steer or a stop must name this exact one.
 */
export interface ChatTarget {
  sessionId: string;
  conversation: string;
}

export class ActiveChat {
  #open: { harness: Pick<Harness, "submission">; conversation: Conversation } | undefined;
  #ready: Promise<boolean>;
  #settleReady!: (ready: boolean) => void;
  #accepting = true;
  readonly #inflight = new Set<Promise<unknown>>();
  /** Steers accepted, by request ID, in the order they were first admitted. */
  readonly steers = new Map<string, SubmissionId>();
  /** The runtime's own steers (the wrap-up), awaited like the user's but never reported as theirs. */
  readonly internal: Submission[] = [];

  constructor(
    /** The QDash project the turn's credentials are scoped to; a steer must name the same one. */
    readonly projectId: string | undefined,
    private readonly context: Context,
    /** The chat the turn runs; unset, the turn matches any (one conversation per store). */
    readonly target?: ChatTarget,
  ) {
    this.#ready = new Promise((resolve) => (this.#settleReady = resolve));
  }

  /** Whether this turn runs `target`: the same QDash session and the same durable conversation. */
  runs(target: ChatTarget): boolean {
    return (
      this.target === undefined ||
      (this.target.sessionId === target.sessionId && this.target.conversation === target.conversation)
    );
  }

  /** The conversation to stop, once the turn has opened it. */
  get conversation(): Conversation | undefined {
    return this.#open?.conversation;
  }

  /** The turn's own input is admitted: steers may follow it. */
  ready(harness: Pick<Harness, "submission">, conversation: Conversation): void {
    this.#open = { harness, conversation };
    this.#settleReady(true);
  }

  /** The turn ended before its input was admitted; waiting steers are refused. */
  failed(): void {
    this.#accepting = false;
    this.#settleReady(false);
  }

  /**
   * Submit a steer to the running turn. `whenIdle: "reject"`: if the run has
   * already ended, the harness refuses it and writes nothing, so a steer never
   * starts a run of its own. A known request ID returns its submission.
   */
  steer(requestId: string, content: UserInput): Promise<SteerOutcome> {
    // Counted as in flight from the call on, so a status lookup that drains
    // after fencing the request ID sees every submit that started before it.
    const work = this.#steer(requestId, content);
    this.#inflight.add(work);
    return work.finally(() => this.#inflight.delete(work));
  }

  async #steer(requestId: string, content: UserInput): Promise<SteerOutcome> {
    if (!(await this.#ready) || !this.#accepting || !this.#open) {
      return this.#known(requestId);
    }
    const { conversation } = this.#open;
    let submission: Submission;
    try {
      submission = await conversation.submit(
        {
          type: "input",
          content,
          requestId: steerKey(this.projectId, requestId),
          whenBusy: "steer",
          whenIdle: "reject",
          entry: { kind: STEER_KIND, data: { requestId } },
        },
        this.context,
      );
    } catch (error) {
      if (error instanceof ConversationIdle) return { status: "rejected", reason: "idle" };
      throw error;
    }
    if (!this.steers.has(requestId)) this.steers.set(requestId, submission.id);
    return steerOutcomeOf(await submission.status(this.context));
  }

  /**
   * Steer the running turn on the runtime's behalf (the wrap-up instruction), as a plain user message. Undefined when
   * nothing runs any more.
   */
  async steerInternal(content: UserInput): Promise<Submission | undefined> {
    if (!(await this.#ready) || !this.#accepting || !this.#open) return undefined;
    const { conversation } = this.#open;
    const work = (async () => {
      try {
        const submission = await conversation.submit(
          { type: "input", content, whenBusy: "steer", whenIdle: "reject" },
          this.context,
        );
        this.internal.push(submission);
        return submission;
      } catch (error) {
        if (error instanceof ConversationIdle) return undefined;
        throw error;
      }
    })();
    this.#inflight.add(work);
    try {
      return await work;
    } finally {
      this.#inflight.delete(work);
    }
  }

  /** A steer this turn admitted before it stopped accepting, or a refusal. */
  async #known(requestId: string): Promise<SteerOutcome> {
    const id = this.steers.get(requestId);
    const submission = id && this.#open ? await this.#open.harness.submission(id, this.context) : undefined;
    if (!submission) return { status: "rejected", reason: "idle" };
    return steerOutcomeOf(await submission.status(this.context));
  }

  /** Steers still being submitted. */
  get inflight(): number {
    return this.#inflight.size;
  }

  /** Wait for the steers being submitted now. */
  async drain(): Promise<void> {
    await Promise.allSettled([...this.#inflight]);
  }

  /** Refuse every later steer. Synchronous, so no submit starts after a check that nothing is in flight. */
  stopAccepting(): void {
    this.#accepting = false;
  }
}

/** How a turn ended once nothing it started runs any more. */
export interface ChatSettlement {
  /**
   * The submission whose run ended last: the turn's own, or the steer placed
   * last, which a later run answered when the steer came after the answer.
   */
  final: SettledSubmissionRecord;
  /** Every steer the turn accepted, by request ID, as it ended. */
  steers: Map<string, SettledSubmissionRecord>;
}

/**
 * Wait for the turn and every run its steers started, then stop accepting steers.
 *
 * A steer placed after a tool round joins the running run and settles with its
 * answer. One that arrives after the model's last tool round is placed after
 * that answer and starts the next run, so the turn waits for that run too, and
 * for steers sent while it runs. A steer the harness withdrew (the run failed,
 * or the user stopped it) settles unanswered without an entry.
 */
export async function settleChat(
  active: ActiveChat,
  harness: Pick<Harness, "submission">,
  own: Submission,
  context: Context,
  /** Called once the turn's own submission settled, before the steers it accepted are awaited. */
  onOwnSettled?: () => Promise<void>,
): Promise<ChatSettlement> {
  const ownSettled = await own.wait(context);
  await onOwnSettled?.();
  const steers = new Map<string, SettledSubmissionRecord>();
  const internal: SettledSubmissionRecord[] = [];
  for (;;) {
    for (const [requestId, id] of active.steers) {
      if (steers.has(requestId)) continue;
      const submission = await harness.submission(id, context);
      if (submission) steers.set(requestId, await submission.wait(context));
    }
    while (internal.length < active.internal.length) {
      internal.push(await active.internal[internal.length].wait(context));
    }
    if (active.inflight > 0) {
      await active.drain();
      continue;
    }
    // No await since the checks below: no steer is between its submit and its registration.
    if (
      internal.length === active.internal.length &&
      [...active.steers.keys()].every((requestId) => steers.has(requestId))
    ) {
      active.stopAccepting();
      break;
    }
  }
  let final: SettledSubmissionRecord = ownSettled;
  let last = -1;
  for (const record of [...steers.values(), ...internal]) {
    if (record.type !== "input" || record.entry === undefined) continue;
    const at = Number(record.entry);
    if (at > last) {
      last = at;
      final = record;
    }
  }
  return { final, steers };
}

/** The submission a request ID names in this conversation, to recover a retried request before any gate. */
export async function submissionByRequest(
  harness: Pick<Harness, "submission">,
  conversation: Conversation,
  requestId: string,
  context: Context,
): Promise<{ submission: Submission; record: SubmissionRecord } | undefined> {
  const record = await conversation.commit(
    (tx) => tx.submissionByRequest(conversation.id, requestId),
    context,
  );
  if (!record) return undefined;
  const submission = await harness.submission(record.id, context);
  return submission ? { submission, record } : undefined;
}

/** How long a steer status lookup waits for the store's lock before it gives up. */
export const STEER_RECEIPT_BUSY_TIMEOUT_MS = 1000;

/**
 * Where a steer stands, read from the session's durable store without opening
 * a harness: a second SQLite connection beside the turn's writer, if one runs.
 * No harness means no recovery, no task, and no admission, so a status lookup
 * never admits a steer or starts a run.
 *
 * It is not a pure read at the SQLite level. Opening the storage checks the
 * schema version in a write transaction (`BEGIN IMMEDIATE`), which takes the
 * store's write lock and would create the schema of a store that has none, and
 * closing it checkpoints the write-ahead log. Both wait at most
 * `STEER_RECEIPT_BUSY_TIMEOUT_MS` for a writer holding the lock; past that the
 * lookup throws, and the caller reports that it could not tell, never
 * `not_found`.
 *
 * `not_found` means the store holds no steer with this request ID from
 * `projectId` in `conversationId` (or no store exists). A steer with the same
 * request ID from another project is refused as `wrong_project`. A store holds
 * the root conversation and its branches; each has its own steers.
 */
export async function readSteerReceipt(
  path: string,
  projectId: string | undefined,
  requestId: string,
  context: Context,
  conversationId: ConversationId = ROOT_CONVERSATION_ID,
): Promise<SteerOutcome | "wrong_project"> {
  if (!existsSync(path)) return { status: "not_found" };
  const storage = await openNodeSqliteStorage(path, { busyTimeoutMs: STEER_RECEIPT_BUSY_TIMEOUT_MS });
  try {
    const record = await storage.submissionByRequest(
      conversationId,
      steerKey(projectId, requestId),
      context,
    );
    if (record) return steerOutcomeOf(record);
    // Request IDs are unique per message, so one under another project's key is this steer.
    const suffix = `:${requestId}`;
    let cursor: Parameters<typeof storage.scanSubmissions>[2];
    do {
      const page = await storage.scanSubmissions(
        { conversationId, order: "descending" },
        200,
        cursor,
        context,
      );
      if (page.items.some((r) => r.requestId?.startsWith("steer:") && r.requestId.endsWith(suffix))) {
        return "wrong_project";
      }
      cursor = page.next;
    } while (cursor !== undefined);
    return { status: "not_found" };
  } finally {
    await storage.close(context);
  }
}

/** Why a run that ended without an answer may be continued. */
const CONTINUABLE: ReadonlySet<RunFailureReason> = new Set([
  "aborted",
  "model_error",
  "no_model",
  "interrupted",
  "restart_limit",
  "turn_limit",
  "faulted",
  "orphaned",
]);

/** Why the conversation cannot be continued now, or undefined when it can. */
export type ContinueBlocker = "busy" | "nothing_to_continue" | "awaiting_user";

/**
 * Whether a continue may start now: nothing runs, the newest run ended
 * without an answer for a reason a new run can get past, and no question,
 * approval, or proposed edit since the last user message waits for the user.
 */
export async function continueBlocker(
  conversation: Conversation,
  context: Context,
): Promise<ContinueBlocker | undefined> {
  const live = await conversation.commit(async (tx) => {
    const doc = await tx.doc(LiveDoc, conversation.id);
    return { busy: doc.run !== undefined, failure: doc.runFailure?.reason };
  }, context);
  if (live.busy) return "busy";
  if (live.failure === undefined || !CONTINUABLE.has(live.failure)) return "nothing_to_continue";
  const view = await conversation.context(context);
  return awaitsUser(view.entries) ? "awaiting_user" : undefined;
}

/** Whether a tool result since the last user message waits for the user. */
export function awaitsUser(entries: readonly EntryRecord[]): boolean {
  for (let i = entries.length - 1; i >= 0; i--) {
    const entry = entries[i];
    if (isUserMessage(entry)) return false;
    if (!ToolResultEntry.is(entry)) continue;
    const message = entry.model?.[0];
    if (message?.role !== "toolResult" || message.isError) continue;
    if (USER_WAIT_TOOLS.has(message.toolName)) return true;
    if ((message.details as { approval?: unknown } | undefined)?.approval) return true;
  }
  return false;
}
