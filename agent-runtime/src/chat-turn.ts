/**
 * The lifecycle of one chat turn once its store is held and its durable session
 * is open: recovery of a reattached or retried turn, the turn's submission, the
 * stream of what it commits, steer and stop readiness, settlement, the turn's
 * terminal event, and the release of everything it held. The HTTP route
 * (server.ts) parses and authenticates the request, takes the store's hold,
 * opens the session, and hands the rest here with the transport it chose.
 */
import type { ImageContent, TextContent } from "@earendil-works/pi-ai";
import {
  UserEntry,
  type EntryId,
  type SettledSubmissionRecord,
  type Submission,
  type SubmissionId,
} from "@earendil-works/pi-durable";

import { unfinishedWork } from "./branch.ts";
import {
  ActiveChat,
  continueBlocker,
  readStoredTurn,
  settleChat,
  storedTurnFinal,
  steerOutcomeOf,
  submissionByRequest,
  type ContinueBlocker,
} from "./chat-control.ts";
import { WRAP_UP_MESSAGE } from "./budget.ts";
import { COMPACTION_FAILED_MESSAGE, isCompactionFailure } from "./compaction.ts";
import { decisionMessage, type ApprovalRequest } from "./durable-tools.ts";
import { formatSettledDetail, toNdjsonEvents, type NdjsonEvent, type SessionEventLike } from "./events.ts";
import { TurnFeed } from "./turn-feed.ts";
import { ViewEventStream } from "./view-events.ts";
import { answerText, pendingApproval, BACKGROUND_CONTEXT, type OpenDurableSession } from "./runtime.ts";

export interface ImageBody {
  data: string;
  mimeType: string;
}

/** Convert wire images into Pi image-content blocks. */
export function toImageContent(images: ImageBody[] | undefined) {
  return (images ?? []).map((image) => ({
    type: "image" as const,
    data: image.data,
    mimeType: image.mimeType,
  }));
}

/** The fields of a chat request the turn itself reads, as they came over the wire. */
export interface TurnRequest {
  request_id?: string;
  message?: string;
  /** Replaces `message` when the conversation is new: an opening QDash wrote in full (an investigation). */
  initial_message?: string;
  /**
   * Goes before `message` when the conversation is new: a task result's context. The runtime
   * appends the user's message itself, after expanding a `/skill:name` command it starts with.
   */
  initial_context?: string;
  /** Figures attached to this turn's message. */
  images?: ImageBody[];
  /** Figures of the opening context; attached only when the conversation is new. */
  initial_images?: ImageBody[];
  /** The user's decision on a write call the previous turn asked approval for. */
  approval?: { id?: string; approve?: boolean };
  /** Continue the conversation's last run instead of sending `message` (see ChatBody). */
  continue?: boolean;
  /** Reattach to the turn `request_id` started, submitting nothing (see ChatBody). */
  reattach?: boolean;
}

/**
 * How the turn answers its request: the route owns the transport. A refusal is
 * sent before anything streams; once the stream starts, every event goes
 * through the feed.
 */
export interface TurnResponse {
  /** Refuse the request with a JSON error reply; nothing has streamed. */
  refuse(status: number, body: Record<string, unknown>): void;
  /** Start streaming the feed's events to the client. */
  stream(feed: TurnFeed): void;
  /** End the response, unless it already ended. */
  end(): void;
}

/** The optional turn budgets and keep-alive (see server.ts); 0 turns each off. */
export interface TurnTiming {
  wrapUpMs: number;
  timeoutMs: number;
  pingMs: number;
}

/** One turn of a chat whose store the route already holds and whose session is open. */
export interface ChatTurn {
  request: TurnRequest;
  opened: OpenDurableSession;
  /** The turn's control, registered in the store's hold; steers and stops reach it there. */
  active: ActiveChat;
  /** Every event the turn writes, for its own response and any request that reattaches. */
  feed: TurnFeed;
  /** The store's SQLite file. */
  storePath: string;
  /** Free the store's hold; called once the session is closed. */
  release(): void;
  timing: TurnTiming;
  /** Expand a `/skill:name` command the user's message starts with. */
  expandSkillCommand(message: string): string;
}

/** Longest settled detail the log keeps: a provider can return a whole page. */
const LOG_DETAIL_MAX_CHARS = 2_000;

function truncateLog(text: string): string {
  return text.length <= LOG_DETAIL_MAX_CHARS ? text : `${text.slice(0, LOG_DETAIL_MAX_CHARS)} [... truncated]`;
}

