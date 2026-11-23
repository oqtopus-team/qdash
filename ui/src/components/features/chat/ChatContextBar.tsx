"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { ExternalLink, FlaskConical, LocateFixed, PanelTop } from "lucide-react";
import type { PageContextSummary } from "@/contexts/ChatDockContext";
import type { InvestigationTarget, TaskChatContext } from "@/types/copilotChat";

/** The execution page for an execution; the id-only route forwards to the chip's page. */
function executionHref(executionId: string, chipId?: string | null): string {
  return chipId
    ? `/execution/${encodeURIComponent(chipId)}/${encodeURIComponent(executionId)}`
    : `/executions/${encodeURIComponent(executionId)}`;
}

function ContextItem({
  icon,
  label,
  title,
  children,
  action,
}: {
  icon: ReactNode;
  /** Names what the value is, e.g. "Result"; part of the item's visible text. */
  label: string;
  /** The full details, for a value that may be truncated. */
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <li
      className="badge badge-sm badge-ghost h-auto min-h-6 max-w-full gap-1 py-0.5 font-normal"
      title={title}
    >
      <span aria-hidden="true" className="shrink-0 text-base-content/50">
        {icon}
      </span>
      <span className="shrink-0 text-base-content/55">{label}</span>
      <span className="min-w-0 truncate text-base-content/80">{children}</span>
      {action}
    </li>
  );
}

function ExecutionLink({ executionId, chipId }: { executionId: string; chipId?: string | null }) {
  return (
    <Link
      href={executionHref(executionId, chipId)}
      className="shrink-0 text-base-content/50 hover:text-base-content"
      aria-label={`Open execution ${executionId}`}
    >
      <ExternalLink className="w-3 h-3" aria-hidden="true" />
    </Link>
  );
}

function joinKnown(parts: (string | null | undefined)[]): string {
  return parts.filter((part): part is string => Boolean(part)).join(" · ");
}

interface ChatContextBarProps {
  /** The task result saved with this chat; every turn names it. */
  context: TaskChatContext | null;
  /** The failure saved with this chat; its first turn opens with the failure's logs. */
  investigation?: InvestigationTarget | null;
  /** The page a turn sent now describes; null on the chat page. */
  page: PageContextSummary | null;
}

/**
 * What the next message carries besides its text: the result or failure saved with this
 * chat, and the page the user has open. Shows only what is known; renders nothing for a
 * general chat on the chat page.
 */
export function ChatContextBar({ context, investigation, page }: ChatContextBarProps) {
  if (!context && !investigation && !page) return null;

  return (
    <ul aria-label="Agent context" className="flex flex-wrap items-center gap-1.5 px-1 pb-2">
      {context && (
        <ContextItem
          icon={<FlaskConical className="w-3 h-3" />}
          label="Result"
          title={`Saved with this chat and sent with every message: ${joinKnown([
            context.taskName,
            context.qid,
            `chip ${context.chipId}`,
            `execution ${context.executionId}`,
          ])}`}
          action={<ExecutionLink executionId={context.executionId} chipId={context.chipId} />}
        >
          {joinKnown([context.taskName, context.qid, context.chipId])}
        </ContextItem>
      )}
      {investigation && (
        <ContextItem
          icon={<LocateFixed className="w-3 h-3" />}
          label="Investigating"
          title={`Saved with this chat; its first message carries the failure's logs: ${joinKnown([
            investigation.taskName,
            investigation.qid,
            investigation.chipId ? `chip ${investigation.chipId}` : null,
            `execution ${investigation.executionId}`,
          ])}`}
          action={
            <ExecutionLink executionId={investigation.executionId} chipId={investigation.chipId} />
          }
        >
          {investigation.taskName || investigation.qid
            ? joinKnown([investigation.taskName, investigation.qid, investigation.chipId])
            : `Execution ${investigation.executionId}`}
        </ContextItem>
      )}
      {page && (
        <ContextItem
          icon={<PanelTop className="w-3 h-3" />}
          label="Page"
          title={`The page you have open, sent with each message: ${
            page.withEditorCode ? `${page.title} (${page.path})` : page.path
          }`}
        >
          {page.withEditorCode
            ? `${page.path} · ${page.editorKind === "dashboard" ? "with dashboard draft" : "with editor code"}`
            : page.path}
        </ContextItem>
      )}
    </ul>
  );
}
