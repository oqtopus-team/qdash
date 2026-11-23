/**
 * Where a turn another window started goes in this window's copy of the chat.
 *
 * A window that did not start the turn has no pointer to it (pointers live in the
 * starting tab's session storage), only the saved transcript and the turn's start
 * as the runtime reports it: `index`, the number of messages before the turn, and
 * `digest`, a fingerprint of the transcript the turn started from (the messages
 * before it and, unless it is a continue, its own message). The starting window
 * sends both with the turn; the server checks its saved chat holds that start and
 * saves the turn's message before anything reaches the runtime. A transcript that
 * does not hold exactly that start (a copy loaded before the turn started, or
 * another conversation under the same length) has no place for the turn: the
 * window asks again later instead of replaying the new answer under an old question.
 *
 * Each steer the turn placed is saved with the part of the answer it closed off,
 * after the start. Reattaching replays the turn from its start, placing those
 * steers again, so the live answer is folded over the transcript up to the start.
 */

import type { ChatMessage } from "@/types/copilotChat";

/** Where a turn starts in its chat's transcript, as the window that sent it saw it. */
export interface TurnStart {
  /** How many messages precede the turn. */
  index: number;
  /** `transcriptDigest` of those messages and, unless a continue, the turn's own message. */
  digest: string;
}

export interface ObservedTurnPlacement {
  /** The messages before the turn. */
  history: ChatMessage[];
  /** What precedes the live answer: the history and the turn's own message. */
  shown: ChatMessage[];
  /** Where the turn's own message is in `shown`; -1 for a continue. */
  userAt: number;
}

/** A 64-bit hash (two 32-bit lanes, cyrb53-style mixing) of `text`, as 16 hex digits. */
function hash64(text: string): string {
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (let i = 0; i < text.length; i++) {
    const ch = text.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507);
  h1 ^= Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507);
  h2 ^= Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  const hex = (n: number) => (n >>> 0).toString(16).padStart(8, "0");
  return hex(h2) + hex(h1);
}

/**
 * A fingerprint of `messages` as they are saved: each message's role, text, and
 * whether it is a steer. Not a security measure: it tells one saved transcript
 * from another. Local-only fields (attachment thumbnails) and fields filled in
 * after the turn started (an answer's runtime entry) are left out. An answer of a
 * turn (`turnRequestId`) counts by its turn, not its text: the server and each
 * window fold the same answer with their own timings, and a rating changes it.
 * The server computes the same digest (`transcript_digest` in
 * `src/qdash/api/services/chat_transcript.py`).
 */
export function transcriptDigest(messages: ChatMessage[]): string {
  return hash64(
    JSON.stringify(
      messages.map((m) => [
        m.role,
        m.role === "assistant" && m.turnRequestId ? `@turn:${m.turnRequestId}` : m.content,
        m.steer ? 1 : 0,
      ]),
    ),
  );
}

/** The start of a turn sent after `history`, adding `message` unless it is a continue. */
export function turnStartOf(history: ChatMessage[], message: ChatMessage | null): TurnStart {
  return {
    index: history.length,
    digest: transcriptDigest(message ? [...history, message] : history),
  };
}

/** A turn start as received from the API, or null when it is missing or malformed. */
export function parseTurnStart(raw: unknown): TurnStart | null {
  if (!raw || typeof raw !== "object") return null;
  const { index, digest } = raw as { index?: unknown; digest?: unknown };
  if (typeof index !== "number" || !Number.isInteger(index) || index < 0) return null;
  if (typeof digest !== "string" || !/^[0-9a-f]{16}$/.test(digest)) return null;
  return { index, digest };
}

/**
 * The turn's place in `messages`, or null when the transcript does not hold the
 * start the turn was sent from: a copy loaded before the server saved the start, or
 * the runtime reported no start (a turn sent by an older version of the page).
 */
export function observedTurnPlacement(
  messages: ChatMessage[],
  continuing: boolean,
  start: TurnStart | null,
): ObservedTurnPlacement | null {
  if (!start) return null;
  const end = start.index + (continuing ? 0 : 1);
  if (messages.length < end) return null;
  const shown = messages.slice(0, end);
  if (!continuing) {
    const own = shown[start.index];
    if (own.role !== "user" || own.steer) return null;
  }
  if (transcriptDigest(shown) !== start.digest) return null;
  return {
    history: messages.slice(0, start.index),
    shown,
    userAt: continuing ? -1 : start.index,
  };
}