/** What a refused continue tells the user. */
const CONTINUE_REFUSALS: Record<ContinueBlocker, string> = {
  busy: "The conversation is still answering.",
  nothing_to_continue: "There is nothing to continue: the last answer finished. Send a new message instead.",
  awaiting_user: "The assistant is waiting for your answer, approval, or decision on its proposal; answer it instead.",
};

/** Translate one committed durable event to the existing NDJSON bridge. */
function writeAgentEvent(event: SessionEventLike, write: (event: NdjsonEvent) => void): void {
  for (const line of toNdjsonEvents(event)) write(line);
}

/**
 * Run a turn to its end and release what it holds: the active chat, the
 * session, the store's hold, the feed, and the response, in that order.
 */
export async function runChatTurn(turn: ChatTurn, response: TurnResponse): Promise<void> {
  const { request: body, opened, active, feed } = turn;
  const continuing = body.continue === true;
  const reattach = body.reattach === true;
  const { conversation, harness } = opened;
  let settlement: Awaited<ReturnType<typeof settleChat>> | undefined;

  try {
    // The store's hold is in memory only. After a restart, a run another
    // conversation of this store left unfinished is known only to the store,
    // and `harness.resume()` below would run it beside this turn in the
    // shared workspace. Refuse until that conversation's own next request
    // recovers it; this conversation's own unfinished work recovers here.
    if ((await unfinishedWork(harness, BACKGROUND_CONTEXT, conversation.id)).length > 0) {
      response.refuse(409, {
        error:
          "Another branch of this chat has unfinished work from before the assistant restarted. Open that branch and send a message there to let it finish, then try again.",
        reason: "store_busy",
      });
      return;
    }

    let approval: ApprovalRequest | undefined;
    // A reattach decides nothing again: the turn it recovers already carried the decision.
    if (body.approval && !reattach) {
      approval = body.approval.id
        ? await pendingApproval(conversation, body.approval.id)
        : undefined;
      if (!approval) {
        response.refuse(400, {
          error: "This approval is no longer pending; ask the assistant again.",
        });
        return;
      }
    }

    // A retried continue recovers the submission it made, before the gate below
    // reads a state that submission itself has changed.
    let own: Submission | undefined;
    // The turn's own submission once its submit returned (undefined if it failed):
    // the stream tells this turn's own message from any other by it, exactly.
    let knowOwn!: (submission: Submission | undefined) => void;
    const ownKnown = new Promise<Submission | undefined>((resolve) => (knowOwn = resolve));
    // The input entry a recovered turn placed: its stream replays what followed it,
    // through `replayThrough` when a later turn follows it in the store.
    let replayFrom: EntryId | undefined;
    let replayThrough: EntryId | undefined;
    // The steers the store shows the recovered turn placed, which may have ended it.
    let storedMembers: SubmissionId[] = [];
    if (reattach) {
      // The turn ran in a runtime that is gone, or ended before this request:
      // recover its submission by request ID and submit nothing.
      const known = await submissionByRequest(harness, conversation, body.request_id!, BACKGROUND_CONTEXT);
      if (!known) {
        response.refuse(404, {
          error: "The assistant has no record of this message; it may never have arrived.",
          reason: "turn_not_found",
        });
        return;
      }
      own = known.submission;
      if (known.record.type === "input" && known.record.entry !== undefined) {
        // Only this turn is replayed: the store's submissions say where it ends. Where
        // they do not, nothing is replayed rather than another turn's events under it.
        const stored = await readStoredTurn(turn.storePath, conversation.id, known.record, BACKGROUND_CONTEXT);
        if (stored.status === "unknown") {
          response.refuse(409, {
            error: "Where this message's answer ends is not settled yet; reload the chat in a moment.",
            reason: "turn_boundary_unknown",
          });
          return;
        }
        replayFrom = stored.after;
        replayThrough = stored.through;
        storedMembers = stored.members.map((member) => member.id);
      }
    } else if (continuing) {
      const known = body.request_id
        ? await submissionByRequest(harness, conversation, body.request_id, BACKGROUND_CONTEXT)
        : undefined;
      if (known && known.record.type !== "continue") {
        response.refuse(409, { error: "request_id already names another message" });
        return;
      }
      own = known?.submission;
      if (!own) {
        const blocker = await continueBlocker(conversation, BACKGROUND_CONTEXT);
        if (blocker) {
          response.refuse(409, { error: CONTINUE_REFUSALS[blocker], reason: blocker });
          return;
        }
      }
    }

    // A dropped browser connection does not cancel durable work. A request with
    // the same request_id and `reattach` gets the turn's events again from the
    // feed (or, after the turn, from the store) instead of paying for a second
    // model turn.
    response.stream(feed);
    const write = (event: NdjsonEvent): void => feed.write(event);
    const { pingMs, wrapUpMs, timeoutMs } = turn.timing;
    const ping = pingMs > 0 ? setInterval(() => write({ type: "ping" }), pingMs) : null;

    // Stream what changes in the conversation view; its first value is history.
    const events = await conversation.watch(BACKGROUND_CONTEXT);
    if (own) knowOwn(own);
    // Where the turn's own message was placed, once its submit returned. Its
    // placement commits the entry and the submission's `entry` together, so
    // by the time the stream sees an entry, the record names it if it is ours.
    const ownEntry = async (): Promise<number | undefined> => {
      const submission = await ownKnown;
      const record = await submission?.status(BACKGROUND_CONTEXT);
      return record?.type === "input" && record.entry !== undefined ? Number(record.entry) : undefined;
    };
    // A recovered turn replays what followed its own message: the view's first
    // value then counts only the entries up to that message as history.
    const initial = replayFrom === undefined ? events.value : { entries: [], docs: {}, before: replayFrom };
    const stream = new ViewEventStream(
      conversation,
      initial,
      (event) => writeAgentEvent(event, write),
      BACKGROUND_CONTEXT,
      // A run recovered from a runtime that died with a steer queued places that
      // steer before this turn's message, which waits for the run. A continue has
      // no message of its own: a steer streamed during it lands where it shows.
      continuing
        ? undefined
        : async (entryId) => {
            const at = await ownEntry();
            return at === undefined || at > entryId;
          },
      // Where this turn's own message lands, so what a recovered run streamed
      // before it closes there. Only the entry its own submission placed: a
      // plain user message a recovered run places first (an earlier turn's
      // wrap-up) is not it.
      continuing ? undefined : async (entryId) => (await ownEntry()) === entryId,
      replayThrough === undefined ? undefined : Number(replayThrough),
    );
    // Replay at once: a turn that already ended commits nothing more to push.
    if (replayFrom !== undefined) await stream.push(events.value);
    events.start(async (call) => {
      if (call.kind !== "value") return;
      await stream.push(call.value).catch((error: unknown) => {
        console.warn("[agent-runtime] chat stream revision failed:", error);
      });
    });
    try {
      // Only now, with the conversation watched, may a run recovered from an
      // earlier request go on: every steer it places is streamed.
      harness.resume();
      // Abort also resumes scheduling: expose the conversation only after the
      // store-wide recovery guard and watch are ready. Earlier stops stay queued.
      active.opened(conversation);
      try {
        if (!own && continuing) {
          own = await conversation.submit(
            { type: "continue", ...(body.request_id ? { requestId: body.request_id } : {}) },
            BACKGROUND_CONTEXT,
          );
        } else if (!own) {
          own = await submitInput(
            body,
            conversation,
            approval,
            opened.writeTools,
            write,
            turn.expandSkillCommand,
            opened.fitInputContent,
          );
        }
      } finally {
        knowOwn(own);
      }
      // A stop that came while the input was admitted may have aborted
      // nothing yet (the run the submit started came after it): apply it now,
      // before any steer is admitted.
      if (active.stopRequested) await conversation.abort(BACKGROUND_CONTEXT);
      // Steers may follow from here: the turn's own input is admitted.
      active.ready(harness, conversation);
      // A steer is placed after the current tool round, so the model reads it
      // before deciding on more tools and answers in the same run.
      let wrapUp: Promise<Submission | undefined> | undefined;
      const wrapUpTimer =
        wrapUpMs > 0
          ? setTimeout(() => {
              wrapUp = active.steerInternal(WRAP_UP_MESSAGE);
              // Handled after the turn settles; keep the rejection from going unhandled meanwhile.
              wrapUp.catch(() => undefined);
            }, wrapUpMs)
          : null;
      const timeout =
        timeoutMs > 0
          ? setTimeout(() => void conversation.abort(BACKGROUND_CONTEXT), timeoutMs)
          : null;
      const ownSubmission = own;
      settlement = await settleChat(active, harness, ownSubmission, BACKGROUND_CONTEXT, async () => {
        // The turn answered: a wrap-up still queued would only start another run.
        await wrapUp
          ?.then((placed) => placed?.abort(BACKGROUND_CONTEXT))
          .catch((error: unknown) => console.warn("[agent-runtime] wrap-up steer failed:", error));
      }).finally(() => {
        if (wrapUpTimer) clearTimeout(wrapUpTimer);
        if (timeout) clearTimeout(timeout);
      });
      // Stream every commit of the turn, also those the watch had not delivered when it settled.
      await stream.finish(events);
      for (const [requestId, record] of settlement.steers) {
        const outcome = steerOutcomeOf(record);
        if (outcome.status === "withdrawn") {
          write({ type: "steer", request_id: requestId, status: "withdrawn", reason: outcome.reason });
        }
      }
      let settled = settlement.final;
      if (reattach && storedMembers.length > 0) {
        // A recovered turn's steers live in the store, not in this request: the one
        // placed last ended the turn, as for a live one.
        const members: SettledSubmissionRecord[] = [];
        for (const id of storedMembers) {
          const submission = await harness.submission(id, BACKGROUND_CONTEXT);
          if (submission) members.push(await submission.wait(BACKGROUND_CONTEXT));
        }
        settled = storedTurnFinal(settlement.final, members);
      }
      if (settled.status === "done" && settled.type !== "write") {
        write({
          type: "done",
          text: await answerText(conversation, settled.answer),
          entry_id: String(settled.answer),
        });
      } else if (settled.type === "continue" && settled.reason === "nothing_to_answer") {
        // Not a failure: the context ended in an answer, so nothing was asked of the model.
        write({ type: "noop", reason: "nothing_to_answer" });
      } else {
        // `detail` carries the provider's error text (HTTP status, vLLM message).
        const detail = formatSettledDetail(settled.detail);
        console.error(`[agent-runtime] chat not answered: ${settled.reason}${truncateLog(detail)}`);
        // A failed compaction says nothing the user can act on in its own words;
        // its detail stays in the log above.
        write(
          isCompactionFailure(settled.reason, settled.detail)
            ? { type: "error", code: "compaction_failed", message: COMPACTION_FAILED_MESSAGE }
            : { type: "error", message: `conversation was not answered: ${settled.reason}${detail}` },
        );
      }
    } catch (error) {
      write({
        type: "error",
        message: error instanceof Error ? error.message : String(error),
      });
    } finally {
      // Whatever ended the turn, no stream revision waits for its submission any more.
      knowOwn(own);
      if (ping) clearInterval(ping);
      await events.stop();
    }
  } finally {
    // Refuse steers still waiting for the turn to be ready, and every later one.
    active.failed();
    await active.drain();
    try {
      await opened.close();
    } finally {
      turn.release();
      // End the stream only once the conversation is free, so a client that
      // sends its next message as soon as the stream ends is not refused.
      feed.end();
      response.end();
    }
  }
}

