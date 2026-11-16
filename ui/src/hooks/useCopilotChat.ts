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
  const { sendMessage, stop: stopSession } = ctx;
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
  };
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
