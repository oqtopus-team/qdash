"use client";

import { useCallback, useMemo } from "react";
import { useOptionalChatDock } from "@/contexts/ChatDockContext";
import { recoverMessageImages } from "@/lib/chatAttachments";
import type { AnswerFeedback, ChatImageAttachment, ChatMessage } from "@/types/copilotChat";
import {
  useCopilotChatSessionContext,
  type CopilotChatSession,
} from "@/contexts/CopilotChatSessionContext";
import { thinkingLevelForRequest } from "@/lib/chatThinking";
import { useChatModelSelection, useChatThinkingSelection } from "@/hooks/useChatModelSelection";
import { canResendSteer, isUnresolvedSteer, type PendingSteer } from "@/lib/copilotSteer";

export type CopilotSession = CopilotChatSession;

/** One chat (the active one by default) as seen by a chat surface. */
export function useCopilotChat(sessionId?: string | null) {
  const ctx = useCopilotChatSessionContext();
  const session =
    sessionId === undefined
      ? ctx.activeSession
      : (ctx.sessions.find((s) => s.id === sessionId) ?? null);
  const run = session ? ctx.runs[session.id] : undefined;
  // Every chat, with or without a task result as its context, picks the planner
  // from `chat_models`; the evaluation model is configured separately.
  const model = useChatModelSelection();
  const modelOverride = model.selected.model;
  const thinking = useChatThinkingSelection(model);
  const thinkingLevel = thinkingLevelForRequest(thinking.choice);
  const {
    sendMessage,
    stop: stopSession,
    steer: steerSession,
    checkSteer,
    dismissSteer,
    dismissNotice,
  } = ctx;
  const id = session?.id;
  // The page the user has open, read when a turn goes out; null on the chat page.
  const dock = useOptionalChatDock();
  const currentPage = dock?.currentPage;
  const messages = useMemo(() => session?.messages ?? [], [session?.messages]);

  const send = useCallback(
    (text: string, images?: ChatImageAttachment[]) =>
      sendMessage(text, {
        sessionId: id,
        modelOverride,
        thinkingLevel,
        page: currentPage?.() ?? null,
        ...(images?.length ? { images } : {}),
      }),
    [id, modelOverride, thinkingLevel, sendMessage, currentPage],
  );

  /** Answer the approval card on the last answer; the label is what the thread shows. */
  const decide = useCallback(
    (approvalId: string, approve: boolean, label: string) =>
      sendMessage(label, {
        sessionId: id,
        modelOverride,
        thinkingLevel,
        page: currentPage?.() ?? null,
        approval: { id: approvalId, approve },
      }),
    [id, modelOverride, thinkingLevel, sendMessage, currentPage],
  );

  const stop = useCallback(() => {
    if (id) stopSession(id);
  }, [id, stopSession]);

  const steers: PendingSteer[] = useMemo(
    () => (id ? (ctx.steers[id] ?? []) : []),
    [ctx.steers, id],
  );

  /** Send `text` to the answer being written; it reads it after its current step. */
  const steer = useCallback(
    (text: string) => (id ? steerSession(id, text) : false),
    [id, steerSession],
  );

  /**
   * Send a steer the runtime said was not delivered again: to the answer streaming
   * now, or as a new message when none is. One whose delivery is not confirmed is
   * never sent again: the answer may have read it.
   */
  const resendSteer = useCallback(
    (requestId: string) => {
      if (!id) return;
      const pending = steers.find((s) => s.requestId === requestId);
      if (!pending || !canResendSteer(pending)) return;
      const sent = run ? steerSession(id, pending.text) : send(pending.text);
      if (sent) dismissSteer(id, requestId);
    },
    [id, steers, run, steerSession, send, dismissSteer],
  );

  /**
   * Continue the last answer, which was stopped or failed, without a new message.
   * A failed answer's error is replaced by the continuation; a stopped answer stays.
   */
  // A steer the runtime may hold that the chat does not show yet would be part of
  // what a continue answers: wait until the chat knows where each one stands.
  // Before the steers a reload left are restored, one may be hidden: wait for them too.
  const steersSettled = ctx.steersReady && !steers.some(isUnresolvedSteer);

  const continueLast = useCallback(() => {
    if (!id || run || !steersSettled || !canContinueMessages(messages)) return;
    sendMessage("", {
      sessionId: id,
      continueRun: true,
      history: continuationHistory(messages),
      modelOverride,
      thinkingLevel,
      page: currentPage?.() ?? null,
    });
  }, [id, run, steersSettled, messages, sendMessage, modelOverride, thinkingLevel, currentPage]);

  /** Re-send the last user message, replacing the failed or stopped answer. */
  const retryLast = useCallback(() => {
    if (!id || run) return;
    let lastUser = messages.length - 1;
    while (lastUser >= 0 && messages[lastUser].role !== "user") lastUser--;
    if (lastUser < 0) return;
    const images = recoverMessageImages(messages[lastUser]);
    if (images === null) return;
    sendMessage(messages[lastUser].content, {
      images,
      sessionId: id,
      history: messages.slice(0, lastUser),
      modelOverride,
      thinkingLevel,
      page: currentPage?.() ?? null,
    });
  }, [id, messages, modelOverride, thinkingLevel, run, sendMessage, currentPage]);

  /** Replace the user message at `index` and everything after it with a new turn. */
  const editMessage = useCallback(
    (index: number, text: string) => {
      const trimmed = text.trim();
      if (!id || run || !trimmed) return;
      if (messages[index]?.role !== "user") return;
      const images = recoverMessageImages(messages[index]);
      if (images === null) return;
      sendMessage(trimmed, {
        sessionId: id,
        history: messages.slice(0, index),
        modelOverride,
        thinkingLevel,
        images,
        page: currentPage?.() ?? null,
      });
    },
    [id, messages, modelOverride, thinkingLevel, run, sendMessage, currentPage],
  );

  /**
   * Start a new chat from the answer at `index`, through that answer, and switch to it.
   * Only a completed answer saved with its runtime entry qualifies (see `canBranchAt`).
   */
  const branchingEntry = id ? ctx.branching[id] : undefined;
  const { branchFrom: branchSession } = ctx;
  const canBranchAt = useCallback(
    (index: number) =>
      Boolean(id) &&
      !run &&
      steersSettled &&
      !branchingEntry &&
      session?.messagesLoaded === true &&
      isBranchableAnswer(messages[index]),
    [id, run, steersSettled, branchingEntry, session?.messagesLoaded, messages],
  );
  const branchFrom = useCallback(
    (index: number) => {
      const entryId = messages[index]?.entryId;
      if (!id || !entryId || !canBranchAt(index)) return;
      void branchSession(id, entryId);
    },
    [id, messages, canBranchAt, branchSession],
  );

  /** Rate the assistant message at `index`; rating it the same way again clears it. */
  const rateAnswer = useCallback(
    (index: number, feedback: AnswerFeedback) => {
      if (!id) return;
      const current = answerFeedback(messages[index]);
      ctx.setMessageFeedback(id, index, current === feedback ? null : feedback);
    },
    [ctx, id, messages],
  );

  return {
    session,
    messages,
    isLoadingMessages: session !== null && !session.messagesLoaded,
    isStreaming: Boolean(run),
    liveTurn: run?.turn ?? null,
    statusMessage: run?.statusMessage ?? null,
    /** Whether the live turn's stream is connected, and when the turn last sent something. */
    connection: run?.connection ?? null,
    model,
    thinking,
    send,
    decide,
    stop,
    retryLast,
    canRetryLast:
      !run &&
      messages
        .filter((m) => m.role === "user")
        .slice(-1)
        .some((m) => recoverMessageImages(m) !== null),
    canEditMessage: (index: number) =>
      !run && messages[index]?.role === "user" && recoverMessageImages(messages[index]) !== null,
    editMessage,
    rateAnswer,
    steers,
    steer,
    resendSteer,
    checkSteer: (requestId: string) => {
      if (id) checkSteer(id, requestId);
    },
    dismissSteer: (requestId: string) => {
      if (id) dismissSteer(id, requestId);
    },
    notice: id ? (ctx.notices[id] ?? null) : null,
    dismissNotice: () => {
      if (id) dismissNotice(id);
    },
    continueLast,
    canContinue: !run && steersSettled && canContinueMessages(messages),
    branchFrom,
    canBranchAt,
    /** The index of the answer being branched from, while its request runs. */
    branchingIndex: branchingEntry
      ? messages.findIndex((m) => m.role === "assistant" && m.entryId === branchingEntry)
      : -1,
  };
}

