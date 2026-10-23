"use client";

import { useEffect, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import {
  getGetCopilotPreferencesQueryKey,
  getGetCopilotSystemPromptQueryKey,
  useGetCopilotPreferences,
  useUpdateCopilotPreferences,
} from "@/client/copilot/copilot";
import { useToast } from "@/components/ui/Toast";
import { getApiErrorMessage } from "@/lib/utils/apiError";

const FALLBACK_LIMIT = 2000;

const EXAMPLES = [
  "Answer in Japanese, conclusion first.",
  "Put numbers in a table with units.",
  "Write qubits as Q05 and couplings as Q04-Q05.",
];

/**
 * The user's own instructions for Copilot chat. They are stored with the
 * account, so they follow the user across devices, and they apply to chats
 * only: evaluations and forum replies stay the same for everyone.
 */
export function CopilotInstructionsSettings() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { data, isLoading } = useGetCopilotPreferences();
  const saved = data?.data.instructions ?? "";
  const limit = data?.data.max_instructions_chars ?? FALLBACK_LIMIT;
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setDraft(saved);
  }, [saved]);

  const update = useUpdateCopilotPreferences({
    mutation: {
      onSuccess: (response) => {
        queryClient.setQueryData(getGetCopilotPreferencesQueryKey(), response);
        // The read-only view shows the instructions as appended; refresh it.
        queryClient.invalidateQueries({ queryKey: getGetCopilotSystemPromptQueryKey() });
        toast.success(response.data.instructions ? "Instructions saved" : "Instructions cleared");
      },
      onError: (error) => toast.error(getApiErrorMessage(error, "Failed to save instructions")),
    },
  });

  const dirty = draft.trim() !== saved;
  const tooLong = draft.length > limit;

  return (
    <div className="flex flex-col gap-3">
      <label htmlFor="copilot-instructions" className="text-sm font-medium">
        Your instructions
      </label>
      <textarea
        id="copilot-instructions"
        className={`textarea textarea-bordered w-full min-h-32 text-sm ${tooLong ? "textarea-error" : ""}`}
        placeholder={EXAMPLES.join("\n")}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        disabled={isLoading || update.isPending}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className={`text-xs ${tooLong ? "text-error" : "text-base-content/50"}`}>
          {draft.length} / {limit}
        </span>
        <div className="flex gap-2">
          {saved && (
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() => update.mutate({ data: { instructions: "" } })}
              disabled={update.isPending}
            >
              Clear
            </button>
          )}
          <button
            type="button"
            className="btn btn-sm btn-primary"
            onClick={() => update.mutate({ data: { instructions: draft } })}
            disabled={!dirty || tooLong || update.isPending}
          >
            {update.isPending ? <span className="loading loading-spinner loading-xs" /> : "Save"}
          </button>
        </div>
      </div>
      <p className="text-sm text-base-content/60">
        Added to every Copilot chat you start, after QDash&apos;s own rules (shown below): use it
        for language, tone and formats. It does not apply to AI evaluations or forum replies, which
        stay the same for everyone, and it cannot skip the approval of write operations.
      </p>
    </div>
  );
}
