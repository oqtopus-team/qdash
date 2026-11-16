/**
 * Messages the user sends while an answer is still being written ("steers").
 *
 * A steer is not a new turn: the runtime hands it to the running answer, which
 * reads it after its current step. Until the chat knows where it landed in the
 * transcript, it shows it as pending under the live answer. These helpers keep
 * that state honest:
 *
 * - A steer only ever moves forward; a later report never undoes a settled one.
 * - Only the runtime says a steer was or was not delivered. When the stream
 *   ends (a stop, a dropped connection) before it said, the steer is
 *   unconfirmed and the chat asks the runtime's store, which never sends it.
 * - A steer the runtime read is placed in the saved conversation once, by its
 *   request ID, in transcript order (`placeLateSteer`).
 */

import type { ChatMessage, ChatMessageSteer } from "@/types/copilotChat";

export type PendingSteerStatus =
  /** The request is on its way, or its reply was lost and the chat is asking where it stands. */
  | "sending"
  /** Accepted; the answer reads it after its current step. */
  | "queued"
  /** The stream ended before it said whether the answer read it; the runtime has not said yet. */
  | "unconfirmed"
  /** The answer read it; it moves into the conversation at the place it landed. */
  | "delivered"
  /** It never reached an answer: nothing was running any more, or the stream ended first. */
  | "rejected"
  /** The answer was stopped or failed before reading it; it was not delivered. */
  | "withdrawn"
  /** The request was refused before it reached the runtime. */
  | "failed";

/** Where in the conversation the turn a steer was sent to starts. */
export interface SteerAnchor {
  /** Index of the turn's user message, or of its first answer for a continue. */
  start: number;
  /** The turn's user message, to tell that the conversation still holds it there; null for a continue. */
  userText: string | null;
}

export interface PendingSteer {
  requestId: string;
  text: string;
  status: PendingSteerStatus;
  /** Why it was rejected, withdrawn or failed, in the runtime's or the API's words. */
  reason?: string;
  /** Its entry in the runtime's transcript, once delivered. */
  entryId?: string | null;
  /** The project it was sent from; every later request about it names the same one. */
  projectId?: string | null;
  /** The turn it was sent to, to place it in the conversation if the stream did not. */
  anchor?: SteerAnchor;
  /** A status lookup is under way. */
  checking?: boolean;
  /** Delivered, but the conversation changed since, so there is no place to show it. */
  unplaced?: boolean;
}

const RANK: Record<PendingSteerStatus, number> = {
  sending: 0,
  queued: 1,
  unconfirmed: 2,
  delivered: 3,
  rejected: 3,
  withdrawn: 3,
  failed: 3,
};

/** Whether a steer is still waiting for the answer to read it. */
export function isOpenSteer(steer: PendingSteer): boolean {
  return steer.status === "sending" || steer.status === "queued";
}

/**
 * Whether the chat does not yet know where a steer stands in the conversation:
 * the runtime may hold it where the chat does not show it.
 */
export function isUnresolvedSteer(steer: PendingSteer): boolean {
  return (
    isOpenSteer(steer) ||
    steer.status === "unconfirmed" ||
    (steer.status === "delivered" && !steer.unplaced)
  );
}

/** Whether the user can send this steer again: only once the runtime said it was not delivered. */
export function canResendSteer(steer: PendingSteer): boolean {
  return steer.status === "rejected" || steer.status === "withdrawn" || steer.status === "failed";
}

/** Whether the user can ask again where an unconfirmed steer stands. */
export function canCheckSteer(steer: PendingSteer): boolean {
  return steer.status === "unconfirmed" && !steer.checking;
}

/** Move one steer forward; a later report never undoes a settled one. */
export function advanceSteer(
  steers: PendingSteer[],
  requestId: string,
  status: PendingSteerStatus,
  reason?: string,
  entryId?: string | null,
): PendingSteer[] {
  return steers.map((steer) =>
    steer.requestId === requestId && RANK[status] > RANK[steer.status]
      ? {
          ...steer,
          status,
          ...(reason ? { reason } : {}),
          ...(entryId !== undefined ? { entryId } : {}),
        }
      : steer,
  );
}

/** Change fields of one steer other than its status. */
export function patchSteer(
  steers: PendingSteer[],
  requestId: string,
  patch: Partial<Pick<PendingSteer, "checking" | "unplaced" | "entryId">>,
): PendingSteer[] {
  return steers.map((steer) => (steer.requestId === requestId ? { ...steer, ...patch } : steer));
}

