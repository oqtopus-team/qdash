import { useCallback, useState } from "react";

import type { FlowDocument } from "@/components/features/flow/useFlowDocument";

/** Workflows whose unsaved drafts an action would drop, and the action to run once confirmed. */
export interface DiscardPrompt {
  names: string[];
  action: () => void;
}

/**
 * Defers an action that would drop unsaved drafts until the user confirms it. An action that
 * drops no draft runs at once.
 */
export function useDiscardConfirmation() {
  const [prompt, setPrompt] = useState<DiscardPrompt | null>(null);

  /** Run `action`, first asking to discard any unsaved draft among `candidates`. */
  const confirmDiscard = useCallback((candidates: FlowDocument[], action: () => void) => {
    const names = candidates
      .filter((doc) => doc.isDirty && doc.name)
      .map((doc) => doc.name as string);
    if (names.length === 0) {
      action();
      return;
    }
    setPrompt({ names, action });
  }, []);

  const confirm = () => {
    const action = prompt?.action;
    setPrompt(null);
    action?.();
  };

  const dismiss = useCallback(() => setPrompt(null), []);

  return { prompt, confirmDiscard, confirm, dismiss };
}