/** Submit the turn's message: what the user typed, or the outcome of the write call they decided on. */
async function submitInput(
  body: TurnRequest,
  conversation: OpenDurableSession["conversation"],
  approval: ApprovalRequest | undefined,
  writeTools: OpenDurableSession["writeTools"],
  write: (event: NdjsonEvent) => void,
  expandSkillCommand: (message: string) => string,
  fitInput?: OpenDurableSession["fitInputContent"],
): Promise<Submission> {
  const view = await conversation.context(BACKGROUND_CONTEXT);
  const isNew = !view.entries.some((entry) => UserEntry.is(entry));
  const opening = isNew && body.initial_message ? body.initial_message : undefined;
  let message = opening ?? body.message ?? "";
  if (approval) {
    // The runtime, not the model, runs the call the user approved, with the
    // exact arguments the user saw. The model only learns the outcome.
    if (body.approval?.approve === true) {
      const id = `${approval.id}:approved`;
      write({
        type: "tool_start",
        name: approval.tool,
        id,
        args: approval.args,
      });
      try {
        const result = await writeTools.runApproved(approval);
        write({
          type: "tool_end",
          name: approval.tool,
          id,
          isError: false,
        });
        message = decisionMessage(approval, { approved: true, result });
      } catch (error) {
        write({ type: "tool_end", name: approval.tool, id, isError: true });
        const reason = error instanceof Error ? error.message : String(error);
        message = decisionMessage(approval, {
          approved: true,
          error: reason,
        });
      }
    } else {
      message = decisionMessage(approval, { approved: false });
    }
  } else if (opening === undefined) {
    // `/skill:name args` typed by the user runs that skill (see expandSkillCommand).
    // Expand the user's own text before any opening context goes in front of it,
    // so the command still starts the text the expansion reads.
    message = expandSkillCommand(message);
    if (isNew && body.initial_context) message = `${body.initial_context}${message}`;
  }
  // Opening figures go with the first turn only; attachments go with every turn.
  const images = [
    ...(isNew ? toImageContent(body.initial_images) : []),
    ...toImageContent(body.images),
  ];
  const blocks: Array<TextContent | ImageContent> = [{ type: "text", text: message }, ...images];
  const content = images.length ? (fitInput ? await fitInput(blocks) : blocks) : message;
  return conversation.submit(
    {
      type: "input",
      content,
      ...(body.request_id ? { requestId: body.request_id } : {}),
    },
    BACKGROUND_CONTEXT,
  );
}
