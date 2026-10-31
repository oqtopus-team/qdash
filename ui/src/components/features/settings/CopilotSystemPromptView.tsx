"use client";

import { useState } from "react";

import { Lock } from "lucide-react";

import { useGetCopilotSystemPrompt } from "@/client/copilot/copilot";
import { getApiErrorMessage } from "@/lib/utils/apiError";

/**
 * What QDash tells the chat model, read-only: the system prompt the
 * application sets, then the user's own instructions as they are appended.
 * Loaded when opened; it is the runtime's live text, not a copy.
 */
export function CopilotSystemPromptView() {
  const [open, setOpen] = useState(false);
  const { data, isLoading, error } = useGetCopilotSystemPrompt({
    query: { enabled: open, staleTime: 30_000 },
  });
  const shown = data?.data;

  return (
    <details
      className="rounded-lg bg-base-100"
      onToggle={(event) => setOpen((event.target as HTMLDetailsElement).open)}
    >
      <summary className="flex cursor-pointer items-center gap-2 p-4 text-sm font-medium">
        <Lock className="h-3.5 w-3.5 text-base-content/50" />
        What Copilot is told
        <span className="text-xs font-normal text-base-content/50">
          set by the application, read-only
        </span>
      </summary>
      <div className="space-y-3 px-4 pb-4">
        {isLoading && (
          <div className="flex justify-center py-4">
            <span className="loading loading-spinner loading-sm" />
          </div>
        )}
        {error != null && (
          <div className="alert alert-warning py-2 text-sm">
            {getApiErrorMessage(error, "The system prompt is not available right now")}
          </div>
        )}
        {shown && (
          <>
            <section>
              <div className="mb-1 text-xs text-base-content/50">System prompt</div>
              <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded border border-base-300 bg-base-200/40 p-3 text-xs">
                {shown.system_prompt}
              </pre>
            </section>
            <section>
              <div className="mb-1 text-xs text-base-content/50">
                Your instructions, as appended
              </div>
              {shown.user_preferences ? (
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded border border-primary/30 bg-primary/5 p-3 text-xs">
                  {shown.user_preferences}
                </pre>
              ) : (
                <p className="text-xs text-base-content/50">None: you have not set any.</p>
              )}
            </section>
            {(shown.tools?.length ?? 0) > 0 && (
              <section>
                <div className="mb-1 text-xs text-base-content/50">
                  Tools offered ({shown.tools?.length})
                </div>
                <div className="flex flex-wrap gap-1">
                  {shown.tools?.map((tool) => (
                    <span key={tool} className="badge badge-ghost badge-sm font-mono">
                      {tool}
                    </span>
                  ))}
                </div>
                <p className="mt-1 text-xs text-base-content/50">
                  Each tool&apos;s description is sent with the request alongside this text.
                </p>
              </section>
            )}
          </>
        )}
      </div>
    </details>
  );
}
