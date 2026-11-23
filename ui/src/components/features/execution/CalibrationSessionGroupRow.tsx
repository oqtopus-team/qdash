"use client";

import Link from "next/link";

import { ChevronRight, ExternalLink, Target } from "lucide-react";

import type {
  CalibrationGroupPipelineRun,
  ExecutionGroupItem,
  ExecutionResponseSummary,
} from "@/schemas";

import {
  calibrationSessionHref,
  dispatchStatusStyle,
  runDisplayName,
  runKindLabel,
  runTriggerLabel,
} from "@/lib/chatCalibrationSession";
import { formatDateTime } from "@/lib/utils/datetime";

import { pluralize } from "./agentSessionDisplay";
import { AgentSessionGroupRow } from "./AgentSessionGroupRow";
import { ExecutionListCard } from "./ExecutionListCard";

interface CalibrationSessionGroupRowProps {
  item: ExecutionGroupItem;
  projectId: string | null;
  expanded: ReadonlySet<string>;
  onToggle: (key: string) => void;
  selectedExecutionId: string | null;
  isPanelOpen: boolean;
  onOpenExecution: (execution: ExecutionResponseSummary) => void;
  registerCard: (executionId: string, element: HTMLDivElement | null) => void;
  hasDayFilter: boolean;
}

/** The expansion key of a calibration session row; agent session rows use their own id. */
export function calibrationRowKey(calibrationSessionId: string): string {
  return `calibration:${calibrationSessionId}`;
}

/** The executions a calibration session row shows when expanded, in display order. */
export function calibrationRowExecutions(
  item: ExecutionGroupItem,
  expanded: ReadonlySet<string>,
): ExecutionResponseSummary[] {
  const runs = (item.pipeline_runs ?? []).flatMap((run) => run.executions ?? []);
  const agents = (item.nested_agent_sessions ?? []).flatMap((group) =>
    expanded.has(group.agent_session.session_id)
      ? (group.children ?? []).map((child) => child.execution)
      : [],
  );
  return [...runs, ...agents];
}

function timeRange(first: string, latest: string): string {
  const start = formatDateTime(first);
  const end = formatDateTime(latest);
  return start === end ? start : `${start} – ${end}`;
}

function PipelineRunGroup({
  run,
  selectedExecutionId,
  isPanelOpen,
  onOpenExecution,
  registerCard,
  hasDayFilter,
}: {
  run: CalibrationGroupPipelineRun;
  selectedExecutionId: string | null;
  isPanelOpen: boolean;
  onOpenExecution: (execution: ExecutionResponseSummary) => void;
  registerCard: (executionId: string, element: HTMLDivElement | null) => void;
  hasDayFilter: boolean;
}) {
  const dispatch = dispatchStatusStyle(run.dispatch_status);
  const executions = run.executions ?? [];
  const omitted = (run.executions_total ?? 0) - executions.length;
  const trigger = runTriggerLabel(run.trigger);
  return (
    <li className="flex flex-col gap-2" data-testid="calibration-row-run">
      <div className="flex flex-wrap items-center gap-2 text-xs text-base-content/60">
        <span className="text-sm font-medium text-base-content">{runDisplayName(run)}</span>
        <span className="badge badge-outline badge-sm">{runKindLabel(run.run_kind)}</span>
        {trigger ? <span className="badge badge-ghost badge-sm">{trigger}</span> : null}
        <span className={`badge badge-soft badge-sm ${dispatch.badge}`}>{dispatch.label}</span>
        {run.decision_id ? (
          <span className="badge badge-ghost badge-sm" title="The decision this run carries out">
            Carries out decision {run.decision_id.slice(0, 8)}
          </span>
        ) : null}
        <span>
          {run.requested_by} · {formatDateTime(run.requested_at)}
        </span>
        {hasDayFilter && run.executions_in_filter !== run.executions_total ? (
          <span>({run.executions_in_filter} on this day)</span>
        ) : null}
      </div>
      {executions.length === 0 ? (
        <p className="text-xs text-base-content/60">
          {run.dispatch_status === "rejected"
            ? "Refused before it started; nothing ran."
            : run.dispatch_status === "unknown"
              ? "QDash could not confirm whether this run started; check before starting it again."
              : "No step execution recorded yet."}
        </p>
      ) : (
        <div className="flex flex-col gap-2 border-l border-base-content/10 pl-3">
          {executions.map((execution) => (
            <ExecutionListCard
              key={execution.execution_id}
              execution={execution}
              isSelected={selectedExecutionId === execution.execution_id}
              isPanelOpen={isPanelOpen}
              onOpen={onOpenExecution}
              registerCard={registerCard}
            />
          ))}
          {omitted > 0 ? (
            <p className="text-xs text-base-content/60">
              {pluralize(omitted, "earlier step execution")} not listed here
            </p>
          ) : null}
        </div>
      )}
    </li>
  );
}

/**
 * One calibration session in the Execution list: the objective and what its records hold, and,
 * expanded, every run (a workflow, pipeline, or task launch) with its step executions and every
 * admitted agent session with the executions it dispatched. A run started without a session is
 * shown in the automatic session QDash created for it, if it got one; a run in no session is an
 * ordinary execution row. Membership comes from the server's records only.
 */
