"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { ExternalLink, Loader2 } from "lucide-react";
import { useGetExecution } from "@/client/execution/execution";
import { useGetForumPost } from "@/client/forum/forum";
import { useGetTaskResult } from "@/client/task/task";
import { FigureStrip } from "@/components/features/chat/ChatFigures";
import { ExecutionProgress } from "@/components/features/chat/ExecutionProgress";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { ImagePreviewDialog } from "@/components/ui/ImagePreviewDialog";
import { chatLinkPagePath, classifyChatLink, type ChatLink } from "@/lib/chatLinks";
import { figureUrl } from "@/components/features/chat/ChatFigures";

type PreviewLink = Extract<
  ChatLink,
  { kind: "task-result" | "execution" | "forum-post" | "figure" }
>;

interface ChatLinkPreviewValue {
  /** Open a preview for the link; false when the link is not previewable. */
  preview: (href: string) => boolean;
}

const ChatLinkPreviewContext = createContext<ChatLinkPreviewValue | null>(null);

/** The preview hook, or null outside a provider (links then behave normally). */
export function useChatLinkPreview(): ChatLinkPreviewValue | null {
  return useContext(ChatLinkPreviewContext);
}

/** Previewable links open in a dialog over the chat; the rest are left to the browser. */
export function ChatLinkPreviewProvider({ children }: { children: ReactNode }) {
  const [link, setLink] = useState<PreviewLink | null>(null);

  const preview = useCallback((href: string) => {
    const classified = classifyChatLink(href);
    if (classified.kind === "internal" || classified.kind === "external") return false;
    setLink(classified);
    return true;
  }, []);

  const value = useMemo(() => ({ preview }), [preview]);

  return (
    <ChatLinkPreviewContext.Provider value={value}>
      {children}
      {link?.kind === "figure" ? (
        <ImagePreviewDialog src={figureUrl(link.path)} onClose={() => setLink(null)} />
      ) : (
        <ChatLinkPreviewDialog link={link} onClose={() => setLink(null)} />
      )}
    </ChatLinkPreviewContext.Provider>
  );
}

function OpenPageLink({ href }: { href: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="btn btn-sm btn-ghost gap-1.5 rounded-full"
    >
      <ExternalLink className="w-3.5 h-3.5" />
      Open page
    </a>
  );
}

function Loading({ what }: { what: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-base-content/50">
      <Loader2 className="w-4 h-4 animate-spin" /> Loading {what}…
    </div>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number")
    return Number.isInteger(value) ? String(value) : value.toPrecision(5);
  if (typeof value === "object") {
    const record = value as { value?: unknown; unit?: unknown };
    if ("value" in record) {
      const unit = typeof record.unit === "string" && record.unit ? ` ${record.unit}` : "";
      return `${formatValue(record.value)}${unit}`;
    }
    return JSON.stringify(value);
  }
  return String(value);
}

const PARAMETER_LIMIT = 8;

function TaskResultPreview({ taskId }: { taskId: string }) {
  const query = useGetTaskResult(taskId, { query: { staleTime: 30_000 } });
  const result = query.data?.data;
  if (query.isError) return <p className="text-sm text-error">Could not load this task result.</p>;
  if (!result) return <Loading what="task result" />;

  const params = Object.entries(result.output_parameters ?? {}).slice(0, PARAMETER_LIMIT);
  return (
    <div className="space-y-3">
      <DialogTitle className="text-base">
        {result.task_name}
        <span className="ml-2 font-normal text-base-content/50">· {result.qid}</span>
      </DialogTitle>
      <DialogDescription className="text-xs text-base-content/50">
        {result.status}
        {result.chip_id ? ` · ${result.chip_id}` : ""} · execution {result.execution_id}
        {result.message ? ` · ${result.message}` : ""}
      </DialogDescription>
      {result.figure_path.length > 0 && <FigureStrip paths={result.figure_path} />}
      {params.length > 0 && (
        <dl className="grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
          {params.map(([name, value]) => (
            <div key={name} className="contents">
              <dt className="font-mono text-base-content/55">{name}</dt>
              <dd className="m-0 font-mono">{formatValue(value)}</dd>
            </div>
          ))}
        </dl>
      )}
      <div className="flex justify-end">
        <OpenPageLink href={`/task-results/${encodeURIComponent(result.task_id)}`} />
      </div>
    </div>
  );
}

function ExecutionPreview({ executionId, chipId }: { executionId: string; chipId: string | null }) {
  const query = useGetExecution(executionId, { query: { staleTime: 5_000 } });
  const execution = query.data?.data;
  const resolvedChip = chipId ?? execution?.chip_id ?? null;
  return (
    <div className="space-y-3">
      <DialogTitle className="text-base">
        {execution?.name ?? `Execution ${executionId}`}
      </DialogTitle>
      <DialogDescription className="sr-only">Execution status and tasks</DialogDescription>
      <ExecutionProgress executionId={executionId} />
      <div className="flex justify-end">
        <OpenPageLink
          href={chatLinkPagePath({
            kind: "execution",
            executionId,
            chipId: resolvedChip,
            href: "",
          })!}
        />
      </div>
    </div>
  );
}

const CONTENT_LIMIT = 600;

function ForumPostPreview({ postId }: { postId: string }) {
  const query = useGetForumPost(postId, { query: { staleTime: 30_000 } });
  const post = query.data?.data;
  if (query.isError) return <p className="text-sm text-error">Could not load this post.</p>;
  if (!post) return <Loading what="post" />;
  const content =
    post.content.length > CONTENT_LIMIT ? `${post.content.slice(0, CONTENT_LIMIT)}…` : post.content;
  return (
    <div className="space-y-3">
      <DialogTitle className="text-base">{post.title || "Forum post"}</DialogTitle>
      <DialogDescription className="text-xs text-base-content/50">
        {post.username}
        {post.category ? ` · ${post.category}` : ""}
        {post.reply_count ? ` · ${post.reply_count} replies` : ""}
      </DialogDescription>
      <p className="whitespace-pre-wrap text-sm text-base-content/80">{content}</p>
      <div className="flex justify-end">
        <OpenPageLink href={`/forum/${encodeURIComponent(post.id)}`} />
      </div>
    </div>
  );
}

function ChatLinkPreviewDialog({
  link,
  onClose,
}: {
  link: Exclude<PreviewLink, { kind: "figure" }> | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={link !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl p-5" data-testid="chat-link-preview">
        {link?.kind === "task-result" && <TaskResultPreview taskId={link.taskId} />}
        {link?.kind === "execution" && (
          <ExecutionPreview executionId={link.executionId} chipId={link.chipId} />
        )}
        {link?.kind === "forum-post" && <ForumPostPreview postId={link.postId} />}
      </DialogContent>
    </Dialog>
  );
}
