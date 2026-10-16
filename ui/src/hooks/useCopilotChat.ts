"use client";

import { useCallback, useMemo, useState } from "react";
import { recoverMessageImages } from "@/lib/chatAttachments";
import { useGetCopilotConfig } from "@/client/copilot/copilot";
import type { AnswerFeedback, ChatImageAttachment, ChatMessage } from "@/types/copilotChat";
import {
  useCopilotChatSessionContext,
  type CopilotChatSession,
} from "@/contexts/CopilotChatSessionContext";
import {
  getStoredThinkingChoice,
  levelOfEffort,
  setStoredThinkingChoice,
  thinkingLevelForRequest,
  type ChatThinkingChoice,
  type ChatThinkingLevel,
} from "@/lib/chatThinking";
import {
  buildChatModelOptions,
  getStoredChatModelKey,
  resolveChatModelOption,
  setStoredChatModelKey,
  type ModelOption,
} from "@/lib/copilotModels";

export type CopilotSession = CopilotChatSession;

export interface ChatModelSelection {
  options: ModelOption[];
  selected: ModelOption;
  select: (key: string) => void;
}

/**
 * Model menu for a chat. Every chat, with or without a task result as its
 * context, picks the planner from `chat_models`; the evaluation model is not a
 * planner and is configured separately (evaluation.yaml).
 */
function useChatModel(): ChatModelSelection {
  const { data } = useGetCopilotConfig();
  const config = data?.data ?? null;
  const [chatKey, setChatKey] = useState(getStoredChatModelKey);
  const chatOptions = useMemo(() => buildChatModelOptions(config), [config]);
  const select = useCallback((key: string) => {
    setChatKey(key);
    setStoredChatModelKey(key);
  }, []);
  return { options: chatOptions, selected: resolveChatModelOption(chatOptions, chatKey), select };
}

export interface ChatThinkingSelection {
  choice: ChatThinkingChoice;
  select: (choice: ChatThinkingChoice) => void;
  /** What "auto" amounts to for the selected model, when its config says. */
  modelDefault: ChatThinkingLevel | null;
}

/** Thinking menu for a chat; remembered across chats like the model. */
function useChatThinking(model: ChatModelSelection): ChatThinkingSelection {
  const [choice, setChoice] = useState<ChatThinkingChoice>(getStoredThinkingChoice);
  const select = useCallback((next: ChatThinkingChoice) => {
    setChoice(next);
    setStoredThinkingChoice(next);
  }, []);
  return { choice, select, modelDefault: levelOfEffort(model.selected?.reasoningEffort) };
}

/** One chat (the active one by default) as seen by a chat surface. */
export function useCopilotChat(sessionId?: string | null) {
  const ctx = useCopilotChatSessionContext();
  const session =
    sessionId === undefined
      ? ctx.activeSession
      : (ctx.sessions.find((s) => s.id === sessionId) ?? null);
  const run = session ? ctx.runs[session.id] : undefined;
  const model = useChatModel();
  const modelOverride = model.selected?.model ?? null;
  const thinking = useChatThinking(model);
  const thinkingLevel = thinkingLevelForRequest(thinking.choice);
  const { sendMessage, stop: stopSession } = ctx;
  const id = session?.id;
  const messages = useMemo(() => session?.messages ?? [], [session?.messages]);

  const send = useCallback(
    (text: string, images?: ChatImageAttachment[]) =>
      sendMessage(text, {
        sessionId: id,
        modelOverride,
        thinkingLevel,
        ...(images?.length ? { images } : {}),
      }),
    [id, modelOverride, thinkingLevel, sendMessage],
  );

  /** Answer the approval card on the last answer; the label is what the thread shows. */
  const decide = useCallback(
    (approvalId: string, approve: boolean, label: string) =>
      sendMessage(label, {
        sessionId: id,
        modelOverride,
        thinkingLevel,
        approval: { id: approvalId, approve },
      }),
    [id, modelOverride, thinkingLevel, sendMessage],
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
    });
  }, [id, messages, modelOverride, thinkingLevel, run, sendMessage]);

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
      });
    },
    [id, messages, modelOverride, thinkingLevel, run, sendMessage],
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
