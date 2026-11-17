/**
 * Stopping a chat whose work only the durable store remembers.
 *
 * A runtime that dies mid-run leaves the run in the store, and nothing in
 * memory knows it: `POST /chat/abort` finds no turn to stop. The run resumes
 * with the store's next turn, and until then every other branch of the store
 * refuses to start (see server.ts). When the chat it belongs to was deleted,
 * no turn of it ever comes, so its work is stopped from the store instead.
 *
 * `Conversation.abort()` cannot do that alone: it starts the store's
 * scheduling, which runs every runnable task of every conversation of the
 * store, also a sibling's run a crash left behind, with no turn watching it.
 * Instead, with scheduling paused, this marks the chat's own live tasks for
 * abort (`Harness.abortTask()` commits the mark and starts nothing) and
 * withdraws its queued inputs (`Harness.abortSubmission()`). A marked task
 * runs only its abort handler: the built-in generation and tool tasks then
 * record the run as aborted and the calls that did not finish as aborted
 * results, and call no model and run no tool. A task whose definition is not
 * registered (the harness opened for this has no extension) is orphaned
 * without running anything.
 *
 * Only when no other conversation of the store has work that could run does
 * this start scheduling and wait, bounded, for the marked work to end. Else
 * the marks stay in the store: the work winds down (`windsDown`) as soon as
 * the store's next turn starts scheduling, and it no longer keeps that turn
 * from starting.
 */

import type { Context } from "@earendil-works/chord/context";
import type { ConversationId, Harness } from "@earendil-works/pi-durable";

import { windsDown, workByChat } from "./branch.ts";

/**
 * What stopping did:
 * - `none`: the conversation has no unfinished work.
 * - `marked`: its work is marked and will wind down with the store's next turn
 *   (or did not end within the wait); nothing of it runs a model or a tool again.
 * - `settled`: its work ended.
 */
export type StoredStop = "none" | "marked" | "settled";

/** Stop the unfinished work of chat conversation `id` in a store opened with scheduling paused. */
export async function stopStoredConversation(
  harness: Harness,
  id: ConversationId,
  context: Context,
  settleWithinMs: number,
): Promise<StoredStop> {
  const work = (await workByChat(harness, context)).get(id);
  if (!work) return "none";
  for (const record of work.submissions) {
    if (record.status === "queued") await harness.abortSubmission(record.id, context, record.conversationId);
  }
  for (const task of work.tasks) {
    // A `restart` mark waits for its definition; an abort request replaces it.
    if (!task.record.abortRequested || task.record.abortReason !== undefined) {
      await harness.abortTask(task.record.id, context);
    }
  }
  const others = [...(await workByChat(harness, context))].filter(([chat, rest]) => chat !== id && !windsDown(rest));
  if (others.length > 0) return "marked";
  const conversation = await harness.conversation(id, context);
  if (!conversation) return "marked";
  // Nothing else can run: scheduling may start. Marks set again, withdrawals
  // repeated, background work included; then wait for the scope to be idle.
  let timer: ReturnType<typeof setTimeout> | undefined;
  const ended = await Promise.race([
    // Closing the harness ends a wait still running; that is no failure here.
    conversation.abort(context, { background: true }).then(
      () => true,
      () => false,
    ),
    new Promise<boolean>((resolve) => (timer = setTimeout(() => resolve(false), settleWithinMs))),
  ]).finally(() => clearTimeout(timer));
  return ended ? "settled" : "marked";
}
