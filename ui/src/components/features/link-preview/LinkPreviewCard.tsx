"use client";

import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { useGetExecution } from "@/client/execution/execution";
import { useGetForumPost } from "@/client/forum/forum";
import { useGetTaskResult } from "@/client/task/task";
import { figureLabel, figureUrl } from "@/components/features/chat/ChatFigures";
import type { LinkDescription } from "@/lib/linkPreview";
import { formatDateTimeCompact } from "@/lib/utils/datetime";

/** A parameter value as text: numbers to five significant digits, `{value, unit}` with its unit. */
export function formatValue(value: unknown): string {
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

// The record queries share their keys and stale times with the chat's click-to-open dialog,
// so opening the dialog after hovering reuses the fetched record.
const TASK_RESULT_STALE_MS = 30_000;
const EXECUTION_STALE_MS = 5_000;
const FORUM_POST_STALE_MS = 30_000;

const CARD_PARAMETER_LIMIT = 3;
const CARD_SNIPPET_LIMIT = 180;

function CardFrame({
  kind,
  title,
  meta,
  children,
}: {
  kind: string;
  title: ReactNode;
  meta?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <p className="text-xs text-base-content/50">{kind}</p>
      <p className="break-words text-sm font-medium">{title}</p>
      {meta && (
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-base-content/60">
          {meta}
        </div>
      )}
      {children}
    </div>
  );
}

function CardLoading({ kind, what }: { kind: string; what: string }) {
  return (
    <CardFrame
      kind={kind}
      title={
        <span className="flex items-center gap-2 font-normal text-base-content/50">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading {what}…
        </span>
      }
    />
  );
}

function CardError({ kind, what }: { kind: string; what: string }) {
  return (
    <CardFrame kind={kind} title={<span className="text-error">Could not load {what}.</span>} />
  );
}

function statusBadgeClass(status: string): string {
  if (status === "completed" || status === "success") return "badge-success";
  if (status === "failed") return "badge-error";
  if (status === "running") return "badge-info";
  if (status === "scheduled" || status === "pending") return "badge-warning";
  return "badge-ghost";
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`badge badge-sm ${statusBadgeClass(status)}`}>{status}</span>;
}

function TaskResultCard({ taskId }: { taskId: string }) {
  const query = useGetTaskResult(taskId, { query: { staleTime: TASK_RESULT_STALE_MS } });
  const result = query.data?.data;
  if (query.isError) return <CardError kind="Task result" what="this task result" />;
  if (!result) return <CardLoading kind="Task result" what="task result" />;

  const params = Object.entries(result.output_parameters ?? {}).slice(0, CARD_PARAMETER_LIMIT);
  const figures = result.figure_path.length;
  return (
    <CardFrame
      kind="Task result"
      title={
        <>
          {result.task_name}
          <span className="ml-1.5 font-normal text-base-content/50">· {result.qid}</span>
        </>
      }
      meta={
        <>
          <StatusBadge status={result.status} />
          {result.chip_id && <span>{result.chip_id}</span>}
          {figures > 0 && <span>· {figures === 1 ? "1 figure" : `${figures} figures`}</span>}
        </>
      }
    >
      {params.length > 0 && (
        <dl className="grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-xs">
          {params.map(([name, value]) => (
            <div key={name} className="contents">
              <dt className="truncate font-mono text-base-content/55">{name}</dt>
              <dd className="m-0 truncate font-mono">{formatValue(value)}</dd>
            </div>
          ))}
        </dl>
      )}
    </CardFrame>
  );
}

function ExecutionCard({ executionId, chipId }: { executionId: string; chipId: string | null }) {
  const query = useGetExecution(executionId, { query: { staleTime: EXECUTION_STALE_MS } });
  const execution = query.data?.data;
  if (query.isError) return <CardError kind="Execution" what="this execution" />;
  if (!execution) return <CardLoading kind="Execution" what="execution" />;

  const chip = chipId ?? execution.chip_id;
  const tasks = execution.task?.length ?? 0;
  return (
    <CardFrame
      kind="Execution"
      title={execution.name || executionId}
      meta={
        <>
          <StatusBadge status={execution.status} />
          {chip && <span>{chip}</span>}
          {execution.start_at && <span>· {formatDateTimeCompact(execution.start_at)}</span>}
          {tasks > 0 && <span>· {tasks === 1 ? "1 task" : `${tasks} tasks`}</span>}
        </>
      }
    >
      <p className="truncate font-mono text-xs text-base-content/50">{executionId}</p>
    </CardFrame>
  );
}

