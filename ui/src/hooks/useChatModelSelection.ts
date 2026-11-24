"use client";

import { useMemo, useSyncExternalStore } from "react";

import { useGetAgentConfig } from "@/client/agent/agent";
import {
  levelOfEffort,
  thinkingChoiceStore,
  type ChatThinkingChoice,
  type ChatThinkingLevel,
} from "@/lib/chatThinking";
import {
  buildChatModelOptions,
  chatModelChoice,
  chatModelIdentityOfKey,
  hasNoChatModel,
  modelIdentity,
  resolveChatModelOption,
  type ModelOption,
} from "@/lib/agentModels";
import type { StoredChoice } from "@/lib/storedChoice";

/** `none`: the config loaded, but no chat model has its API key set in the agent runtime. */
export type ChatModelListStatus = "loading" | "error" | "ready" | "none";

export interface ChatModelSelection {
  /** The chat models whose API key is set, default first. */
  options: ModelOption[];
  /** The model the next message goes to. */
  selected: ModelOption;
  select: (key: string) => void;
  status: ChatModelListStatus;
  /** The `provider:name` of a remembered model the current config no longer offers. */
  unavailableModel: string | null;
}

export interface ChatThinkingSelection {
  choice: ChatThinkingChoice;
  select: (choice: ChatThinkingChoice) => void;
  /** What "auto" amounts to for the selected model, when its config says. */
  modelDefault: ChatThinkingLevel | null;
}

function useStoredChoice<T extends string>(store: StoredChoice<T>): T {
  return useSyncExternalStore(store.subscribe, store.read, () => store.initial);
}

/**
 * The chat model menu shared by Settings and every chat surface.
 *
 * The model list is fetched again whenever a surface mounts, the window regains
 * focus, or the network reconnects, so a list changed by a redeploy shows up
 * without a manual reload. The server lists only models whose API key the agent
 * runtime has, and its default is the first of them. A remembered model the list
 * no longer offers falls back to that default instead of being sent.
 */
export function useChatModelSelection(): ChatModelSelection {
  const { data, isError } = useGetAgentConfig({
    query: {
      staleTime: 0,
      refetchOnMount: "always",
      refetchOnWindowFocus: "always",
      refetchOnReconnect: "always",
    },
  });
  const config = data?.data ?? null;
  const storedKey = useStoredChoice(chatModelChoice);
  const options = useMemo(() => buildChatModelOptions(config), [config]);
  const selected = resolveChatModelOption(options, storedKey);
  const status: ChatModelListStatus = config
    ? hasNoChatModel(options)
      ? "none"
      : "ready"
    : isError
      ? "error"
      : "loading";
  // A remembered model that became the default is still the one that answers.
  const storedIdentity = chatModelIdentityOfKey(storedKey);
  const selectedIdentity = selected.resolvedModel ? modelIdentity(selected.resolvedModel) : null;
  const unavailableModel =
    status === "ready" && storedIdentity !== null && storedIdentity !== selectedIdentity
      ? storedIdentity
      : null;
  return { options, selected, select: chatModelChoice.write, status, unavailableModel };
}

/** The thinking menu for a chat; remembered across chats and surfaces like the model. */
export function useChatThinkingSelection(model: ChatModelSelection): ChatThinkingSelection {
  const choice = useStoredChoice(thinkingChoiceStore);
  return {
    choice,
    select: thinkingChoiceStore.write,
    modelDefault: levelOfEffort(model.selected.reasoningEffort),
  };
}