export function CalibrationSessionGroupRow({
  item,
  projectId,
  expanded,
  onToggle,
  selectedExecutionId,
  isPanelOpen,
  onOpenExecution,
  registerCard,
  hasDayFilter,
}: CalibrationSessionGroupRowProps) {
  const summary = item.calibration_session;
  if (!summary) return null;
  const { counts } = summary;
  const unknownDispatch = counts.unknown_dispatch ?? 0;
  const decisions = counts.decisions ?? 0;
  const key = calibrationRowKey(summary.calibration_session_id);
  const isExpanded = expanded.has(key);
  const childrenId = `calibration-session-children-${summary.calibration_session_id}`;
  const runs = item.pipeline_runs ?? [];
  const agents = item.nested_agent_sessions ?? [];
  const recommendation = summary.recommendation;
  const isOpen = summary.status === "open";
  const isAutomatic = summary.origin === "automatic";

  return (
    <div
      data-testid="calibration-session-card"
      className="rounded-box border border-base-200 border-l-4 border-l-primary/60 bg-base-100 shadow-sm"
    >
      <div className="flex flex-col gap-2 p-3 sm:flex-row sm:items-start sm:justify-between sm:p-4">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-start gap-2 text-left"
          aria-expanded={isExpanded}
          aria-controls={childrenId}
          onClick={() => onToggle(key)}
        >
          <ChevronRight
            className={`mt-0.5 h-4 w-4 shrink-0 text-base-content/60 transition-transform ${isExpanded ? "rotate-90" : ""}`}
            aria-hidden="true"
          />
          <span className="min-w-0">
            <span className="flex flex-wrap items-center gap-2">
              <Target className="h-4 w-4 shrink-0 text-base-content/60" aria-hidden="true" />
              <span className="text-sm font-medium wrap-anywhere">{summary.objective}</span>
              <span className={`badge badge-soft badge-sm ${isOpen ? "badge-info" : ""}`}>
                {isOpen ? "Open" : "Closed"}
              </span>
              {isAutomatic ? (
                <span
                  className="badge badge-ghost badge-sm"
                  title="QDash created this session for a run started without one"
                >
                  Automatic
                </span>
              ) : null}
              {recommendation ? (
                <span
                  className="badge badge-outline badge-sm"
                  title="A recorded conclusion, not a status"
                >
                  {recommendation.outcome === "inconclusive"
                    ? "Concluded: inconclusive"
                    : `Recommends ${recommendation.recommended_candidate_id}`}
                </span>
              ) : null}
            </span>
            <span className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-sm text-base-content/60">
              <span>{timeRange(summary.first_activity_at, summary.latest_activity_at)}</span>
              <span>{summary.created_by}</span>
              {summary.targets && summary.targets.length > 0 ? (
                <span>Targets {summary.targets.join(", ")}</span>
              ) : (
                <span>No target recorded</span>
              )}
            </span>
            <span className="mt-1 block text-xs text-base-content/60">
              {pluralize(counts.pipeline_runs, "run")}
              {counts.agent_sessions > 0
                ? ` · ${pluralize(counts.agent_sessions, "agent session")}`
                : ""}
              {` · ${pluralize(counts.executions, "execution")}`}
              {hasDayFilter && counts.executions_in_filter !== counts.executions
                ? ` (${counts.executions_in_filter} on this day)`
                : ""}
              {counts.running > 0 ? ` · ${counts.running} running` : ""}
              {counts.failed > 0 ? ` · ${counts.failed} failed` : ""}
              {unknownDispatch > 0
                ? ` · ${pluralize(unknownDispatch, "run")} with unknown launch`
                : ""}
              {decisions > 0 ? ` · ${pluralize(decisions, "decision")}` : ""}
            </span>
          </span>
        </button>
        <div className="flex shrink-0 flex-wrap gap-1">
          <Link
            href={calibrationSessionHref(summary.calibration_session_id, projectId)}
            className="btn btn-ghost btn-sm"
          >
            <ExternalLink data-icon="inline-start" aria-hidden="true" />
            Open calibration session
          </Link>
        </div>
      </div>
      {isExpanded && (
        <div id={childrenId} className="flex flex-col gap-3 border-t border-base-content/10 p-3">
          {runs.length === 0 && agents.length === 0 ? (
            <p className="text-sm text-base-content/60">Nothing has been started in it yet.</p>
          ) : null}
          {(item.pipeline_runs_omitted ?? 0) > 0 ? (
            <p className="text-xs text-base-content/60">
              {pluralize(item.pipeline_runs_omitted ?? 0, "earlier run")} not listed here; the
              calibration session lists all of them
            </p>
          ) : null}
          {runs.length > 0 ? (
            <ul className="flex flex-col gap-3" aria-label="Runs">
              {runs.map((run) => (
                <PipelineRunGroup
                  key={run.run_id}
                  run={run}
                  selectedExecutionId={selectedExecutionId}
                  isPanelOpen={isPanelOpen}
                  onOpenExecution={onOpenExecution}
                  registerCard={registerCard}
                  hasDayFilter={hasDayFilter}
                />
              ))}
            </ul>
          ) : null}
          {agents.map((group) => (
            <AgentSessionGroupRow
              key={group.agent_session.session_id}
              item={{
                kind: "agent_session",
                agent_session: group.agent_session,
                children: group.children,
                children_total: group.children_total,
                children_in_filter: group.children_in_filter,
                children_omitted: group.children_omitted,
              }}
              projectId={projectId}
              isExpanded={expanded.has(group.agent_session.session_id)}
              onToggle={onToggle}
              selectedExecutionId={selectedExecutionId}
              isPanelOpen={isPanelOpen}
              onOpenExecution={onOpenExecution}
              registerCard={registerCard}
              hasDayFilter={hasDayFilter}
              hideCalibrationLink
            />
          ))}
        </div>
      )}
    </div>
  );
}