function isErrorContent(message: ChatMessage | undefined): boolean {
  return message?.role === "assistant" && message.content.startsWith("Error: ");
}

/**
 * Whether a chat can be branched from this message: an answer the runtime completed,
 * saved with its entry ID. Never one without an ID (older answers, segments a steer
 * closed off), an error, a stopped answer, or one that ended on a question, an
 * approval, or a proposed edit: a branch must not make that card actionable again.
 * The runtime checks the same and refuses otherwise.
 */
export function isBranchableAnswer(message: ChatMessage | undefined): boolean {
  if (!message || message.role !== "assistant" || !message.entryId) return false;
  if (isErrorContent(message)) return false;
  try {
    const parsed = JSON.parse(message.content) as {
      stopped?: unknown;
      blocks?: Array<{ type?: unknown }>;
    };
    if (parsed.stopped === true) return false;
    return !(parsed.blocks ?? []).some(
      (b) => b.type === "ask" || b.type === "approval" || b.type === "edit",
    );
  } catch {
    return false;
  }
}

/**
 * Where the turn's last answer is: the last message, or the one before the steers
 * that end the conversation. A steer the answer read just before it was stopped
 * is placed after it, and is part of the unfinished turn a continue answers.
 */
function lastAnswerIndex(messages: ChatMessage[]): number {
  let i = messages.length - 1;
  while (i >= 0 && messages[i].role === "user" && messages[i].steer) i--;
  return i;
}

