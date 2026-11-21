"use client";

import Link from "next/link";

import { Bot, ChevronRight, ExternalLink } from "lucide-react";

import type { ExecutionGroupItem, ExecutionResponseSummary } from "@/schemas";

import { sessionStatusLabel } from "@/components/features/agent-session/interventionLabels";
import { formatDateTime } from "@/lib/utils/datetime";

import {
  pluralize,
  sessionActivityLabel,
  sessionJourneyHref,
  sessionStatusBadgeClass,
} from "./agentSessionDisplay";
import { ExecutionListCard } from "./ExecutionListCard";

interface AgentSessionGroupRowProps {
  item: ExecutionGroupItem;
  projectId: string | null;
  isExpanded: boolean;
  onToggle: (sessionId: string) => void;
  selectedExecutionId: string | null;
  isPanelOpen: boolean;
  onOpenExecution: (execution: ExecutionResponseSummary) => void;
  registerCard: (executionId: string, element: HTMLDivElement | null) => void;
  hasDayFilter: boolean;
}

/**
 * One agent session in the Execution list: the session's own state, and the real executions
 * its actions dispatched. Expanding the row lists those executions with the same cards as the
 * rest of the list; the journey page shows every step, decision, and intervention.
 */
export function AgentSessionGroupRow({
  item,
  projectId,
  isExpanded,
  onToggle,
  selectedExecutionId,
  isPanelOpen,
  onOpenExecution,
  registerCard,
  hasDayFilter,
}: AgentSessionGroupRowProps) {
  const summary = item.agent_session;
  if (!summary) return null;
  const { counts } = summary;
  const children = item.children ?? [];
  const omitted = item.children_omitted ?? 0;
  const inFilter = item.children_in_filter ?? 0;
  const childrenId = `agent-session-children-${summary.session_id}`;
  const title = summary.skill_name || "Agent session";

  return (
    <div className="rounded-box border border-base-200 border-l-4 border-l-base-300 bg-base-100 shadow-sm">
      <div className="flex flex-col gap-2 p-3 sm:flex-row sm:items-start sm:justify-between sm:p-4">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-start gap-2 text-left"
          aria-expanded={isExpanded}
          aria-controls={childrenId}
          onClick={() => onToggle(summary.session_id)}
        >
          <ChevronRight
            className={`mt-0.5 h-4 w-4 shrink-0 text-base-content/60 transition-transform ${isExpanded ? "rotate-90" : ""}`}
            aria-hidden="true"
          />
          <span className="min-w-0">
            <span className="flex flex-wrap items-center gap-2">
              <Bot className="h-4 w-4 shrink-0 text-base-content/60" aria-hidden="true" />
              <span className="truncate text-sm font-medium">{title}</span>
              <span
                className={`badge badge-soft badge-sm ${sessionStatusBadgeClass(summary.status)}`}
              >
                {sessionStatusLabel(summary.status)}
              </span>
            </span>
            <span className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-sm text-base-content/60">
              <span>{formatDateTime(item.sort_at ?? summary.latest_activity_at)}</span>
              <span>@{summary.created_by}</span>
              <span>{sessionActivityLabel(summary)}</span>
            </span>
            <span className="mt-1 block text-xs text-base-content/60">
              {pluralize(counts.measurements, "execution")}
              {hasDayFilter && inFilter !== counts.measurements ? ` (${inFilter} on this day)` : ""}
              {counts.pending_dispatch > 0
                ? ` · ${counts.pending_dispatch} not dispatched yet`
                : ""}
              {counts.rejected_proposals > 0
                ? ` · ${pluralize(counts.rejected_proposals, "rejected proposal")}`
                : ""}
              {counts.decisions > 0 ? ` · ${pluralize(counts.decisions, "decision")}` : ""}
              {counts.open_interventions > 0
                ? ` · ${pluralize(counts.open_interventions, "open question")}`
                : ""}
              {` · ${counts.actions} of ${counts.max_actions} actions used`}
            </span>
          </span>
        </button>
        <Link
          href={sessionJourneyHref(summary.chip_id, summary.session_id, projectId)}
          className="btn btn-ghost btn-sm shrink-0"
        >
          <ExternalLink data-icon="inline-start" aria-hidden="true" />
          Open journey
        </Link>
      </div>
      {isExpanded && (
        <div id={childrenId} className="flex flex-col gap-2 border-t border-base-content/10 p-3">
          {omitted > 0 && (
            <p className="text-xs text-base-content/60">
              {pluralize(omitted, "earlier execution")} not listed here; the journey lists all of
              them
            </p>
          )}
          {children.length === 0 ? (
            <p className="text-sm text-base-content/60">
              No measurement has been dispatched yet
              {counts.rejected_proposals > 0 ? "; rejected proposals never reach hardware" : ""}
            </p>
          ) : (
            children.map((child) => (
              <ExecutionListCard
                key={child.execution.execution_id}
                execution={child.execution}
                isSelected={selectedExecutionId === child.execution.execution_id}
                isPanelOpen={isPanelOpen}
                onOpen={onOpenExecution}
                registerCard={registerCard}
                prefix={
                  <span className="font-mono text-xs text-base-content/60">
                    #{child.sequence}
                    {child.attempt > 1 ? ` · try ${child.attempt}` : ""}
                  </span>
                }
                footer={
                  hasDayFilter && !child.in_filter ? (
                    <p className="mt-1 text-xs text-base-content/60">Outside the selected day</p>
                  ) : null
                }
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}
