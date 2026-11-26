"use client";

import { useState } from "react";
import Link from "next/link";
import { isAxiosError } from "axios";
import { ArrowLeft, CircleSlash, Info, Square, Trash2, XCircle } from "lucide-react";

import {
  getGetAgentChatShareQueryKey,
  useGetAgentChatShare,
  useRevokeAgentChatShare,
} from "@/client/agent/agent";
import type { AgentChatShareMessageSchema } from "@/schemas";
import {
  projectRequest,
  useLinkedProject,
} from "@/components/features/agent-session/useLinkedProject";
import { ChatMarkdown } from "@/components/features/chat/ChatMarkdown";
import { UserMessage } from "@/components/features/chat/ChatMessages";
import { ChatPlotlyChart } from "@/components/features/chat/ChatPlotlyChart";
import { ChatUiBlock } from "@/components/features/chat/ChatUiBlock";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { CopyLinkButton } from "@/components/ui/CopyLinkButton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import { VisibilityLabel } from "@/components/ui/VisibilityLabel";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { formatDateTime, formatRelativeTime } from "@/lib/utils/datetime";
import type { UiBlockPayload } from "@/lib/agentUiSpec";

const noop = () => {};

function SharedAnswer({ message }: { message: AgentChatShareMessageSchema }) {
  if (message.is_error) {
    return (
      <div className="chat-assistant-row">
        <div className="flex items-start gap-2 rounded-[var(--radius-box)] border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">
          <XCircle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
          <span className="min-w-0 break-words">{message.blocks?.[0]?.content ?? "Error"}</span>
        </div>
      </div>
    );
  }
  return (
    <div className="chat-assistant-row">
      {(message.blocks ?? []).map((block, i) => {
        if (block.type === "text" && block.content) {
          return <ChatMarkdown key={i}>{block.content}</ChatMarkdown>;
        }
        if (block.type === "chart" && block.chart) {
          const chart = block.chart as {
            data: Record<string, unknown>[];
            layout?: Record<string, unknown>;
          };
          return (
            <div
              key={i}
              className="my-3 overflow-hidden rounded-[var(--radius-box)] border border-base-300/60"
            >
              <ChatPlotlyChart data={chart.data} layout={chart.layout ?? {}} />
            </div>
          );
        }
        if (block.type === "ui") {
          const ui = (block.ui as UiBlockPayload | null | undefined) ?? {
            fallback: block.content ?? "",
          };
          return <ChatUiBlock key={i} ui={ui} />;
        }
        return null;
      })}
      {!message.blocks?.length && message.omitted_content && (
        <p className="text-xs text-base-content/50">
          This answer only had tool steps or interactive content, which shared chats leave out.
        </p>
      )}
      {message.incomplete === "stopped" && (
        <div className="mt-2 inline-flex items-center gap-1.5 text-xs text-base-content/45">
          <Square className="h-3 w-3" aria-hidden="true" />
          Stopped
        </div>
      )}
      {message.incomplete === "interrupted" && (
        <div className="mt-2 inline-flex items-center gap-1.5 text-xs text-base-content/45">
          <CircleSlash className="h-3 w-3" aria-hidden="true" />
          Interrupted before it ended
        </div>
      )}
    </div>
  );
}

function SharedMessages({ messages }: { messages: AgentChatShareMessageSchema[] }) {
  return (
    <div className="space-y-7">
      {messages.map((message, i) =>
        message.role === "user" ? (
          <UserMessage
            key={i}
            message={{
              role: "user",
              content: message.blocks?.[0]?.content ?? "",
              attachedImage: message.figures_attached,
            }}
            canEdit={false}
            onEdit={noop}
          />
        ) : (
          <SharedAnswer key={i} message={message} />
        ),
      )}
    </div>
  );
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full overflow-y-auto bg-base-100">
      <div className="mx-auto w-full max-w-3xl px-4 pt-4 pb-10">
        <Link href="/chat" className="btn btn-ghost btn-sm mb-3">
          <ArrowLeft data-icon="inline-start" aria-hidden="true" />
          Agent
        </Link>
        {children}
      </div>
    </div>
  );
}

function Notice({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Frame>
      <h1 className="mb-3 text-xl font-medium">{title}</h1>
      <div role="alert" className="alert alert-error alert-soft">
        <span>{children}</span>
      </div>
    </Frame>
  );
}

/**
 * A chat snapshot shared with a project, read-only. It opens in the project the link names;
 * nothing here sends messages, branches, or reaches the owner's runtime workspace.
 */