/**
 * The stream ended without placing these steers. A stop or a dropped
 * connection says nothing about whether the answer read one: the runtime may
 * have placed it just before, so a queued steer is unconfirmed until the
 * runtime's store says. A steer whose request is still on its way waits for
 * its reply.
 */
export function settleOpenSteers(steers: PendingSteer[]): PendingSteer[] {
  return steers.map((steer) =>
    steer.status === "queued" ? { ...steer, status: "unconfirmed" } : steer,
  );
}

/** What a steer request or status lookup reported. */
export interface SteerReply {
  status: PendingSteerStatus;
  reason?: string;
  entryId?: string | null;
}

/** The status a steer request's or status lookup's reply reports. */
export function steerReplyStatus(reply: unknown): SteerReply {
  const { status, reason, entry_id } = (reply ?? {}) as {
    status?: unknown;
    reason?: unknown;
    entry_id?: unknown;
  };
  const why = typeof reason === "string" && reason ? reason : undefined;
  if (status === "queued") return { status: "queued" };
  if (status === "applied") {
    return { status: "delivered", entryId: typeof entry_id === "string" ? entry_id : null };
  }
  if (status === "withdrawn") return { status: "withdrawn", reason: why };
  if (status === "rejected") return { status: "rejected", reason: why };
  // A status lookup: never admitted, and the runtime will not admit it later.
  if (status === "not_found") return { status: "rejected", reason: "not_found" };
  return { status: "unconfirmed", reason: why ?? "Unexpected reply" };
}

/** One line on where a steer stands, for the chip under the answer. */
export function steerStatusText(steer: PendingSteer): string {
  switch (steer.status) {
    case "sending":
      return "Sending…";
    case "queued":
      return "Read after the current step";
    case "unconfirmed":
      return steer.checking
        ? "Checking whether the answer read it…"
        : "Not confirmed whether the answer read it";
    case "delivered":
      return steer.unplaced
        ? "Read by the answer; the chat changed since, so it is not shown in place"
        : "Read by the answer";
    case "rejected":
      return steer.reason === "not_found"
        ? "Not delivered: the answer ended before it arrived"
        : "Not sent: the answer had already finished";
    case "withdrawn":
      return steer.reason === "stopped" || steer.reason === "aborted"
        ? "Not delivered: the answer was stopped"
        : "Not delivered: the answer ended without reading it";
    case "failed":
      return `Not sent${steer.reason ? `: ${steer.reason}` : ""}`;
  }
}

/** Transcript order of an entry ID; one not known sorts last. */
function entryOrder(entryId: string | null | undefined): number {
  return entryId && /^\d+$/.test(entryId) ? Number(entryId) : Number.POSITIVE_INFINITY;
}

/**
 * The conversation with a delivered steer the stream did not place, or the
 * same array when it already holds it, or null when the turn it was sent to
 * is no longer where the steer remembers it (the conversation was edited).
 *
 * The answer the steer interrupted was saved as one message, so the steer
 * cannot be put at the exact point inside it: it goes right after that
 * message, marked `approximate`. Among the turn's steers it keeps transcript
 * order by entry ID, whatever order their receipts arrived in, and it never
 * moves past the next turn.
 */
export function placeLateSteer(
  messages: ChatMessage[],
  steer: Pick<PendingSteer, "requestId" | "text" | "entryId" | "anchor">,
): ChatMessage[] | null {
  if (messages.some((m) => m.steer?.requestId === steer.requestId)) return messages;
  const anchor = steer.anchor;
  if (!anchor) return null;
  let first: number;
  if (anchor.userText !== null) {
    const turn = messages[anchor.start];
    if (turn?.role !== "user" || turn.steer || turn.content !== anchor.userText) return null;
    first = anchor.start + 1;
  } else {
    if (anchor.start > messages.length) return null;
    first = anchor.start;
  }
  // The turn ends where the next one starts: a user message that is not a steer.
  let end = first;
  while (end < messages.length && !(messages[end].role === "user" && !messages[end].steer)) end++;
  const at = entryOrder(steer.entryId);
  let after = first - 1;
  for (let i = first; i < end; i++) {
    const placed = messages[i].steer;
    if (placed && entryOrder(placed.entryId) < at) after = i;
  }
  // Past the part of the answer it interrupted, before any steer that landed later.
  let position = after + 1;
  if (position < end && messages[position].role === "assistant") position++;
  const meta: ChatMessageSteer = {
    requestId: steer.requestId,
    entryId: steer.entryId ?? null,
    placement: "approximate",
  };
  return [
    ...messages.slice(0, position),
    { role: "user", content: steer.text, steer: meta },
    ...messages.slice(position),
  ];
}
