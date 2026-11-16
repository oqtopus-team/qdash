"use client";

import { useMemo, useSyncExternalStore } from "react";

import { useGetCopilotConfig } from "@/client/copilot/copilot";
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
  resolveChatModelOption,
  type ModelOption,
} from "@/lib/copilotModels";
import type { StoredChoice } from "@/lib/storedChoice";

export type ChatModelListStatus = "loading" | "error" | "ready";

export interface ChatModelSelection {
  /** The configured chat models, default first. */
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
 * without a manual reload. A remembered model the list no longer offers falls
 * back to the configured default instead of being sent.
 */
export function useChatModelSelection(): ChatModelSelection {
  const { data, isError } = useGetCopilotConfig({
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
  const status: ChatModelListStatus = config ? "ready" : isError ? "error" : "loading";
  const unavailableModel =
    status === "ready" && selected.key !== storedKey ? chatModelIdentityOfKey(storedKey) : null;
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
