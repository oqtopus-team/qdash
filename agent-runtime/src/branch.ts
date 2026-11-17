/**
 * Branching a chat from one of its answers.
 *
 * A branch is a Pi fork (`Conversation.fork(at)`) of the conversation the user
 * branches from, in the same SQLite store: pi-durable keeps no per-conversation
 * export, import, or delete, so a branch never gets a store of its own. QDash
 * records which store and which durable conversation a chat session uses, and
 * the runtime opens that conversation (`openBranch`) instead of the root.
 *
 * The fork copies what Pi copies: the transcript up to the selected answer, the
 * agent as of that answer (`pi.agent` with its loaded deferred tools), the Code
 * Mode store as of that answer, and fresh `pi.live`, `pi.inbox`, `pi.usage`, and
 * provider state. Files are not copied: the workspace belongs to the store, so
 * every conversation of the store sees its current files.
 *
 * Each fork records a receipt in the store's `qdash.branches` document, in the
 * fork's own commit (`init`), keyed by the QDash session the branch belongs to.
 * The same request again finds the receipt and returns the same branch; the same
 * target with another source or answer is a conflict.
 */

import type { Context } from "@earendil-works/chord/context";
import {
  AssistantEntry,
  defineDoc,
  LiveDoc,
  type Conversation,
  type ConversationId,
  type EntryId,
  type Harness,
  type SubmissionRecord,
  type TaskInspection,
} from "@earendil-works/pi-durable";

import { awaitsUser } from "./chat-control.ts";

/** One branch the runtime created: its conversation, and where it was forked from. */
export type BranchReceipt = {
  conversation: number;
  source: number;
  at: number;
};

type BranchIndex = {
  /** Receipts by the QDash session the branch belongs to. */
  targets: Record<string, BranchReceipt>;
};

/** The store's branches, written in the commit that forks each one. */
export const BRANCHES_DOC = defineDoc<BranchIndex>({
  kind: "qdash.branches",
  version: 1,
  scope: "session",
  initial: () => ({ targets: {} }),
  checkpointWhen: () => true,
});

/** Why a branch was refused. */
export type BranchRefusal =
  | "invalid_request"
  | "store_not_found"
  | "conversation_not_found"
  | "entry_not_found"
  | "not_final_answer"
  | "awaiting_user"
  | "busy"
  | "conflict";

/** The HTTP status of each refusal. */
export const BRANCH_REFUSAL_STATUS: Record<BranchRefusal, number> = {
  invalid_request: 400,
  store_not_found: 404,
  conversation_not_found: 404,
  entry_not_found: 404,
  not_final_answer: 409,
  awaiting_user: 409,
  busy: 409,
  conflict: 409,
};

export class BranchError extends Error {
  constructor(
    readonly reason: BranchRefusal,
    message: string,
  ) {
    super(message);
    this.name = "BranchError";
  }
}

/** A durable ID from its decimal wire form, or undefined when it is not one. */
export function parseDurableId<I extends ConversationId | EntryId>(value: unknown): I | undefined {
  if (typeof value !== "string" || !/^[0-9]{1,15}$/.test(value)) return undefined;
  const id = Number(value);
  return Number.isSafeInteger(id) ? (id as I) : undefined;
}

/** The receipt of the branch `target`, if this store has one. */
export async function branchReceipt(
  harness: Pick<Harness, "commit">,
  target: string,
  context: Context,
): Promise<BranchReceipt | undefined> {
  return harness.commit(async (tx) => {
    const receipt = (await tx.doc(BRANCHES_DOC)).targets[target];
    return receipt ? { conversation: receipt.conversation, source: receipt.source, at: receipt.at } : undefined;
  }, context);
}

/**
 * The branch conversation `id` of this store. Only a conversation the runtime
 * forked as a branch opens: a subagent's or any other conversation does not.
 */
export async function openBranch(harness: Harness, id: ConversationId, context: Context): Promise<Conversation> {
  const known = await harness.commit(
    async (tx) => Object.values((await tx.doc(BRANCHES_DOC)).targets).some((r) => r.conversation === id),
    context,
  );
  const conversation = known ? await harness.conversation(id, context) : undefined;
  if (!conversation) throw new BranchError("conversation_not_found", "the chat's conversation was not found");
  return conversation;
}

/** Unfinished work of one chat conversation, and of the conversations its tasks created. */
export interface ChatWork {
  tasks: TaskInspection[];
  submissions: SubmissionRecord[];
}

/**
 * Whether `work` only winds down: every live task carries an abort mark, so
 * it runs its abort handler next (which calls no model and runs no tool) or
 * is orphaned, and no input waits to be placed. A run stopped while no
 * runtime ran it (`stopStoredConversation`) is left like this until the
 * store's scheduling next starts.
 */
export function windsDown(work: ChatWork): boolean {
  return (
    work.tasks.every((task) => task.record.abortRequested) &&
    work.submissions.every((record) => record.status !== "queued")
  );
}