export function SharedChatPageContent({ shareId }: { shareId: string }) {
  const linked = useLinkedProject();
  const projectId = linked.status === "ready" ? linked.projectId : null;
  const request = projectId ? projectRequest(projectId) : undefined;
  const toast = useToast();
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [revoked, setRevoked] = useState(false);
  const shareQuery = useGetAgentChatShare(shareId, {
    query: {
      queryKey: [...getGetAgentChatShareQueryKey(shareId), projectId],
      enabled: projectId !== null && !revoked,
      retry: false,
    },
    request,
  });
  const revoke = useRevokeAgentChatShare({ request });

  if (linked.status === "unavailable") {
    return (
      <Notice title="Shared chat">
        This chat is shared in project {linked.projectId}, which your account cannot open. Ask a
        project owner for access.
      </Notice>
    );
  }
  if (linked.status === "no_project") {
    return (
      <Notice title="Shared chat">
        Your account has no project, so this shared chat cannot be opened.
      </Notice>
    );
  }
  if (revoked) {
    return (
      <Frame>
        <EmptyState
          emoji="speech-balloon"
          title="Sharing stopped"
          description="Project members can no longer open this snapshot. The original chat is unchanged."
          action={
            <Link href="/chat" className="btn btn-sm">
              Back to Agent
            </Link>
          }
        />
      </Frame>
    );
  }
  if (linked.status === "pending" || shareQuery.isLoading) {
    return (
      <Frame>
        <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading shared chat">
          <div className="skeleton h-7 w-64" />
          <div className="skeleton h-4 w-48" />
          <div className="skeleton ml-auto h-10 w-2/3" />
          <div className="skeleton h-24 w-full" />
        </div>
      </Frame>
    );
  }
  const data = shareQuery.data?.data;
  if (shareQuery.isError || !data) {
    const missing = isAxiosError(shareQuery.error) && shareQuery.error.response?.status === 404;
    return (
      <Frame>
        {missing ? (
          <EmptyState
            emoji="speech-balloon"
            title="This shared chat is not available"
            description="Its owner may have stopped sharing it, or it is shared in another project. Switch to the project the link was shared in, or ask the owner for a new link."
          />
        ) : (
          <div role="alert" className="alert alert-error alert-soft">
            <span>
              {getApiErrorMessage(shareQuery.error, "This shared chat could not be loaded")}
            </span>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => void shareQuery.refetch()}
              disabled={shareQuery.isRefetching}
            >
              Retry
            </button>
          </div>
        )}
      </Frame>
    );
  }

  const handleRevoke = () => {
    revoke.mutate(
      { shareId },
      {
        onSuccess: () => {
          setConfirmRevoke(false);
          setRevoked(true);
          toast.success("Stopped sharing the chat");
        },
        onError: (error) => {
          setConfirmRevoke(false);
          toast.error(getApiErrorMessage(error, "Failed to stop sharing"));
        },
      },
    );
  };

  return (
    <Frame>
      <header className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-medium">{data.title}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-base-content/60">
            <VisibilityLabel visibility="project" />
            <span>by {data.owner_username}</span>
            <span title={formatDateTime(data.snapshot_at)}>
              Snapshot taken {formatRelativeTime(data.snapshot_at)}
            </span>
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-1">
          <CopyLinkButton />
          {data.can_revoke && (
            <button
              type="button"
              className="btn btn-ghost btn-sm text-error"
              onClick={() => setConfirmRevoke(true)}
            >
              <Trash2 data-icon="inline-start" aria-hidden="true" />
              Stop sharing
            </button>
          )}
        </div>
      </header>

      <div role="note" className="alert alert-info alert-soft mb-6 text-sm">
        <Info className="h-4 w-4" aria-hidden="true" />
        <span>
          Read-only snapshot. It does not update when the chat continues
          {data.is_owner ? "; update it from the chat's Share dialog" : ""}. Tool steps, workspace
          files and figures are not included.
        </span>
      </div>

      {data.messages.length === 0 ? (
        <EmptyState emoji="speech-balloon" title="No messages in this snapshot" />
      ) : (
        <SharedMessages messages={data.messages} />
      )}

      <ConfirmDialog
        open={confirmRevoke}
        title="Stop sharing this chat?"
        description={
          data.is_owner
            ? "Project members will no longer be able to open this snapshot. Your chat is not changed."
            : `Project members will no longer be able to open ${data.owner_username}'s snapshot. Their chat is not changed.`
        }
        confirmLabel="Stop sharing"
        destructive
        pending={revoke.isPending}
        onConfirm={handleRevoke}
        onOpenChange={setConfirmRevoke}
      />
    </Frame>
  );
}