/** The history a continue sends: the conversation without a failed answer's error, steers kept. */
export function continuationHistory(messages: ChatMessage[]): ChatMessage[] {
  const at = lastAnswerIndex(messages);
  return isErrorContent(messages[at])
    ? [...messages.slice(0, at), ...messages.slice(at + 1)]
    : messages;
}

/**
 * Whether the last answer ended without finishing (stopped, or an error) so it may be
 * continued, also when steers it read before it stopped follow it. An answer that
 * ended on a question, an approval or a proposed edit is answered instead; the
 * runtime refuses to continue past one as well.
 */
export function canContinueMessages(messages: ChatMessage[]): boolean {
  const last = messages[lastAnswerIndex(messages)];
  if (!last || last.role !== "assistant") return false;
  if (isErrorContent(last)) return messages.some((m) => m.role === "user");
  try {
    const parsed = JSON.parse(last.content) as {
      stopped?: unknown;
      blocks?: Array<{ type?: unknown }>;
    };
    if (parsed.stopped !== true) return false;
    return !(parsed.blocks ?? []).some(
      (b) => b.type === "ask" || b.type === "approval" || b.type === "edit",
    );
  } catch {
    return false;
  }
}

/** Whether an assistant message shows nothing but a trace: no blocks, only work done. */
function isTraceOnly(message: ChatMessage): boolean {
  if (message.role !== "assistant" || !message.content.startsWith("{")) return false;
  try {
    const parsed = JSON.parse(message.content) as { blocks?: unknown };
    return Array.isArray(parsed.blocks) && parsed.blocks.length === 0;
  } catch {
    return false;
  }
}

/**
 * The user's reply to the answer at `index`, if one follows it. An approved write runs
 * before the decision is placed, so its tool trace becomes an assistant message of its
 * own between the approval card and the "Approved: ..." reply; such trace-only
 * messages are passed over. Any other message in between means no reply.
 */
export function replyAfter(messages: ChatMessage[], index: number): string | undefined {
  for (let i = index + 1; i < messages.length; i++) {
    const message = messages[i];
    if (message.role === "user") return message.content;
    if (!isTraceOnly(message)) return undefined;
  }
  return undefined;
}

/** The stored rating of an assistant message, if any. */
export function answerFeedback(message: ChatMessage | undefined): AnswerFeedback | null {
  if (!message || message.role !== "assistant" || !message.content.startsWith("{")) return null;
  try {
    const parsed = JSON.parse(message.content) as { feedback?: unknown };
    return parsed.feedback === "up" || parsed.feedback === "down" ? parsed.feedback : null;
  } catch {
    return null;
  }
}