function ForumPostCard({ postId }: { postId: string }) {
  const query = useGetForumPost(postId, { query: { staleTime: FORUM_POST_STALE_MS } });
  const post = query.data?.data;
  if (query.isError) return <CardError kind="Forum post" what="this post" />;
  if (!post) return <CardLoading kind="Forum post" what="post" />;

  const snippet =
    post.content.length > CARD_SNIPPET_LIMIT
      ? `${post.content.slice(0, CARD_SNIPPET_LIMIT)}…`
      : post.content;
  return (
    <CardFrame
      kind="Forum post"
      title={post.title || "Forum post"}
      meta={
        <>
          <span>{post.username}</span>
          {post.category && <span>· {post.category}</span>}
          {post.reply_count ? (
            <span>· {post.reply_count === 1 ? "1 reply" : `${post.reply_count} replies`}</span>
          ) : null}
        </>
      }
    >
      {snippet && (
        <p className="line-clamp-3 whitespace-pre-wrap text-xs text-base-content/70">{snippet}</p>
      )}
    </CardFrame>
  );
}

function FigureCard({ path }: { path: string }) {
  const label = figureLabel(path);
  return (
    <CardFrame kind="Figure" title={label}>
      <div className="overflow-hidden rounded-[var(--radius-field)] border border-base-300 bg-base-200">
        {/* eslint-disable-next-line @next/next/no-img-element -- API-served calibration figure */}
        <img
          src={figureUrl(path)}
          alt={label}
          loading="lazy"
          decoding="async"
          className="mx-auto max-h-44 w-full object-contain"
        />
      </div>
    </CardFrame>
  );
}

function NewTabNote({ newTab }: { newTab: boolean }) {
  return newTab ? <p className="text-xs text-base-content/50">Opens in a new tab</p> : null;
}

function UrlLine({ children }: { children: ReactNode }) {
  return (
    <p className="line-clamp-2 break-all font-mono text-xs text-base-content/60">{children}</p>
  );
}

type DestinationLink = Exclude<LinkDescription, { kind: RecordKind }>;
type RecordKind = "task-result" | "execution" | "forum-post" | "figure";

/** Where a link goes, from its URL alone: nothing is fetched and nothing is opened. */
function DestinationCard({ link }: { link: DestinationLink }) {
  switch (link.kind) {
    case "fragment":
      return (
        <CardFrame kind="Section on this page" title={link.label || `#${link.id}`}>
          {link.label && <UrlLine>#{link.id}</UrlLine>}
        </CardFrame>
      );
    case "page":
      return (
        <CardFrame
          kind="QDash page"
          title={link.section ?? <span className="font-mono">{link.path}</span>}
        >
          {link.section && <UrlLine>{link.path}</UrlLine>}
          <NewTabNote newTab={link.newTab} />
        </CardFrame>
      );
    case "api":
      return (
        <CardFrame kind="QDash API" title={<span className="font-mono">{link.path}</span>}>
          <NewTabNote newTab={link.newTab} />
        </CardFrame>
      );
    case "download":
      return (
        <CardFrame kind="Download" title={link.filename}>
          <UrlLine>{link.href}</UrlLine>
          <p className="text-xs text-base-content/50">Saves a file</p>
        </CardFrame>
      );
    case "email":
      return (
        <CardFrame kind="Email" title={link.address || link.href}>
          <p className="text-xs text-base-content/50">Opens your email app</p>
        </CardFrame>
      );
    case "phone":
      return (
        <CardFrame kind="Phone" title={link.number || link.href}>
          <p className="text-xs text-base-content/50">Opens your phone app</p>
        </CardFrame>
      );
    case "external":
      return (
        <CardFrame kind="External link" title={link.host || link.href}>
          <UrlLine>{link.href}</UrlLine>
          <NewTabNote newTab={link.newTab} />
        </CardFrame>
      );
    case "other":
      return (
        <CardFrame
          kind={`${link.scheme}: link`}
          title={<span className="font-mono">{link.href}</span>}
        >
          <p className="text-xs text-base-content/50">Opens in another app</p>
        </CardFrame>
      );
  }
}

/**
 * The hover card body for a link. Record cards fetch only when they mount, which is when
 * the card opens; other links describe their destination without a request.
 */
export function LinkPreviewCard({ link }: { link: LinkDescription }) {
  switch (link.kind) {
    case "task-result":
      return <TaskResultCard taskId={link.taskId} />;
    case "execution":
      return <ExecutionCard executionId={link.executionId} chipId={link.chipId} />;
    case "forum-post":
      return <ForumPostCard postId={link.postId} />;
    case "figure":
      return <FigureCard path={link.path} />;
    default:
      return <DestinationCard link={link} />;
  }
}
