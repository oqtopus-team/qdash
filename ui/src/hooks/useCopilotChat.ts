"use client";

import { useCallback, useMemo, useState } from "react";
import { useGetCopilotConfig } from "@/client/copilot/copilot";
import {
  useCopilotChatSessionContext,
  type CopilotChatSession,
} from "@/contexts/CopilotChatSessionContext";
import {
  buildAnalysisModelOptions,
  buildChatModelOptions,
  getStoredAnalysisModelKey,
  getStoredChatModelKey,
  resolveAnalysisModelOption,
  resolveChatModelOption,
  setStoredAnalysisModelKey,
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
 * Model menu for a chat. Analysis chats pick from `analysis_models`, general
 * chats from `chat_models`; each remembers its own choice.
 */
function useChatModel(isAnalysis: boolean): ChatModelSelection {
  const { data } = useGetCopilotConfig();
  const config = data?.data ?? null;
  const [chatKey, setChatKey] = useState(getStoredChatModelKey);
  const [analysisKey, setAnalysisKey] = useState(getStoredAnalysisModelKey);

  const chatOptions = useMemo(() => buildChatModelOptions(config), [config]);
  const analysisOptions = useMemo(() => buildAnalysisModelOptions(config), [config]);

  const select = useCallback(
    (key: string) => {
      if (isAnalysis) {
        setAnalysisKey(key);
        setStoredAnalysisModelKey(key);
      } else {
        setChatKey(key);
        setStoredChatModelKey(key);
      }
    },
    [isAnalysis],
  );

  return isAnalysis
    ? {
        options: analysisOptions,
        selected: resolveAnalysisModelOption(analysisOptions, analysisKey),
        select,
      }
    : { options: chatOptions, selected: resolveChatModelOption(chatOptions, chatKey), select };
}

/** One chat (the active one by default) as seen by a chat surface. */
export function useCopilotChat(sessionId?: string | null) {
  const ctx = useCopilotChatSessionContext();
  const session =
    sessionId === undefined
      ? ctx.activeSession
      : (ctx.sessions.find((s) => s.id === sessionId) ?? null);
  const run = session ? ctx.runs[session.id] : undefined;
  const model = useChatModel(Boolean(session?.context));
  const modelOverride = model.selected?.model ?? null;
  const { sendMessage, stop: stopSession } = ctx;
  const id = session?.id;
  const messages = useMemo(() => session?.messages ?? [], [session?.messages]);

  const send = useCallback(
    (text: string) => sendMessage(text, { sessionId: id, modelOverride }),
    [id, modelOverride, sendMessage],
  );

  /** Answer the approval card on the last answer; the label is what the thread shows. */
  const decide = useCallback(
    (approvalId: string, approve: boolean, label: string) =>
      sendMessage(label, { sessionId: id, modelOverride, approval: { id: approvalId, approve } }),
    [id, modelOverride, sendMessage],
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
    sendMessage(messages[lastUser].content, {
      sessionId: id,
      history: messages.slice(0, lastUser),
      modelOverride,
    });
  }, [id, messages, modelOverride, run, sendMessage]);

  return {
    session,
    messages,
    isLoadingMessages: session !== null && !session.messagesLoaded,
    isStreaming: Boolean(run),
    liveTurn: run?.turn ?? null,
    statusMessage: run?.statusMessage ?? null,
    model,
    send,
    decide,
    stop,
    retryLast,
  };
}