/**
 * The unfinished work of this store by chat conversation: queued or placed
 * submissions and live tasks, read from the durable store (so also work a
 * runtime that died left behind, which nothing in memory remembers). Work of
 * a conversation a task created counts for the chat conversation that owns it.
 *
 * Writes nothing and runs nothing; read before `harness.resume()`, while
 * scheduling is paused, it is what the store held when it was opened.
 */
export async function workByChat(
  harness: Pick<Harness, "inspect" | "commit">,
  context: Context,
): Promise<Map<ConversationId, ChatWork>> {
  const inspection = await harness.inspect(context);
  const ids = new Set<ConversationId>([
    ...inspection.submissions.map((record) => record.conversationId),
    ...inspection.tasks.map((task) => task.record.conversationId),
  ]);
  const work = new Map<ConversationId, ChatWork>();
  if (ids.size === 0) return work;
  const owners = await harness.commit(async (tx) => {
    const chats = new Map<ConversationId, ConversationId>();
    for (const id of ids) {
      let record = await tx.conversation(id);
      // A conversation a task created belongs to the task's conversation.
      for (let depth = 0; record?.owner && depth < 64; depth++) {
        record = await tx.conversation(record.owner.conversationId);
      }
      chats.set(id, record?.id ?? id);
    }
    return chats;
  }, context);
  const of = (id: ConversationId): ChatWork => {
    const chat = owners.get(id) ?? id;
    let entry = work.get(chat);
    if (!entry) work.set(chat, (entry = { tasks: [], submissions: [] }));
    return entry;
  };
  for (const task of inspection.tasks) of(task.record.conversationId).tasks.push(task);
  for (const record of inspection.submissions) of(record.conversationId).submissions.push(record);
  return work;
}

/**
 * The chat conversations of this store with unfinished work that may still
 * run a model or a tool (see `workByChat`): work that only winds down
 * (`windsDown`) is left out. `except` leaves out one chat conversation, the
 * one a request is about to recover itself.
 */
export async function unfinishedWork(
  harness: Pick<Harness, "inspect" | "commit">,
  context: Context,
  except?: ConversationId,
): Promise<ConversationId[]> {
  const work = await workByChat(harness, context);
  return [...work].filter(([id, chat]) => id !== except && !windsDown(chat)).map(([id]) => id);
}

/**
 * Fork `source` at `at` as the branch of QDash session `target`.
 *
 * Refused unless the source is idle and the store has no unfinished work in
 * any conversation (no run, also none a crash left behind, no queued input,
 * no live task) and `at` is a completed final answer visible from
 * the source: an assistant message that stopped normally, without tool calls,
 * with no question, approval, or proposed edit since the last user message.
 * Writes nothing to the source. The caller holds the store exclusively and does
 * not resume scheduling, so nothing runs while it checks and forks.
 */
export async function branchFrom(
  harness: Harness,
  source: Conversation,
  at: EntryId,
  target: string,
  context: Context,
): Promise<{ conversationId: ConversationId; created: boolean }> {
  const known = await branchReceipt(harness, target, context);
  if (known) {
    if (known.source === source.id && known.at === at) {
      return { conversationId: known.conversation as ConversationId, created: false };
    }
    throw new BranchError("conflict", "this branch already exists from another answer");
  }

  const busy = await source.commit(async (tx) => (await tx.doc(LiveDoc, source.id)).run !== undefined, context);
  // Any conversation of the store, not only the source: work a crash left in
  // another branch resumes with the store's next turn and shares its workspace.
  if (busy || (await unfinishedWork(harness, context)).length > 0) {
    throw new BranchError("busy", "the conversation is still answering or has unfinished work");
  }

  // Checked before reading the context at `at`, which throws a plain Error for an
  // entry that is not visible: any error from here on is a storage fault, not a refusal.
  const visible = await source.entries({ minEntryId: at, maxEntryId: at }, 1, undefined, context);
  if (!visible.items.some((record) => record.id === at)) {
    throw new BranchError("entry_not_found", "the answer is not part of this conversation");
  }
  const view = await source.context(context, { at });
  const entry = view.entries.at(-1);
  if (!entry || entry.id !== at) {
    throw new BranchError("entry_not_found", "the answer is not part of this conversation");
  }
  const message = AssistantEntry.is(entry) ? entry.model?.[0] : undefined;
  if (
    message?.role !== "assistant" ||
    message.stopReason !== "stop" ||
    message.content.some((block) => block.type === "toolCall")
  ) {
    throw new BranchError("not_final_answer", "only a completed final answer can be branched from");
  }
  if (awaitsUser(view.entries)) {
    throw new BranchError("awaiting_user", "this answer waits for the user's answer, approval, or decision");
  }

  const branch = await source.fork(
    at,
    {
      ownership: { kind: "ownerless" },
      // No `agent` change: the fork keeps the agent as of the answer, its loaded tools included.
      init: async (tx, id) => {
        const index = await tx.doc(BRANCHES_DOC);
        if (index.targets[target]) throw new BranchError("conflict", "this branch already exists");
        index.targets[target] = { conversation: id, source: source.id, at };
      },
    },
    context,
  );
  return { conversationId: branch.id, created: true };
}
