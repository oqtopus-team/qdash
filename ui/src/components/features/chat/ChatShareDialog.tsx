"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  getGetAgentChatShareStatusQueryKey,
  useGetAgentChatShareStatus,
  usePublishAgentChatShare,
  useRevokeAgentChatShare,
} from "@/client/agent/agent";
import { useProject } from "@/contexts/ProjectContext";
import { projectRequest } from "@/components/features/agent-session/useLinkedProject";
import { CopyLinkButton } from "@/components/ui/CopyLinkButton";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { useToast } from "@/components/ui/Toast";
import { VisibilityLabel, type Visibility } from "@/components/ui/VisibilityLabel";
import { VisibilitySelector } from "@/components/ui/VisibilitySelector";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { formatDateTime, formatRelativeTime } from "@/lib/utils/datetime";
import { sharedChatUrl } from "@/lib/utils/sharedChat";

/**
 * Share a read-only snapshot of one of the user's chats with the current project.
 *
 * The chat stays private. Sharing copies it as the server holds it now; later messages
 * reach project members only when the owner updates the snapshot here.
 */
export function ChatShareDialog({
  open,
  onOpenChange,
  sessionId,
  title,
  running,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sessionId: string;
  title: string;
  /** An answer is being written; a snapshot is taken only after it ends. */
  running: boolean;
}) {
  const { projectId, currentProject, canEdit } = useProject();
  const toast = useToast();
  const queryClient = useQueryClient();
  const request = projectId ? projectRequest(projectId) : undefined;
  const statusKey = [...getGetAgentChatShareStatusQueryKey(sessionId), projectId];
  const statusQuery = useGetAgentChatShareStatus(sessionId, {
    query: { queryKey: statusKey, enabled: open && projectId !== null, retry: false },
    request,
  });
  const share = statusQuery.data?.data.share ?? null;
  const current: Visibility = share ? "project" : "private";
  const [choice, setChoice] = useState<Visibility>(current);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) setChoice(current);
  }, [open, current]);
  useEffect(() => {
    if (!open) setError(null);
  }, [open]);

  const publish = usePublishAgentChatShare({ request });
  const revoke = useRevokeAgentChatShare({ request });
  const pending = publish.isPending || revoke.isPending;
  const projectName = currentProject?.name ?? "this project";

  const refreshStatus = () => queryClient.invalidateQueries({ queryKey: statusKey });

  const handlePublish = (updating: boolean) => {
    setError(null);
    publish.mutate(
      { sessionId },
      {
        onSuccess: () => {
          void refreshStatus();
          toast.success(updating ? "Snapshot updated" : `Snapshot shared with ${projectName}`);
        },
        onError: (err) => setError(getApiErrorMessage(err, "Failed to share the chat")),
      },
    );
  };

  const handleRevoke = () => {
    if (!share) return;
    setError(null);
    revoke.mutate(
      { shareId: share.share_id },
      {
        onSuccess: () => {
          void refreshStatus();
          toast.success("Stopped sharing the chat");
        },
        onError: (err) => setError(getApiErrorMessage(err, "Failed to stop sharing")),
      },
    );
  };

  const changed = choice !== current;
  const applyLabel = choice === "project" ? "Share snapshot" : "Stop sharing";

  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent className="max-w-xl">
        <DialogTitle>Share chat</DialogTitle>
        <DialogDescription className="mt-2 text-sm text-base-content/70">
          Share a read-only snapshot of <strong className="font-medium">{title}</strong> with
          members of {projectName}. The chat itself stays private, and nobody can send messages in
          the snapshot.
        </DialogDescription>

        {statusQuery.isLoading ? (
          <div className="mt-4 flex flex-col gap-2" aria-busy="true">
            <div className="skeleton h-4 w-40" />
            <div className="skeleton h-16 w-full" />
          </div>
        ) : statusQuery.isError ? (
          <div role="alert" className="alert alert-error alert-soft mt-4">
            <span>{getApiErrorMessage(statusQuery.error, "Could not load the sharing state")}</span>
            <button type="button" className="btn btn-sm" onClick={() => void statusQuery.refetch()}>
              Retry
            </button>
          </div>
        ) : (
          <div className="mt-2 flex flex-col gap-3">
            <VisibilitySelector
              value={choice}
              onChange={setChoice}
              disabled={pending || (!canEdit && !share)}
              privateDescription="Only you can open this chat"
              projectLabel="Snapshot shared with project"
              projectDescription="Project members can read the chat as it is now. It does not update automatically."
              hint={
                !canEdit && !share
                  ? "Viewers cannot share chats with the project"
                  : running && choice === "project" && !share
                    ? "Wait for the current answer to end before sharing"
                    : undefined
              }
            />

            {share && (
              <div className="rounded-[var(--radius-box)] border border-base-300 p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <VisibilityLabel
                    visibility="project"
                    projectLabel="Shared with project"
                    className="font-medium"
                  />
                  <span
                    className="text-xs text-base-content/60"
                    title={formatDateTime(share.snapshot_at)}
                  >
                    Snapshot taken {formatRelativeTime(share.snapshot_at)} · {share.message_count}{" "}
                    messages
                  </span>
                </div>
                <p className="mt-2 text-xs text-base-content/60">
                  Messages you send after the snapshot are not shared until you update it. The link
                  stays the same.
                </p>
                <div className="mt-2 flex flex-wrap gap-1">
                  <CopyLinkButton url={sharedChatUrl(share.share_id, share.project_id)} />
                  {canEdit && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => handlePublish(true)}
                      disabled={pending || running}
                      title={running ? "Wait for the current answer to end" : undefined}
                    >
                      {publish.isPending ? (
                        <span
                          data-icon="inline-start"
                          className="loading loading-spinner loading-xs"
                        />
                      ) : (
                        <RefreshCw data-icon="inline-start" aria-hidden="true" />
                      )}
                      Update snapshot
                    </button>
                  )}
                </div>
              </div>
            )}

            <p className="text-xs text-base-content/60">
              The snapshot includes your messages and the answers&apos; text, charts and tables.
              Tool steps, workspace files, figures and interactive cards are left out. Only answers
              from {projectName} can be shared; review the chat before sharing.
            </p>

            {error && (
              <div role="alert" className="alert alert-error alert-soft">
                <span>{error}</span>
              </div>
            )}
          </div>
        )}

        <div className="modal-action">
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => onOpenChange(false)}
            disabled={pending}
          >
            {changed ? "Cancel" : "Close"}
          </button>
          {changed && (
            <button
              type="button"
              className={`btn ${choice === "project" ? "btn-primary" : "btn-error"}`}
              onClick={() => (choice === "project" ? handlePublish(false) : handleRevoke())}
              disabled={pending || (choice === "project" && (running || !canEdit))}
            >
              {pending && (
                <span data-icon="inline-start" className="loading loading-spinner loading-xs" />
              )}
              {applyLabel}
            </button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
